"""Game metadata extraction helpers for GUI imports.

The readers mirror the Spectrum client import flow: package/game files may
carry a cover, title ID, content ID, version, region, size, and APR-EMU marker.
Extraction is best-effort; malformed or unsupported files return fallbacks
instead of raising into the GUI.
"""

from __future__ import annotations

import contextlib
import json
import re
import struct
from dataclasses import dataclass
from pathlib import Path
from typing import BinaryIO

from .exfat import ExfatEntry, ExfatReader
from .pfs import (
    inspect_pfs_image,
    iter_inode_logical_blocks,
    open_inner_file_view,
)

_DASH = "-"
_MAX_PARAM_SIZE = 4 * 1024 * 1024
_MAX_ICON_SIZE = 10 * 1024 * 1024
_PKG_ENTRY_SIZE = 0x20
_PKG_ENTRY_ID_PARAM_SFO = 0x1000
_PKG_ENTRY_ID_ICON0_PNG = 0x1200
_FFPKG_MAGIC = b"\x19\x01\x54\x19"
_FFPKG_MAGIC_OFFSET = 0xFFEC
_FFPKG_DIR_OFFSET = 0x38000
_FFPKG_SCAN_LIMIT = 1_048_576
_FFPKG_APR_SCAN_LIMIT = 8 * 1024 * 1024
_TITLE_ID_PATTERN = re.compile(
    r"(PPSA|CUSA|PUSA|PCSE|PCSB|PCAS|PCJS|BCUS|BCES|BLAS|BLJM|BCAS|BCJS|NPUB|NPEB|NPJB|NPAS|SLES|SLPS)\d+",
    re.IGNORECASE,
)


@dataclass
class GameMetadata:
    """Metadata shown by the GUI when a file is imported."""

    file_path: Path
    file_name: str
    file_size: int = 0
    game_title: str = ""
    content_id: str = _DASH
    title_id: str = _DASH
    package_type: str = _DASH
    version: str = ""
    region: str = ""
    icon_bytes: bytes | None = None
    has_apr_emu: bool = False
    error: str = ""

    @property
    def size_display(self) -> str:
        """Human-friendly file size."""
        return format_bytes(self.file_size)

    @property
    def apr_emu_display(self) -> str:
        """Human-friendly APR-EMU state."""
        return "APR-EMU" if self.has_apr_emu else "No"


def read_game_metadata(file_path: str | Path) -> GameMetadata:
    """Read game metadata from a supported package, image, or source folder.

    Args:
        file_path: File or folder selected by the user.

    Returns:
        Best-effort metadata for the GUI preview.
    """
    path = Path(file_path).expanduser()
    meta = _base_metadata(path)
    if not path.exists():
        meta.error = f"Path not found: {path}"
        return meta
    if path.is_dir():
        return _read_folder_metadata(path, meta)

    suffix = path.suffix.lower()
    try:
        if suffix == ".pkg":
            return _read_pkg_metadata(path, meta)
        if suffix == ".exfat":
            return _read_exfat_metadata(path, meta)
        if suffix == ".ffpkg":
            return _read_ffpkg_metadata(path, meta)
        if suffix in {".ffpfs", ".ffpfsc"}:
            return _read_pfs_metadata(path, meta)
        meta.package_type = suffix.lstrip(".").upper() or _DASH
    except Exception as exc:
        meta.error = str(exc)
    return meta


def format_bytes(size: int) -> str:
    """Return Spectrum-style byte formatting."""
    if size <= 0:
        return _DASH
    value = float(size)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if value < 1024.0 or unit == "TB":
            if unit == "B":
                return f"{int(value)} B"
            if unit == "KB":
                return f"{value:.0f} KB"
            if unit == "MB":
                return f"{value:.1f} MB"
            return f"{value:.2f} {unit}"
        value /= 1024.0
    return f"{value:.2f} PB"


def detect_region_from_content_id(content_id: str) -> str:
    """Detect the likely PSN region from a Content ID prefix."""
    if not content_id or len(content_id) < 2 or content_id == _DASH:
        return ""
    prefix = content_id[:2].upper()
    if prefix == "UP":
        return "USA"
    if prefix == "EP":
        return "EUR"
    if prefix == "JP":
        return "JPN"
    if prefix in {"HP", "AP"}:
        return "ASIA"
    if prefix == "KP":
        return "KOR"
    return ""


