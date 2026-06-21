"""Forward-only exFAT image serializer.

Builds a valid exFAT volume from a source directory by computing the entire
layout up front (all file sizes are known after scanning), then emitting the
image strictly in offset order: boot regions, FAT, then the cluster heap
(allocation bitmap, up-case table, root directory, and each directory/file laid
out contiguously). Because nothing is written out of order, the byte stream can
be consumed straight into the compressor with no temporary image.

Allocation is contiguous per node and the FAT carries an explicit chain for each
run (the widely compatible form). OS-generated metadata is excluded at scan time.
"""

from __future__ import annotations

import os
import struct
from collections.abc import Callable, Iterator
from dataclasses import dataclass, field
from pathlib import Path

from ._exfat_upcase import UPCASE_CHECKSUM, UPCASE_TABLE
from .pbar import Progress
from .utils import default_image_basename, is_ignored_name

BYTES_PER_SECTOR: int = 512
BYTES_PER_SECTOR_SHIFT: int = 9
_FAT_OFFSET_SECTORS: int = 128  # leave aligned room before the FAT (matches newfs_exfat)
_NUMBER_OF_FATS: int = 1
_FAT_ENTRY_EOC: int = 0xFFFFFFFF
_FAT_ENTRY_MEDIA: int = 0xFFFFFFF8
_DEFAULT_CLUSTER_SIZE: int = 32 * 1024
_LARGE_CLUSTER_SIZE: int = 64 * 1024
_LARGE_FILE_THRESHOLD: int = 1024 * 1024
_VOLUME_SERIAL: int = 0x4D6B5046  # "MkPF"; fixed for deterministic output
_FIXED_TIMESTAMP: int = (2024 - 1980) << 25 | 1 << 21 | 1 << 16  # 2024-01-01 00:00:00

_ATTR_DIRECTORY: int = 0x10
_ATTR_ARCHIVE: int = 0x20
_FLAG_ALLOCATION_POSSIBLE: int = 0x01
_NAME_CHARS_PER_ENTRY: int = 15
_BITMAP_FIRST_CLUSTER: int = 2


def _ceil_div(a: int, b: int) -> int:
    return (a + b - 1) // b


def _align_up(value: int, alignment: int) -> int:
    return _ceil_div(value, alignment) * alignment


@dataclass
class _Node:
    """A directory or file in the source tree with its assigned allocation."""

    rel_path: str
    name: str
    is_dir: bool
    size: int = 0
    abs_path: Path | None = None
    children: list[_Node] = field(default_factory=list)
    first_cluster: int = 0
    cluster_count: int = 0


def _scan_tree(root: Path) -> _Node:
    """Build the directory tree, sorted and with OS metadata excluded."""
    root_node = _Node(rel_path="", name="", is_dir=True)

    def _walk(dir_path: Path, node: _Node) -> None:
        entries = sorted(
            (e for e in os.scandir(dir_path) if not is_ignored_name(e.name)),
            key=lambda e: e.name.lower(),
        )
        for entry in entries:
            if entry.is_dir(follow_symlinks=False):
                child = _Node(
                    rel_path=f"{node.rel_path}/{entry.name}" if node.rel_path else entry.name,
                    name=entry.name,
                    is_dir=True,
                )
                node.children.append(child)
                _walk(Path(entry.path), child)
            elif entry.is_file(follow_symlinks=False):
                node.children.append(
                    _Node(
                        rel_path=f"{node.rel_path}/{entry.name}" if node.rel_path else entry.name,
                        name=entry.name,
                        is_dir=False,
                        size=entry.stat().st_size,
                        abs_path=Path(entry.path),
                    )
                )

    _walk(root, root_node)
    return root_node


def _choose_cluster_size(root: _Node) -> int:
    total: int = 0
    count: int = 0

    def _accum(node: _Node) -> None:
        nonlocal total, count
        for child in node.children:
            if child.is_dir:
                _accum(child)
            else:
                total += child.size
                count += 1

    _accum(root)
    avg: int = total // count if count else 0
    return _LARGE_CLUSTER_SIZE if avg >= _LARGE_FILE_THRESHOLD else _DEFAULT_CLUSTER_SIZE


