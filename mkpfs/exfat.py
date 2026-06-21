"""Read-only exFAT parser.

Parses and extracts files from an exFAT image exposed as any seekable binary
source. This is used to validate produced images and to peel the inner exFAT out
of a packed container without mounting. It is deliberately read-only and covers
the subset of exFAT that game images use (single FAT, standard directory entry
sets, contiguous or FAT-chained allocation).
"""

from __future__ import annotations

import struct
from collections.abc import Iterator
from dataclasses import dataclass, field
from typing import BinaryIO

EXFAT_SIGNATURE = b"EXFAT   "
_END_OF_DIRECTORY = 0x00
_ENTRY_BITMAP = 0x81
_ENTRY_UPCASE = 0x82
_ENTRY_VOLUME_LABEL = 0x83
_ENTRY_FILE = 0x85
_ENTRY_STREAM_EXTENSION = 0xC0
_ENTRY_FILE_NAME = 0xC1
_IN_USE_MASK = 0x80
_ATTR_DIRECTORY = 0x10
_SECONDARY_FLAG_NO_FAT_CHAIN = 0x02
_FAT_END_OF_CHAIN = 0xFFFFFFFF
_NAME_CHARS_PER_ENTRY = 15


class ExfatError(ValueError):
    """Raised when an exFAT image is malformed or unsupported."""


@dataclass(frozen=True)
class ExfatGeometry:
    """Parsed exFAT volume geometry from the main boot sector.

    Attributes:
        bytes_per_sector: Sector size in bytes.
        sectors_per_cluster: Cluster size in sectors.
        fat_offset_sectors: First FAT offset in sectors.
        cluster_heap_offset_sectors: Cluster heap offset in sectors.
        cluster_count: Number of clusters in the heap.
        root_dir_cluster: First cluster of the root directory.
        volume_serial: Volume serial number.
    """

    bytes_per_sector: int
    sectors_per_cluster: int
    fat_offset_sectors: int
    cluster_heap_offset_sectors: int
    cluster_count: int
    root_dir_cluster: int
    volume_serial: int

    @property
    def cluster_size(self) -> int:
        """Cluster size in bytes."""
        return self.bytes_per_sector * self.sectors_per_cluster


@dataclass
class ExfatEntry:
    """A file or directory entry parsed from an exFAT directory.

    Attributes:
        name: Entry base name.
        rel_path: POSIX-style path relative to the volume root.
        is_dir: Whether the entry is a directory.
        first_cluster: First cluster of the entry's data (0 when empty).
        length: Data length in bytes.
        no_fat_chain: Whether the allocation is contiguous (no FAT chain).
    """

    name: str
    rel_path: str
    is_dir: bool
    first_cluster: int
    length: int
    no_fat_chain: bool
    children: list[ExfatEntry] = field(default_factory=list)


