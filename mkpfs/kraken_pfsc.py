"""Kraken PFSC v3 encoder/decoder.

This module implements a conservative, license-free Python writer for the
PS5 PFSv3 "PFSC" container. It supports two usage modes:

- Stored-only writer (default): emits blocks uncompressed so round-trip
  validation is possible without Oodle.
- Optional encoder callback: callers may pass an `encode_block_fn(block_bytes, level)`
  callable that returns compressed bytes for a block. The writer applies the
  same keep-compressed heuristic used by LibProsperoPKG and falls back to
  stored blocks when compression is not beneficial.

The decoder understands both stored and Kraken-compressed blocks and will
attempt to call the Oodle runtime lazily when a compressed block is
encountered. If Oodle is not available an ImportError with actionable advice
is raised.
"""

from __future__ import annotations

import hashlib
import struct
from typing import Callable

from .logging import warning

# Constants matching LibProsperoPKG's writer
MAGIC = 0x43534650  # 'PFSC' little-endian bytes == b'PFSC'
HEADER_SIZE = 0x48
DIRECTORY_ENTRY_SIZE = 16
SECTION_COUNT = 7
SECTION_ALIGNMENT = 8
DATA_ALIGNMENT = 0x400
DIGEST_LENGTH = 32

ENCODE_PARAM_0C = 0x0802
ALGORITHM_KRAKEN = 2
KRAKEN_WINDOW_BITS = 18

STORED_FLAG_BASE = 0x0C
STORED_FLAG_LARGE_HALF = 0xC0
COMPRESSED_FLAG = 0x06
MULTICHUNK_FLAG = 0x20
BOUNDARY_FLAG_SHIFT = 48
SIZE_HINT_SHIFT = 44
SIZE_HINT_MAX = 0x1FFFF

# Git hash (id=1) and shuffle table (id=2) copied verbatim from the reference writer
_GIT_HASH = bytes(
    [
        0x23,
        0x98,
        0x7D,
        0x16,
        0xC9,
        0x20,
        0x9A,
        0xC7,
        0x28,
        0x37,
        0x19,
        0x32,
        0x7E,
        0x0F,
        0x50,
        0x6B,
        0xBC,
        0xF4,
        0x59,
        0xF4,
    ]
)

_SHUFFLE_TABLE = bytes(
    [
        0x04,
        0x04,
        0x00,
        0x00,
        0x00,
        0x00,
        0x00,
        0x00,
        0x02,
        0x02,
        0x04,
        0x00,
        0x00,
        0x00,
        0x00,
        0x00,
        0x01,
        0x01,
        0x06,
        0x00,
        0x00,
        0x00,
        0x00,
        0x00,
        0x01,
        0x01,
        0x01,
        0x01,
        0x01,
        0x01,
        0x01,
        0x01,
        0x08,
        0x02,
        0x02,
        0x04,
        0x00,
        0x00,
        0x00,
        0x00,
        0x01,
        0x01,
        0x06,
        0x02,
        0x02,
        0x04,
        0x00,
        0x00,
        0x01,
        0x01,
        0x06,
        0x01,
        0x01,
        0x06,
        0x00,
        0x00,
        0x04,
        0x04,
        0x04,
        0x04,
        0x00,
        0x00,
        0x00,
        0x00,
    ]
)


def _align(value: int, alignment: int) -> int:
    return (value + alignment - 1) & ~(alignment - 1)


def compute_block_digest(uncompressed_block: bytes) -> bytes:
    """SHA3-256 digest of an uncompressed block (32 bytes)."""
    h = hashlib.sha3_256()
    h.update(uncompressed_block)
    return h.digest()


def compute_file_digest(
    header_params: bytes, shuffle_section: bytes, boundary_section: bytes, block_hash_section: bytes
) -> bytes:
    """Compute the container's file-level SHA3-256 digest.

    header_params must be exactly 24 bytes (container[0x08..0x20]).
    The preimage is header32 || shuffleSection || boundarySection || blockHashSection
    where header32 is the 32-byte structure used by the reference writer.
    """
    if len(header_params) != 24:
        raise ValueError("header_params must be exactly 24 bytes")

    header32 = bytearray(32)
    struct.pack_into("<I", header32, 0, 1)
    header32[4:12] = header_params[0:8]
    # bytes 12..16 are zero
    header32[16:32] = header_params[8:24]

    h = hashlib.sha3_256()
    h.update(header32)
    h.update(shuffle_section)
    h.update(boundary_section)
    h.update(block_hash_section)
    return h.digest()