def _base_metadata(path: Path) -> GameMetadata:
    size = _path_size(path)
    title_id = _fallback_title_id(path)
    return GameMetadata(
        file_path=path,
        file_name=path.name,
        file_size=size,
        content_id=title_id if title_id != path.stem else _DASH,
        title_id=title_id,
    )


def _path_size(path: Path) -> int:
    if path.is_dir():
        total = 0
        for child in path.rglob("*"):
            if child.is_file():
                with contextlib.suppress(OSError):
                    total += child.stat().st_size
        return total
    with contextlib.suppress(OSError):
        return path.stat().st_size
    return 0


def _fallback_title_id(path: Path) -> str:
    match = _TITLE_ID_PATTERN.search(path.stem)
    return match.group(0).upper() if match else path.stem


def _read_folder_metadata(path: Path, meta: GameMetadata) -> GameMetadata:
    meta.package_type = "FOLDER"
    _fill_from_source_folder(path, meta)
    return meta


def _read_pkg_metadata(path: Path, meta: GameMetadata) -> GameMetadata:
    meta.package_type = "PKG"
    with path.open("rb") as fh:
        magic = _read_at(fh, 0, 4)
        if magic != b"\x7fCNT":
            meta.package_type = "UNKNOWN"
            return meta

        content_id = _read_at(fh, 0x40, 48).decode("ascii", errors="ignore").rstrip("\0").strip()
        if content_id:
            meta.content_id = content_id
            meta.title_id = _title_id_from_content_id(content_id) or meta.title_id
            meta.region = detect_region_from_content_id(content_id)

        entry_count = _read_u32be(fh, 0x10)
        entry_table_offset = _read_u32be(fh, 0x18)
        flags = _read_u32be(fh, 0x04)
        if entry_count == 0 or entry_count > 4096 or entry_table_offset == 0:
            meta.package_type = _pkg_type_from_flags(flags)
            return meta

        sfo_offset: int | None = None
        sfo_size: int | None = None
        icon_offset: int | None = None
        icon_size: int | None = None
        for index in range(entry_count):
            entry_base = entry_table_offset + index * _PKG_ENTRY_SIZE
            entry_id = _read_u32be(fh, entry_base)
            data_offset = _read_u32be(fh, entry_base + 0x10)
            data_size = _read_u32be(fh, entry_base + 0x14)
            if entry_id == _PKG_ENTRY_ID_PARAM_SFO:
                sfo_offset, sfo_size = data_offset, data_size
            elif entry_id == _PKG_ENTRY_ID_ICON0_PNG:
                icon_offset, icon_size = data_offset, data_size
            if sfo_offset is not None and icon_offset is not None:
                break

        if sfo_offset is not None and sfo_size is not None and 0 < sfo_size <= _MAX_PARAM_SIZE:
            params = _parse_sfo(_read_at(fh, sfo_offset, sfo_size))
            _fill_from_sfo_params(params, meta, default_package_type=_pkg_type_from_flags(flags))
        else:
            meta.package_type = _pkg_type_from_flags(flags)

        if icon_offset is not None and icon_size is not None and 0 < icon_size <= _MAX_ICON_SIZE:
            icon = _read_at(fh, icon_offset, icon_size)
            if _is_png(icon):
                meta.icon_bytes = icon
    return meta


def _read_exfat_metadata(path: Path, meta: GameMetadata) -> GameMetadata:
    meta.package_type = "EXFAT"
    with path.open("rb") as fh:
        reader = ExfatReader(fh)
        _fill_from_exfat_reader(reader, meta)
    return meta