class ExfatReader:
    """Read-only exFAT parser over a seekable binary source."""

    def __init__(self, fh: BinaryIO) -> None:
        """Initialize the reader and parse the boot sector.

        Args:
            fh: Seekable binary source positioned anywhere; the reader seeks
                absolutely and does not take ownership of the handle.

        Raises:
            ExfatError: If the source is not a recognizable exFAT volume.
        """
        self._fh: BinaryIO = fh
        self.geometry: ExfatGeometry = self._parse_boot_sector()

    def _parse_boot_sector(self) -> ExfatGeometry:
        self._fh.seek(0)
        vbr: bytes = self._fh.read(512)
        if len(vbr) < 512:
            raise ExfatError("source too small for an exFAT boot sector")
        if vbr[3:11] != EXFAT_SIGNATURE:
            raise ExfatError("missing exFAT file system signature")
        if struct.unpack_from("<H", vbr, 0x1FE)[0] != 0xAA55:
            raise ExfatError("missing boot signature 0xAA55")
        fat_off, _fat_len, heap_off, cluster_count, root_cluster, serial = struct.unpack_from("<IIIIII", vbr, 0x50)
        bytes_per_sector_shift: int = vbr[0x6C]
        sectors_per_cluster_shift: int = vbr[0x6D]
        if not (9 <= bytes_per_sector_shift <= 12):
            raise ExfatError(f"unsupported bytes-per-sector shift {bytes_per_sector_shift}")
        return ExfatGeometry(
            bytes_per_sector=1 << bytes_per_sector_shift,
            sectors_per_cluster=1 << sectors_per_cluster_shift,
            fat_offset_sectors=fat_off,
            cluster_heap_offset_sectors=heap_off,
            cluster_count=cluster_count,
            root_dir_cluster=root_cluster,
            volume_serial=serial,
        )

    def _cluster_byte_offset(self, cluster: int) -> int:
        geo: ExfatGeometry = self.geometry
        sector: int = geo.cluster_heap_offset_sectors + (cluster - 2) * geo.sectors_per_cluster
        return sector * geo.bytes_per_sector

    def _fat_next(self, cluster: int) -> int:
        geo: ExfatGeometry = self.geometry
        offset: int = geo.fat_offset_sectors * geo.bytes_per_sector + cluster * 4
        self._fh.seek(offset)
        return struct.unpack("<I", self._fh.read(4))[0]

    def _iter_clusters(self, first_cluster: int, no_fat_chain: bool, length: int) -> Iterator[int]:
        """Yield cluster numbers for an allocation.

        Args:
            first_cluster: First cluster (0 when empty).
            no_fat_chain: When True, the allocation is contiguous.
            length: Data length in bytes; 0 means "follow the FAT to end of chain"
                (used for the root and other directories without a known length).
        """
        if first_cluster < 2:
            return
        cluster_size: int = self.geometry.cluster_size
        if no_fat_chain:
            if length <= 0:
                return
            count: int = (length + cluster_size - 1) // cluster_size
            for i in range(count):
                yield first_cluster + i
            return
        remaining: int = (length + cluster_size - 1) // cluster_size if length > 0 else -1
        cluster: int = first_cluster
        seen: int = 0
        while 2 <= cluster < _FAT_END_OF_CHAIN:
            yield cluster
            seen += 1
            if remaining > 0 and seen >= remaining:
                return
            if seen > self.geometry.cluster_count + 2:
                raise ExfatError("cluster chain exceeds volume size (loop?)")
            cluster = self._fat_next(cluster)

    def _read_directory_entries(self, first_cluster: int, no_fat_chain: bool, length: int) -> Iterator[bytes]:
        """Yield 32-byte directory entries from a directory's cluster chain."""
        cluster_size: int = self.geometry.cluster_size
        for cluster in self._iter_clusters(first_cluster, no_fat_chain, length):
            self._fh.seek(self._cluster_byte_offset(cluster))
            data: bytes = self._fh.read(cluster_size)
            for off in range(0, len(data), 32):
                entry: bytes = data[off : off + 32]
                if len(entry) < 32:
                    return
                if entry[0] == _END_OF_DIRECTORY:
                    return
                yield entry

    def _walk_directory(self, first_cluster: int, no_fat_chain: bool, length: int, rel_dir: str) -> list[ExfatEntry]:
        entries: list[ExfatEntry] = []
        pending: list[bytes] = list(self._read_directory_entries(first_cluster, no_fat_chain, length))
        idx: int = 0
        while idx < len(pending):
            entry: bytes = pending[idx]
            entry_type: int = entry[0]
            if entry_type != _ENTRY_FILE:
                idx += 1
                continue

            # A File entry is followed by SecondaryCount secondary entries:
            # one Stream Extension, then the File Name entries holding the name.
            secondary_count: int = entry[1]
            file_attrs: int = struct.unpack_from("<H", entry, 0x04)[0]
            secondaries: list[bytes] = pending[idx + 1 : idx + 1 + secondary_count]
            idx += 1 + secondary_count
            if len(secondaries) < secondary_count or not secondaries:
                continue
            stream: bytes = secondaries[0]
            if stream[0] != _ENTRY_STREAM_EXTENSION:
                continue

            flags: int = stream[1]
            name_length: int = stream[3]
            data_length: int = struct.unpack_from("<Q", stream, 0x18)[0]
            child_cluster: int = struct.unpack_from("<I", stream, 0x14)[0]
            child_no_fat: bool = bool(flags & _SECONDARY_FLAG_NO_FAT_CHAIN)

            name_units: bytearray = bytearray()
            for secondary in secondaries[1:]:
                if secondary[0] == _ENTRY_FILE_NAME:
                    name_units += secondary[2:32]
            name: str = name_units.decode("utf-16-le", errors="replace")[:name_length]

            is_dir: bool = bool(file_attrs & _ATTR_DIRECTORY)
            rel_path: str = f"{rel_dir}/{name}" if rel_dir else name
            node: ExfatEntry = ExfatEntry(
                name=name,
                rel_path=rel_path,
                is_dir=is_dir,
                first_cluster=child_cluster,
                length=data_length,
                no_fat_chain=child_no_fat,
            )
            if is_dir:
                node.children = self._walk_directory(child_cluster, child_no_fat, data_length, rel_path)
            entries.append(node)
        return entries

    def root_entries(self) -> list[ExfatEntry]:
        """Return the directory tree rooted at the volume root."""
        return self._walk_directory(self.geometry.root_dir_cluster, no_fat_chain=False, length=0, rel_dir="")

    def iter_files(self) -> Iterator[ExfatEntry]:
        """Yield every file entry (not directories) in deterministic order."""

        def _walk(nodes: list[ExfatEntry]) -> Iterator[ExfatEntry]:
            for node in sorted(nodes, key=lambda n: n.rel_path.lower()):
                if node.is_dir:
                    yield from _walk(node.children)
                else:
                    yield node

        yield from _walk(self.root_entries())

    def read_file(self, entry: ExfatEntry, chunk_size: int = 4 * 1024 * 1024) -> Iterator[bytes]:
        """Yield the bytes of a file entry, bounded by ``chunk_size`` per yield.

        Args:
            entry: A file entry from :meth:`iter_files` or :meth:`root_entries`.
            chunk_size: Maximum bytes per yielded chunk.

        Yields:
            File data chunks in order; total length equals ``entry.length``.
        """
        if entry.is_dir:
            raise ExfatError(f"not a file: {entry.rel_path}")
        cluster_size: int = self.geometry.cluster_size
        remaining: int = entry.length
        for cluster in self._iter_clusters(entry.first_cluster, entry.no_fat_chain, entry.length):
            if remaining <= 0:
                break
            self._fh.seek(self._cluster_byte_offset(cluster))
            want: int = min(cluster_size, remaining)
            data: bytes = self._fh.read(want)
            remaining -= len(data)
            # Re-chunk to the requested size for bounded memory on large clusters.
            for pos in range(0, len(data), chunk_size):
                yield data[pos : pos + chunk_size]
        if remaining > 0:
            raise ExfatError(f"file '{entry.rel_path}' truncated: {remaining} bytes short")


