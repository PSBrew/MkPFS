"""AMPR emulation index (``ampr_emu.index``) generation.

This module builds the ``AMPRIDX3`` index consumed by the PS5 AMPR/APR resolver
under emulation. The index maps each game file path (``/app0/<rel>``) to its
size and modification time, with an FNV-1a-64 open-addressed hash table for fast
path lookups. The binary layout is fixed and must stay byte-compatible with the
resolver, so the structures here are intentionally not abstracted away.

The index is written into the source tree before packing so it becomes part of
the resulting PFS image. Generation is gated on the presence of
``fakelib/libSceAmpr.sprx`` in the source root, which signals an emulation build.
"""

from __future__ import annotations

import os
import struct
from pathlib import Path

from .logging import info, warning
from .utils import is_ignored_name

# AMPRIDX3 on-disk structures. Do not change without matching the resolver.
RECORD_STRUCT = struct.Struct("<IIQq")  # path_blob_offset, path_len, size, mtime
HASH_SLOT_STRUCT = struct.Struct("<QII")  # fnv1a64 hash, record_index + 1, flags
HEADER_STRUCT = struct.Struct("<8sIIQQQII")  # magic, version, record_size, num_rows, ...

AMPR_INDEX_NAME = "ampr_emu.index"
AMPR_FAKELIB_MARKER = Path("fakelib") / "libSceAmpr.sprx"
_AMPR_MAGIC = b"AMPRIDX3"
_AMPR_VERSION = 3
_FNV_OFFSET_BASIS = 1469598103934665603
_FNV_PRIME = 1099511628211
_UINT64_MASK = 0xFFFFFFFFFFFFFFFF
_DUPLICATE_FLAG = 1


def ampr_key_for(path: str) -> str:
    """Normalize a path for hashing and collision detection.

    Args:
        path: Raw path string.

    Returns:
        The path with backslashes converted to forward slashes and lowercased.
    """
    return path.replace("\\", "/").lower()


def fnv1a64_path_hash(path: str) -> int:
    """Compute the FNV-1a 64-bit hash used by the APR resolver.

    Args:
        path: Path string; normalized via :func:`ampr_key_for` before hashing.

    Returns:
        The 64-bit hash, never zero (zero is remapped to ``1`` so empty slots
        stay distinguishable).
    """
    h: int = _FNV_OFFSET_BASIS
    for ch in ampr_key_for(path):
        h ^= ord(ch)
        h = (h * _FNV_PRIME) & _UINT64_MASK
    return h or 1


def ampr_hash_slot_count(entry_count: int) -> int:
    """Return the power-of-two hash slot count for ``entry_count`` entries.

    Args:
        entry_count: Number of indexed records.

    Returns:
        The smallest power of two that is at least ``2 * entry_count`` (minimum
        2), or 0 when there are no entries.
    """
    if entry_count <= 0:
        return 0
    slots: int = 2
    target: int = entry_count * 2
    while slots < target:
        slots <<= 1
    return slots


def build_ampr_hash_slots(rows: list[tuple[int, int, str]]) -> list[tuple[int, int, int]]:
    """Build open-addressed hash slots with linear probing.

    Args:
        rows: Indexed rows as ``(size, mtime, indexed_path)`` tuples in record order.

    Returns:
        A list of ``(hash, record_index + 1, flags)`` slots. Empty slots are
        ``(0, 0, 0)``; the duplicate flag is set on a slot whose hash collides
        with a later identical hash.
    """
    slots: list[tuple[int, int, int]] = [(0, 0, 0) for _ in range(ampr_hash_slot_count(len(rows)))]
    if not slots:
        return slots
    mask: int = len(slots) - 1

    for index, (_size, _mtime, path) in enumerate(rows):
        h: int = fnv1a64_path_hash(path)
        pos: int = h & mask
        while slots[pos][1] != 0:
            if slots[pos][0] == h:
                old_hash, old_index_plus_one, old_flags = slots[pos]
                slots[pos] = (old_hash, old_index_plus_one, old_flags | _DUPLICATE_FLAG)
            pos = (pos + 1) & mask
        slots[pos] = (h, index + 1, 0)

    return slots


