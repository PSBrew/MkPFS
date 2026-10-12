"""Overlay folders and RAR/ZIP archives into one pack source.

A game and its patches usually arrive as separate pieces: the base game, an update,
maybe a backport and some DLC, each one a folder or an archive. Packing them used to
mean copying every piece over the previous one and packing the result, which costs a
second copy of the game and a long wait. A :class:`LayeredSource` serves that merged
view directly: every layer is listed once, the highest layer wins for each path, and
file contents are streamed from whichever layer provides them. Nothing is copied or
modified on disk.

Layers are given bottom to top. Each one is a folder or a RAR/ZIP archive, optionally
followed by ``::folder`` to name the directory inside it that holds the game files;
when it is omitted the game folder is located automatically (see
:func:`detect_layer_root`).
"""

from __future__ import annotations

import io
import os
import re
import time
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import BinaryIO, Union

from .ampr import AMPR_FAKELIB_MARKER, AMPR_INDEX_NAME, build_ampr_index_bytes
from .archive_source import (
    ArchiveEntry,
    ArchiveError,
    ArchiveSource,
    ArchiveSubtree,
    SourceTree,
    _normalize_member_path,
    is_archive_path,
    prepare_archive_subtree,
)
from .logging import info, warning
from .utils import human_readable_size, is_ignored_name

LAYER_ROOT_SEPARATOR: str = "::"
_APP_FOLDER_RE: re.Pattern[str] = re.compile(r"-app0?$", re.IGNORECASE)
# Loose files that release folders carry next to the game folder; they never decide
# where the game root is and are not packed when the root is a subfolder.
_LOOSE_FILE_SUFFIXES: tuple[str, ...] = (".nfo", ".txt", ".sfv", ".md5", ".sha1", ".url", ".jpg", ".png", ".diz")
# Folders that live at the root of a game: the level that holds one of them is the root.
_GAME_ROOT_FOLDERS: frozenset[str] = frozenset({"sce_sys", "sce_module", "fakelib", "data", "app0"})


@dataclass
class FolderLayer:
    """A directory used as a layer, with the same read interface as ``ArchiveSubtree``."""

    root: Path

    @property
    def path(self) -> Path:
        """The directory on disk."""
        return self.root

    @property
    def name(self) -> str:
        """Last component of the directory path."""
        return self.root.name

    def entries(self) -> list[ArchiveEntry]:
        """Return every file and directory below the folder, OS metadata and symlinks excluded."""
        found: list[ArchiveEntry] = []
        pending: list[tuple[Path, str]] = [(self.root, "")]
        while pending:
            dir_path, rel_dir = pending.pop()
            with os.scandir(dir_path) as it:
                for entry in it:
                    if is_ignored_name(entry.name):
                        continue
                    rel: str = f"{rel_dir}/{entry.name}" if rel_dir else entry.name
                    if entry.is_dir(follow_symlinks=False):
                        mtime: int = int(entry.stat(follow_symlinks=False).st_mtime)
                        found.append(ArchiveEntry(rel_path=rel, size=0, is_dir=True, mtime=mtime))
                        pending.append((Path(entry.path), rel))
                    elif entry.is_file(follow_symlinks=False):
                        stat = entry.stat(follow_symlinks=False)
                        found.append(
                            ArchiveEntry(rel_path=rel, size=stat.st_size, is_dir=False, mtime=int(stat.st_mtime))
                        )
        return found

    def has_file(self, rel_path: str) -> bool:
        """Return True when ``rel_path`` is a regular file below the folder."""
        return (self.root / rel_path).is_file()

    def open(self, rel_path: str) -> BinaryIO:
        """Open a file below the folder for sequential reading."""
        return (self.root / rel_path).open("rb")

    def read_bytes(self, rel_path: str, *, limit: int = 16 * 1024 * 1024) -> bytes:
        """Read up to ``limit`` bytes of a file below the folder."""
        with self.open(rel_path) as fh:
            return fh.read(limit)

    def total_size(self) -> int:
        """Return the byte total of all files below the folder."""
        return sum(e.size for e in self.entries() if not e.is_dir)

    def display(self) -> str:
        """Return a display string for logs."""
        return f"{self.root} (folder)"