def _directory_entry_count(node: _Node, *, is_root: bool) -> int:
    """Number of 32-byte directory entries a directory occupies."""
    count: int = 3 if is_root else 0  # root adds Volume Label + Bitmap + Up-case entries
    for child in node.children:
        name_entries: int = _ceil_div(len(child.name), _NAME_CHARS_PER_ENTRY)
        count += 2 + name_entries  # File entry + Stream Extension + File Name entries
    return count


def _assign_clusters(root: _Node, cluster_size: int) -> tuple[int, int, int, int]:
    """Assign contiguous cluster runs to every node and the metadata regions.

    Returns ``(bitmap_clusters, upcase_clusters, cluster_count, root_cluster)``.
    """
    upcase_clusters: int = _ceil_div(len(UPCASE_TABLE), cluster_size)

    # Cluster count for every directory/file is fixed by sizes; sum it once.
    def _node_clusters(node: _Node, *, is_root: bool) -> int:
        if node.is_dir:
            return max(1, _ceil_div(_directory_entry_count(node, is_root=is_root) * 32, cluster_size))
        return _ceil_div(node.size, cluster_size)

    content_clusters: int = _node_clusters(root, is_root=True)

    def _accum(node: _Node) -> None:
        nonlocal content_clusters
        for child in node.children:
            content_clusters += _node_clusters(child, is_root=False)
            if child.is_dir:
                _accum(child)

    _accum(root)
    content_clusters += upcase_clusters

    # Solve for the bitmap size (the bitmap must cover itself plus all content).
    bitmap_clusters: int = 1
    while True:
        cluster_count: int = bitmap_clusters + content_clusters
        need: int = _ceil_div(_ceil_div(cluster_count, 8), cluster_size)
        if need == bitmap_clusters:
            break
        bitmap_clusters = need
    cluster_count = bitmap_clusters + content_clusters

    # Lay out clusters: bitmap, up-case, root, then the tree in pre-order.
    next_cluster: int = _BITMAP_FIRST_CLUSTER + bitmap_clusters + upcase_clusters
    root.first_cluster = next_cluster
    root.cluster_count = _node_clusters(root, is_root=True)
    next_cluster += root.cluster_count

    def _assign(node: _Node) -> None:
        nonlocal next_cluster
        for child in node.children:
            child.cluster_count = _node_clusters(child, is_root=False)
            if child.cluster_count and not (not child.is_dir and child.size == 0):
                child.first_cluster = next_cluster
                next_cluster += child.cluster_count
            if child.is_dir:
                _assign(child)

    _assign(root)
    return bitmap_clusters, upcase_clusters, cluster_count, root.first_cluster


def _upcase_ascii(name: str) -> str:
    return name.upper()  # source names are ASCII; matches the up-case table over that range


def _name_hash(name: str) -> int:
    h: int = 0
    for byte in _upcase_ascii(name).encode("utf-16-le"):
        h = (((h << 15) | (h >> 1)) & 0xFFFF) + byte
        h &= 0xFFFF
    return h


def _entry_set_checksum(entries: bytes) -> int:
    cs: int = 0
    for i, byte in enumerate(entries):
        if i in (2, 3):  # SetChecksum field in the File directory entry
            continue
        cs = (((cs << 15) | (cs >> 1)) & 0xFFFF) + byte
        cs &= 0xFFFF
    return cs


