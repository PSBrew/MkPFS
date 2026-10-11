"""Streaming read access to RAR and ZIP archives used as pack sources.

Lets ``pack folder`` consume a game straight from the archive it was distributed in,
with no extraction step and no temporary copy on disk. The archive is listed once up
front (names, sizes, mtimes), which is everything the exFAT serializer needs to plan
its layout; member contents are then streamed one at a time, in the same order the
serializer emits them. That order (case-insensitive path order) is also the order most
release archives store their members in, so even solid archives read mostly forward.

Backends:

* RAR (RAR4/RAR5, multi-volume, password): shells out to the ``unrar`` tool
  (``unrar lt`` to list, ``unrar p`` to stream a member to stdout). ``unrar`` must be
  on ``PATH`` or named by the ``MKPFS_UNRAR`` environment variable.
* ZIP (stored/deflated, legacy ZipCrypto; AES when ``pyzipper`` is installed): the
  standard library ``zipfile`` module.
"""

from __future__ import annotations

import io
import json
import os
import queue
import re
import shutil
import subprocess
import threading
import time
import zipfile
from collections.abc import Iterable
from dataclasses import dataclass, field
from pathlib import Path
from typing import BinaryIO

from .ampr import AMPR_FAKELIB_MARKER, AMPR_INDEX_NAME, build_ampr_index_bytes
from .logging import info, warning
from .utils import _sanitize_name_component, default_image_basename, human_readable_size, is_ignored_name

ARCHIVE_SUFFIXES: tuple[str, ...] = (".rar", ".zip")
_RAR_VOLUME_RE: re.Pattern[str] = re.compile(r"\.r\d\d$", re.IGNORECASE)
_PREFETCH_CHUNK: int = 1024 * 1024
_PREFETCH_DEPTH: int = 32  # chunks kept ahead of the consumer (32 MiB per open member)
_PASSWORD_PROBE_LIMIT: int = 64 * 1024
_UNRAR_EXIT_MESSAGES: dict[int, str] = {
    1: "non fatal error",
    2: "fatal error",
    3: "CRC error (corrupt data or wrong password)",
    4: "archive is locked",
    5: "write error",
    6: "file open error",
    7: "wrong command line option",
    8: "not enough memory",
    9: "file create error",
    10: "no files matched",
    11: "wrong password",
}


class ArchiveError(RuntimeError):
    """Raised when an archive cannot be listed or a member cannot be streamed."""


@dataclass(frozen=True)
class ArchiveEntry:
    """A member of an archive.

    Attributes:
        rel_path: POSIX-style path inside the archive, without a leading slash.
        size: Uncompressed size in bytes (0 for directories).
        is_dir: Whether the member is a directory entry.
        mtime: Modification time as a Unix timestamp (0 when unknown).
    """

    rel_path: str
    size: int
    is_dir: bool
    mtime: int


def is_archive_path(path: Path) -> bool:
    """Return True when ``path`` names a file this module can read as a pack source.

    Args:
        path: Candidate source path.

    Returns:
        True for existing ``.rar`` / ``.zip`` files and old-style ``.rNN`` RAR volumes.
    """
    if not path.is_file():
        return False
    lowered: str = path.name.lower()
    return lowered.endswith(ARCHIVE_SUFFIXES) or bool(_RAR_VOLUME_RE.search(lowered))


def _normalize_member_path(raw: str) -> str:
    return raw.replace("\\", "/").strip("/")


def _is_ignored_member(rel_path: str) -> bool:
    return any(is_ignored_name(part) for part in rel_path.split("/"))


# ---------------------------------------------------------------------------
# Streaming readers
# ---------------------------------------------------------------------------