def render_exfat_tree(entries: list[ExfatEntry], prefix: str = "") -> list[str]:
    """Render an exFAT directory tree as ASCII lines (directories first).

    Args:
        entries: Directory entries at one level (e.g. ``reader.root_entries()``).
        prefix: Internal indentation prefix used during recursion.

    Returns:
        Lines using ``|-- `` / `` `-- `` branch markers, matching the PFS tree style.
    """
    lines: list[str] = []
    ordered: list[ExfatEntry] = sorted(entries, key=lambda e: (not e.is_dir, e.name.lower(), e.name))
    for idx, entry in enumerate(ordered):
        last: bool = idx == len(ordered) - 1
        lines.append(prefix + ("`-- " if last else "|-- ") + entry.name)
        if entry.is_dir:
            lines.extend(render_exfat_tree(entry.children, prefix + ("    " if last else "|   ")))
    return lines


def open_exfat(path: str) -> ExfatReader:
    """Open an exFAT image file for reading.

    Args:
        path: Path to an exFAT image.

    Returns:
        An :class:`ExfatReader` over the opened file. The caller is responsible
        for the process lifetime; the handle stays open for the reader's use.
    """
    fh: BinaryIO = open(path, "rb")  # noqa: SIM115 - reader holds the handle for its lifetime
    return ExfatReader(fh)