def _build_file_entry_set(child: _Node, cluster_size: int) -> bytes:
    name_entries: int = _ceil_div(len(child.name), _NAME_CHARS_PER_ENTRY)
    secondary_count: int = 1 + name_entries
    data_length: int = child.cluster_count * cluster_size if child.is_dir else child.size
    attrs: int = _ATTR_DIRECTORY if child.is_dir else _ATTR_ARCHIVE
    has_alloc: bool = child.first_cluster >= 2

    file_entry: bytearray = bytearray(32)
    file_entry[0] = 0x85
    file_entry[1] = secondary_count
    struct.pack_into("<H", file_entry, 0x04, attrs)
    struct.pack_into("<III", file_entry, 0x08, _FIXED_TIMESTAMP, _FIXED_TIMESTAMP, _FIXED_TIMESTAMP)

    stream: bytearray = bytearray(32)
    stream[0] = 0xC0
    stream[1] = _FLAG_ALLOCATION_POSSIBLE if has_alloc else 0x00
    stream[3] = len(child.name)
    struct.pack_into("<H", stream, 0x04, _name_hash(child.name))
    struct.pack_into("<Q", stream, 0x08, data_length)
    struct.pack_into("<I", stream, 0x14, child.first_cluster if has_alloc else 0)
    struct.pack_into("<Q", stream, 0x18, data_length)

    name_bytes: bytes = child.name.encode("utf-16-le")
    name_entry_blob: bytearray = bytearray()
    for i in range(name_entries):
        entry: bytearray = bytearray(32)
        entry[0] = 0xC1
        chunk: bytes = name_bytes[i * 30 : (i + 1) * 30]
        entry[2 : 2 + len(chunk)] = chunk
        name_entry_blob += entry

    entry_set: bytes = bytes(file_entry) + bytes(stream) + bytes(name_entry_blob)
    struct.pack_into("<H", file_entry, 0x02, _entry_set_checksum(entry_set))
    return bytes(file_entry) + bytes(stream) + bytes(name_entry_blob)


def _build_directory_bytes(
    node: _Node, cluster_size: int, *, is_root: bool, bitmap_clusters: int, upcase_clusters: int, cluster_count: int
) -> bytes:
    out: bytearray = bytearray()
    if is_root:
        label: bytearray = bytearray(32)
        label[0] = 0x83  # Volume Label, empty
        out += label

        bitmap: bytearray = bytearray(32)
        bitmap[0] = 0x81
        struct.pack_into("<I", bitmap, 0x14, _BITMAP_FIRST_CLUSTER)
        struct.pack_into("<Q", bitmap, 0x18, _ceil_div(cluster_count, 8))
        out += bitmap

        upcase: bytearray = bytearray(32)
        upcase[0] = 0x82
        struct.pack_into("<I", upcase, 0x04, UPCASE_CHECKSUM)
        struct.pack_into("<I", upcase, 0x14, _BITMAP_FIRST_CLUSTER + bitmap_clusters)
        struct.pack_into("<Q", upcase, 0x18, len(UPCASE_TABLE))
        out += upcase

    for child in node.children:
        out += _build_file_entry_set(child, cluster_size)
    # Remaining bytes in the directory's clusters stay zero (end-of-directory).
    return bytes(out)