class _PrefetchReader(io.RawIOBase):
    """Read-ahead wrapper that keeps a slow producer busy while the consumer compresses.

    A background thread pulls fixed-size chunks from ``inner`` into a bounded queue so
    the decompressor never idles while the PFSC encoder is busy with earlier blocks.
    """

    def __init__(self, inner: BinaryIO, *, describe: str) -> None:
        super().__init__()
        self._inner: BinaryIO = inner
        self._describe: str = describe
        self._queue: queue.Queue[bytes | BaseException] = queue.Queue(maxsize=_PREFETCH_DEPTH)
        self._stop: threading.Event = threading.Event()
        self._leftover: bytes = b""
        self._eof: bool = False
        self._thread: threading.Thread = threading.Thread(target=self._pump, daemon=True)
        self._thread.start()

    def _pump(self) -> None:
        try:
            while not self._stop.is_set():
                chunk: bytes = self._inner.read(_PREFETCH_CHUNK)
                if not chunk:
                    break
                while not self._stop.is_set():
                    try:
                        self._queue.put(chunk, timeout=0.2)
                        break
                    except queue.Full:
                        continue
        except BaseException as exc:  # surfaced to the consumer on its next read
            self._put_final(exc)
            return
        self._put_final(b"")

    def _put_final(self, item: bytes | BaseException) -> None:
        while not self._stop.is_set():
            try:
                self._queue.put(item, timeout=0.2)
                return
            except queue.Full:
                continue

    def readable(self) -> bool:
        return True

    def _next_chunk(self) -> bytes:
        if self._leftover:
            chunk, self._leftover = self._leftover, b""
            return chunk
        if self._eof:
            return b""
        item: bytes | BaseException = self._queue.get()
        if isinstance(item, BaseException):
            self._eof = True
            raise ArchiveError(f"failed while streaming {self._describe}: {item}") from item
        if not item:
            self._eof = True
            # Give the producer a chance to report a non-zero exit status.
            close_check = getattr(self._inner, "raise_for_status", None)
            if callable(close_check):
                close_check()
        return item

    def read(self, size: int = -1) -> bytes:  # type: ignore[override]
        if size is None or size < 0:
            parts: list[bytes] = []
            while True:
                chunk: bytes = self._next_chunk()
                if not chunk:
                    return b"".join(parts)
                parts.append(chunk)
        chunk = self._next_chunk()
        if len(chunk) > size:
            self._leftover = chunk[size:]
            chunk = chunk[:size]
        return chunk

    def readinto(self, buffer: bytearray | memoryview) -> int:  # type: ignore[override]
        data: bytes = self.read(len(buffer))
        buffer[: len(data)] = data
        return len(data)

    def close(self) -> None:
        if self.closed:
            return
        self._stop.set()
        try:
            self._inner.close()
        finally:
            # Drain so a blocked producer can observe the stop flag and exit.
            try:
                while True:
                    self._queue.get_nowait()
            except queue.Empty:
                pass
            super().close()


class _ProcessReader(io.RawIOBase):
    """Raw stream over a child process' stdout (``unrar p``)."""

    def __init__(self, argv: list[str], *, describe: str) -> None:
        super().__init__()
        self._describe: str = describe
        try:
            self._proc: subprocess.Popen[bytes] = subprocess.Popen(
                argv, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, stdin=subprocess.DEVNULL
            )
        except OSError as exc:
            raise ArchiveError(f"cannot start {argv[0]}: {exc}") from exc

    def readable(self) -> bool:
        return True

    def read(self, size: int = -1) -> bytes:  # type: ignore[override]
        assert self._proc.stdout is not None
        return self._proc.stdout.read(size)

    def raise_for_status(self) -> None:
        """Raise ``ArchiveError`` when the finished child reported a failure."""
        code: int | None = self._proc.poll()
        if code is None:
            code = self._proc.wait()
        if code not in (0, 1):
            reason: str = _UNRAR_EXIT_MESSAGES.get(code, f"exit status {code}")
            raise ArchiveError(f"unrar failed while reading {self._describe}: {reason}")

    def close(self) -> None:
        if self.closed:
            return
        try:
            if self._proc.poll() is None:
                self._proc.kill()
            if self._proc.stdout is not None:
                self._proc.stdout.close()
            self._proc.wait(timeout=5)
        except (OSError, subprocess.TimeoutExpired):
            pass
        finally:
            super().close()