Layer = Union[FolderLayer, ArchiveSubtree]  # ``X | Y`` at runtime needs Python 3.10


def _with_implicit_dirs(entries: Iterable[ArchiveEntry]) -> list[ArchiveEntry]:
    """Return ``entries`` plus a directory entry for every parent that is only implied by a path."""
    result: list[ArchiveEntry] = list(entries)
    known: set[str] = {e.rel_path for e in result if e.is_dir}
    for entry in list(result):
        parent: str = entry.rel_path.rpartition("/")[0]
        while parent and parent not in known:
            known.add(parent)
            result.append(ArchiveEntry(rel_path=parent, size=0, is_dir=True, mtime=entry.mtime))
            parent = parent.rpartition("/")[0]
    return result


class LayeredSource(SourceTree):
    """Several layers merged into one tree; the highest layer wins for every path.

    A file in an upper layer replaces a file (or a whole directory) of the same path
    in the layers below it; a directory in an upper layer is merged with the
    directories below it. ``extra_files`` holds in-memory members (the generated
    ``ampr_emu.index``) that sit on top of everything.
    """

    def __init__(self, layers: list[Layer]) -> None:
        """Merge the listings of ``layers`` (given bottom to top).

        Args:
            layers: Folders and archive subtrees, lowest first.

        Raises:
            ArchiveError: If no layer was given.
        """
        if not layers:
            raise ArchiveError("at least one layer is needed")
        self.layers: list[Layer] = list(layers)
        self.extra_files: dict[str, bytes] = {}
        self.replaced: int = 0  # files of lower layers hidden by upper ones (for the log)
        self._merged: dict[str, tuple[int, ArchiveEntry]] = {}
        self._merge()

    def _merge(self) -> None:
        merged: dict[str, tuple[int, ArchiveEntry]] = {}
        replaced: int = 0
        for index, layer in enumerate(self.layers):
            # Directories first: a directory replacing a lower file must be settled
            # before the files inside it land.
            for entry in sorted(_with_implicit_dirs(layer.entries()), key=lambda e: (not e.is_dir, e.rel_path)):
                previous: tuple[int, ArchiveEntry] | None = merged.get(entry.rel_path)
                if entry.is_dir:
                    if previous is not None:
                        if previous[1].is_dir:
                            continue
                        replaced += 1  # a lower file hidden by this directory
                    merged[entry.rel_path] = (index, entry)
                    continue
                if previous is not None:
                    if previous[1].is_dir:
                        prefix: str = entry.rel_path + "/"
                        hidden: list[str] = [key for key in merged if key.startswith(prefix)]
                        replaced += sum(1 for key in hidden if not merged[key][1].is_dir)
                        for key in hidden:
                            del merged[key]
                    else:
                        replaced += 1
                merged[entry.rel_path] = (index, entry)
        self._merged = merged
        self.replaced = replaced

    @property
    def base(self) -> Layer:
        """The lowest layer (the game itself)."""
        return self.layers[0]

    @property
    def path(self) -> Path:
        """The base layer's path on disk."""
        return self.base.path

    @property
    def name(self) -> str:
        """The base layer's name."""
        return self.base.name

    def layer_of(self, rel_path: str) -> int | None:
        """Return the index of the layer that provides ``rel_path``, or None."""
        found: tuple[int, ArchiveEntry] | None = self._merged.get(_normalize_member_path(rel_path))
        return None if found is None else found[0]

    def entries(self) -> list[ArchiveEntry]:
        """Return the merged listing with in-memory extras on top."""
        result: dict[str, ArchiveEntry] = {rel: entry for rel, (_index, entry) in self._merged.items()}
        for rel, data in self.extra_files.items():
            result[rel] = ArchiveEntry(rel_path=rel, size=len(data), is_dir=False, mtime=_extra_mtime())
        return list(result.values())

    def has_file(self, rel_path: str) -> bool:
        """Return True when ``rel_path`` is a file in the merged view."""
        rel_path = _normalize_member_path(rel_path)
        if rel_path in self.extra_files:
            return True
        found: tuple[int, ArchiveEntry] | None = self._merged.get(rel_path)
        return found is not None and not found[1].is_dir

    def open(self, rel_path: str) -> BinaryIO:
        """Open a file of the merged view, streamed from the layer that provides it."""
        rel_path = _normalize_member_path(rel_path)
        if rel_path in self.extra_files:
            return io.BytesIO(self.extra_files[rel_path])
        found: tuple[int, ArchiveEntry] | None = self._merged.get(rel_path)
        if found is None or found[1].is_dir:
            raise ArchiveError(f"'{rel_path}' is not a file in the merged layers")
        return self.layers[found[0]].open(rel_path)

    def read_bytes(self, rel_path: str, *, limit: int = 16 * 1024 * 1024) -> bytes:
        """Read up to ``limit`` bytes of a file of the merged view."""
        rel_path = _normalize_member_path(rel_path)
        if rel_path in self.extra_files:
            return self.extra_files[rel_path][:limit]
        found: tuple[int, ArchiveEntry] | None = self._merged.get(rel_path)
        if found is None or found[1].is_dir:
            raise ArchiveError(f"'{rel_path}' is not a file in the merged layers")
        return self.layers[found[0]].read_bytes(rel_path, limit=limit)

    def display(self) -> str:
        """Return a display string for logs and summaries."""
        upper: int = len(self.layers) - 1
        return f"{self.base.display()} + {upper} layer{'s' if upper != 1 else ''}"


