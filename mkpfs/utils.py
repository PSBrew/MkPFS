"""Utilities shared between multiple modules."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path
from typing import BinaryIO

# OS-generated metadata files/directories that should never be packed into an
# image or indexed. Matched case-insensitively against the entry's base name;
# AppleDouble resource forks ("._*") are matched by prefix.
IGNORED_NAMES: frozenset[str] = frozenset(
    {
        # macOS
        ".ds_store",
        ".spotlight-v100",
        ".trashes",
        ".fseventsd",
        ".temporaryitems",
        ".documentrevisions-v100",
        ".apdisk",
        "__macosx",
        ".volumeicon.icns",
        # Windows
        "thumbs.db",
        "ehthumbs.db",
        "desktop.ini",
        "$recycle.bin",
        "system volume information",
    }
)


def _sanitize_name_component(name: str) -> str:
    """Replace filesystem-unsafe characters in a single name component with ``_``."""
    return "".join(c if (c.isalnum() or c in "._-") else "_" for c in name)


def title_id_from_source(source_root: Path) -> str | None:
    """Return the title ID from ``sce_sys/param.json`` when present.

    Args:
        source_root: Source tree root to inspect.

    Returns:
        The trimmed ``titleId`` / ``title_id`` value, or ``None`` when missing or
        unreadable.
    """
    param_json: Path = source_root / "sce_sys" / "param.json"
    if not param_json.exists():
        return None
    try:
        parsed: dict[str, object] = read_param_json(param_json)
    except ValueError:
        return None
    value: object | None = parsed.get("titleId") or parsed.get("title_id")
    if isinstance(value, str) and value.strip():
        return value.strip()
    return None


def default_image_basename(source_root: Path) -> str:
    """Return the base name (no extension) for an image built from ``source_root``.

    Prefers the title ID from ``sce_sys/param.json``; falls back to the source
    directory name. The result is sanitized for use as a filename.

    Args:
        source_root: Source tree root.

    Returns:
        A non-empty, filesystem-safe base name.
    """
    base: str = title_id_from_source(source_root) or source_root.name or "image"
    sanitized: str = _sanitize_name_component(base)
    return sanitized or "image"


def is_ignored_name(name: str) -> bool:
    """Return True if ``name`` is OS-generated metadata to exclude from images.

    Args:
        name: A single path component (file or directory base name).

    Returns:
        True for known macOS/Windows metadata entries (case-insensitive) and for
        AppleDouble resource forks (names starting with ``._``).
    """
    if name.startswith("._"):
        return True
    return name.lower() in IGNORED_NAMES


def human_readable_size(size: int) -> str:
    """Convert a byte count to a human-readable string.

    Args:
        size: Number of bytes.

    Returns:
        Human readable string using binary prefixes (KB, MB, ...).
    """
    s: float = float(size)
    for unit in ["B", "KB", "MB", "GB", "TB"]:
        if s < 1024.0:
            return f"{s:.2f} {unit}"
        s /= 1024.0
    return f"{s:.2f} PB"


def ceil_div(a: int, b: int) -> int:
    """Compute the integer ceiling of a / b.

    Args:
        a: Numerator.
        b: Denominator (must be positive).

    Returns:
        The smallest integer >= a / b.
    """
    result: int = (a + b - 1) // b
    return result


def is_power_of_two(v: int) -> bool:
    """Return True if ``v`` is a positive power of two.

    Args:
        v: Value to test.

    Returns:
        True when v is 1,2,4,8,...; False otherwise.
    """
    return v > 0 and (v & (v - 1)) == 0


def normalize_output_path(path_arg: str, desired_suffix: str, adjust: bool = True) -> tuple[Path, bool]:
    """Normalize an output path extension when automatic adjustment is enabled.

    Args:
        path_arg: Input path string provided by the user.
        desired_suffix: Desired output suffix, including the leading dot.
        adjust: When True, replace the current suffix when it does not match the
            desired suffix. When False, return the path unchanged.

    Returns:
        A tuple of ``(normalized_path, changed)`` where ``changed`` is True when
        the suffix was updated.
    """
    p: Path = Path(path_arg)
    if not adjust:
        return p, False
    if p.suffix.lower() == desired_suffix.lower():
        return p, False
    normalized: Path = p.with_suffix(desired_suffix)
    return normalized, True


def resolve_temp_root(temp_folder: Path | None = None) -> Path:
    """Resolve the temporary root directory used for pack artifacts.

    Args:
        temp_folder: Optional caller-provided temp directory path.

    Returns:
        Existing directory path used for temporary files.
    """
    if temp_folder is None:
        return Path(tempfile.gettempdir())

    temp_root: Path = temp_folder.expanduser().resolve()
    temp_root.mkdir(parents=True, exist_ok=True)
    return temp_root


def read_param_json(path: Path) -> dict[str, object]:
    """Read and parse a JSON parameter file used by games.

    Args:
        path: Path to the JSON file.

    Returns:
        Parsed JSON object as a dict.

    Raises:
        ValueError: When the file cannot be read or parsed as JSON.
    """
    try:
        with path.open(mode="r", encoding="utf-8") as f:
            result: dict[str, object] = json.load(f)
            return result
    except (OSError, json.JSONDecodeError) as exc:  # pragma: no cover - bubble up
        raise ValueError(f"Failed to parse {path}: {exc}") from exc


def _read_exact(fh: BinaryIO, offset: int, size: int) -> bytes:
    """Read exactly ``size`` bytes from file handle starting at ``offset``.

    Args:
        fh: Binary file-like object supporting seek and read.
        offset: Offset in bytes from the start of the file where read begins.
        size: Number of bytes to read.

    Returns:
        The requested bytes.

    Raises:
        ValueError: If the read returns fewer than ``size`` bytes.
    """
    fh.seek(offset)
    data: bytes = fh.read(size)
    if len(data) != size:
        raise ValueError(f"truncated read at offset {offset} (wanted {size}, got {len(data)})")
    return data