def _write_directory_entry(buf: bytearray, index: int, id_: int, offset: int, size: int) -> None:
    p = HEADER_SIZE + index * DIRECTORY_ENTRY_SIZE
    struct.pack_into("<H", buf, p, id_)
    struct.pack_into("<I", buf, p + 2, offset)
    struct.pack_into("<I", buf, p + 10, size)


def encode_pfsc_kraken_payload(
    payload: bytes,
    level: int = 7,
    block_size: int = 0x40000,
    encode_block_fn: Callable[[bytes, int], bytes] | None = None,
) -> bytes:
    """Build a PFSv3 PFSC container for `payload`.

    When `encode_block_fn` is provided it is called as `encode_block_fn(block_bytes, level)`
    and must return compressed bytes for the logical block. The writer applies the
    keep-compressed heuristic (keep only when compressed_size <= (uncomp_size * 15) >> 4)
    and falls back to storing the raw block when compression is not beneficial or
    when the compressor raises an error.
    """
    if block_size <= 0:
        raise ValueError("block_size must be positive")

    payload_len = len(payload)
    block_count = 1 if payload_len == 0 else (payload_len + block_size - 1) // block_size

    sec1_size = len(_GIT_HASH)
    sec2_size = len(_SHUFFLE_TABLE)
    sec3_size = (block_count + 1) * DIRECTORY_ENTRY_SIZE
    sec4_size = block_count * DIGEST_LENGTH
    sec5_size = block_count * DIRECTORY_ENTRY_SIZE

    off1 = HEADER_SIZE + SECTION_COUNT * DIRECTORY_ENTRY_SIZE
    off2 = _align(off1 + sec1_size, SECTION_ALIGNMENT)
    off3 = _align(off2 + sec2_size, SECTION_ALIGNMENT)
    off4 = _align(off3 + sec3_size, SECTION_ALIGNMENT)
    off5 = _align(off4 + sec4_size, SECTION_ALIGNMENT)
    off6 = _align(off5 + sec5_size, SECTION_ALIGNMENT)
    off7 = _align(off6, DATA_ALIGNMENT)

    # Allocate with the stored-path upper bound (data section <= payload_len)
    total_alloc = off7 + payload_len
    buf = bytearray(total_alloc)

    # Header (some fields updated again after building data)
    struct.pack_into("<I", buf, 0x00, MAGIC)
    struct.pack_into("<H", buf, 0x04, 3)  # version 3
    struct.pack_into("<H", buf, 0x06, SECTION_COUNT)
    struct.pack_into("<I", buf, 0x08, block_size)
    struct.pack_into("<I", buf, 0x0C, ENCODE_PARAM_0C)
    level_byte = level & 0xFF
    encode_param10 = (ALGORITHM_KRAKEN) | (level_byte << 8) | (KRAKEN_WINDOW_BITS << 16)
    struct.pack_into("<Q", buf, 0x10, encode_param10)

    # payload length (uncompressed logical size)
    struct.pack_into("<Q", buf, 0x18, payload_len)
    # total_size (will be updated later to off7 + cumulative_comp)
    struct.pack_into("<Q", buf, 0x20, off7 + payload_len)

    # Reserve directory (id=1..7). id=7 size is a placeholder; we'll write the
    # real value after writing block data.
    _write_directory_entry(buf, 0, 1, off1, sec1_size)
    _write_directory_entry(buf, 1, 2, off2, sec2_size)
    _write_directory_entry(buf, 2, 3, off3, sec3_size)
    _write_directory_entry(buf, 3, 4, off4, sec4_size)
    _write_directory_entry(buf, 4, 5, off5, sec5_size)
    _write_directory_entry(buf, 5, 6, off6, 0)
    _write_directory_entry(buf, 6, 7, off7, 0)  # placeholder

    # id=1 and id=2
    buf[off1 : off1 + sec1_size] = _GIT_HASH
    buf[off2 : off2 + sec2_size] = _SHUFFLE_TABLE

    # Build id=3 (boundary table) entries, id=4 block hashes and id=7 data
    half_block = block_size // 2
    cumulative = 0  # uncompressed running offset
    cumulative_comp = 0  # compressed-section running offset

    compressed_count = 0
    for i in range(block_count):
        size = 0 if payload_len == 0 else min(block_size, payload_len - cumulative)

        # Extract the source bytes for this logical block
        block_bytes = b"" if size == 0 else payload[cumulative : cumulative + size]

        # Try compression if requested
        compressed = False
        comp_bytes = None
        if encode_block_fn is not None and size > 0:
            try:
                comp_candidate = encode_block_fn(block_bytes, level)
                # Accept only when compressor returned bytes and they satisfy keep rule
                if isinstance(comp_candidate, (bytes, bytearray)):
                    comp_len = len(comp_candidate)
                    if comp_len <= ((size * 15) >> 4):
                        compressed = True
                        comp_bytes = bytes(comp_candidate)
                        compressed_count += 1
            except Exception:
                # TODO: Log the error so we can see that something was wrong while compression.
                # Compressor error -> fall back to stored path silently
                compressed = False
                comp_bytes = None

        # Decide flags and size hint based on chosen path
        if compressed and comp_bytes is not None:
            flags = COMPRESSED_FLAG
            comp_write_size = len(comp_bytes)
            size_hint = min(max(comp_write_size - 1, 0), SIZE_HINT_MAX)
        else:
            flags = STORED_FLAG_BASE | (STORED_FLAG_LARGE_HALF if size > half_block else 0)
            comp_write_size = size
            size_hint = min(max(size - 1, 0), SIZE_HINT_MAX)

        # Write boundary entry (compOffset | flags, uncompOffset | sizeHint)
        e = off3 + i * DIRECTORY_ENTRY_SIZE
        comp_offset_field = (cumulative_comp & ((1 << BOUNDARY_FLAG_SHIFT) - 1)) | (
            (flags & 0xFF) << BOUNDARY_FLAG_SHIFT
        )
        struct.pack_into("<Q", buf, e, comp_offset_field)
        uncomp_offset_field = (cumulative & ((1 << SIZE_HINT_SHIFT) - 1)) | (
            (size_hint & SIZE_HINT_MAX) << SIZE_HINT_SHIFT
        )
        struct.pack_into("<Q", buf, e + 8, uncomp_offset_field)

        # Per-block hash (id=4) always computed over the uncompressed bytes
        hpos = off4 + i * DIGEST_LENGTH
        buf[hpos : hpos + DIGEST_LENGTH] = compute_block_digest(block_bytes)

        # Write the chosen representation into the data section at off7 + cumulative_comp
        if comp_write_size > 0:
            if compressed and comp_bytes is not None:
                buf[off7 + cumulative_comp : off7 + cumulative_comp + comp_write_size] = comp_bytes
            else:
                buf[off7 + cumulative_comp : off7 + cumulative_comp + comp_write_size] = block_bytes

        cumulative_comp += comp_write_size
        cumulative += size
    if encode_block_fn is not None and compressed_count == 0 and block_count > 0:
        warning(
            "Oodle Kraken library loaded but all "
            f"{block_count} block(s) stored uncompressed "
            "(compression failed or was not beneficial)"
        )

    # Sentinel boundary entry
    sentinel = off3 + block_count * DIRECTORY_ENTRY_SIZE
    struct.pack_into("<Q", buf, sentinel, payload_len)
    struct.pack_into("<Q", buf, sentinel + 8, payload_len)

    # Now that we know the real id=7 size, update the directory entry and header total_size
    _write_directory_entry(buf, 6, 7, off7, cumulative_comp)
    real_total_size = off7 + cumulative_comp
    struct.pack_into("<Q", buf, 0x20, real_total_size)

    # Compute file digest and write into header @0x28
    header_params = bytes(buf[0x08 : 0x08 + 24])
    shuffle_section = bytes(buf[off2 : off2 + sec2_size])
    boundary_section = bytes(buf[off3 : off3 + sec3_size])
    block_hash_section = bytes(buf[off4 : off4 + sec4_size])
    file_digest = compute_file_digest(header_params, shuffle_section, boundary_section, block_hash_section)
    buf[0x28 : 0x28 + DIGEST_LENGTH] = file_digest

    # Return only the used prefix (data section may be shorter than payload_len when compressed)
    return bytes(buf[:real_total_size])