def _read_ffpkg_metadata(path: Path, meta: GameMetadata) -> GameMetadata:
    meta.package_type = "FFPKG"
    with path.open("rb") as fh:
        if _read_at(fh, _FFPKG_MAGIC_OFFSET, 4) != _FFPKG_MAGIC:
            meta.package_type = "UNKNOWN"
            meta.content_id = _DASH
            return meta

        title_id = _scan_ffpkg_directory(fh) or _scan_title_id(fh, 0, min(_FFPKG_SCAN_LIMIT, meta.file_size))
        if title_id:
            meta.title_id = title_id
            meta.content_id = title_id

        meta.icon_bytes = _scan_png(fh, _FFPKG_DIR_OFFSET)
        meta.has_apr_emu = _scan_ascii(
            fh,
            0,
            min(_FFPKG_APR_SCAN_LIMIT, meta.file_size),
            (b"libSceAmpr.sprx", b"libSceAmpr.SPRX"),
        )
    return meta


def _read_pfs_metadata(path: Path, meta: GameMetadata) -> GameMetadata:
    meta.package_type = "FFPFSC" if path.suffix.lower() == ".ffpfsc" else "FFPFS"
    inspection = inspect_pfs_image(image=path, verify_payloads=False)
    if inspection.header is not None:
        meta.package_type = f"{meta.package_type} ({len(inspection.inodes)} inodes)"

    if inspection.header is not None and inspection.inodes and inspection.file_inodes:
        meta.has_apr_emu = any(name.lower() == "fakelib/libsceampr.sprx" for name in inspection.file_inodes)
        with path.open("rb") as fh:
            param_inode_num = _find_rel_path(inspection.file_inodes, "sce_sys/param.json")
            if param_inode_num is not None:
                param_inode = inspection.inodes[param_inode_num]
                if 0 < param_inode.logical_size <= _MAX_PARAM_SIZE:
                    data = _read_pfs_inode_bytes(fh, inspection.header, param_inode, _MAX_PARAM_SIZE)
                    _fill_from_param_json(data, meta)

            icon_inode_num = _find_rel_path(inspection.file_inodes, "sce_sys/icon0.png")
            if icon_inode_num is not None:
                icon_inode = inspection.inodes[icon_inode_num]
                if 0 < icon_inode.logical_size <= _MAX_ICON_SIZE:
                    icon = _read_pfs_inode_bytes(fh, inspection.header, icon_inode, _MAX_ICON_SIZE)
                    if _is_png(icon):
                        meta.icon_bytes = icon

    if not meta.game_title and not meta.icon_bytes:
        view_tuple = open_inner_file_view(path)
        if view_tuple is not None:
            view, handle, _inner_name = view_tuple
            try:
                _fill_from_exfat_reader(ExfatReader(view), meta)
            finally:
                handle.close()

    return meta


def _fill_from_exfat_reader(reader: ExfatReader, meta: GameMetadata) -> None:
    files: dict[str, ExfatEntry] = {entry.rel_path.lower(): entry for entry in reader.iter_files()}
    meta.has_apr_emu = "fakelib/libsceampr.sprx" in files

    param = files.get("sce_sys/param.json")
    if param is not None and 0 < param.length <= _MAX_PARAM_SIZE:
        _fill_from_param_json(b"".join(reader.read_file(param, chunk_size=_MAX_PARAM_SIZE)), meta)

    icon = files.get("sce_sys/icon0.png")
    if icon is not None and 0 < icon.length <= _MAX_ICON_SIZE:
        icon_bytes = b"".join(reader.read_file(icon, chunk_size=_MAX_ICON_SIZE))
        if _is_png(icon_bytes):
            meta.icon_bytes = icon_bytes


def _fill_from_source_folder(path: Path, meta: GameMetadata) -> None:
    meta.has_apr_emu = (path / "fakelib" / "libSceAmpr.sprx").is_file()

    param_json = path / "sce_sys" / "param.json"
    if param_json.is_file():
        with contextlib.suppress(OSError, ValueError, json.JSONDecodeError):
            if 0 < param_json.stat().st_size <= _MAX_PARAM_SIZE:
                _fill_from_param_json(param_json.read_bytes(), meta)

    param_sfo = path / "sce_sys" / "param.sfo"
    if param_sfo.is_file() and not meta.game_title:
        with contextlib.suppress(OSError, ValueError):
            if 0 < param_sfo.stat().st_size <= _MAX_PARAM_SIZE:
                _fill_from_sfo_params(_parse_sfo(param_sfo.read_bytes()), meta)

    icon = path / "sce_sys" / "icon0.png"
    if icon.is_file():
        with contextlib.suppress(OSError):
            if 0 < icon.stat().st_size <= _MAX_ICON_SIZE:
                icon_bytes = icon.read_bytes()
                if _is_png(icon_bytes):
                    meta.icon_bytes = icon_bytes