def _extra_mtime() -> int:
    return int(time.time())


def parse_layer_spec(spec: str) -> tuple[Path, str | None]:
    """Split ``PATH`` or ``PATH::FOLDER`` into the path and the optional folder inside it.

    Args:
        spec: A ``--layer`` value.

    Returns:
        ``(path, folder)``; ``folder`` is ``None`` when it must be detected and ``""``
        for the root of the layer.
    """
    head, sep, inner = spec.rpartition(LAYER_ROOT_SEPARATOR)
    if not sep:
        return Path(spec).expanduser(), None
    return Path(head).expanduser(), _normalize_member_path(inner)


def detect_layer_root(entries: Iterable[ArchiveEntry]) -> str:
    """Find the directory inside a layer that holds the game files.

    The root is, in order: the layer root itself when it holds ``eboot.bin`` or
    ``sce_sys``; the single directory that holds them or is named ``*-app``; else the
    layer root after descending through levels that contain one directory and no
    files (release notes such as ``.nfo`` or ``.txt`` do not count), stopping at the
    level that holds a known game folder such as ``data`` or ``sce_module``.

    Args:
        entries: The layer listing.

    Returns:
        The directory relative to the layer root (``""`` for the root itself).

    Raises:
        ArchiveError: If several unrelated game folders are found.
    """
    listed: list[ArchiveEntry] = _with_implicit_dirs(entries)
    files: set[str] = {e.rel_path for e in listed if not e.is_dir}
    dirs: set[str] = {e.rel_path for e in listed if e.is_dir}

    def game_like(rel_dir: str) -> bool:
        head: str = f"{rel_dir}/" if rel_dir else ""
        if f"{head}eboot.bin" in files or f"{head}sce_sys/param.json" in files or f"{head}sce_sys" in dirs:
            return True
        return bool(rel_dir) and bool(_APP_FOLDER_RE.search(rel_dir.rsplit("/", 1)[-1]))

    if game_like(""):
        return ""
    candidates: list[str] = sorted(d for d in dirs if game_like(d))
    outer: list[str] = [c for c in candidates if not any(c.startswith(o + "/") for o in candidates if o != c)]
    if len(outer) == 1:
        return outer[0]
    if outer:
        listing: str = "\n  ".join(outer)
        raise ArchiveError(f"the layer holds {len(outer)} game folders; pick one with '::FOLDER':\n  {listing}")

    current: str = ""
    while True:
        head = f"{current}/" if current else ""
        child_dirs: set[str] = set()
        child_files: list[str] = []
        for rel in files | dirs:
            if not rel.startswith(head) or rel == current:
                continue
            first: str = rel[len(head) :].split("/", 1)[0]
            if rel in files and "/" not in rel[len(head) :]:
                child_files.append(first)
            else:
                child_dirs.add(first)
        loose: bool = all(name.lower().endswith(_LOOSE_FILE_SUFFIXES) for name in child_files)
        if len(child_dirs) == 1 and loose and next(iter(child_dirs)).lower() not in _GAME_ROOT_FOLDERS:
            current = f"{head}{next(iter(child_dirs))}"
            continue
        return current