def build_ampr_index(root: Path, output_path: Path) -> int:
    """Write the AMPRIDX3 index for ``root`` to ``output_path``.

    Scans the source tree, records each file as ``/app0/<rel>`` with its size and
    mtime, and emits the records, path blob, and FNV-1a hash table atomically.

    Args:
        root: Source tree to index.
        output_path: Destination ``ampr_emu.index`` path.

    Returns:
        The number of file records written (0 when the tree has no files).

    Raises:
        ValueError: If the path blob exceeds the 32-bit offset/length limits.
    """
    root = root.resolve()
    output_path = output_path.resolve()
    output_tmp: Path = output_path.with_suffix(output_path.suffix + ".tmp")

    seen: dict[str, str] = {}
    rows: list[tuple[int, int, str]] = []  # (size, mtime, indexed_path)

    # Scan files deterministically (case-insensitive order), skipping the index
    # itself and OS-generated metadata (consistent with what gets packed).
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = sorted((d for d in dirnames if not is_ignored_name(d)), key=str.lower)
        filenames.sort(key=str.lower)
        for filename in filenames:
            if is_ignored_name(filename):
                continue
            path: Path = Path(dirpath) / filename
            try:
                resolved: Path = path.resolve()
            except OSError:
                continue
            if resolved in (output_path, output_tmp):
                continue
            rel: str = path.relative_to(root).as_posix()
            indexed_path: str = "/app0/" + rel
            if ampr_key_for(indexed_path) in (f"/app0/{AMPR_INDEX_NAME}", f"/app0/{AMPR_INDEX_NAME}.tmp"):
                continue
            try:
                stat = path.stat()
            except OSError:
                continue
            if not path.is_file():
                continue
            key: str = ampr_key_for(indexed_path)
            if key in seen:
                continue  # keep first on case-insensitive collision
            seen[key] = indexed_path
            rows.append((stat.st_size, int(stat.st_mtime), indexed_path))

    if not rows:
        return 0

    rows = sorted(rows, key=lambda row: ampr_key_for(row[2]))

    # Build the path blob and fixed-size records that reference offsets into it.
    path_blob: bytearray = bytearray()
    records: bytearray = bytearray()
    for size, mtime, path_str in rows:
        encoded: bytes = path_str.encode("utf-8") + b"\0"
        offset: int = len(path_blob)
        path_len: int = len(encoded) - 1
        if offset > 0xFFFFFFFF or path_len > 0xFFFFFFFF:
            raise ValueError("AMPR index path blob is too large")
        records += RECORD_STRUCT.pack(offset, path_len, size, mtime)
        path_blob += encoded

    hash_slots: list[tuple[int, int, int]] = build_ampr_hash_slots(rows)

    # The hash table is aligned to the slot size after the header, records, and blob.
    path_end: int = HEADER_STRUCT.size + len(records) + len(path_blob)
    hash_offset: int = (path_end + (HASH_SLOT_STRUCT.size - 1)) & ~(HASH_SLOT_STRUCT.size - 1)
    padding: bytes = b"\0" * (hash_offset - path_end)

    with output_tmp.open("wb") as out:
        out.write(
            HEADER_STRUCT.pack(
                _AMPR_MAGIC,
                _AMPR_VERSION,
                RECORD_STRUCT.size,
                len(rows),
                len(path_blob),
                hash_offset,
                HASH_SLOT_STRUCT.size,
                len(hash_slots),
            )
        )
        out.write(records)
        out.write(path_blob)
        out.write(padding)
        for h, index_plus_one, flags in hash_slots:
            out.write(HASH_SLOT_STRUCT.pack(h, index_plus_one, flags))

    output_tmp.replace(output_path)
    return len(rows)