def _fill_from_param_json(data: bytes, meta: GameMetadata) -> None:
    root = json.loads(data.decode("utf-8-sig"))
    if not isinstance(root, dict):
        return

    content_id = _string_value(root, "contentId", "content_id")
    if content_id:
        meta.content_id = content_id
        meta.region = detect_region_from_content_id(content_id)

    title_id = _string_value(root, "titleId", "title_id")
    if title_id:
        meta.title_id = title_id

    version = _string_value(root, "contentVersion", "masterVersion", "appVersion", "version")
    if version:
        meta.version = version

    title = _extract_game_title(root)
    if title:
        meta.game_title = title


def _fill_from_sfo_params(
    params: dict[str, str],
    meta: GameMetadata,
    default_package_type: str | None = None,
) -> None:
    category = params.get("CATEGORY", "")
    if category:
        meta.package_type = _pkg_category_to_type(category)
    elif default_package_type:
        meta.package_type = default_package_type

    content_id = params.get("CONTENT_ID", "").strip()
    if content_id:
        meta.content_id = content_id
        meta.title_id = _title_id_from_content_id(content_id) or meta.title_id
        meta.region = detect_region_from_content_id(content_id)

    meta.title_id = params.get("TITLE_ID", meta.title_id).strip() or meta.title_id
    meta.version = params.get("APP_VER", meta.version).strip() or meta.version
    meta.game_title = params.get("TITLE", meta.game_title).strip() or meta.game_title


def _extract_game_title(root: dict[str, object]) -> str:
    for key in ("title", "titleName", "localizedTitle", "name"):
        value = root.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()

    for value in root.values():
        if isinstance(value, dict):
            title = _string_value(value, "titleName", "title", "name")
            if title:
                return title

    localized = root.get("localizedParameters")
    if isinstance(localized, dict):
        for value in localized.values():
            if isinstance(value, dict):
                title = _string_value(value, "titleName", "title", "name")
                if title:
                    return title
    return ""


def _string_value(source: dict[str, object], *keys: str) -> str:
    for key in keys:
        value = source.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


def _read_pfs_inode_bytes(fh: BinaryIO, header: object, inode: object, limit: int) -> bytes:
    chunks: list[bytes] = []
    total = 0
    for chunk in iter_inode_logical_blocks(fh, header, inode):
        total += len(chunk)
        if total > limit:
            raise ValueError("PFS metadata file exceeds safe read limit")
        chunks.append(chunk)
    return b"".join(chunks)


def _find_rel_path(mapping: dict[str, int], wanted: str) -> int | None:
    wanted = wanted.lower()
    for rel_path, inode_num in mapping.items():
        if rel_path.lower() == wanted:
            return inode_num
    return None


def _scan_ffpkg_directory(fh: BinaryIO) -> str | None:
    try:
        data = _read_at(fh, _FFPKG_DIR_OFFSET, 4096)
        pos = 0
        while pos + 8 <= len(data):
            record_length = struct.unpack_from("<H", data, pos + 4)[0]
            name_length = data[pos + 7]
            if record_length < 8 or pos + 8 + name_length > len(data):
                break
            if record_length == 0:
                break
            if name_length > 0:
                name = data[pos + 8 : pos + 8 + name_length].decode("ascii", errors="ignore")
                match = _TITLE_ID_PATTERN.search(name)
                if match:
                    return match.group(0).upper()
            pos += record_length
    except (OSError, struct.error):
        return None
    return None


def _scan_title_id(fh: BinaryIO, offset: int, size: int) -> str | None:
    data = _read_at(fh, offset, size)
    text = "".join(chr(byte) if 0x20 <= byte <= 0x7E else " " for byte in data)
    match = _TITLE_ID_PATTERN.search(text)
    return match.group(0).upper() if match else None


def _scan_ascii(fh: BinaryIO, offset: int, size: int, needles: tuple[bytes, ...]) -> bool:
    data = _read_at(fh, offset, size)
    return any(needle in data for needle in needles)