def decode_pfsc_kraken_payload(container: bytes) -> bytes:
    """Decode a PFSC v3 container produced by encode_pfsc_kraken_payload.

    For stored-only containers this returns the raw payload bytes. If the
    container contains Kraken-compressed blocks the function attempts a
    lazy import of the Oodle wrapper and uses it to decompress each block.
    """
    if len(container) < HEADER_SIZE:
        raise ValueError("container too small")
    magic = struct.unpack_from("<I", container, 0)[0]
    if magic != MAGIC:
        raise ValueError("invalid PFSC magic")
    version = struct.unpack_from("<H", container, 0x04)[0]
    if version != 3:
        raise ValueError("unsupported PFSC version")

    # Parse directory
    dir_base = HEADER_SIZE
    sections: dict[int, tuple[int, int]] = {}
    for idx in range(SECTION_COUNT):
        p = dir_base + idx * DIRECTORY_ENTRY_SIZE
        id_ = struct.unpack_from("<H", container, p)[0]
        offset = struct.unpack_from("<I", container, p + 2)[0]
        size = struct.unpack_from("<I", container, p + 10)[0]
        sections[id_] = (offset, size)

    if 7 not in sections:
        raise ValueError("PFSC container missing id=7 data section")
    off7, sec7_size = sections[7]

    if 3 not in sections or 4 not in sections:
        raise ValueError("PFSC container missing required id=3 (boundary) or id=4 (hash) sections")
    off3, _sec3_size = sections[3]
    off4, sec4_size = sections[4]

    if sec4_size % DIGEST_LENGTH != 0:
        raise ValueError("invalid block-hash section size")
    block_count = sec4_size // DIGEST_LENGTH

    payload_len = struct.unpack_from("<Q", container, 0x18)[0]

    comp_mask = (1 << BOUNDARY_FLAG_SHIFT) - 1
    uncomp_mask = (1 << SIZE_HINT_SHIFT) - 1

    comp_offsets: list[int] = []
    uncomp_offsets: list[int] = []
    flags_arr: list[int] = []

    for i in range(block_count):
        e0 = struct.unpack_from("<Q", container, off3 + i * DIRECTORY_ENTRY_SIZE)[0]
        e1 = struct.unpack_from("<Q", container, off3 + i * DIRECTORY_ENTRY_SIZE + 8)[0]
        comp_off = e0 & comp_mask
        flags = (e0 >> BOUNDARY_FLAG_SHIFT) & 0xFF
        uncomp_off = e1 & uncomp_mask
        comp_offsets.append(comp_off)
        flags_arr.append(flags)
        uncomp_offsets.append(uncomp_off)

    out = bytearray(payload_len)

    for i in range(block_count):
        comp_off = comp_offsets[i]
        comp_next = comp_offsets[i + 1] if i + 1 < block_count else sec7_size
        comp_size = comp_next - comp_off
        uncomp_off = uncomp_offsets[i]
        uncomp_next = uncomp_offsets[i + 1] if i + 1 < block_count else payload_len
        uncomp_size = uncomp_next - uncomp_off

        if comp_off + comp_size > sec7_size:
            raise ValueError("PFSC data section truncated (comp offsets out of range)")
        if uncomp_off + uncomp_size > payload_len:
            raise ValueError("PFSC payload bounds exceeded by block uncomp offsets")

        comp_block = container[off7 + comp_off : off7 + comp_off + comp_size]
        flags = flags_arr[i]

        if (flags & COMPRESSED_FLAG) == COMPRESSED_FLAG:
            # compressed -- require Oodle
            try:
                from . import oodle as _oodle
            except Exception as exc:  # pragma: no cover - environment dependent
                raise ImportError(
                    "PFSC contains Kraken-compressed blocks but the Oodle native"
                    " library is not available. Set OODLE_LIB or install liboo2core.*"
                ) from exc

            decompressed_block = _oodle.decompress_kraken_block(comp_block, uncomp_size)
            if len(decompressed_block) != uncomp_size:
                raise RuntimeError(
                    f"decompressed block size mismatch (got {len(decompressed_block)}, expected {uncomp_size})"
                )
            out[uncomp_off : uncomp_off + uncomp_size] = decompressed_block
        else:
            # stored
            if len(comp_block) < uncomp_size:
                raise ValueError("stored block truncated")
            out[uncomp_off : uncomp_off + uncomp_size] = comp_block[:uncomp_size]
            decompressed_block = bytes(out[uncomp_off : uncomp_off + uncomp_size])

        # validate digest
        digest_pos = off4 + i * DIGEST_LENGTH
        expected_digest = bytes(container[digest_pos : digest_pos + DIGEST_LENGTH])
        actual_digest = compute_block_digest(decompressed_block)
        if actual_digest != expected_digest:
            raise ValueError(f"block digest mismatch at index {i}")

    return bytes(out)