# ---------------------------------------------------------------------------
# RAR backend (unrar command line tool)
# ---------------------------------------------------------------------------


def unrar_executable() -> str | None:
    """Locate the ``unrar`` tool.

    Returns:
        The executable path from ``MKPFS_UNRAR`` or ``PATH``, or ``None`` when absent.
    """
    override: str = os.environ.get("MKPFS_UNRAR", "").strip()
    if override:
        return override if Path(override).is_file() else shutil.which(override)
    for candidate in ("unrar", "UnRAR", "UnRAR.exe", "unrar.exe"):
        found: str | None = shutil.which(candidate)
        if found:
            return found
    return None


def _unrar_base_args(password: str | None) -> list[str]:
    tool: str | None = unrar_executable()
    if tool is None:
        raise ArchiveError(
            "unrar was not found. Install UnRAR (https://www.rarlab.com/rar_add.htm), put it on PATH, "
            "or point MKPFS_UNRAR at the executable."
        )
    return [tool, "-y", "-inul", "-idq", f"-p{password}" if password else "-p-"]


def _parse_unrar_mtime(text: str) -> int:
    match = re.match(r"(\d{4}-\d\d-\d\d \d\d:\d\d:\d\d)", text.strip())
    if not match:
        return 0
    try:
        return int(time.mktime(time.strptime(match.group(1), "%Y-%m-%d %H:%M:%S")))
    except (ValueError, OverflowError):
        return 0


def parse_unrar_listing(text: str) -> tuple[list[ArchiveEntry], bool, bool]:
    """Parse ``unrar lt`` technical listing output.

    Args:
        text: Complete stdout of ``unrar lt``.

    Returns:
        ``(entries, solid, encrypted)``; split members of multi-volume archives are
        collapsed into a single entry.
    """
    entries: dict[str, ArchiveEntry] = {}
    solid: bool = False
    encrypted: bool = False
    current: dict[str, str] = {}

    def flush() -> None:
        nonlocal encrypted
        name: str | None = current.get("Name")
        if name is None:
            current.clear()
            return
        rel_path: str = _normalize_member_path(name)
        is_dir: bool = current.get("Type", "File").lower().startswith("dir")
        size: int = int(current.get("Size", "0") or 0)
        mtime: int = _parse_unrar_mtime(current.get("mtime", ""))
        if "encrypted" in current.get("Flags", "").lower():
            encrypted = True
        previous: ArchiveEntry | None = entries.get(rel_path)
        if rel_path and (previous is None or size > previous.size):
            entries[rel_path] = ArchiveEntry(rel_path=rel_path, size=0 if is_dir else size, is_dir=is_dir, mtime=mtime)
        current.clear()

    for line in text.splitlines():
        stripped: str = line.strip()
        if stripped.startswith("Details:"):
            details: str = stripped.lower()
            solid = solid or "solid" in details
            encrypted = encrypted or "encrypted" in details
            continue
        if not stripped:
            flush()
            continue
        key, sep, value = stripped.partition(":")
        if not sep:
            continue
        key = key.strip()
        if key == "Name" and "Name" in current:
            flush()
        current[key] = value.strip()
    flush()
    return list(entries.values()), solid, encrypted


def rar_member_argument(rel_path: str, *, windows: bool = os.name == "nt") -> str:
    """Return the member name as the ``unrar`` tool expects it on this platform.

    Listings are normalized to forward slashes; UnRAR.exe on Windows only matches
    members written with backslashes, while unrar on POSIX accepts forward slashes.
    """
    return rel_path.replace("/", "\\") if windows else rel_path