def _build_boot_region(
    volume_length: int,
    fat_offset: int,
    fat_length: int,
    heap_offset: int,
    cluster_count: int,
    root_cluster: int,
    spc_shift: int,
) -> bytes:
    """Build the 12-sector main boot region (sector 12 onward is its backup copy)."""
    vbr: bytearray = bytearray(BYTES_PER_SECTOR)
    vbr[0:3] = b"\xeb\x76\x90"
    vbr[3:11] = b"EXFAT   "
    struct.pack_into("<Q", vbr, 64, 0)  # PartitionOffset
    struct.pack_into("<Q", vbr, 72, volume_length)
    struct.pack_into("<I", vbr, 80, fat_offset)
    struct.pack_into("<I", vbr, 84, fat_length)
    struct.pack_into("<I", vbr, 88, heap_offset)
    struct.pack_into("<I", vbr, 92, cluster_count)
    struct.pack_into("<I", vbr, 96, root_cluster)
    struct.pack_into("<I", vbr, 100, _VOLUME_SERIAL)
    struct.pack_into("<H", vbr, 104, 0x0100)  # FileSystemRevision 1.00
    struct.pack_into("<H", vbr, 106, 0)  # VolumeFlags
    vbr[108] = BYTES_PER_SECTOR_SHIFT
    vbr[109] = spc_shift
    vbr[110] = _NUMBER_OF_FATS
    vbr[111] = 0x80  # DriveSelect
    vbr[112] = 0xFF  # PercentInUse = not available
    struct.pack_into("<H", vbr, 510, 0xAA55)

    region: bytearray = bytearray()
    region += vbr
    # Extended boot sectors 1..8: boot code zero, ExtendedBootSignature 0xAA550000 at the tail.
    for _ in range(8):
        ext: bytearray = bytearray(BYTES_PER_SECTOR)
        struct.pack_into("<I", ext, BYTES_PER_SECTOR - 4, 0xAA550000)
        region += ext
    region += bytearray(BYTES_PER_SECTOR)  # OEM parameters (sector 9)
    region += bytearray(BYTES_PER_SECTOR)  # reserved (sector 10)

    checksum: int = 0
    for i in range(11 * BYTES_PER_SECTOR):
        if i in (106, 107, 112):  # VolumeFlags + PercentInUse are excluded
            continue
        checksum = (((checksum << 31) | (checksum >> 1)) & 0xFFFFFFFF) + region[i]
        checksum &= 0xFFFFFFFF
    region += struct.pack("<I", checksum) * (BYTES_PER_SECTOR // 4)  # checksum sector (11)
    return bytes(region)


def _build_fat(
    root: _Node, bitmap_clusters: int, upcase_clusters: int, cluster_count: int, fat_length_bytes: int
) -> bytes:
    """Build the FAT with an explicit chain for every contiguous run."""
    fat: bytearray = bytearray(fat_length_bytes)
    struct.pack_into("<I", fat, 0, _FAT_ENTRY_MEDIA)
    struct.pack_into("<I", fat, 4, _FAT_ENTRY_EOC)

    def _chain(first: int, count: int) -> None:
        for i in range(count - 1):
            struct.pack_into("<I", fat, (first + i) * 4, first + i + 1)
        struct.pack_into("<I", fat, (first + count - 1) * 4, _FAT_ENTRY_EOC)

    _chain(_BITMAP_FIRST_CLUSTER, bitmap_clusters)
    _chain(_BITMAP_FIRST_CLUSTER + bitmap_clusters, upcase_clusters)

    def _walk(node: _Node) -> None:
        if node.first_cluster >= 2 and node.cluster_count:
            _chain(node.first_cluster, node.cluster_count)
        for child in node.children:
            _walk(child)

    _walk(root)
    return bytes(fat)


def iter_exfat_image(
    source_root: Path,
    cluster_size: int | None = None,
    on_layout: Callable[[int], None] | None = None,
) -> Iterator[bytes]:
    """Yield a complete exFAT image for ``source_root`` in strict offset order.

    Args:
        source_root: Directory whose contents become the volume root.
        cluster_size: Optional cluster size in bytes; chosen by file-size policy
            when omitted (32 KiB, or 64 KiB for large-average-file trees).
        on_layout: Optional callback invoked once with the total image size in
            bytes before any chunk is yielded (useful for progress reporting).

    Yields:
        Image byte chunks in increasing offset order; concatenation is the volume.
    """
    root: _Node = _scan_tree(source_root)
    cluster_size = cluster_size or _choose_cluster_size(root)
    spc: int = cluster_size // BYTES_PER_SECTOR
    spc_shift: int = (cluster_size // BYTES_PER_SECTOR).bit_length() - 1

    bitmap_clusters, upcase_clusters, cluster_count, root_cluster = _assign_clusters(root, cluster_size)

    fat_entries: int = cluster_count + 2
    fat_length_sectors: int = _align_up(_ceil_div(fat_entries * 4, BYTES_PER_SECTOR), spc)
    heap_offset: int = _align_up(_FAT_OFFSET_SECTORS + fat_length_sectors * _NUMBER_OF_FATS, spc)
    volume_length: int = heap_offset + cluster_count * spc

    if on_layout is not None:
        on_layout(volume_length * BYTES_PER_SECTOR)

    # 1. Boot region + its backup copy.
    boot: bytes = _build_boot_region(
        volume_length, _FAT_OFFSET_SECTORS, fat_length_sectors, heap_offset, cluster_count, root_cluster, spc_shift
    )
    yield boot  # main (sectors 0..11)
    yield boot  # backup (sectors 12..23)

    # 2. Pad to the FAT, then the FAT, then pad to the cluster heap.
    yield bytes((_FAT_OFFSET_SECTORS - 24) * BYTES_PER_SECTOR)
    yield _build_fat(root, bitmap_clusters, upcase_clusters, cluster_count, fat_length_sectors * BYTES_PER_SECTOR)
    pad_to_heap: int = (heap_offset - (_FAT_OFFSET_SECTORS + fat_length_sectors * _NUMBER_OF_FATS)) * BYTES_PER_SECTOR
    if pad_to_heap:
        yield bytes(pad_to_heap)

    # 3. Cluster heap, in cluster order: bitmap, up-case, root, then the tree.
    bitmap_bytes: int = _ceil_div(cluster_count, 8)
    bitmap: bytearray = bytearray(_align_up(bitmap_bytes, cluster_size))
    for bit in range(cluster_count):  # every heap cluster is allocated (tight image)
        bitmap[bit // 8] |= 1 << (bit % 8)
    yield bytes(bitmap)

    upcase_padded: int = upcase_clusters * cluster_size
    yield UPCASE_TABLE + bytes(upcase_padded - len(UPCASE_TABLE))

    def _emit_dir_bytes(node: _Node, *, is_root: bool) -> bytes:
        body: bytes = _build_directory_bytes(
            node,
            cluster_size,
            is_root=is_root,
            bitmap_clusters=bitmap_clusters,
            upcase_clusters=upcase_clusters,
            cluster_count=cluster_count,
        )
        return body + bytes(node.cluster_count * cluster_size - len(body))

    yield _emit_dir_bytes(root, is_root=True)

    # Emit remaining nodes in the same pre-order used for assignment.
    def _emit(node: _Node) -> Iterator[bytes]:
        for child in node.children:
            if child.is_dir:
                yield _emit_dir_bytes(child, is_root=False)
                yield from _emit(child)
            elif child.size > 0:
                assert child.abs_path is not None
                written: int = 0
                with child.abs_path.open("rb") as fh:
                    while True:
                        chunk: bytes = fh.read(1024 * 1024)
                        if not chunk:
                            break
                        written += len(chunk)
                        yield chunk
                padding: int = child.cluster_count * cluster_size - written
                if padding:
                    yield bytes(padding)

    yield from _emit(root)


def write_exfat_image(
    source_root: Path,
    output_path: Path,
    cluster_size: int | None = None,
    progress: Progress | None = None,
) -> Path:
    """Write a complete exFAT image and return the path written.

    Args:
        source_root: Directory whose contents become the volume root.
        output_path: Destination image path, or an existing directory in which to
            create ``<titleId>.exfat`` (the title ID comes from
            ``sce_sys/param.json``, falling back to the source folder name).
        cluster_size: Optional cluster size in bytes (auto-selected when omitted).
        progress: Optional progress reporter, updated by bytes written.

    Returns:
        The path of the written image.
    """
    if output_path.is_dir():
        output_path = output_path / f"{default_image_basename(source_root)}.exfat"

    total: int = 0
    written: int = 0
    last_reported: int = 0
    update_interval: int = 8 * 1024 * 1024

    def on_layout(size: int) -> None:
        nonlocal total
        total = size
        if progress is not None:
            progress.step("exfat", 0, max(size, 1), bytes_processed=0)

    with output_path.open("wb") as out:
        for chunk in iter_exfat_image(source_root, cluster_size=cluster_size, on_layout=on_layout):
            out.write(chunk)
            written += len(chunk)
            if progress is not None and written - last_reported >= update_interval:
                last_reported = written
                progress.step("exfat", min(written, total), max(total, 1), bytes_processed=written)
    if progress is not None:
        progress.step("exfat", max(total, 1), max(total, 1), bytes_processed=written)
    return output_path