def open_layer(path: Path, inner: str | None, *, password: str | None = None) -> Layer:
    """Open one layer (a folder or an archive) at the directory that holds its game files.

    Args:
        path: Folder or RAR/ZIP file.
        inner: Directory inside it, or ``None`` to detect it.
        password: Password for encrypted archives.

    Returns:
        The layer, rooted at the game files.

    Raises:
        ArchiveError: If the path does not exist, the archive cannot be read, or the
            requested directory is missing.
    """
    if is_archive_path(path):
        source: ArchiveSource = ArchiveSource(path, password=password)
        root: str = inner if inner is not None else detect_layer_root(source.entries)
        return source.subtree(root)
    if not path.is_dir():
        raise ArchiveError(f"layer not found (expected a folder or a .rar/.zip file): {path}")
    folder_inner: str = inner if inner is not None else detect_layer_root(FolderLayer(path).entries())
    root_path: Path = path / folder_inner if folder_inner else path
    if not root_path.is_dir():
        raise ArchiveError(f"'{folder_inner}' does not exist inside {path}")
    return FolderLayer(root_path)


def prepare_layered_source(
    base: Path,
    layer_specs: list[str],
    *,
    password: str | None = None,
    archive_root: str | None = None,
    ampr_index: bool = True,
) -> LayeredSource:
    """Open the base source and its layers as one merged pack source.

    The base is a folder (used as-is) or an archive (its game folder is located as
    ``pack folder`` does, honouring ``archive_root``). Every layer spec is a folder or
    archive path, optionally with ``::FOLDER``. The AMPR emulation index is generated
    in memory from the merged listing when the merged view holds
    ``fakelib/libSceAmpr.sprx``; an index present in any layer is replaced.

    Args:
        base: Game folder or archive (the lowest layer).
        layer_specs: ``--layer`` values, bottom to top.
        password: Password shared by every encrypted archive.
        archive_root: Explicit game folder inside the base archive.
        ampr_index: Whether to generate ``ampr_emu.index`` for emulation builds.

    Returns:
        The merged source, ready for the exFAT serializer.

    Raises:
        ArchiveError: If a layer cannot be opened or its game folder is ambiguous.
    """
    layers: list[Layer] = []
    if is_archive_path(base):
        layers.append(prepare_archive_subtree(base, password=password, archive_root=archive_root, ampr_index=False))
    elif base.is_dir():
        layers.append(FolderLayer(base))
    else:
        raise ArchiveError(f"source not found (expected a folder or a .rar/.zip file): {base}")
    for spec in layer_specs:
        path, inner = parse_layer_spec(spec)
        layers.append(open_layer(path, inner, password=password))

    source: LayeredSource = LayeredSource(layers)
    for index, layer in enumerate(layers):
        files: int = sum(1 for e in layer.entries() if not e.is_dir)
        label: str = "Base" if index == 0 else f"Layer {index}"
        info(f"{label}: {layer.display()}; {files} files, {human_readable_size(layer.total_size())}")
    merged_files: list[ArchiveEntry] = [e for e in source.entries() if not e.is_dir]
    info(
        f"Merged view: {len(merged_files)} files, {human_readable_size(sum(e.size for e in merged_files))}; "
        f"{source.replaced} file(s) of lower layers replaced by upper ones"
    )
    if not source.has_file("eboot.bin") or not source.has_file("sce_sys/param.json"):
        warning("The merged view has no eboot.bin + sce_sys/param.json at its root; check the layer folders")
    if ampr_index and source.has_file(AMPR_FAKELIB_MARKER.as_posix()):
        info(f"Detected {AMPR_FAKELIB_MARKER.as_posix()}; generating {AMPR_INDEX_NAME} from the merged listing...")
        index_bytes: bytes = build_ampr_index_bytes(
            (e.rel_path, e.size, e.mtime) for e in source.entries() if not e.is_dir
        )
        if index_bytes:
            source.extra_files[AMPR_INDEX_NAME] = index_bytes
            info(f"Generated {AMPR_INDEX_NAME} ({human_readable_size(len(index_bytes))})")
    return source