def _scan_png(fh: BinaryIO, offset: int) -> bytes | None:
    signature = b"\x89PNG\r\n\x1a\n"
    iend = b"IEND\xaeB`\x82"
    chunk_size = 256 * 1024
    overlap = len(signature)
    pos = offset
    while True:
        data = _read_at(fh, pos, chunk_size)
        if len(data) < len(signature):
            return None
        index = data.find(signature)
        if index >= 0:
            return _read_png_from(fh, pos + index, iend)
        if len(data) < chunk_size:
            return None
        pos += chunk_size - overlap


def _read_png_from(fh: BinaryIO, offset: int, iend: bytes) -> bytes | None:
    data = _read_at(fh, offset, min(_MAX_ICON_SIZE, 3_145_728))
    if not _is_png(data):
        return None
    index = data.find(iend)
    if index < 0:
        return data
    return data[: index + len(iend)]


def _parse_sfo(data: bytes) -> dict[str, str]:
    result: dict[str, str] = {}
    if len(data) < 20 or data[:4] != b"\x00PSF":
        return result
    key_table_offset = _le32(data, 0x08)
    data_table_offset = _le32(data, 0x0C)
    entry_count = _le32(data, 0x10)

    for index in range(entry_count):
        entry_base = 0x14 + index * 16
        if entry_base + 16 > len(data):
            break
        key_offset, fmt = struct.unpack_from("<HH", data, entry_base)
        param_len = _le32(data, entry_base + 4)
        data_offset = _le32(data, entry_base + 12)

        key_start = key_table_offset + key_offset
        if key_start >= len(data):
            continue
        key_end = data.find(b"\0", key_start)
        if key_end < 0:
            continue
        key = data[key_start:key_end].decode("ascii", errors="ignore")

        value_start = data_table_offset + data_offset
        if value_start >= len(data):
            continue
        value_len = min(param_len, len(data) - value_start)
        if fmt == 0x0404 and value_len >= 4:
            value = str(_le32(data, value_start))
        else:
            raw = data[value_start : value_start + value_len]
            value = raw.split(b"\0", 1)[0].decode("utf-8", errors="replace")
        result[key] = value.rstrip("\0")
    return result


def _title_id_from_content_id(content_id: str) -> str | None:
    if not content_id or content_id == _DASH:
        return None
    parts = content_id.split("-")
    if len(parts) >= 2:
        middle = parts[1]
        return middle.split("_", 1)[0] or None
    return content_id


def _pkg_category_to_type(category: str) -> str:
    mapping = {
        "ac": "PS4AC",
        "bd": "PS4BD",
        "gc": "PS4GC",
        "gd": "PS4GD",
        "gda": "PS4GDA",
        "gdc": "PS4GDC",
        "gdd": "PS4GDD",
        "gde": "PS4GDE",
        "gdk": "PS4GDK",
        "gdl": "PS4GDL",
        "gdo": "PS4GDO",
        "gp": "PS4GP",
        "gpc": "PS4GPC",
        "sd": "PS4SD",
    }
    return mapping.get(category.lower(), category.upper())


def _pkg_type_from_flags(flags: int) -> str:
    type_flag = flags & 0xFF
    if type_flag == 0x01:
        return "PS4GD"
    if type_flag == 0x02:
        return "PS4AC"
    if type_flag == 0x04:
        return "PS4DX"
    if type_flag == 0x08:
        return "PS4DA"
    if type_flag == 0x10:
        return "PS4GP"
    return f"0x{flags:08X}"


def _read_at(fh: BinaryIO, offset: int, size: int) -> bytes:
    fh.seek(offset)
    return fh.read(size)


def _read_u32be(fh: BinaryIO, offset: int) -> int:
    data = _read_at(fh, offset, 4)
    return struct.unpack(">I", data)[0] if len(data) == 4 else 0


def _le32(data: bytes, offset: int) -> int:
    return struct.unpack_from("<I", data, offset)[0] if offset + 4 <= len(data) else 0


def _is_png(data: bytes) -> bool:
    return len(data) > 8 and data[:4] == b"\x89PNG"