def _list_rar(path: Path, password: str | None) -> tuple[list[ArchiveEntry], bool, bool]:
    argv: list[str] = _unrar_base_args(password)
    # ``-v`` lists every volume of a multi-volume set; without it only the first volume is shown.
    argv = [argv[0], "lt", "-v", "-y", argv[4], "--", str(path)]
    try:
        result = subprocess.run(argv, capture_output=True, text=True, errors="replace", stdin=subprocess.DEVNULL)
    except OSError as exc:
        raise ArchiveError(f"cannot run unrar: {exc}") from exc
    entries, solid, encrypted = parse_unrar_listing(result.stdout)
    if result.returncode not in (0, 1) and not entries:
        if result.returncode == 11 or "password" in (result.stderr or "").lower():
            raise ArchiveError("the archive needs a password (or the password is wrong); pass --password")
        reason: str = _UNRAR_EXIT_MESSAGES.get(result.returncode, f"exit status {result.returncode}")
        raise ArchiveError(f"unrar could not list {path.name}: {reason}")
    if not entries:
        raise ArchiveError(f"{path.name} contains no members")
    return entries, solid, encrypted


def _open_rar_member(path: Path, password: str | None, rel_path: str) -> BinaryIO:
    argv: list[str] = [*_unrar_base_args(password), "p", "--", str(path), rar_member_argument(rel_path)]
    describe: str = f"'{rel_path}' from {path.name}"
    return _PrefetchReader(_ProcessReader(argv, describe=describe), describe=describe)


# ---------------------------------------------------------------------------
# ZIP backend (zipfile, optionally pyzipper for AES)
# ---------------------------------------------------------------------------


def _open_zipfile(path: Path) -> zipfile.ZipFile:
    try:
        import pyzipper  # type: ignore[import-not-found]  # optional dependency: AES-encrypted ZIPs
    except ImportError:
        return zipfile.ZipFile(str(path))
    try:
        return pyzipper.AESZipFile(str(path))
    except pyzipper.BadZipFile as exc:  # pyzipper raises its own BadZipFile class
        raise zipfile.BadZipFile(str(exc)) from exc


def _list_zip(path: Path) -> tuple[list[ArchiveEntry], bool]:
    encrypted: bool = False
    entries: list[ArchiveEntry] = []
    try:
        archive = _open_zipfile(path)
    except (OSError, zipfile.BadZipFile) as exc:
        raise ArchiveError(f"cannot open {path.name}: {exc}") from exc
    with archive:
        for info in archive.infolist():
            rel_path: str = _normalize_member_path(info.filename)
            if not rel_path:
                continue
            if info.flag_bits & 0x1:
                encrypted = True
            try:
                mtime: int = int(time.mktime((*info.date_time, 0, 0, -1)))
            except (ValueError, OverflowError):
                mtime = 0
            is_dir: bool = info.is_dir()
            entries.append(
                ArchiveEntry(rel_path=rel_path, size=0 if is_dir else info.file_size, is_dir=is_dir, mtime=mtime)
            )
    if not entries:
        raise ArchiveError(f"{path.name} contains no members")
    return entries, encrypted


class _ZipMemberReader(io.RawIOBase):
    """Raw stream over one ZIP member; owns its ``ZipFile`` handle."""

    def __init__(self, path: Path, password: str | None, rel_path: str) -> None:
        super().__init__()
        self._archive = _open_zipfile(path)
        pwd: bytes | None = password.encode("utf-8") if password else None
        try:
            self._member = self._archive.open(rel_path, "r", pwd=pwd)
        except RuntimeError as exc:  # zipfile reports bad passwords as RuntimeError
            self._archive.close()
            raise ArchiveError(f"cannot read '{rel_path}' from {path.name}: {exc}") from exc

    def readable(self) -> bool:
        return True

    def read(self, size: int = -1) -> bytes:  # type: ignore[override]
        return self._member.read(size)

    def close(self) -> None:
        if self.closed:
            return
        try:
            self._member.close()
            self._archive.close()
        finally:
            super().close()