def validate_ampr_index(index_path: Path, source_root: Path) -> bool:
    """Validate an existing AMPR index file against the current source tree.

    Performs header sanity checks (magic, version, bounds) plus a lightweight
    row-count comparison against the source tree. The count-only walk is
    substantially cheaper than :func:`build_ampr_index` because it avoids
    per-file ``stat`` for size/mtime, sorting, path encoding, and hash-table
    building.

    Args:
        index_path: Path to the ``ampr_emu.index`` file.
        source_root: Source tree the index is expected to represent.

    Returns:
        ``True`` when the index passes validation, ``False`` otherwise.
    """
    if not index_path.is_file():
        return False
    try:
        data: bytes = index_path.read_bytes()
    except OSError:
        return False

    if len(data) < HEADER_STRUCT.size:
        return False

    (magic, version, record_size, num_rows, path_blob_len, hash_offset, hash_slot_size, num_hash_slots) = (
        HEADER_STRUCT.unpack_from(data, 0)
    )

    if magic != _AMPR_MAGIC or version != _AMPR_VERSION:
        return False
    if record_size != RECORD_STRUCT.size:
        return False
    if num_rows <= 0 or path_blob_len <= 0:
        return False
    if hash_slot_size != HASH_SLOT_STRUCT.size:
        return False
    if num_hash_slots <= 0:
        return False
    # Verify hash_offset is past the records+path blob region (structural layout
    # consistency).  A corrupted header with a hash_offset that falls inside the
    # records or path-blob area would otherwise pass the bounds check above.
    records_end: int = HEADER_STRUCT.size + num_rows * record_size
    path_end: int = records_end + path_blob_len
    if hash_offset < path_end:
        return False
    if hash_offset % hash_slot_size != 0:
        return False
    expected_tail: int = hash_offset + num_hash_slots * hash_slot_size
    if len(data) < expected_tail:
        return False

    # Count indexable files for a lightweight staleness check against
    # the recorded row count.  This mirrors what ``build_ampr_index``
    # indexes without the per-file stat/sort/encoding overhead.
    live_count: int = 0
    seen_keys: set[str] = set()
    try:
        resolved_index: Path = index_path.resolve()
        resolved_tmp: Path = index_path.with_suffix(index_path.suffix + ".tmp").resolve()
        index_name_key: str = ampr_key_for(f"/app0/{AMPR_INDEX_NAME}")
        index_tmp_key: str = ampr_key_for(f"/app0/{AMPR_INDEX_NAME}.tmp")
        for dirpath, dirnames, filenames in os.walk(source_root):
            dirnames[:] = sorted((d for d in dirnames if not is_ignored_name(d)), key=str.lower)
            for filename in filenames:
                if is_ignored_name(filename):
                    continue
                path: Path = Path(dirpath) / filename
                try:
                    resolved: Path = path.resolve()
                except OSError:
                    continue
                if resolved in (resolved_index, resolved_tmp):
                    continue
                if not resolved.is_file():
                    continue
                # Also skip any file whose indexed path key matches the index
                # name (mirrors build's ampr_key_for check at L155-156).
                try:
                    key_rel: str = path.relative_to(source_root).as_posix()
                    key_candidate: str = ampr_key_for(f"/app0/{key_rel}")
                except ValueError:
                    continue
                if key_candidate in (index_name_key, index_tmp_key):
                    continue
                if key_candidate in seen_keys:
                    continue  # case-insensitive collision, keep first
                seen_keys.add(key_candidate)
                live_count += 1
    except OSError:
        return False

    return live_count == num_rows


def ensure_ampr_index(
    source_root: Path,
    *,
    enabled: bool = True,
    create_if_missing: bool = False,
    force_regen: bool = False,
    validate: bool = True,
) -> Path | None:
    """Generate ``ampr_emu.index`` in ``source_root`` when an emulation build needs it.

    Regenerates the index whenever enabled and the marker ``fakelib/libSceAmpr.sprx``
    exists. The rebuild is metadata-only (a directory walk plus per-file ``stat``),
    so it always refreshes the index to match the current tree rather than trusting a
    possibly stale existing file. When disabled, any existing index is left untouched.

    With ``create_if_missing=True``, generation is skipped when a valid index already
    exists, making repeated builds faster. Pass ``force_regen=True`` to override this
    and always rebuild. The ``validate`` parameter controls whether an existing index
    is sanity-checked before skipping.

    Args:
        source_root: Source tree to index and write into.
        enabled: When False, do nothing (preserving any existing index).
        create_if_missing: When True, skip regeneration if a valid index file exists.
        force_regen: When True, always regenerate even when ``create_if_missing`` is set.
        validate: When True (default) and ``create_if_missing`` is active, perform a
            lightweight validation (header sanity + row-count comparison) on the
            existing index before skipping.


    Returns:
        The index path when generated, otherwise ``None``.
    """
    if not enabled:
        return None
    index_path: Path = source_root / AMPR_INDEX_NAME
    if not (source_root / AMPR_FAKELIB_MARKER).exists():
        return None

    # Skip regeneration when an existing index is valid and caller opted in.
    if create_if_missing and not force_regen and index_path.exists():
        if not validate or validate_ampr_index(index_path, source_root):
            info(f"{AMPR_INDEX_NAME} valid and present; skipping generation (create_if_missing)")
            return None
        warning(f"{AMPR_INDEX_NAME} failed validation; regenerating...")

    info(f"Detected {AMPR_FAKELIB_MARKER.as_posix()}; generating {AMPR_INDEX_NAME}...")
    try:
        record_count: int = build_ampr_index(source_root, index_path)
    except (OSError, ValueError) as exc:
        warning(f"Failed to generate {AMPR_INDEX_NAME}: {exc}")
        return None
    info(f"Generated {AMPR_INDEX_NAME} with {record_count} entries")
    return index_path