def _open_zip_member(path: Path, password: str | None, rel_path: str) -> BinaryIO:
    describe: str = f"'{rel_path}' from {path.name}"
    return _PrefetchReader(_ZipMemberReader(path, password, rel_path), describe=describe)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


class ArchiveSource:
    """A listed RAR or ZIP archive whose members can be streamed on demand."""

    def __init__(self, path: Path, *, password: str | None = None) -> None:
        """Open and list an archive.

        Args:
            path: Archive file (for multi-volume RAR sets, any volume; the first is best).
            password: Optional password for encrypted members.

        Raises:
            ArchiveError: If the file is not a supported archive, cannot be listed, or
                needs a password that was not given or is wrong.
        """
        self.path: Path = path
        self.password: str | None = password or None
        lowered: str = path.name.lower()
        if lowered.endswith(".zip"):
            self.kind: str = "zip"
            self.entries, self.encrypted = _list_zip(path)
            self.solid: bool = False
        elif lowered.endswith(".rar") or _RAR_VOLUME_RE.search(lowered):
            self.kind = "rar"
            self.entries, self.solid, self.encrypted = _list_rar(path, self.password)
        else:
            raise ArchiveError(f"unsupported archive type: {path.name} (expected .rar or .zip)")
        self._by_path: dict[str, ArchiveEntry] = {entry.rel_path: entry for entry in self.entries}
        if self.encrypted:
            self._probe_password()

    def _probe_password(self) -> None:
        """Fail fast with a clear message when encrypted members cannot be read."""
        candidates: list[ArchiveEntry] = sorted(
            (e for e in self.entries if not e.is_dir and e.size > 0), key=lambda e: e.size
        )
        if not candidates:
            return
        if not self.password:
            raise ArchiveError("the archive is encrypted; pass --password")
        try:
            self.read_bytes(candidates[0].rel_path, limit=_PASSWORD_PROBE_LIMIT)
        except ArchiveError as exc:
            raise ArchiveError(f"wrong password for {self.path.name}: {exc}") from exc

    # -- listing -------------------------------------------------------------

    def files(self, prefix: str = "") -> list[ArchiveEntry]:
        """Return the file members below ``prefix`` (``""`` for the whole archive)."""
        head: str = f"{prefix}/" if prefix else ""
        return [e for e in self.entries if not e.is_dir and e.rel_path.startswith(head)]

    def total_size(self, prefix: str = "") -> int:
        """Return the uncompressed byte total of the files below ``prefix``."""
        return sum(e.size for e in self.files(prefix))

    def game_roots(self) -> list[str]:
        """Return the member directories that look like game roots.

        A game root holds both ``sce_sys/param.json`` and ``eboot.bin``. The archive
        root is reported as ``""``.
        """
        roots: list[str] = []
        for entry in self.entries:
            if entry.is_dir or not entry.rel_path.endswith("sce_sys/param.json"):
                continue
            base: str = entry.rel_path[: -len("sce_sys/param.json")].rstrip("/")
            eboot: str = f"{base}/eboot.bin" if base else "eboot.bin"
            if eboot in self._by_path:
                roots.append(base)
        return sorted(roots)

    def subtree(self, prefix: str = "") -> ArchiveSubtree:
        """Return a view rooted at ``prefix`` (``""`` for the archive root)."""
        prefix = _normalize_member_path(prefix)
        if prefix and prefix not in self._by_path and not self.files(prefix):
            raise ArchiveError(f"'{prefix}' does not exist inside {self.path.name}")
        return ArchiveSubtree(source=self, prefix=prefix)

    # -- reading -------------------------------------------------------------

    def open(self, rel_path: str) -> BinaryIO:
        """Open a member for sequential reading.

        Args:
            rel_path: Member path as listed in :attr:`entries`.

        Returns:
            A binary stream; it must be read forward and closed by the caller.
        """
        entry: ArchiveEntry | None = self._by_path.get(_normalize_member_path(rel_path))
        if entry is None or entry.is_dir:
            raise ArchiveError(f"'{rel_path}' is not a file inside {self.path.name}")
        if self.kind == "zip":
            return _open_zip_member(self.path, self.password, entry.rel_path)
        return _open_rar_member(self.path, self.password, entry.rel_path)

    def read_bytes(self, rel_path: str, *, limit: int = 16 * 1024 * 1024) -> bytes:
        """Read up to ``limit`` bytes of a member (meant for small metadata files)."""
        stream: BinaryIO = self.open(rel_path)
        try:
            data: bytes = stream.read(limit)
            return data
        finally:
            stream.close()

    def describe(self) -> str:
        """Return a short human-readable description for logs."""
        flags: list[str] = [self.kind.upper()]
        if self.solid:
            flags.append("solid")
        if self.encrypted:
            flags.append("encrypted")
        return ", ".join(flags)


@dataclass
class ArchiveSubtree:
    """A directory inside an archive, exposed as a pack source.

    ``extra_files`` holds in-memory members (such as a freshly generated
    ``ampr_emu.index``) that are packed as if they were part of the tree; a member with
    the same path inside the archive is replaced.
    """

    source: ArchiveSource
    prefix: str = ""
    extra_files: dict[str, bytes] = field(default_factory=dict)

    @property
    def path(self) -> Path:
        """The archive file on disk."""
        return self.source.path

    @property
    def name(self) -> str:
        """Last component of the subtree path, or the archive stem at the root."""
        if self.prefix:
            return self.prefix.rsplit("/", 1)[-1]
        return self.source.path.stem

    def _head(self) -> str:
        return f"{self.prefix}/" if self.prefix else ""

    def entries(self) -> list[ArchiveEntry]:
        """Return members below this subtree with paths relative to it.

        OS metadata is excluded and in-memory extras are merged in.
        """
        head: str = self._head()
        merged: dict[str, ArchiveEntry] = {}
        for entry in self.source.entries:
            if head and not entry.rel_path.startswith(head):
                continue
            rel: str = entry.rel_path[len(head) :]
            if not rel or _is_ignored_member(rel):
                continue
            merged[rel] = ArchiveEntry(rel_path=rel, size=entry.size, is_dir=entry.is_dir, mtime=entry.mtime)
        now: int = int(time.time())
        for rel, data in self.extra_files.items():
            merged[rel] = ArchiveEntry(rel_path=rel, size=len(data), is_dir=False, mtime=now)
        return list(merged.values())

    def has_file(self, rel_path: str) -> bool:
        """Return True when ``rel_path`` (relative to the subtree) is a file member."""
        if rel_path in self.extra_files:
            return True
        entry: ArchiveEntry | None = self.source._by_path.get(self._head() + rel_path)
        return entry is not None and not entry.is_dir

    def open(self, rel_path: str) -> BinaryIO:
        """Open a member relative to the subtree for sequential reading."""
        if rel_path in self.extra_files:
            return io.BytesIO(self.extra_files[rel_path])
        return self.source.open(self._head() + rel_path)

    def read_bytes(self, rel_path: str, *, limit: int = 16 * 1024 * 1024) -> bytes:
        """Read up to ``limit`` bytes of a member relative to the subtree."""
        if rel_path in self.extra_files:
            return self.extra_files[rel_path][:limit]
        return self.source.read_bytes(self._head() + rel_path, limit=limit)

    def total_size(self) -> int:
        """Return the uncompressed byte total of all files in the subtree."""
        return sum(e.size for e in self.entries() if not e.is_dir)

    def title_id(self) -> str | None:
        """Return ``titleId`` from ``sce_sys/param.json`` when present and valid."""
        if not self.has_file("sce_sys/param.json"):
            return None
        try:
            parsed: object = json.loads(
                self.read_bytes("sce_sys/param.json", limit=4 * 1024 * 1024).decode("utf-8-sig")
            )
        except (ArchiveError, ValueError):
            return None
        if not isinstance(parsed, dict):
            return None
        value: object = parsed.get("titleId") or parsed.get("title_id")
        if isinstance(value, str) and value.strip():
            return value.strip()
        return None

    def image_basename(self) -> str:
        """Return the output base name: the title ID, else the subtree or archive name."""
        base: str = self.title_id() or self.name or "image"
        return _sanitize_name_component(base) or "image"


def source_image_basename(source: Path | ArchiveSubtree) -> str:
    """Return the default image base name for a folder or an archive subtree."""
    if isinstance(source, ArchiveSubtree):
        return source.image_basename()
    return default_image_basename(source)


def describe_source(source: Path | ArchiveSubtree) -> str:
    """Return a display string for logs and summaries."""
    if isinstance(source, ArchiveSubtree):
        inner: str = f"/{source.prefix}" if source.prefix else ""
        return f"{source.path}{inner} ({source.source.describe()})"
    return str(source)


def iter_archive_entries_for_ampr(subtree: ArchiveSubtree) -> Iterable[tuple[str, int, int]]:
    """Yield ``(rel_path, size, mtime)`` for the files of ``subtree`` (AMPR index input)."""
    for entry in subtree.entries():
        if not entry.is_dir:
            yield entry.rel_path, entry.size, entry.mtime


def prepare_archive_subtree(
    archive_path: Path,
    *,
    password: str | None = None,
    archive_root: str | None = None,
    ampr_index: bool = True,
) -> ArchiveSubtree:
    """Open an archive as a pack source and select the game directory inside it.

    When ``archive_root`` is omitted the single game folder (``sce_sys/param.json`` +
    ``eboot.bin``) found in the archive is used; the archive root is used when there is
    none. The AMPR emulation index is generated in memory from the listing when the
    ``fakelib/libSceAmpr.sprx`` marker is present, mirroring the folder workflow.

    Args:
        archive_path: RAR or ZIP file.
        password: Optional password for encrypted members.
        archive_root: Explicit directory inside the archive to pack (``""`` for the root).
        ampr_index: Whether to generate ``ampr_emu.index`` for emulation builds.

    Returns:
        The subtree ready to be passed to the exFAT serializer.

    Raises:
        ArchiveError: If the archive cannot be read, needs a password, or holds several
            game folders and none was selected.
    """
    source: ArchiveSource = ArchiveSource(archive_path, password=password)
    info(
        f"Archive source: {archive_path.name} ({source.describe()}; {len(source.files())} files, "
        f"{human_readable_size(source.total_size())} uncompressed)"
    )
    if archive_root is None:
        roots: list[str] = source.game_roots()
        if len(roots) > 1:
            listing: str = "\n  ".join(root or "(archive root)" for root in roots)
            raise ArchiveError(
                f"{archive_path.name} holds {len(roots)} game folders; pick one with --archive-root:\n  {listing}"
            )
        archive_root = roots[0] if roots else ""
        if roots:
            info(f"Game folder inside the archive: {archive_root or '(archive root)'}")
        else:
            warning("No sce_sys/param.json + eboot.bin found inside the archive; packing its root as-is")
    subtree: ArchiveSubtree = source.subtree(archive_root)
    if source.solid:
        warning("Solid RAR archive: each member is decompressed from the start of its block; expect slow reads")
    if ampr_index and subtree.has_file(AMPR_FAKELIB_MARKER.as_posix()):
        info(f"Detected {AMPR_FAKELIB_MARKER.as_posix()}; generating {AMPR_INDEX_NAME} from the archive listing...")
        index_bytes: bytes = build_ampr_index_bytes(iter_archive_entries_for_ampr(subtree))
        if index_bytes:
            subtree.extra_files[AMPR_INDEX_NAME] = index_bytes
            info(f"Generated {AMPR_INDEX_NAME} ({human_readable_size(len(index_bytes))})")
    return subtree
