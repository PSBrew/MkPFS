"""Manages PFS file images that could be mounted in the PS4 and PS5.

Inspired by LibOrbisPkg's layout for inner PFS images and the way
ShadowMountPlus mount images.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import multiprocessing as mp
import queue
import shutil
import struct
import time
import uuid
import zlib
from collections.abc import Callable, Iterator
from contextlib import suppress
from dataclasses import dataclass, field
from pathlib import Path
from typing import BinaryIO, Protocol

from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

from . import consts
from .logging import info
from .pbar import Progress
from .utils import _read_exact, ceil_div, human_readable_size, read_param_json, resolve_temp_root

PFSC_PROGRESS_REPORT_BYTES: int = consts.PFSC_LOGICAL_BLOCK_SIZE * 16
PFSC_SINGLE_FILE_PARALLEL_MIN_SIZE: int = 256 * 1024 * 1024
AUTO_FIT_BLOCK_SIZE_CANDIDATES: tuple[int, ...] = (0x1000, 0x2000, 0x4000, 0x8000, 0x10000)


class SupportsIntQueue(Protocol):
    """Protocol for queue-like objects used by compression progress reporting."""

    def put(self, item: int) -> None:
        """Push a byte delta into the queue."""

    def get_nowait(self) -> int:
        """Return the next queued byte delta without blocking."""


def estimate_file_data_footprint(*, file_sizes: list[int], block_size: int) -> int:
    """Estimate data-block footprint for file payloads at a given PFS block size."""
    return sum((ceil_div(size, block_size) * block_size) if size > 0 else block_size for size in file_sizes)


def choose_auto_fit_block_size(source_root: Path) -> int:
    """Choose a PFS block size that minimizes estimated file-data footprint."""
    file_sizes: list[int] = [p.stat().st_size for p in source_root.rglob("*") if p.is_file()]
    if not file_sizes:
        return consts.PFSC_LOGICAL_BLOCK_SIZE

    return min(
        AUTO_FIT_BLOCK_SIZE_CANDIDATES,
        key=lambda candidate: (
            estimate_file_data_footprint(file_sizes=file_sizes, block_size=candidate),
            -candidate,
        ),
    )


def validate_d32_ranges(inodes: list[Inode], final_ndblock: int) -> None:
    """Validate values that will be serialized into 32-bit inode structures.

    Matches legacy/ffpfs.py:validate_d32_ranges exactly:
    - inode.number, .flags, .blocks must be in [0, UINT32_MAX]
    - inode.mode, .nlink must be in [0, 0xFFFF]
    - final_ndblock and all db/ib pointers must not exceed INT32_MAX
      (they are stored as signed int32 on disk, -1 is the sentinel)

    Args:
        inodes: List of Inode objects to validate.
        final_ndblock: The final data block index after layout assignment.

    Raises:
        BuildError: When a value is out of the supported range.
    """
    if final_ndblock > consts.INT32_MAX:
        raise BuildError(f"Image requires block index {final_ndblock}, exceeds D32 pointer limit {consts.INT32_MAX}")

    for ino in inodes:
        if not (0 <= ino.number <= consts.UINT32_MAX):
            raise BuildError(f"Inode number {ino.number} out of uint32 range")
        if not (0 <= ino.mode <= 0xFFFF):
            raise BuildError(f"Inode mode {ino.mode} out of uint16 range")
        if not (0 <= ino.nlink <= 0xFFFF):
            raise BuildError(f"Inode nlink {ino.nlink} out of uint16 range")
        if not (0 <= ino.flags <= consts.UINT32_MAX):
            raise BuildError(f"Inode flags {ino.flags} out of uint32 range")
        if not (0 <= ino.blocks <= consts.UINT32_MAX):
            raise BuildError(f"Inode blocks {ino.blocks} out of uint32 range")

        for ptr in ino.db:
            if not (-1 <= ptr <= consts.INT32_MAX):
                raise BuildError(f"Direct block pointer {ptr} out of int32 range")
        for ptr in ino.ib:
            if not (-1 <= ptr <= consts.INT32_MAX):
                raise BuildError(f"Indirect block pointer {ptr} out of int32 range")


def pfs_gen_sign_key(ekpfs: bytes, seed: bytes) -> bytes:
    """Generate the HMAC-based signing key used for PFS signatures.

    This is a small wrapper around :func:`pfs_gen_crypto_key` that selects the
    conventionally reserved index for the signing key.

    Args:
        ekpfs: Master EKPFS key material.
        seed: PFS seed value from the image header.

    Returns:
        32-byte HMAC-SHA256-derived key.
    """
    return pfs_gen_crypto_key(ekpfs, seed, 2)


def hmac_sha256(key: bytes, data: bytes) -> bytes:
    """Return the HMAC-SHA256 digest of ``data`` using ``key``.

    Args:
        key: HMAC key.
        data: Data to authenticate.

    Returns:
        Raw 32-byte HMAC-SHA256 digest.
    """
    return hmac.new(key, data, hashlib.sha256).digest()


def pfs_gen_crypto_key(ekpfs: bytes, seed: bytes, index: int) -> bytes:
    """Derive a per-index cryptographic key with HMAC-SHA256.

    Args:
        ekpfs: Base key material.
        seed: Image seed bytes.
        index: Integer index distinguishing derived keys.

    Returns:
        32-byte derived key.
    """
    data: bytes = struct.pack("<I", index) + seed
    return hmac.new(ekpfs, data, hashlib.sha256).digest()


def resolve_ekpfs_key(ekpfs: bytes | None = None) -> bytes:
    """Return validated EKPFS key material, defaulting to the all-zero key.

    Args:
        ekpfs: Optional caller-provided EKPFS bytes.

    Returns:
        A validated 32-byte EKPFS key.

    Raises:
        BuildError: If the provided key is not exactly 32 bytes.
    """
    if ekpfs is None:
        return consts.ZERO_EKPFS
    if len(ekpfs) != len(consts.ZERO_EKPFS):
        raise BuildError(f"EKPFS key must be {len(consts.ZERO_EKPFS)} bytes, got {len(ekpfs)}")
    return ekpfs


def parse_ekpfs_key_hex(key_hex: str | None = None) -> bytes:
    """Parse a compact EKPFS hex string and default to the all-zero key.

    Args:
        key_hex: Optional 64-hex-character EKPFS string.

    Returns:
        Parsed EKPFS bytes, or the all-zero key when omitted.

    Raises:
        BuildError: If the provided text is not valid 64-character hex.
    """
    if key_hex is None:
        return consts.ZERO_EKPFS
    normalized_hex: str = key_hex.strip().lower()
    if normalized_hex == "":
        return consts.ZERO_EKPFS
    if len(normalized_hex) != 64 or any(char not in "0123456789abcdef" for char in normalized_hex):
        raise BuildError("--ekpfs-key must be exactly 64 hexadecimal characters")
    return bytes.fromhex(normalized_hex)


def pfs_gen_enc_keys(ekpfs: bytes, seed: bytes, new_crypt: bool = False) -> tuple[bytes, bytes]:
    """Derive XTS tweak and data keys for encrypted PFS images.

    Args:
        ekpfs: Master EKPFS key material.
        seed: PFS seed value from the image header.
        new_crypt: When True, derive the encryption key from HMAC(EKPFS, seed)
            before running the standard PFS key derivation.

    Returns:
        Tuple of `(tweak_key, data_key)`, each 16 bytes long.
    """
    base_key: bytes = (
        hmac_sha256(resolve_ekpfs_key(ekpfs=ekpfs), seed) if new_crypt else resolve_ekpfs_key(ekpfs=ekpfs)
    )
    enc_key: bytes = pfs_gen_crypto_key(base_key, seed, 1)
    tweak_key: bytes = enc_key[:16]
    data_key: bytes = enc_key[16:32]
    return tweak_key, data_key


def pfs_gen_xts_key(ekpfs: bytes, seed: bytes, new_crypt: bool = False) -> bytes:
    """Return the combined AES-XTS key bytes for the cryptography backend.

    Args:
        ekpfs: Master EKPFS key material.
        seed: PFS seed value from the image header.
        new_crypt: When True, use the alternate newCrypt derivation path.

    Returns:
        32-byte XTS key, ordered as data-key then tweak-key.
    """
    tweak_key: bytes
    data_key: bytes
    tweak_key, data_key = pfs_gen_enc_keys(ekpfs=ekpfs, seed=seed, new_crypt=new_crypt)
    return data_key + tweak_key


def pfs_xts_start_sector(block_size: int) -> int:
    """Return the first XTS sector index used for encrypted PFS blocks.

    Args:
        block_size: Filesystem block size in bytes.

    Returns:
        XTS sector index where block 1 begins.

    Raises:
        BuildError: If the block size is not a multiple of the XTS sector size.
    """
    if (block_size % consts.PFS_XTS_SECTOR_SIZE) != 0:
        raise BuildError(f"block size {block_size} is not aligned to XTS sector size {consts.PFS_XTS_SECTOR_SIZE}")
    return block_size // consts.PFS_XTS_SECTOR_SIZE


def pfs_xts_tweak(sector_number: int) -> bytes:
    """Return the 16-byte tweak input for one AES-XTS sector.

    Args:
        sector_number: Absolute XTS sector number.

    Returns:
        16-byte little-endian tweak buffer.
    """
    return struct.pack("<QQ", sector_number, 0)


def crypt_pfs_xts_sector(sector_data: bytes, xts_key: bytes, sector_number: int, *, encrypt: bool) -> bytes:
    """Encrypt or decrypt one AES-XTS sector.

    Args:
        sector_data: Sector bytes, must be exactly one XTS sector.
        xts_key: 32-byte XTS key in data+tweak order.
        sector_number: Absolute XTS sector number.
        encrypt: When True, encrypt; otherwise decrypt.

    Returns:
        Transformed sector bytes.

    Raises:
        BuildError: If the input is not exactly one XTS sector.
    """
    if len(sector_data) != consts.PFS_XTS_SECTOR_SIZE:
        raise BuildError(f"XTS sector input must be {consts.PFS_XTS_SECTOR_SIZE} bytes, got {len(sector_data)}")
    cipher: Cipher = Cipher(algorithm=algorithms.AES(xts_key), mode=modes.XTS(pfs_xts_tweak(sector_number)))
    transform = cipher.encryptor() if encrypt else cipher.decryptor()
    return transform.update(sector_data) + transform.finalize()


def read_image_bytes(
    fh: BinaryIO,
    header: ParsedHeader,
    offset: int,
    size: int,
    ekpfs: bytes | None = None,
    new_crypt: bool = False,
) -> bytes:
    """Read bytes from an image, transparently decrypting encrypted regions.

    Args:
        fh: Open image file handle.
        header: Parsed image header.
        offset: Absolute byte offset in the image.
        size: Number of bytes to read.
        ekpfs: Optional EKPFS key material. Defaults to the all-zero key.
        new_crypt: When True, use the alternate newCrypt key derivation path.

    Returns:
        Requested bytes, decrypted when the image is encrypted.

    Raises:
        ValueError: If the request spans plaintext header bytes and encrypted data.
    """
    if size <= 0:
        return b""
    if (header.mode & consts.PFS_MODE_ENCRYPTED) == 0 or offset < header.block_size:
        if offset < header.block_size < offset + size:
            raise ValueError("mixed plaintext/encrypted reads are not supported")
        return _read_exact(fh, offset, size)

    sector_size: int = consts.PFS_XTS_SECTOR_SIZE
    aligned_start: int = (offset // sector_size) * sector_size
    aligned_end: int = ceil_div(offset + size, sector_size) * sector_size
    raw: bytes = _read_exact(fh, aligned_start, aligned_end - aligned_start)
    xts_key: bytes = pfs_gen_xts_key(resolve_ekpfs_key(ekpfs=ekpfs), header.seed, new_crypt=new_crypt)
    decrypted = bytearray()
    sector_number: int = aligned_start // sector_size
    for chunk_offset in range(0, len(raw), sector_size):
        chunk: bytes = raw[chunk_offset : chunk_offset + sector_size]
        decrypted += crypt_pfs_xts_sector(chunk, xts_key, sector_number, encrypt=False)
        sector_number += 1
    inner_offset: int = offset - aligned_start
    return bytes(decrypted[inner_offset : inner_offset + size])


def encrypt_image_filesystem(
    out: BinaryIO,
    block_size: int,
    total_blocks: int,
    ekpfs: bytes,
    seed: bytes,
    new_crypt: bool = False,
    skip_block_numbers: set[int] | None = None,
) -> None:
    """Encrypt all on-disk filesystem sectors after the plaintext header block.

    Args:
        out: Open writable image file handle.
        block_size: Filesystem block size in bytes.
        total_blocks: Total number of blocks in the image.
        ekpfs: EKPFS key material.
        seed: PFS seed value from the image header.
        new_crypt: When True, use the alternate newCrypt key derivation path.
        skip_block_numbers: Optional filesystem block numbers that must remain
            plaintext and must not be XTS-encrypted.
    """
    xts_key: bytes = pfs_gen_xts_key(resolve_ekpfs_key(ekpfs=ekpfs), seed, new_crypt=new_crypt)
    start_sector: int = pfs_xts_start_sector(block_size=block_size)
    total_sectors: int = (total_blocks * block_size) // consts.PFS_XTS_SECTOR_SIZE
    skipped_blocks: set[int] = skip_block_numbers or set()
    sector_buffer: bytes
    for sector_number in range(start_sector, total_sectors):
        if (sector_number * consts.PFS_XTS_SECTOR_SIZE) // block_size in skipped_blocks:
            continue
        sector_offset: int = sector_number * consts.PFS_XTS_SECTOR_SIZE
        sector_buffer = _read_exact(out, sector_offset, consts.PFS_XTS_SECTOR_SIZE)
        out.seek(sector_offset)
        out.write(crypt_pfs_xts_sector(sector_buffer, xts_key, sector_number, encrypt=True))


@dataclass(frozen=True)
class SignedInodeLayout:
    """Describe the signed inode layout currently being written or parsed.

    Attributes:
        inode_size: Total serialized inode size.
        entry_size: Size of each signed block entry, including signature and pointer.
        block_format: ``struct`` format string for the on-disk block pointer.
        pointer_table_offset: Offset where the signed db/ib entry table begins.
    """

    inode_size: int
    entry_size: int
    block_format: str
    pointer_table_offset: int


def signed_inode_layout(inode_bits: int) -> SignedInodeLayout:
    """Return the signed inode layout for the requested inode width.

    Args:
        inode_bits: Signed inode width, 32 or 64.

    Returns:
        Layout metadata for the signed inode structure.

    Raises:
        BuildError: If ``inode_bits`` is not a supported signed width.
    """
    if inode_bits == 32:
        return SignedInodeLayout(
            inode_size=consts.INODE_S32_SIZE,
            entry_size=consts.SIG_ENTRY_S32_SIZE,
            block_format="<i",
            pointer_table_offset=0x64,
        )
    if inode_bits == 64:
        return SignedInodeLayout(
            inode_size=consts.INODE_S64_SIZE,
            entry_size=consts.SIG_ENTRY_S64_SIZE,
            block_format="<q",
            pointer_table_offset=0x68,
        )
    raise BuildError(f"Unsupported signed inode width: {inode_bits}")


def signed_inode_bits_from_mode(mode: int) -> int:
    """Return the signed inode width encoded in a PFS header mode field.

    Args:
        mode: PFS mode bitfield.

    Returns:
        64 when the signed image uses 64-bit inodes, otherwise 32.
    """
    if mode & consts.PFS_MODE_64BIT_INODES:
        return 64
    return 32


def signed_inode_capacity_bytes(block_size: int, inode_bits: int) -> int:
    """Return the maximum payload size (bytes) representable by a signed inode.

    Signed inodes use a layout with direct pointers, one-level and two-level
    indirect chains described by signature records. This helper computes the
    maximum number of data blocks addressable and converts it to bytes.

    Args:
        block_size: Filesystem block size in bytes.
        inode_bits: Signed inode width, 32 or 64.

    Returns:
        Maximum representable payload size in bytes for a single signed inode.
    """
    layout: SignedInodeLayout = signed_inode_layout(inode_bits)
    sigs_per_block: int = block_size // layout.entry_size
    if sigs_per_block <= 0:
        return 0
    max_blocks: int = 12 + sigs_per_block + (sigs_per_block * sigs_per_block)
    return max_blocks * block_size


def compose_pfs_mode(inode_bits: int, case_insensitive: bool) -> int:
    """Compose the PFS header mode flags from options.

    Args:
        inode_bits: 32 or 64 to indicate inode width.
        case_insensitive: When True, set the case-insensitive flag.

    Returns:
        Integer mode bitfield suitable for writing to the header.
    """
    # Bit 3 (0x8) controls case-sensitivity: when set, filesystem is case-insensitive.
    mode: int = 0
    if inode_bits == 64:
        mode |= consts.PFS_MODE_64BIT_INODES
    if case_insensitive:
        mode |= consts.PFS_MODE_CASE_INSENSITIVE
    return mode


def compose_pfs_mode_with_options(inode_bits: int, case_insensitive: bool, signed: bool, encrypted: bool) -> int:
    """Compose PFS mode flags with signed and encrypted options.

    Args:
        inode_bits: 32 or 64.
        case_insensitive: Case-insensitive flag.
        signed: Whether to set the signed-mode bit.
        encrypted: Whether to set the encrypted-mode bit.

    Returns:
        Integer mode bitfield.
    """
    mode: int = compose_pfs_mode(inode_bits, case_insensitive)
    if signed:
        mode |= consts.PFS_MODE_SIGNED
    if encrypted:
        mode |= consts.PFS_MODE_ENCRYPTED
    return mode


def compose_pfs_mode_with_sign(inode_bits: int, case_insensitive: bool, signed: bool) -> int:
    """Compose PFS mode flags and optionally include the signed flag.

    Args:
        inode_bits: 32 or 64.
        case_insensitive: Case-insensitive flag.
        signed: Whether to set the signed-mode bit.

    Returns:
        Integer mode bitfield.
    """
    return compose_pfs_mode_with_options(
        inode_bits=inode_bits,
        case_insensitive=case_insensitive,
        signed=signed,
        encrypted=False,
    )


def build_inode_block_sig_s64(inode_block_count: int, block_size: int, now: int, signed: bool = False) -> bytes:
    """Create the 0x310-byte InodeBlockSig used in the header.

    The header encodes a small DinodeS64 structure for the inode-table block
    signature region. This helper builds that fixed-size structure. The layout
    matches observed reference images where signatures are zeroed and only a
    small subset of db/ib entries contain block pointers.

    Args:
        inode_block_count: Number of inode table blocks.
        block_size: Filesystem block size.
        now: Current epoch seconds to populate timestamp fields.
        signed: When True, set flags appropriate for signed layout.

    Returns:
        The fixed-size bytes blob to place into the header.
    """
    sig: bytearray = bytearray(0x310)

    struct.pack_into("<H", sig, 0x00, 0)  # mode
    struct.pack_into("<H", sig, 0x02, 1)  # nlink
    struct.pack_into("<I", sig, 0x04, 0 if signed else consts.INODE_FLAG_READONLY)  # flags
    size_bytes: int = inode_block_count * block_size
    struct.pack_into("<q", sig, 0x08, size_bytes)
    struct.pack_into("<q", sig, 0x10, size_bytes)

    struct.pack_into("<qqqq", sig, 0x18, now, now, now, now)
    struct.pack_into("<IIII", sig, 0x38, 0, 0, 0, 0)
    struct.pack_into("<I", sig, 0x48, 0)  # uid
    struct.pack_into("<I", sig, 0x4C, 0)  # gid
    struct.pack_into("<Q", sig, 0x50, 0)  # unk1
    struct.pack_into("<Q", sig, 0x58, 0)  # unk2
    struct.pack_into("<I", sig, 0x60, inode_block_count)  # blocks

    # Signed-64 layout: 12 direct and 5 indirect entries, each 32-byte sig + 8-byte block.
    # Reference images use zeroed signatures and only db[0] = 1 for inode-table start block.
    # Observed S64 header layout includes 4-byte padding after `blocks`.
    db_base: int = 0x68
    for i in range(12):
        if signed:
            block: int = 1 + i if i < inode_block_count else 0
        else:
            block = 1 if i == 0 else 0
        struct.pack_into("<q", sig, db_base + i * 40 + 32, block)

    ib_base: int = db_base + 12 * 40
    for i in range(5):
        struct.pack_into("<q", sig, ib_base + i * 40 + 32, 0)

    return bytes(sig)


@dataclass
class SignatureTarget:
    block: int
    sig_offset: int
    size: int
    level: int


class BuildError(RuntimeError):
    pass


@dataclass
class Dirent:
    inode_number: int
    type_code: int
    name: str

    @property
    def name_length(self) -> int:
        return len(self.name)

    @property
    def ent_size(self) -> int:
        size = self.name_length + 17
        rem = size % 8
        if rem:
            size += 8 - rem
        return size

    def to_bytes(self) -> bytes:
        """Serialize this directory entry to the on-disk dirent format.

        The returned bytes contain fields (inode, type, name length, entry size)
        followed by the ASCII name and padding to reach the aligned entry size.

        Returns:
            Bytes suitable for writing into a directory payload block.
        """
        name_bytes: bytes = self.name.encode("ascii", errors="strict")
        out: bytearray = bytearray()
        out += struct.pack("<Iiii", self.inode_number, self.type_code, self.name_length, self.ent_size)
        out += name_bytes
        if len(out) < self.ent_size:
            out += b"\x00" * (self.ent_size - len(out))
        return bytes(out)


@dataclass
class Inode:
    number: int
    mode: int
    nlink: int
    flags: int
    size: int
    size_compressed: int
    blocks: int
    db: list[int] = field(default_factory=lambda: [0] * consts.MAX_DIRECT_BLOCKS)
    ib: list[int] = field(default_factory=lambda: [0] * consts.MAX_INDIRECT_BLOCKS)
    db_sig: list[bytes] = field(
        default_factory=lambda: [b"\x00" * consts.SIG_SIZE for _ in range(consts.MAX_DIRECT_BLOCKS)]
    )
    ib_sig: list[bytes] = field(
        default_factory=lambda: [b"\x00" * consts.SIG_SIZE for _ in range(consts.MAX_INDIRECT_BLOCKS)]
    )
    time_sec: int = 0

    def _base_bytes(self) -> bytearray:
        """Return common inode header bytes used by various on-disk inode layouts.

        This helper centralizes packing of the fixed-size fields present in both
        signed and unsigned inode representations.
        """
        ts: int = self.time_sec
        time_nsec: int = 0
        uid: int = 0
        gid: int = 0
        unk1: int = 0
        unk2: int = 0
        out: bytearray = bytearray()
        out += struct.pack("<HHI", self.mode, self.nlink, self.flags)
        out += struct.pack("<qq", self.size, self.size_compressed)
        out += struct.pack("<qqqq", ts, ts, ts, ts)
        out += struct.pack("<IIII", time_nsec, time_nsec, time_nsec, time_nsec)
        out += struct.pack("<IIQQI", uid, gid, unk1, unk2, self.blocks)
        return out

    def to_bytes(self) -> bytes:
        """Serialize the inode in the unsigned D32 layout.

        Returns:
            Bytes of length INODE_D32_SIZE containing the inode fields.

        Raises:
            BuildError: If the produced byte length does not match expectations.
        """
        out: bytearray = self._base_bytes()
        out += struct.pack("<" + "i" * consts.MAX_DIRECT_BLOCKS, *self.db)
        out += struct.pack("<" + "i" * consts.MAX_INDIRECT_BLOCKS, *self.ib)
        if len(out) != consts.INODE_D32_SIZE:
            raise BuildError(f"Unexpected inode size {len(out)}")
        return bytes(out)

    def to_bytes_signed32(self) -> bytes:
        """Serialize the inode using the signed S32 layout (32-byte signatures).

        This layout interleaves 32-byte signature placeholders and 4-byte block
        pointers for each direct/indirect entry.
        """
        return self._to_bytes_signed(layout=signed_inode_layout(32))

    def to_bytes_signed64(self) -> bytes:
        """Serialize the inode using the signed S64 layout (32-byte signatures).

        This layout stores the same signatures as S32, but uses 64-bit block
        pointers and includes the observed 4-byte padding after the ``blocks``
        field before the pointer table begins.
        """
        return self._to_bytes_signed(layout=signed_inode_layout(64))

    def _to_bytes_signed(self, *, layout: SignedInodeLayout) -> bytes:
        """Serialize a signed inode using the supplied signed layout metadata.

        Args:
            layout: Signed inode layout description.

        Returns:
            Serialized inode bytes for the selected signed layout.

        Raises:
            BuildError: If signature size or final inode size is invalid.
        """
        out: bytearray = self._base_bytes()
        if len(out) < layout.pointer_table_offset:
            out += b"\x00" * (layout.pointer_table_offset - len(out))
        for sig, block in zip(self.db_sig, self.db):
            if len(sig) != consts.SIG_SIZE:
                raise BuildError("Signed inode direct signature must be 32 bytes")
            out += sig
            out += struct.pack(layout.block_format, block)
        for sig, block in zip(self.ib_sig, self.ib):
            if len(sig) != consts.SIG_SIZE:
                raise BuildError("Signed inode indirect signature must be 32 bytes")
            out += sig
            out += struct.pack(layout.block_format, block)
        if len(out) != layout.inode_size:
            raise BuildError(f"Unexpected signed inode size {len(out)}")
        return bytes(out)


@dataclass
class FileNode:
    rel_path: str
    abs_path: Path
    parent_rel_dir: str
    name: str
    raw_size: int
    stored_source_path: Path | None = None
    stored_source_is_temp: bool = False
    stored_size: int = 0
    compressed: bool = False
    gain_pct: float = 0.0
    hypothetical_compressed_size: int = 0
    inode: Inode | None = None


def should_skip_executable_compression(file_name: str) -> bool:
    """Return True for executable payloads that should stay raw when requested."""
    lower_name: str = file_name.lower()
    return (
        (lower_name.startswith("eboot") and lower_name.endswith(".bin"))
        or lower_name.endswith(".prx")
        or lower_name.endswith(".sprx")
    )


def store_file_node_raw(file_node: FileNode) -> None:
    """Mark a file node to be stored directly from the source file."""
    file_node.stored_source_path = file_node.abs_path
    file_node.stored_source_is_temp = False
    file_node.stored_size = file_node.raw_size
    file_node.compressed = False
    file_node.gain_pct = 0.0

    file_node.hypothetical_compressed_size = file_node.raw_size


@dataclass
class DirNode:
    rel_dir: str
    name: str
    parent_rel_dir: str | None
    children_dirs: list[str] = field(default_factory=list)
    children_files: list[str] = field(default_factory=list)
    dirents: list[Dirent] = field(default_factory=list)
    inode: Inode | None = None


@dataclass
class BuildStats:
    input_path: Path
    output_path: Path
    total_files: int = 0
    uncompressed_total_size: int = 0
    stored_total_size: int = 0
    all_compressed_total_size: int = 0
    compressed_files: int = 0
    uncompressed_files: int = 0
    elapsed_seconds: float = 0.0
    compression_enabled: bool = True
    block_size: int = 65536
    block_alignment_waste: int = 0

    @property
    def actual_gain_pct(self) -> float:
        if self.uncompressed_total_size == 0:
            return 0.0
        return ((self.uncompressed_total_size - self.stored_total_size) / self.uncompressed_total_size) * 100.0

    @property
    def max_possible_gain_pct(self) -> float:
        if self.uncompressed_total_size == 0:
            return 0.0
        return ((self.uncompressed_total_size - self.all_compressed_total_size) / self.uncompressed_total_size) * 100.0


@dataclass
class PFSCHeader:
    """PFSC header compatible with the reference ``PFSCHdr`` layout.

    Args:
        magic: PFSC magic value.
        unk4: Expected zero field at offset ``0x04``.
        unk8: Observed version-like field at offset ``0x08``.
        logical_block_size: Logical PFSC block size.
        block_offsets_offset: Offset to the block offset table from payload start.
        data_offset: Absolute offset where PFSC block data begins.
        data_length: Logical padded byte length managed by the PFSC stream.
    """

    magic: int
    unk4: int
    unk8: int
    logical_block_size: int
    block_offsets_offset: int
    data_offset: int
    data_length: int


def _split_pfsc_blocks(payload: bytes, logical_block_size: int) -> list[bytes]:
    """Split bytes into logical PFSC-sized blocks.

    Args:
        payload: Raw file payload.
        logical_block_size: Logical PFSC block size.

    Returns:
        List of logical blocks in order.

    Raises:
        ValueError: If logical_block_size is not positive.
    """
    if logical_block_size <= 0:
        raise ValueError(f"logical_block_size must be positive, got {logical_block_size}")
    return [payload[offset : offset + logical_block_size] for offset in range(0, len(payload), logical_block_size)]


def _pfsc_header_size(*, block_count: int, logical_block_size: int) -> int:
    """Return the PFSC header size required for the given block table.

    Args:
        block_count: Number of logical PFSC blocks.
        logical_block_size: Logical PFSC block size.

    Returns:
        Header size, including any extra blocks needed to fit the offsets table.
    """
    if block_count < 0:
        raise ValueError(f"block_count must be non-negative, got {block_count}")
    if logical_block_size <= 0:
        raise ValueError(f"logical_block_size must be positive, got {logical_block_size}")
    pointer_table_size: int = (block_count + 1) * consts.PFSC_OFFSET_ENTRY_SIZE
    extra_table_bytes: int = max(0, pointer_table_size - consts.PFSC_INITIAL_OFFSET_TABLE_CAPACITY)
    extra_blocks: int = ceil_div(extra_table_bytes, logical_block_size) if extra_table_bytes > 0 else 0
    return consts.PFSC_INITIAL_DATA_OFFSET + (extra_blocks * logical_block_size)


def encode_pfsc_payload(
    raw: bytes,
    threshold_gain: int,
    zlib_level: int,
    logical_block_size: int = consts.PFSC_LOGICAL_BLOCK_SIZE,
    progress_callback: Callable[[int], None] | None = None,
) -> tuple[bytes, float, int]:
    """Encode raw bytes into PFSC block-compressed payload bytes.

    Compression decisions are made per logical block. A block is stored compressed
    only when its local gain reaches ``threshold_gain``.

    Args:
        raw: Raw file bytes.
        threshold_gain: Minimum per-block gain percent to keep compressed bytes.
        zlib_level: zlib compression level.
        logical_block_size: Logical PFSC block size.
        progress_callback: Optional callback receiving raw bytes processed per block.

    Returns:
        Tuple of ``(encoded_payload, effective_gain_pct, hypothetical_all_compressed_size)``.

    Raises:
        ValueError: If threshold_gain or logical_block_size are invalid.
    """
    if not (0 <= threshold_gain <= 100):
        raise ValueError(f"threshold_gain must be between 0 and 100 inclusive, got {threshold_gain}")
    if logical_block_size <= 0:
        raise ValueError(f"logical_block_size must be positive, got {logical_block_size}")

    logical_blocks: list[bytes] = _split_pfsc_blocks(payload=raw, logical_block_size=logical_block_size)
    block_count: int = len(logical_blocks)
    if block_count == 0:
        return b"", 0.0, 0

    encoded_blocks: list[bytes] = []
    all_compressed_size: int = 0
    compressed_blocks: int = 0

    for block in logical_blocks:
        padded_block: bytes = block.ljust(logical_block_size, b"\x00")
        compressed_block: bytes = zlib.compress(padded_block, level=zlib_level)
        all_compressed_size += len(compressed_block)
        gain_pct: float = ((len(padded_block) - len(compressed_block)) / len(padded_block)) * 100.0
        chosen_block: bytes = compressed_block if gain_pct >= threshold_gain else padded_block
        if chosen_block is compressed_block:
            compressed_blocks += 1
        encoded_blocks.append(chosen_block)
        if progress_callback is not None:
            progress_callback(len(block))

    header_size: int = _pfsc_header_size(block_count=block_count, logical_block_size=logical_block_size)
    offsets: list[int] = [header_size]
    for block in encoded_blocks:
        offsets.append(offsets[-1] + len(block))
    header: PFSCHeader = PFSCHeader(
        magic=consts.PFSC_MAGIC,
        unk4=consts.PFSC_UNK4,
        unk8=consts.PFSC_UNK8,
        logical_block_size=logical_block_size,
        block_offsets_offset=consts.PFSC_BLOCK_OFFSETS_OFFSET,
        data_offset=header_size,
        data_length=block_count * logical_block_size,
    )
    header_area: bytearray = bytearray(header_size)
    struct.pack_into(
        "<iiiiqqQq",
        header_area,
        0,
        header.magic,
        header.unk4,
        header.unk8,
        header.logical_block_size,
        header.logical_block_size,
        header.block_offsets_offset,
        header.data_offset,
        header.data_length,
    )
    struct.pack_into(f"<{block_count + 1}Q", header_area, consts.PFSC_BLOCK_OFFSETS_OFFSET, *offsets)
    encoded_payload: bytes = bytes(header_area) + b"".join(encoded_blocks)
    effective_gain_pct: float = ((len(raw) - len(encoded_payload)) / len(raw)) * 100.0
    hypothetical_all_compressed_size: int = header_size + all_compressed_size

    if compressed_blocks == 0 or len(encoded_payload) >= len(raw):
        return raw, 0.0, hypothetical_all_compressed_size

    return encoded_payload, effective_gain_pct, hypothetical_all_compressed_size


def _make_compression_spool_path(*, source_path: Path, temp_folder: Path | None = None) -> Path:
    """Build a unique temporary spool path for a compressed payload.

    Args:
        source_path: Source file path used only for naming context.
        temp_folder: Optional temporary folder for spool files.

    Returns:
        A unique path under the system temporary directory.
    """
    suffix: str = uuid.uuid4().hex
    safe_name: str = source_path.name.replace(" ", "_")
    temp_root: Path = resolve_temp_root(temp_folder=temp_folder)
    return temp_root / f"mkpfs-{safe_name}.{suffix}.pfsc"


def resolve_block_compression_worker_count(*, requested_cpu_count: int, file_size: int) -> int:
    """Resolve block-level worker count for one file compression workload.

    Args:
        requested_cpu_count: Requested CPU budget for compression.
        file_size: Raw file size in bytes.

    Returns:
        Effective block worker count. Returns ``1`` when the file is below the
        single-file block-parallel threshold.

    Raises:
        ValueError: If ``requested_cpu_count`` is negative or ``file_size`` is negative.
    """
    if requested_cpu_count < 0:
        raise ValueError(f"requested_cpu_count must be non-negative, got {requested_cpu_count}")
    if file_size < 0:
        raise ValueError(f"file_size must be non-negative, got {file_size}")
    if file_size < PFSC_SINGLE_FILE_PARALLEL_MIN_SIZE:
        return 1
    return max(1, requested_cpu_count)


def _iter_pfsc_block_worker_args(
    *,
    abs_path: Path,
    block_count: int,
    logical_block_size: int,
    zlib_level: int,
) -> Iterator[tuple[Path, int, int, int]]:
    """Yield block worker arguments for one file in logical block order."""
    block_index: int
    for block_index in range(block_count):
        block_offset: int = block_index * logical_block_size
        yield abs_path, block_offset, logical_block_size, zlib_level


def _compress_pfsc_block_lengths_worker(args: tuple[Path, int, int, int]) -> tuple[int, int]:
    """Compress one logical block and return raw/compressed lengths.

    Args:
        args: Tuple ``(abs_path, block_offset, logical_block_size, zlib_level)``.

    Returns:
        Tuple ``(raw_block_length, compressed_block_length)``.
    """
    abs_path: Path
    block_offset: int
    logical_block_size: int
    zlib_level: int
    (abs_path, block_offset, logical_block_size, zlib_level) = args
    raw_chunk: bytes
    with abs_path.open("rb") as source_file:
        source_file.seek(block_offset)
        raw_chunk = source_file.read(logical_block_size)
    padded_chunk: bytes = raw_chunk.ljust(logical_block_size, b"\x00")
    compressed_chunk: bytes = zlib.compress(padded_chunk, level=zlib_level)
    return len(raw_chunk), len(compressed_chunk)


def _compress_pfsc_block_payload_worker(args: tuple[Path, int, int, int]) -> tuple[bytes, bytes]:
    """Compress one logical block and return raw/compressed payload bytes.

    Args:
        args: Tuple ``(abs_path, block_offset, logical_block_size, zlib_level)``.

    Returns:
        Tuple ``(raw_chunk, compressed_chunk)``.
    """
    abs_path: Path
    block_offset: int
    logical_block_size: int
    zlib_level: int
    (abs_path, block_offset, logical_block_size, zlib_level) = args
    raw_chunk: bytes
    with abs_path.open("rb") as source_file:
        source_file.seek(block_offset)
        raw_chunk = source_file.read(logical_block_size)
    padded_chunk: bytes = raw_chunk.ljust(logical_block_size, b"\x00")
    compressed_chunk: bytes = zlib.compress(padded_chunk, level=zlib_level)
    return raw_chunk, compressed_chunk


def _analyze_pfsc_file_storage(
    *,
    abs_path: Path,
    threshold_gain: int,
    min_file_gain: int,
    zlib_level: int,
    logical_block_size: int,
    block_worker_count: int = 1,
    progress_callback: Callable[[int], None] | None = None,
) -> tuple[int, bool, float, int]:
    """Analyze PFSC storage choice for a file without creating output payload bytes.

    Args:
        abs_path: Source file path.
        threshold_gain: Minimum per-block gain percent to keep compressed bytes.
        min_file_gain: Minimum whole-file gain percent required to store PFSC.
        zlib_level: zlib compression level.
        logical_block_size: PFSC logical block size.
        block_worker_count: Number of worker processes to use for block-level
            compression of this file.
        progress_callback: Optional callback receiving processed raw byte deltas.

    Returns:
        Tuple ``(stored_size, is_compressed, gain_pct, hypothetical_all_compressed_size)``.
    """
    raw_size: int = abs_path.stat().st_size
    if not (0 <= min_file_gain <= 100):
        raise ValueError(f"min_file_gain must be between 0 and 100 inclusive, got {min_file_gain}")
    if raw_size == 0:
        return 0, False, 0.0, 0

    block_count: int = ceil_div(raw_size, logical_block_size)
    header_size: int = _pfsc_header_size(block_count=block_count, logical_block_size=logical_block_size)
    chosen_payload_size: int = 0
    all_compressed_size: int = 0
    compressed_blocks: int = 0
    effective_block_workers: int = max(1, min(block_worker_count, block_count))

    if effective_block_workers == 1:
        with abs_path.open("rb") as source_file:
            for _idx in range(block_count):
                chunk: bytes = source_file.read(logical_block_size)
                padded_chunk: bytes = chunk.ljust(logical_block_size, b"\x00")
                compressed_chunk: bytes = zlib.compress(padded_chunk, level=zlib_level)
                all_compressed_size += len(compressed_chunk)
                gain_pct: float = ((len(padded_chunk) - len(compressed_chunk)) / len(padded_chunk)) * 100.0
                if gain_pct >= threshold_gain:
                    chosen_payload_size += len(compressed_chunk)
                    compressed_blocks += 1
                else:
                    chosen_payload_size += len(padded_chunk)
                if progress_callback is not None:
                    progress_callback(len(chunk))
    else:
        worker_args_iter: Iterator[tuple[Path, int, int, int]] = _iter_pfsc_block_worker_args(
            abs_path=abs_path,
            block_count=block_count,
            logical_block_size=logical_block_size,
            zlib_level=zlib_level,
        )
        with mp.Pool(processes=effective_block_workers) as pool:
            results_iter = pool.imap(_compress_pfsc_block_lengths_worker, worker_args_iter, chunksize=1)
            raw_block_len: int
            compressed_block_len: int
            for raw_block_len, compressed_block_len in results_iter:
                all_compressed_size += compressed_block_len
                padded_block_len: int = logical_block_size
                gain_pct: float = ((padded_block_len - compressed_block_len) / padded_block_len) * 100.0
                if gain_pct >= threshold_gain:
                    chosen_payload_size += compressed_block_len
                    compressed_blocks += 1
                else:
                    chosen_payload_size += padded_block_len
                if progress_callback is not None:
                    progress_callback(raw_block_len)

    encoded_payload_size: int = header_size + chosen_payload_size
    hypothetical_all_compressed_size: int = header_size + all_compressed_size
    if compressed_blocks == 0 or encoded_payload_size >= raw_size:
        return raw_size, False, 0.0, hypothetical_all_compressed_size
    effective_gain_pct: float = ((raw_size - encoded_payload_size) / raw_size) * 100.0
    if effective_gain_pct < min_file_gain:
        return raw_size, False, effective_gain_pct, hypothetical_all_compressed_size
    return encoded_payload_size, True, effective_gain_pct, hypothetical_all_compressed_size


def _encode_pfsc_file_to_spool(
    *,
    abs_path: Path,
    spool_path: Path,
    threshold_gain: int,
    min_file_gain: int,
    zlib_level: int,
    logical_block_size: int,
    block_worker_count: int = 1,
    progress_callback: Callable[[int], None] | None = None,
) -> tuple[int, bool, float, int]:
    """Write a file's PFSC payload to a spool file using low-memory streaming.

    Args:
        abs_path: Source file path.
        spool_path: Output spool file path for compressed PFSC payload.
        threshold_gain: Minimum per-block gain percent to keep compressed bytes.
        min_file_gain: Minimum whole-file gain percent required to store PFSC.
        zlib_level: zlib compression level.
        logical_block_size: PFSC logical block size.
        block_worker_count: Number of worker processes to use for block-level
            compression of this file.
        progress_callback: Optional callback receiving processed raw byte deltas.

    Returns:
        Tuple ``(stored_size, is_compressed, gain_pct, hypothetical_all_compressed_size)``.
    """
    raw_size: int = abs_path.stat().st_size
    if not (0 <= min_file_gain <= 100):
        raise ValueError(f"min_file_gain must be between 0 and 100 inclusive, got {min_file_gain}")
    if raw_size == 0:
        return 0, False, 0.0, 0

    block_count: int = ceil_div(raw_size, logical_block_size)
    header_size: int = _pfsc_header_size(block_count=block_count, logical_block_size=logical_block_size)
    offsets: list[int] = [header_size]
    all_compressed_size: int = 0
    compressed_blocks: int = 0
    effective_block_workers: int = max(1, min(block_worker_count, block_count))

    with spool_path.open("w+b") as spool_file:
        spool_file.seek(header_size)
        if effective_block_workers == 1:
            with abs_path.open("rb") as source_file:
                for _idx in range(block_count):
                    chunk: bytes = source_file.read(logical_block_size)
                    padded_chunk: bytes = chunk.ljust(logical_block_size, b"\x00")
                    compressed_chunk: bytes = zlib.compress(padded_chunk, level=zlib_level)
                    all_compressed_size += len(compressed_chunk)
                    gain_pct: float = ((len(padded_chunk) - len(compressed_chunk)) / len(padded_chunk)) * 100.0
                    selected_chunk: bytes = compressed_chunk if gain_pct >= threshold_gain else padded_chunk
                    if selected_chunk is compressed_chunk:
                        compressed_blocks += 1
                    spool_file.write(selected_chunk)
                    offsets.append(offsets[-1] + len(selected_chunk))
                    if progress_callback is not None:
                        progress_callback(len(chunk))
        else:
            worker_args_iter: Iterator[tuple[Path, int, int, int]] = _iter_pfsc_block_worker_args(
                abs_path=abs_path,
                block_count=block_count,
                logical_block_size=logical_block_size,
                zlib_level=zlib_level,
            )
            with mp.Pool(processes=effective_block_workers) as pool:
                results_iter = pool.imap(_compress_pfsc_block_payload_worker, worker_args_iter, chunksize=1)
                raw_chunk: bytes
                compressed_chunk: bytes
                for raw_chunk, compressed_chunk in results_iter:
                    padded_chunk: bytes = raw_chunk.ljust(logical_block_size, b"\x00")
                    all_compressed_size += len(compressed_chunk)
                    gain_pct: float = ((len(padded_chunk) - len(compressed_chunk)) / len(padded_chunk)) * 100.0
                    selected_chunk: bytes = compressed_chunk if gain_pct >= threshold_gain else padded_chunk
                    if selected_chunk is compressed_chunk:
                        compressed_blocks += 1
                    spool_file.write(selected_chunk)
                    offsets.append(offsets[-1] + len(selected_chunk))
                    if progress_callback is not None:
                        progress_callback(len(raw_chunk))

        encoded_payload_size: int = offsets[-1]
        hypothetical_all_compressed_size: int = header_size + all_compressed_size
        if compressed_blocks == 0 or encoded_payload_size >= raw_size:
            return raw_size, False, 0.0, hypothetical_all_compressed_size

        effective_gain_pct: float = ((raw_size - encoded_payload_size) / raw_size) * 100.0
        if effective_gain_pct < min_file_gain:
            return raw_size, False, effective_gain_pct, hypothetical_all_compressed_size

        header: PFSCHeader = PFSCHeader(
            magic=consts.PFSC_MAGIC,
            unk4=consts.PFSC_UNK4,
            unk8=consts.PFSC_UNK8,
            logical_block_size=logical_block_size,
            block_offsets_offset=consts.PFSC_BLOCK_OFFSETS_OFFSET,
            data_offset=header_size,
            data_length=block_count * logical_block_size,
        )
        header_area: bytearray = bytearray(header_size)
        struct.pack_into(
            "<iiiiqqQq",
            header_area,
            0,
            header.magic,
            header.unk4,
            header.unk8,
            header.logical_block_size,
            header.logical_block_size,
            header.block_offsets_offset,
            header.data_offset,
            header.data_length,
        )
        struct.pack_into(f"<{block_count + 1}Q", header_area, consts.PFSC_BLOCK_OFFSETS_OFFSET, *offsets)
        spool_file.seek(0)
        spool_file.write(header_area)
        spool_file.truncate(encoded_payload_size)

    return encoded_payload_size, True, effective_gain_pct, hypothetical_all_compressed_size


def _copy_exact_bytes(*, source_file: BinaryIO, destination_file: BinaryIO, byte_count: int, chunk_size: int) -> None:
    """Copy exactly ``byte_count`` bytes between file objects.

    Args:
        source_file: Input binary stream.
        destination_file: Output binary stream.
        byte_count: Number of bytes to copy.
        chunk_size: Maximum chunk size for each read/write.

    Raises:
        BuildError: If source ends before ``byte_count`` bytes are read.
    """
    remaining_bytes: int = byte_count
    while remaining_bytes > 0:
        current_chunk_size: int = min(chunk_size, remaining_bytes)
        chunk: bytes = source_file.read(current_chunk_size)
        if len(chunk) == 0:
            raise BuildError("Stored payload source ended before expected size")
        destination_file.write(chunk)
        remaining_bytes -= len(chunk)


def write_source_to_blocks(
    out: BinaryIO,
    source_path: Path,
    payload_size: int,
    blocks: list[int],
    block_size: int,
) -> None:
    """Write a payload source file into non-contiguous destination blocks.

    Args:
        out: Open output image handle.
        source_path: Path to payload bytes source file.
        payload_size: Number of bytes to copy from source.
        blocks: Destination block numbers.
        block_size: Filesystem block size.
    """
    if payload_size <= 0:
        return
    chunk_size: int = min(block_size, 1024 * 1024)
    with source_path.open("rb") as source_file:
        remaining_bytes: int = payload_size
        for block in blocks:
            if remaining_bytes <= 0:
                break
            out.seek(block * block_size)
            block_bytes_to_copy: int = min(block_size, remaining_bytes)
            _copy_exact_bytes(
                source_file=source_file,
                destination_file=out,
                byte_count=block_bytes_to_copy,
                chunk_size=chunk_size,
            )
            remaining_bytes -= block_bytes_to_copy


def write_source_to_offset(out: BinaryIO, source_path: Path, payload_size: int, offset: int) -> None:
    """Write payload bytes from a source file into one contiguous output region.

    Args:
        out: Open output image handle.
        source_path: Path to payload bytes source file.
        payload_size: Number of bytes to copy from source.
        offset: Absolute output byte offset where payload begins.
    """
    if payload_size <= 0:
        return
    out.seek(offset)
    chunk_size: int = 1024 * 1024
    with source_path.open("rb") as source_file:
        _copy_exact_bytes(
            source_file=source_file,
            destination_file=out,
            byte_count=payload_size,
            chunk_size=chunk_size,
        )


def _drain_compression_progress_queue(progress_queue: SupportsIntQueue) -> int:
    """Drain queued compression progress deltas.

    Args:
        progress_queue: Queue-like object containing byte deltas from workers.

    Returns:
        Total queued byte delta drained from the queue.
    """
    drained_bytes: int = 0
    while True:
        try:
            drained_bytes += progress_queue.get_nowait()
        except queue.Empty:
            break
    return drained_bytes


def resolve_compression_worker_count(*, requested_cpu_count: int) -> int:
    """Resolve the effective compression worker count for the current workload.

    Args:
        requested_cpu_count: Requested worker count from CLI, where ``0`` means
            auto-select with ``max(1, cpu_count())``.

    Returns:
        Effective worker count, always at least ``1``.

    Raises:
        ValueError: If ``requested_cpu_count`` is negative.
    """
    if requested_cpu_count < 0:
        raise ValueError(f"requested_cpu_count must be non-negative, got {requested_cpu_count}")

    resolved_count: int
    if requested_cpu_count == 0:
        resolved_count = max(1, mp.cpu_count())
    else:
        resolved_count = requested_cpu_count

    return max(1, resolved_count)


def _compress_files_in_process(
    *,
    file_nodes_sorted: list[FileNode],
    threshold_gain: int,
    min_file_gain: int,
    min_compress_size: int,
    zlib_level: int,
    compression_cpu_count: int,
    dry_run: bool,
    total_bytes_to_process: int,
    progress: Progress,
    temp_folder: Path | None,
) -> None:
    """Compress files in-process while streaming progress updates.

    Args:
        file_nodes_sorted: Ordered file nodes to process.
        threshold_gain: Minimum per-block gain threshold.
        min_file_gain: Minimum whole-file gain percent required to store PFSC.
        min_compress_size: Minimum raw file size required before trying PFSC.
        zlib_level: zlib compression level.
        compression_cpu_count: CPU budget available to block-level compression for
            a single file.
        dry_run: When True, only analyze compression decisions without writing spool files.
        total_bytes_to_process: Total raw bytes represented by ``file_nodes_sorted``.
        progress: Progress reporter to update.
        temp_folder: Temporary folder used for PFSC spool files.
    """
    progress_total_units: int = total_bytes_to_process if total_bytes_to_process > 0 else len(file_nodes_sorted)
    displayed_progress_units: int = 0
    processed_raw_bytes: int = 0

    progress.step("compress", 0, progress_total_units, bytes_processed=0)

    for completed_files, file_node in enumerate(file_nodes_sorted, start=1):
        file_progress_bytes: int = 0
        file_base_processed_bytes: int = processed_raw_bytes

        def report_progress(
            delta_bytes: int,
            *,
            _file_base_processed_bytes: int = file_base_processed_bytes,
            _completed_files: int = completed_files,
        ) -> None:
            """Update progress as this file's logical blocks are processed."""
            nonlocal displayed_progress_units, file_progress_bytes
            file_progress_bytes += delta_bytes
            target_units: int = (
                min(total_bytes_to_process, _file_base_processed_bytes + file_progress_bytes)
                if total_bytes_to_process > 0
                else _completed_files
            )
            if target_units <= displayed_progress_units:
                return
            displayed_progress_units = target_units
            progress.step(
                "compress",
                displayed_progress_units,
                progress_total_units,
                bytes_processed=displayed_progress_units if total_bytes_to_process > 0 else 0,
            )

        if file_node.raw_size == 0 or file_node.raw_size < min_compress_size:
            store_file_node_raw(file_node)
        else:
            block_worker_count: int = resolve_block_compression_worker_count(
                requested_cpu_count=compression_cpu_count,
                file_size=file_node.raw_size,
            )
            if dry_run:
                stored_size: int
                is_compressed: bool
                gain_pct: float
                hypothetical_compressed_size: int
                stored_size, is_compressed, gain_pct, hypothetical_compressed_size = _analyze_pfsc_file_storage(
                    abs_path=file_node.abs_path,
                    threshold_gain=threshold_gain,
                    min_file_gain=min_file_gain,
                    zlib_level=zlib_level,
                    logical_block_size=consts.PFSC_LOGICAL_BLOCK_SIZE,
                    block_worker_count=block_worker_count,
                    progress_callback=report_progress,
                )
                file_node.stored_source_path = file_node.abs_path
                file_node.stored_source_is_temp = False
                file_node.stored_size = stored_size
                file_node.compressed = is_compressed
                file_node.gain_pct = gain_pct
                file_node.hypothetical_compressed_size = hypothetical_compressed_size
            else:
                spool_path: Path = _make_compression_spool_path(
                    source_path=file_node.abs_path,
                    temp_folder=temp_folder,
                )
                stored_size = 0
                is_compressed = False
                gain_pct = 0.0
                hypothetical_compressed_size = 0
                stored_size, is_compressed, gain_pct, hypothetical_compressed_size = _encode_pfsc_file_to_spool(
                    abs_path=file_node.abs_path,
                    spool_path=spool_path,
                    threshold_gain=threshold_gain,
                    min_file_gain=min_file_gain,
                    zlib_level=zlib_level,
                    logical_block_size=consts.PFSC_LOGICAL_BLOCK_SIZE,
                    block_worker_count=block_worker_count,
                    progress_callback=report_progress,
                )
                if is_compressed:
                    file_node.stored_source_path = spool_path
                    file_node.stored_source_is_temp = True
                else:
                    with suppress(FileNotFoundError):
                        spool_path.unlink()
                    file_node.stored_source_path = file_node.abs_path
                    file_node.stored_source_is_temp = False
                file_node.stored_size = stored_size
                file_node.compressed = is_compressed
                file_node.gain_pct = gain_pct
                file_node.hypothetical_compressed_size = hypothetical_compressed_size

        processed_raw_bytes += file_node.raw_size
        target_units = processed_raw_bytes if total_bytes_to_process > 0 else completed_files
        if target_units > displayed_progress_units:
            displayed_progress_units = target_units
            progress.step(
                "compress",
                displayed_progress_units,
                progress_total_units,
                bytes_processed=displayed_progress_units if total_bytes_to_process > 0 else 0,
            )

    if displayed_progress_units < progress_total_units:
        progress.step(
            "compress",
            progress_total_units,
            progress_total_units,
            bytes_processed=total_bytes_to_process if total_bytes_to_process > 0 else 0,
        )


def decode_pfsc_payload(payload: bytes, expected_logical_size: int | None = None) -> bytes:
    """Decode PFSC block-compressed payload bytes.

    Args:
        payload: Stored PFSC payload bytes.
        expected_logical_size: Optional expected logical size from inode metadata.

    Returns:
        Decoded logical file payload.

    Raises:
        ValueError: If PFSC payload structure or per-block decoding is invalid.
    """
    if len(payload) < consts.PFSC_HEADER_SIZE:
        raise ValueError("PFSC payload is too small for header")

    magic: int
    unk4: int
    unk8: int
    logical_block_size: int
    logical_block_size_2: int
    block_offsets_offset: int
    data_offset: int
    logical_size: int
    (
        magic,
        unk4,
        unk8,
        logical_block_size,
        logical_block_size_2,
        block_offsets_offset,
        data_offset,
        logical_size,
    ) = struct.unpack_from("<iiiiqqQq", payload, 0)

    if magic != consts.PFSC_MAGIC:
        raise ValueError(f"invalid PFSC magic 0x{magic:08X}")
    if unk4 != consts.PFSC_UNK4:
        raise ValueError(f"invalid PFSC unk4 value {unk4}, expected {consts.PFSC_UNK4}")
    if unk8 != consts.PFSC_UNK8:
        raise ValueError(f"invalid PFSC unk8 value {unk8}, expected {consts.PFSC_UNK8}")
    if logical_block_size != consts.PFSC_LOGICAL_BLOCK_SIZE:
        raise ValueError(
            f"invalid PFSC logical block size {logical_block_size}, expected {consts.PFSC_LOGICAL_BLOCK_SIZE}"
        )
    if logical_block_size_2 != logical_block_size:
        raise ValueError("PFSC block size mismatch between block_sz and block_sz2")
    if logical_size < 0:
        raise ValueError("PFSC logical size is negative")
    if logical_size % logical_block_size != 0:
        raise ValueError("PFSC logical size is not aligned to the logical block size")
    if block_offsets_offset < consts.PFSC_HEADER_SIZE:
        raise ValueError("PFSC block offset table overlaps header")
    if block_offsets_offset != consts.PFSC_BLOCK_OFFSETS_OFFSET:
        raise ValueError(
            f"invalid PFSC block offset table pointer {block_offsets_offset}, "
            f"expected {consts.PFSC_BLOCK_OFFSETS_OFFSET}"
        )
    if data_offset < consts.PFSC_INITIAL_DATA_OFFSET:
        raise ValueError("PFSC data offset is smaller than the minimum compatible header span")
    if data_offset > len(payload):
        raise ValueError("PFSC data offset exceeds payload length")

    block_count: int = logical_size // logical_block_size
    offsets_size: int = (block_count + 1) * consts.PFSC_OFFSET_ENTRY_SIZE
    offsets_end: int = block_offsets_offset + offsets_size
    if offsets_end > data_offset or offsets_end > len(payload):
        raise ValueError("PFSC payload is truncated before block offset table")

    offsets: list[int] = list(struct.unpack_from(f"<{block_count + 1}Q", payload, block_offsets_offset))
    if offsets[0] != data_offset:
        raise ValueError("PFSC block offsets must start at data_start")
    if offsets[-1] > len(payload):
        raise ValueError("PFSC block offsets exceed payload size")
    for idx in range(1, len(offsets)):
        if offsets[idx] < offsets[idx - 1]:
            raise ValueError("PFSC block offsets are not monotonic")

    logical_out: bytearray = bytearray()

    for idx in range(block_count):
        start: int = offsets[idx]
        end: int = offsets[idx + 1]
        stored_block: bytes = payload[start:end]
        block_expected_size: int = logical_block_size

        if len(stored_block) == block_expected_size:
            logical_block: bytes = stored_block
        elif len(stored_block) < block_expected_size:
            try:
                logical_block = zlib.decompress(stored_block)
            except zlib.error as exc:
                raise ValueError(f"PFSC block {idx} failed to decompress: {exc}") from exc
            if len(logical_block) != block_expected_size:
                raise ValueError(
                    f"PFSC block {idx} decompressed to {len(logical_block)} bytes, expected {block_expected_size}"
                )
        else:
            raise ValueError(
                f"PFSC block {idx} stored size {len(stored_block)} exceeds logical size {block_expected_size}"
            )
        logical_out.extend(logical_block)

    logical_payload: bytes = bytes(logical_out)
    if len(logical_payload) != logical_size:
        raise ValueError(f"PFSC logical output size {len(logical_payload)} does not match header size {logical_size}")
    if expected_logical_size is not None:
        if expected_logical_size < 0:
            raise ValueError("expected inode logical size is negative")
        if expected_logical_size > logical_size:
            raise ValueError(f"PFSC logical size {logical_size} is smaller than inode size {expected_logical_size}")
        return logical_payload[:expected_logical_size]
    return logical_payload


def decode_inode_payload(
    payload: bytes,
    inode: ParsedInode,
) -> bytes:
    """Decode one inode payload to logical bytes.

    Args:
        payload: Stored on-disk payload bytes.
        inode: Parsed inode metadata for the payload.

    Returns:
        Logical (decompressed) bytes.

    Raises:
        ValueError: If payload decoding fails.
    """
    if not inode.is_compressed:
        return payload
    return decode_pfsc_payload(payload=payload, expected_logical_size=inode.logical_size)


def validate_input(path: Path, require_game_files: bool = True) -> tuple[str | None, list[str]]:
    """Validate a source directory before packing.

    Args:
        path: Source directory to validate.
        require_game_files: When True, require the usual game-folder files,
            including ``sce_sys/param.json`` and ``eboot.bin``. When False,
            skip these checks and allow packing any directory tree.

    Returns:
        A tuple of ``(title_id, warnings)``. ``title_id`` is ``None`` when the
        relaxed mode skips game-file validation.

    Raises:
        BuildError: If the path is not a directory or strict validation fails.
    """
    if not path.exists() or not path.is_dir():
        raise BuildError(f"--path must be an existing directory: {path}")
    if not require_game_files:
        return None, []

    param_json = path / "sce_sys" / "param.json"
    if not param_json.exists():
        raise BuildError(f"Missing required file: {param_json}")

    parsed = read_param_json(param_json)
    title_id = parsed.get("titleId") or parsed.get("title_id")
    if not isinstance(title_id, str) or not title_id.strip():
        raise BuildError("param.json is missing a valid titleId/title_id")

    eboot_path = path / "eboot.bin"
    if not eboot_path.exists():
        raise BuildError(f"Missing required file: {eboot_path}")

    warnings: list[str] = []
    return title_id.strip(), warnings


def file_full_path_for_hash(file_node: FileNode) -> str:
    return "/" + file_node.rel_path.replace("\\", "/")


def dir_full_path_for_hash(dir_node: DirNode) -> str:
    if dir_node.rel_dir == "":
        return ""
    return "/" + dir_node.rel_dir.replace("\\", "/")


def fpt_hash(name: str, case_insensitive: bool = True) -> int:
    """Calculate flat_path_table hash.

    Args:
        name: Path to hash
        case_insensitive: If True, uppercase characters; if False, use as-is
    """
    h = 0
    for c in name:
        char = c.upper() if case_insensitive else c
        h = (ord(char) + (31 * h)) & 0xFFFFFFFF
    return h


def make_fpt_and_collision_blob(
    dirs_sorted: list[DirNode],
    files_sorted: list[FileNode],
    inode_by_path: dict[str, Inode],
    case_insensitive: bool = True,
) -> tuple[bytes, bytes | None, bool]:
    path_entries: list[tuple[str, int, bool]] = []
    for d in dirs_sorted:
        if d.rel_dir == "":
            continue
        path_entries.append((dir_full_path_for_hash(d), inode_by_path[f"dir:{d.rel_dir}"].number, True))
    for f in files_sorted:
        path_entries.append((file_full_path_for_hash(f), inode_by_path[f"file:{f.rel_path}"].number, False))

    by_hash: dict[int, list[tuple[str, int, bool]]] = {}
    for item in path_entries:
        h = fpt_hash(item[0], case_insensitive=case_insensitive)
        by_hash.setdefault(h, []).append(item)

    has_collision = any(len(v) > 1 for v in by_hash.values())

    hash_map: dict[int, int] = {}
    collision_blob = bytearray()
    collision_offsets: dict[int, int] = {}

    if has_collision:
        for h in sorted(by_hash.keys()):
            entries = by_hash[h]
            if len(entries) <= 1:
                continue
            offset = len(collision_blob)
            collision_offsets[h] = offset
            for full_path, ino_num, is_dir in entries:
                d = Dirent(
                    inode_number=ino_num,
                    type_code=consts.DIRENT_TYPE_DIRECTORY if is_dir else consts.DIRENT_TYPE_FILE,
                    name=full_path,
                )
                collision_blob += d.to_bytes()
            collision_blob += b"\x00" * 0x18

    for h in sorted(by_hash.keys()):
        entries = by_hash[h]
        if len(entries) == 1:
            _, ino_num, is_dir = entries[0]
            hash_map[h] = ino_num | (0x20000000 if is_dir else 0)
        else:
            hash_map[h] = 0x80000000 | collision_offsets[h]

    fpt = bytearray()
    for h in sorted(hash_map.keys()):
        fpt += struct.pack("<II", h, hash_map[h] & 0xFFFFFFFF)

    return bytes(fpt), (bytes(collision_blob) if has_collision else None), has_collision


def compute_file_storage(
    file_node: FileNode,
    compress: bool,
    threshold_gain: int,
    min_file_gain: int = 0,
    min_compress_size: int = 0,
    block_size: int = consts.PFSC_LOGICAL_BLOCK_SIZE,
    zlib_level: int = zlib.Z_BEST_COMPRESSION,
) -> None:
    """Decide how a file will be stored in the image.

    This function updates the provided FileNode in-place with source-path based
    metadata and does not retain payload bytes in memory.

    Args:
        file_node: FileNode describing the file to process.
        compress: Whether compression is enabled.
        threshold_gain: Minimum percent gain required to keep compressed data.
        min_file_gain: Minimum whole-file gain percent required to store PFSC.
        min_compress_size: Minimum raw file size required before trying PFSC.
        block_size: PFSC logical block size used for compression planning.
        zlib_level: Compression level passed to zlib.compress.

    Raises:
        OSError: If reading the file from disk fails.
        ValueError: If threshold_gain is outside the 0..100 range.
    """
    # Validate compression parameters up front.
    if not (0 <= threshold_gain <= 100):
        raise ValueError(f"threshold_gain must be between 0 and 100 inclusive, got {threshold_gain}")

    raw_size: int = file_node.abs_path.stat().st_size
    if not compress or raw_size == 0 or raw_size < min_compress_size:
        file_node.stored_source_path = file_node.abs_path
        file_node.stored_source_is_temp = False
        file_node.stored_size = raw_size
        file_node.compressed = False
        file_node.gain_pct = 0.0
        file_node.hypothetical_compressed_size = 0
        return

    stored_size: int
    is_compressed: bool
    gain_pct: float
    hypothetical_size: int
    stored_size, is_compressed, gain_pct, hypothetical_size = _analyze_pfsc_file_storage(
        abs_path=file_node.abs_path,
        threshold_gain=threshold_gain,
        min_file_gain=min_file_gain,
        zlib_level=zlib_level,
        logical_block_size=block_size,
        block_worker_count=1,
    )
    file_node.stored_source_path = file_node.abs_path
    file_node.stored_source_is_temp = False
    file_node.stored_size = stored_size
    file_node.compressed = is_compressed
    file_node.gain_pct = gain_pct
    file_node.hypothetical_compressed_size = hypothetical_size


def _compute_file_storage_worker(
    args: tuple[Path, int, int, int, bool, int, int, bool, SupportsIntQueue | None, Path | None],
) -> tuple[Path, Path, bool, int, bool, float, int]:
    """Worker function for parallel compression.

    This function is executed in a worker process and performs the same storage
    decision logic as :func:`compute_file_storage` but returns the results instead
    of mutating a FileNode.

    Args:
        args: Tuple containing ``(abs_path, threshold_gain, min_file_gain, min_compress_size, compress, block_size,
            zlib_level, dry_run, progress_queue, temp_folder)``.

    Returns:
        A tuple ``(file_path, stored_source_path, stored_source_is_temp, stored_size,
        compressed, gain_pct, hypothetical_compressed_size)``.
    """
    abs_path: Path
    threshold_gain: int
    min_file_gain: int
    min_compress_size: int
    compress: bool
    _block_size: int
    zlib_level: int
    dry_run: bool
    progress_queue: SupportsIntQueue | None
    temp_folder: Path | None
    (
        abs_path,
        threshold_gain,
        min_file_gain,
        min_compress_size,
        compress,
        _block_size,
        zlib_level,
        dry_run,
        progress_queue,
        temp_folder,
    ) = args

    raw_size: int = abs_path.stat().st_size
    if not compress or raw_size == 0 or raw_size < min_compress_size:
        return abs_path, abs_path, False, raw_size, False, 0.0, 0

    batched_progress_bytes: int = 0

    def report_progress(delta_bytes: int) -> None:
        """Batch worker progress updates before pushing them to the parent."""
        nonlocal batched_progress_bytes
        batched_progress_bytes += delta_bytes
        if progress_queue is not None and batched_progress_bytes >= PFSC_PROGRESS_REPORT_BYTES:
            progress_queue.put(batched_progress_bytes)
            batched_progress_bytes = 0

    stored_size: int
    is_compressed: bool
    gain_pct: float
    hypothetical_compressed_size: int
    if dry_run:
        stored_size, is_compressed, gain_pct, hypothetical_compressed_size = _analyze_pfsc_file_storage(
            abs_path=abs_path,
            threshold_gain=threshold_gain,
            min_file_gain=min_file_gain,
            zlib_level=zlib_level,
            logical_block_size=consts.PFSC_LOGICAL_BLOCK_SIZE,
            block_worker_count=1,
            progress_callback=report_progress if progress_queue is not None else None,
        )
        stored_source_path: Path = abs_path
        stored_source_is_temp: bool = False
    else:
        spool_path: Path = _make_compression_spool_path(source_path=abs_path, temp_folder=temp_folder)
        stored_size, is_compressed, gain_pct, hypothetical_compressed_size = _encode_pfsc_file_to_spool(
            abs_path=abs_path,
            spool_path=spool_path,
            threshold_gain=threshold_gain,
            min_file_gain=min_file_gain,
            zlib_level=zlib_level,
            logical_block_size=consts.PFSC_LOGICAL_BLOCK_SIZE,
            block_worker_count=1,
            progress_callback=report_progress if progress_queue is not None else None,
        )
        if is_compressed:
            stored_source_path = spool_path
            stored_source_is_temp = True
        else:
            with suppress(FileNotFoundError):
                spool_path.unlink()
            stored_source_path = abs_path
            stored_source_is_temp = False
    if progress_queue is not None and batched_progress_bytes > 0:
        progress_queue.put(batched_progress_bytes)
    return (
        abs_path,
        stored_source_path,
        stored_source_is_temp,
        stored_size,
        is_compressed,
        gain_pct,
        hypothetical_compressed_size,
    )


def scan_source_tree(root: Path, progress: Progress) -> tuple[dict[str, DirNode], dict[str, FileNode], int]:
    """Scan a source directory tree and return DirNode/FileNode maps.

    The returned structures mirror what the older monolithic implementation
    produced. This helper is used by the build flow and must preserve
    determinism and ordering.

    Args:
        root: Path to the directory to scan.
        progress: Progress instance used to report scanning progress.

    Returns:
        A tuple of (dirs, files, total_files) where dirs and files are maps keyed
        by relative path and total_files is the number of files discovered.
    """
    progress.status("\nDiscovering files...")
    abs_files: list[Path] = [p for p in root.rglob("*") if p.is_file()]
    abs_files.sort(key=lambda p: p.relative_to(root).as_posix().lower())

    dirs: dict[str, DirNode] = {"": DirNode(rel_dir="", name="uroot", parent_rel_dir=None)}
    files: dict[str, FileNode] = {}

    total: int = len(abs_files)
    total_bytes: int = 0
    for i, abs_path in enumerate(abs_files, start=1):
        rel: str = abs_path.relative_to(root).as_posix()
        parent: str = str(Path(rel).parent.as_posix())
        if parent == ".":
            parent = ""
        parts: list[str] = list(Path(rel).parts[:-1])

        curr: str = ""
        for part in parts:  # pragma: no cover - exercised indirectly in integration tests
            next_rel: str = f"{curr}/{part}" if curr else part
            if next_rel not in dirs:
                dirs[next_rel] = DirNode(rel_dir=next_rel, name=part, parent_rel_dir=curr if curr != "" else "")
                dirs[curr].children_dirs.append(next_rel)
            curr = next_rel

        if parent not in dirs:  # pragma: no cover - defensive fallback
            # This should not happen but keep it robust.
            dirs[parent] = DirNode(
                rel_dir=parent, name=Path(parent).name if parent else "uroot", parent_rel_dir=""
            )  # pragma: no cover

        name: str = Path(rel).name  # pragma: no cover - defensive path
        raw_size: int = abs_path.stat().st_size
        total_bytes += raw_size
        file_node: FileNode = FileNode(
            rel_path=rel,
            abs_path=abs_path,
            parent_rel_dir=parent,
            name=name,
            raw_size=raw_size,
        )
        files[rel] = file_node
        dirs[parent].children_files.append(rel)
        progress.step("scan", i, total, bytes_processed=total_bytes)

    for d in dirs.values():
        d.children_dirs.sort(key=str.lower)
        d.children_files.sort(key=str.lower)

    return dirs, files, total


def signed_inode_sig_offset(inode_number: int, ptr_index: int, block_size: int, inode_bits: int) -> int:
    """Compute the file offset of a signed inode pointer signature entry.

    Args:
        inode_number: Index of the inode within the inode table.
        ptr_index: Index of the direct/indirect pointer whose signature is desired.
        block_size: Filesystem block size.
        inode_bits: Signed inode width, 32 or 64.

    Returns:
        Absolute byte offset within the image where the signature should be written.

    Raises:
        BuildError: If block_size cannot contain any signed inodes.
    """
    layout: SignedInodeLayout = signed_inode_layout(inode_bits)
    inodes_per_block: int = block_size // layout.inode_size
    if inodes_per_block <= 0:
        raise BuildError("block size too small for signed inode table")
    inode_table_block: int = inode_number // inodes_per_block
    inode_index_in_block: int = inode_number % inodes_per_block
    inode_offset: int = block_size + (inode_table_block * block_size) + (inode_index_in_block * layout.inode_size)
    return inode_offset + layout.pointer_table_offset + (ptr_index * layout.entry_size)


def header_inode_block_sig_offset(ptr_index: int) -> int:
    """Return the offset inside the header for an inode-block signature slot.

    Each inode-table block reserves a 40-byte signature entry; this helper
    computes the offset for a given index.
    """
    return 0xB8 + (40 * ptr_index)


def make_sig_records_blob(blocks: list[int], block_size: int, inode_bits: int) -> bytes:
    """Serialize a list of block numbers into a signature-record block.

    Each record is SIG_SIZE bytes of signature followed by a layout-dependent
    block pointer. This helper writes zeroed signatures and fills the block
    numbers at the correct entry offsets so the caller may HMAC the resulting
    block and write the signatures later.

    Args:
        blocks: Sequence of block numbers to include in the record block.
        block_size: Size of the filesystem block.
        inode_bits: Signed inode width, 32 or 64.

    Returns:
        A bytes object of length `block_size` containing the packed records.
    """
    layout: SignedInodeLayout = signed_inode_layout(inode_bits)
    blob: bytearray = bytearray(block_size)
    offset: int = 0
    for block in blocks:
        struct.pack_into(layout.block_format, blob, offset + consts.SIG_SIZE, block)
        offset += layout.entry_size
    return bytes(blob)


def collect_signed_block_numbers(
    inode: Inode, block_size: int, indirect_block_records: dict[int, list[int]], inode_bits: int
) -> list[int]:
    """Return ordered data block numbers referenced by a signed inode.

    The returned list contains data block numbers in the order they should be
    written/read for the inode's payload. It follows the signed inode layout
    convention: direct blocks first, then records referenced by ib[0], then
    records referenced by ib[1] via child indirect blocks.

    Args:
        inode: Inode instance describing block counts and ib/db fields.
        block_size: Filesystem block size for computing sigs-per-block.
        indirect_block_records: Map from indirect-block number to its child
            data block list as constructed during layout assignment.
        inode_bits: Signed inode width, 32 or 64.

    Returns:
        List of block numbers in the order payload blocks appear.
    """
    layout: SignedInodeLayout = signed_inode_layout(inode_bits)
    sigs_per_block: int = block_size // layout.entry_size
    blocks: list[int] = []
    direct_count: int = min(inode.blocks, consts.MAX_DIRECT_BLOCKS)
    blocks.extend(inode.db[:direct_count])
    remaining: int = inode.blocks - direct_count

    if remaining > 0:
        ib0_children: list[int] = indirect_block_records.get(inode.ib[0], [])
        take: int = min(remaining, sigs_per_block)
        blocks.extend(ib0_children[:take])
        remaining -= take

    if remaining > 0:
        for child_indirect in indirect_block_records.get(inode.ib[1], []):
            child_children: list[int] = indirect_block_records.get(child_indirect, [])
            take = min(remaining, sigs_per_block)
            blocks.extend(child_children[:take])
            remaining -= take
            if remaining <= 0:
                break

    return blocks


def write_payload_to_blocks(out: BinaryIO, payload: bytes, blocks: list[int], block_size: int) -> None:
    """Write a payload into the specified blocks in the output image.

    Args:
        out: Open binary file object to write into.
        payload: Bytes payload to scatter into blocks.
        blocks: Sequence of block numbers where payload chunks are written.
        block_size: Filesystem block size.
    """
    for index, block in enumerate(blocks):
        chunk: bytes = payload[index * block_size : (index + 1) * block_size]
        if not chunk:
            break
        out.seek(block * block_size)
        out.write(chunk)


def assign_signed_inode_layout(
    inode: Inode,
    block_count: int,
    block_size: int,
    inode_bits: int,
    next_block: int,
    sig_targets: list[SignatureTarget],
    indirect_block_records: dict[int, list[int]],
) -> int:
    layout: SignedInodeLayout = signed_inode_layout(inode_bits)
    sigs_per_block: int = block_size // layout.entry_size
    if sigs_per_block <= 0:
        raise BuildError("Block size too small for signed pointer records")

    if block_count > 12 + sigs_per_block + (sigs_per_block * sigs_per_block):
        raise BuildError(
            f"Signed inode {inode.number} requires {block_count} blocks, exceeds current signed layout capacity"
        )

    for i in range(consts.MAX_DIRECT_BLOCKS):
        inode.db[i] = 0
    for i in range(consts.MAX_INDIRECT_BLOCKS):
        inode.ib[i] = 0

    direct_count = min(block_count, consts.MAX_DIRECT_BLOCKS)
    for i in range(direct_count):
        inode.db[i] = next_block
        sig_targets.append(
            SignatureTarget(
                next_block, signed_inode_sig_offset(inode.number, i, block_size, inode_bits), block_size, 0
            )
        )
        next_block += 1

    remaining = block_count - direct_count
    if remaining <= 0:
        return next_block

    inode.ib[0] = next_block
    ib0_block = next_block
    next_block += 1
    sig_targets.append(
        SignatureTarget(ib0_block, signed_inode_sig_offset(inode.number, 12, block_size, inode_bits), block_size, 1)
    )

    ib0_children: list[int] = []
    simple_count = min(remaining, sigs_per_block)
    for _ in range(simple_count):
        child_block = next_block
        next_block += 1
        ib0_children.append(child_block)
        sig_targets.append(
            SignatureTarget(
                child_block, ib0_block * block_size + len(ib0_children[:-1]) * layout.entry_size, block_size, 0
            )
        )
    indirect_block_records[ib0_block] = ib0_children
    remaining -= simple_count
    if remaining <= 0:
        return next_block

    inode.ib[1] = next_block
    ib1_parent = next_block
    next_block += 1
    sig_targets.append(
        SignatureTarget(ib1_parent, signed_inode_sig_offset(inode.number, 13, block_size, inode_bits), block_size, 2)
    )

    ib1_children: list[int] = []
    for idx in range(sigs_per_block):
        if remaining <= 0:
            break
        child_indirect_block = next_block
        next_block += 1
        ib1_children.append(child_indirect_block)
        sig_targets.append(
            SignatureTarget(child_indirect_block, ib1_parent * block_size + idx * layout.entry_size, block_size, 1)
        )

        child_records: list[int] = []
        child_count = min(remaining, sigs_per_block)
        for rec_idx in range(child_count):
            data_block = next_block
            next_block += 1
            child_records.append(data_block)
            sig_targets.append(
                SignatureTarget(
                    data_block, child_indirect_block * block_size + rec_idx * layout.entry_size, block_size, 0
                )
            )
        indirect_block_records[child_indirect_block] = child_records
        remaining -= child_count

    indirect_block_records[ib1_parent] = ib1_children
    if remaining > 0:
        raise BuildError(f"Signed inode {inode.number} still has {remaining} blocks unallocated")

    return next_block


def build_pfs(
    source_root: Path,
    output_path: Path,
    block_size: int,
    pfs_version: int,
    inode_bits: int,
    case_insensitive: bool,
    signed: bool,
    compress: bool,
    threshold_gain: int,
    cpu_count: int,
    zlib_level: int,
    dry_run: bool,
    verbose: bool,
    encrypted: bool = False,
    new_crypt: bool = False,
    ekpfs: bytes | None = None,
    skip_executable_compression: bool = False,
    min_file_gain: int = 0,
    min_compress_size: int = 0,
    temp_folder: Path | None = None,
) -> BuildStats:
    """Build a PFS image from a source tree.

    Args:
        source_root: Source directory to pack.
        output_path: Final image path to write.
        block_size: Filesystem block size in bytes.
        pfs_version: PFS profile version.
        inode_bits: Inode width in bits.
        case_insensitive: Whether to set the case-insensitive mode bit.
        signed: Whether to build a signed image.
        compress: Whether PFSC compression is enabled.
        threshold_gain: Minimum per-block gain required to keep PFSC blocks.
        cpu_count: Requested CPU worker count for compression.
        zlib_level: Zlib compression level.
        dry_run: When True, only report the layout without writing an image.
        verbose: Whether to emit verbose per-file decisions.
        encrypted: Whether to encrypt filesystem blocks.
        new_crypt: Whether to use the alternate EKPFS derivation.
        ekpfs: Optional EKPFS key bytes.
        skip_executable_compression: Whether to keep executable-like files raw.
        min_file_gain: Minimum whole-file gain required to store PFSC.
        min_compress_size: Minimum raw file size eligible for PFSC.
        temp_folder: Optional temporary folder for PFSC spool files.

    Returns:
        Build statistics for the completed image.
    """
    start: float = time.time()
    progress: Progress = Progress(enabled=True)
    temp_root: Path = resolve_temp_root(temp_folder=temp_folder)
    signed_inode_bits: int = 64 if signed and inode_bits == 64 else 32
    resolved_ekpfs: bytes = resolve_ekpfs_key(ekpfs=ekpfs)
    seed: bytes = consts.ZERO_PFS_SEED if (signed or encrypted) else b"\x00" * len(consts.ZERO_PFS_SEED)
    if not (0 <= min_file_gain <= 100):
        raise BuildError("min_file_gain must be within 0..100")
    if min_compress_size < 0:
        raise BuildError("min_compress_size must be non-negative")

    dirs: dict[str, DirNode]
    files: dict[str, FileNode]
    dirs, files, _ = scan_source_tree(source_root, progress)

    dir_nodes_sorted: list[DirNode] = sorted(dirs.values(), key=lambda d: d.rel_dir.lower())
    file_nodes_sorted: list[FileNode] = sorted(files.values(), key=lambda f: f.rel_path.lower())
    temporary_payload_paths: list[Path] = []

    compression_file_nodes: list[FileNode] = file_nodes_sorted
    if compress and skip_executable_compression:
        compression_file_nodes = []
        for f in file_nodes_sorted:
            if should_skip_executable_compression(f.name):
                store_file_node_raw(f)
            else:
                compression_file_nodes.append(f)
    if compress and min_compress_size > 0:
        eligible_file_nodes: list[FileNode] = []
        for f in compression_file_nodes:
            if f.raw_size < min_compress_size:
                store_file_node_raw(f)
            else:
                eligible_file_nodes.append(f)
        compression_file_nodes = eligible_file_nodes

    if compress and len(compression_file_nodes) > 0:
        # Calculate total bytes for compression progress
        total_bytes_to_process: int = sum(f.raw_size for f in compression_file_nodes)
        compression_cpu_count: int = resolve_compression_worker_count(requested_cpu_count=cpu_count)
        worker_count: int = compression_cpu_count
        file_nodes_by_path: dict[Path, FileNode] = {f.abs_path: f for f in compression_file_nodes}
        progress.status(
            f"\nCompressing {len(compression_file_nodes)} files ({human_readable_size(total_bytes_to_process)}) "
            f"using {worker_count} CPU core{'s' if worker_count != 1 else ''}..."
        )
        if worker_count == 1 or len(compression_file_nodes) == 1:
            # Single-worker or single-file path uses in-process flow so a large file
            # can leverage block-level multiprocessing inside one file.
            _compress_files_in_process(
                file_nodes_sorted=compression_file_nodes,
                threshold_gain=threshold_gain,
                min_file_gain=min_file_gain,
                min_compress_size=min_compress_size,
                zlib_level=zlib_level,
                compression_cpu_count=compression_cpu_count,
                dry_run=dry_run,
                total_bytes_to_process=total_bytes_to_process,
                progress=progress,
                temp_folder=temp_root,
            )
        else:
            # Use multiprocessing for parallel compression.
            progress_total_units: int = (
                total_bytes_to_process if total_bytes_to_process > 0 else len(compression_file_nodes)
            )
            progress.step("compress", 0, progress_total_units, bytes_processed=0)
            total_bytes_processed: int = 0
            displayed_progress_units: int = 0
            with mp.Manager() as manager:
                progress_queue: SupportsIntQueue = manager.Queue()
                worker_args: list[
                    tuple[Path, int, int, int, bool, int, int, bool, SupportsIntQueue | None, Path | None]
                ] = [
                    (
                        f.abs_path,
                        threshold_gain,
                        min_file_gain,
                        min_compress_size,
                        True,
                        consts.PFSC_LOGICAL_BLOCK_SIZE,
                        zlib_level,
                        dry_run,
                        progress_queue,
                        temp_root,
                    )
                    for f in compression_file_nodes
                ]
                with mp.Pool(processes=worker_count) as pool:
                    results = pool.imap_unordered(_compute_file_storage_worker, worker_args, chunksize=1)
                    remaining_results: int = len(worker_args)
                    while remaining_results > 0:
                        queued_bytes: int = _drain_compression_progress_queue(progress_queue=progress_queue)
                        if queued_bytes > 0:
                            displayed_progress_units = min(
                                total_bytes_to_process,
                                displayed_progress_units + queued_bytes,
                            )
                            progress.step(
                                "compress",
                                displayed_progress_units,
                                progress_total_units,
                                bytes_processed=displayed_progress_units if total_bytes_to_process > 0 else 0,
                            )
                        try:
                            result = results.next(timeout=0.1)
                        except mp.TimeoutError:
                            continue

                        remaining_results -= 1
                        (
                            abs_path,
                            stored_source_path,
                            stored_source_is_temp,
                            stored_size,
                            is_compressed,
                            gain_pct,
                            hyp_comp_size,
                        ) = result
                        file_node = file_nodes_by_path[abs_path]
                        file_node.stored_source_path = stored_source_path
                        file_node.stored_source_is_temp = stored_source_is_temp
                        file_node.stored_size = stored_size
                        file_node.compressed = is_compressed
                        file_node.gain_pct = gain_pct
                        file_node.hypothetical_compressed_size = hyp_comp_size
                        total_bytes_processed += file_node.raw_size
                        completed_files: int = len(worker_args) - remaining_results
                        target_progress_units: int = (
                            total_bytes_processed if total_bytes_to_process > 0 else completed_files
                        )
                        if displayed_progress_units < target_progress_units:
                            displayed_progress_units = target_progress_units
                            progress.step(
                                "compress",
                                displayed_progress_units,
                                progress_total_units,
                                bytes_processed=displayed_progress_units if total_bytes_to_process > 0 else 0,
                            )
            if displayed_progress_units < progress_total_units:
                progress.step(
                    "compress",
                    progress_total_units,
                    progress_total_units,
                    bytes_processed=total_bytes_to_process if total_bytes_to_process > 0 else 0,
                )
        if not dry_run:
            temporary_payload_paths.extend(
                [
                    file_node.stored_source_path
                    for file_node in compression_file_nodes
                    if file_node.stored_source_is_temp and file_node.stored_source_path is not None
                ]
            )
    else:
        # No compression: use source files directly and avoid buffering payloads.
        if len(file_nodes_sorted) > 0:
            total_bytes_to_process = sum(f.raw_size for f in file_nodes_sorted)
            progress.status(
                f"\nReading {len(file_nodes_sorted)} files ({human_readable_size(total_bytes_to_process)})..."
            )
            total_bytes_processed = 0
            for idx, f in enumerate(file_nodes_sorted, start=1):
                f.stored_source_path = f.abs_path
                f.stored_source_is_temp = False
                f.stored_size = f.raw_size
                f.compressed = False
                f.gain_pct = 0.0
                f.hypothetical_compressed_size = 0
                total_bytes_processed += f.raw_size
                progress.step(
                    "read", total_bytes_processed, total_bytes_to_process, bytes_processed=total_bytes_processed
                )

    now: int = int(time.time())
    inodes: list[Inode] = []

    super_root_inode = Inode(
        number=0,
        mode=consts.INODE_MODE_DIR | consts.INODE_RX_ONLY,
        nlink=1,
        flags=consts.INODE_FLAG_INTERNAL
        | (0 if signed else consts.INODE_FLAG_READONLY)
        | (consts.INODE_FLAG_SIGNED_EXTRA if signed else 0),
        size=block_size,
        size_compressed=block_size,
        blocks=1,
        time_sec=now,
    )
    fpt_inode = Inode(
        number=1,
        mode=consts.INODE_MODE_FILE | consts.INODE_RX_ONLY,
        nlink=1,
        flags=consts.INODE_FLAG_INTERNAL
        | (0 if signed else consts.INODE_FLAG_READONLY)
        | (consts.INODE_FLAG_SIGNED_EXTRA if signed else 0),
        size=0,
        size_compressed=0,
        blocks=1,
        time_sec=now,
    )

    collision_inode: Inode | None = None

    uroot_inode_num = 2
    uroot_inode = Inode(
        number=uroot_inode_num,
        mode=consts.INODE_MODE_DIR | consts.INODE_RX_ONLY,
        nlink=3,
        flags=(0 if signed else consts.INODE_FLAG_READONLY) | (consts.INODE_FLAG_SIGNED_EXTRA if signed else 0),
        size=block_size,
        size_compressed=block_size,
        blocks=1,
        time_sec=now,
    )

    inodes.extend([super_root_inode, fpt_inode, uroot_inode])
    dirs[""].inode = uroot_inode

    inode_by_path: dict[str, Inode] = {"dir:": uroot_inode}

    next_inode_number = 3

    non_root_dirs = [d for d in dir_nodes_sorted if d.rel_dir != ""]
    for d in non_root_dirs:
        ino = Inode(
            number=next_inode_number,
            mode=consts.INODE_MODE_DIR | consts.INODE_RX_ONLY,
            nlink=2,
            flags=consts.INODE_FLAG_READONLY | (consts.INODE_FLAG_SIGNED_EXTRA if signed else 0),
            size=block_size,
            size_compressed=block_size,
            blocks=1,
            time_sec=now,
        )
        d.inode = ino
        inode_by_path[f"dir:{d.rel_dir}"] = ino
        inodes.append(ino)
        next_inode_number += 1

    for f in file_nodes_sorted:
        flags = (
            consts.INODE_FLAG_READONLY
            | (consts.INODE_FLAG_COMPRESSED if f.compressed else 0)
            | (consts.INODE_FLAG_SIGNED_EXTRA if signed else 0)
        )
        blocks = max(1, ceil_div(f.stored_size, block_size)) if f.stored_size > 0 else 1
        file_size = f.stored_size
        file_size_compressed = f.raw_size if f.compressed else f.stored_size
        ino = Inode(
            number=next_inode_number,
            mode=consts.INODE_MODE_FILE | consts.INODE_RX_ONLY,
            nlink=1,
            flags=flags,
            size=file_size,
            size_compressed=file_size_compressed,
            blocks=blocks,
            time_sec=now,
        )
        f.inode = ino
        inode_by_path[f"file:{f.rel_path}"] = ino
        inodes.append(ino)
        next_inode_number += 1

    for d in dir_nodes_sorted:
        parent_ino = inode_by_path["dir:" + (d.parent_rel_dir if d.parent_rel_dir is not None else "")]
        this_ino = inode_by_path["dir:" + d.rel_dir]

        d.dirents = [
            Dirent(this_ino.number, consts.DIRENT_TYPE_DOT, "."),
            Dirent(parent_ino.number if d.rel_dir != "" else this_ino.number, consts.DIRENT_TYPE_DOTDOT, ".."),
        ]

        for child_rel_dir in d.children_dirs:
            child_dir = dirs[child_rel_dir]
            d.dirents.append(Dirent(child_dir.inode.number, consts.DIRENT_TYPE_DIRECTORY, child_dir.name))
            this_ino.nlink += 1

        for child_rel_file in d.children_files:
            child_file = files[child_rel_file]
            d.dirents.append(Dirent(child_file.inode.number, consts.DIRENT_TYPE_FILE, child_file.name))

    fpt_blob, collision_blob, has_collision = make_fpt_and_collision_blob(
        dir_nodes_sorted,
        file_nodes_sorted,
        inode_by_path,
        case_insensitive=case_insensitive,
    )

    if has_collision:
        collision_inode = Inode(
            number=2,
            mode=consts.INODE_MODE_FILE | consts.INODE_RX_ONLY,
            nlink=1,
            flags=consts.INODE_FLAG_INTERNAL
            | consts.INODE_FLAG_READONLY
            | (consts.INODE_FLAG_SIGNED_EXTRA if signed else 0),
            size=len(collision_blob or b""),
            size_compressed=len(collision_blob or b""),
            blocks=max(1, ceil_div(len(collision_blob or b""), block_size)),
            time_sec=now,
        )
        inodes = [super_root_inode, fpt_inode, collision_inode, uroot_inode] + [
            ino for ino in inodes if ino.number >= 3
        ]

        # Renumber all non-special inodes after inserting collision_resolver.
        remap: dict[int, int] = {}
        for idx, ino in enumerate(inodes):
            old = ino.number
            ino.number = idx
            remap[old] = idx

        # Inode objects are already renumbered in-place above. Only dirent links
        # still carry old inode numbers and need remapping.
        for d in dir_nodes_sorted:
            for ent in d.dirents:
                ent.inode_number = remap[ent.inode_number]

        inode_by_path = {}
        for d in dir_nodes_sorted:
            inode_by_path[f"dir:{d.rel_dir}"] = d.inode
        for f in file_nodes_sorted:
            inode_by_path[f"file:{f.rel_path}"] = f.inode

    super_root_dirents: list[Dirent] = [Dirent(fpt_inode.number, consts.DIRENT_TYPE_FILE, "flat_path_table")]
    if has_collision and collision_inode is not None:
        super_root_dirents.append(Dirent(collision_inode.number, consts.DIRENT_TYPE_FILE, "collision_resolver"))
    super_root_dirents.append(Dirent(uroot_inode.number, consts.DIRENT_TYPE_DIRECTORY, "uroot"))

    inode_count = len(inodes)
    inode_size: int = signed_inode_layout(signed_inode_bits).inode_size if signed else consts.INODE_D32_SIZE
    inodes_per_block = block_size // inode_size
    inode_block_count = ceil_div(inode_count, inodes_per_block)

    all_nodes_data: list[tuple[Inode, int, bool, bytes | None, Path | None]] = []

    # Root directory first, then nested dirs, then files.
    root_blob = b"".join(d.to_bytes() for d in dirs[""].dirents)
    all_nodes_data.append((dirs[""].inode, len(root_blob), True, root_blob, None))
    for d in non_root_dirs:
        blob = b"".join(ent.to_bytes() for ent in d.dirents)
        all_nodes_data.append((d.inode, len(blob), True, blob, None))
    for f in file_nodes_sorted:
        if f.stored_source_path is None:
            raise BuildError(f"Internal error: missing stored payload source for {f.rel_path}")
        all_nodes_data.append((f.inode, f.stored_size, False, None, f.stored_source_path))

    signature_targets: list[SignatureTarget] = []
    indirect_block_records: dict[int, list[int]] = {}
    reserved_empty_blocks: set[int] = set()

    if signed:
        max_signed_size: int = signed_inode_capacity_bytes(block_size, signed_inode_bits)
        if max_signed_size <= 0:
            raise BuildError("Block size too small for signed PFS layout")
        for f in file_nodes_sorted:
            if f.stored_size > max_signed_size:
                raise BuildError(
                    f"Signed mode cannot represent file '{f.rel_path}' with block size {block_size}; "
                    f"max supported stored payload is {max_signed_size} bytes"
                )
        ndblock = 1
        for i in range(inode_block_count):
            signature_targets.append(SignatureTarget(1 + i, header_inode_block_sig_offset(i), block_size, 3))
        ndblock += inode_block_count

        super_root_inode.blocks = 1
        ndblock = assign_signed_inode_layout(
            super_root_inode,
            super_root_inode.blocks,
            block_size,
            signed_inode_bits,
            ndblock,
            signature_targets,
            indirect_block_records,
        )

        fpt_inode.size = len(fpt_blob)
        fpt_inode.size_compressed = len(fpt_blob)
        fpt_inode.blocks = max(1, ceil_div(len(fpt_blob), block_size))
        ndblock = assign_signed_inode_layout(
            fpt_inode,
            fpt_inode.blocks,
            block_size,
            signed_inode_bits,
            ndblock,
            signature_targets,
            indirect_block_records,
        )

        if has_collision and collision_inode is not None:
            collision_inode.blocks = max(1, ceil_div(len(collision_blob or b""), block_size))
            ndblock = assign_signed_inode_layout(
                collision_inode,
                collision_inode.blocks,
                block_size,
                signed_inode_bits,
                ndblock,
                signature_targets,
                indirect_block_records,
            )

        ndblock += 2
        reserved_empty_blocks.update({ndblock - 2, ndblock - 1})

        for inode, payload_size, is_dir, _payload_bytes, _payload_source in all_nodes_data:
            blocks = max(1, ceil_div(payload_size, block_size)) if payload_size > 0 else 1
            inode.blocks = blocks
            if is_dir:
                inode.size = blocks * block_size
                inode.size_compressed = inode.size
            else:
                if inode.flags & consts.INODE_FLAG_COMPRESSED:
                    inode.size = payload_size
                else:
                    inode.size = payload_size
                    inode.size_compressed = inode.size
            ndblock = assign_signed_inode_layout(
                inode,
                blocks,
                block_size,
                signed_inode_bits,
                ndblock,
                signature_targets,
                indirect_block_records,
            )

        signature_targets.append(SignatureTarget(0, consts.HEADER_DIGEST_OFFSET, consts.HEADER_DIGEST_SIZE, 4))
    else:
        ndblock = 1
        ndblock += inode_block_count

        super_root_inode.db[0] = ndblock
        ndblock += super_root_inode.blocks

        fpt_inode.size = len(fpt_blob)
        fpt_inode.size_compressed = len(fpt_blob)
        fpt_inode.blocks = max(1, ceil_div(len(fpt_blob), block_size))
        fpt_inode.db[0] = ndblock
        for i in range(1, consts.MAX_DIRECT_BLOCKS):
            fpt_inode.db[i] = -1
        ndblock += fpt_inode.blocks

        if has_collision and collision_inode is not None:
            collision_inode.db[0] = ndblock
            for i in range(1, consts.MAX_DIRECT_BLOCKS):
                collision_inode.db[i] = -1
            ndblock += collision_inode.blocks
        else:
            ndblock += 1
            reserved_empty_blocks.add(ndblock - 1)

        for inode, payload_size, is_dir, _payload_bytes, _payload_source in all_nodes_data:
            blocks = max(1, ceil_div(payload_size, block_size)) if payload_size > 0 else 1
            inode.db[0] = ndblock
            inode.blocks = blocks
            for i in range(1, consts.MAX_DIRECT_BLOCKS):
                inode.db[i] = -1
            if is_dir:
                inode.size = blocks * block_size
                inode.size_compressed = inode.size
            else:
                if inode.flags & consts.INODE_FLAG_COMPRESSED:
                    inode.size = payload_size
                else:
                    inode.size = payload_size
                    inode.size_compressed = inode.size
            ndblock += blocks

    nblock = 1
    final_ndblock = ndblock

    validate_d32_ranges(inodes, final_ndblock)

    stats = BuildStats(input_path=source_root, output_path=output_path)
    stats.total_files = len(file_nodes_sorted)
    stats.uncompressed_total_size = sum(f.raw_size for f in file_nodes_sorted)
    stats.stored_total_size = sum(f.stored_size for f in file_nodes_sorted)
    stats.all_compressed_total_size = sum(f.hypothetical_compressed_size for f in file_nodes_sorted)
    stats.compressed_files = sum(1 for f in file_nodes_sorted if f.compressed)
    stats.uncompressed_files = stats.total_files - stats.compressed_files
    stats.block_size = block_size
    stats.block_alignment_waste = sum(
        (ceil_div(f.stored_size, block_size) * block_size - f.stored_size) if f.stored_size > 0 else block_size
        for f in file_nodes_sorted
    )
    if verbose:
        for f in file_nodes_sorted:
            state: str = "compressed" if f.compressed else "raw"
            info(
                f"[file] {f.rel_path}: raw={f.raw_size} stored={f.stored_size} gain={f.gain_pct:.2f}% mode={state}",
                icon_name="file",
            )

    if dry_run:
        stats.elapsed_seconds = time.time() - start
        return stats

    mode = compose_pfs_mode_with_options(
        inode_bits=inode_bits,
        case_insensitive=case_insensitive,
        signed=signed,
        encrypted=encrypted,
    )

    progress.status(f"\nWriting PFS image to {output_path}...")
    output_path.parent.mkdir(parents=True, exist_ok=True)

    # Write to a temporary file first
    tmp_path = Path(str(output_path) + ".tmp")
    try:
        image_size = final_ndblock * block_size
        with tmp_path.open("w+b") as out:
            out.truncate(image_size)

            hdr = bytearray(block_size)
            struct.pack_into("<q", hdr, 0x00, pfs_version)
            struct.pack_into("<q", hdr, 0x08, consts.PFS_MAGIC)
            struct.pack_into("<q", hdr, 0x10, 0)
            struct.pack_into("<BBBB", hdr, 0x18, 0, 0, 1, 0)
            struct.pack_into("<H", hdr, 0x1C, mode)
            struct.pack_into("<H", hdr, 0x1E, 0)
            struct.pack_into("<I", hdr, 0x20, block_size)
            struct.pack_into("<I", hdr, 0x24, 0)
            struct.pack_into("<q", hdr, 0x28, nblock)
            struct.pack_into("<q", hdr, 0x30, inode_count)
            struct.pack_into("<q", hdr, 0x38, final_ndblock)
            struct.pack_into("<q", hdr, 0x40, inode_block_count)
            ib_sig_bytes = build_inode_block_sig_s64(inode_block_count, block_size, now, signed=signed)
            hdr[0x50 : 0x50 + len(ib_sig_bytes)] = ib_sig_bytes
            if signed or encrypted:
                struct.pack_into("<I", hdr, 0x36C, 1)
                hdr[0x370 : 0x370 + len(seed)] = seed
            else:
                struct.pack_into("<I", hdr, 0x368, 1)

            out.seek(0)
            out.write(hdr)

            out.seek(block_size)
            for ino in inodes:
                if signed:
                    if signed_inode_bits == 64:
                        out.write(ino.to_bytes_signed64())
                    else:
                        out.write(ino.to_bytes_signed32())
                else:
                    out.write(ino.to_bytes())
                if (out.tell() % block_size) > (block_size - inode_size):
                    out.seek(out.tell() + (block_size - (out.tell() % block_size)))

            out.seek(block_size * (inode_block_count + 1))
            for d in super_root_dirents:
                out.write(d.to_bytes())

            if signed:
                write_payload_to_blocks(
                    out,
                    fpt_blob,
                    collect_signed_block_numbers(fpt_inode, block_size, indirect_block_records, signed_inode_bits),
                    block_size,
                )
                if has_collision and collision_inode is not None and collision_blob is not None:
                    write_payload_to_blocks(
                        out,
                        collision_blob,
                        collect_signed_block_numbers(
                            collision_inode, block_size, indirect_block_records, signed_inode_bits
                        ),
                        block_size,
                    )
                for block, records in indirect_block_records.items():
                    out.seek(block * block_size)
                    out.write(make_sig_records_blob(records, block_size, signed_inode_bits))
            else:
                out.seek(fpt_inode.db[0] * block_size)
                out.write(fpt_blob)

                if has_collision and collision_inode is not None and collision_blob is not None:
                    out.seek(collision_inode.db[0] * block_size)
                    out.write(collision_blob)

            # Calculate total bytes for progress tracking
            total_write_bytes: int = sum(
                payload_size for _inode, payload_size, _is_dir, _bytes, _path in all_nodes_data
            )
            written_bytes: int = 0
            for inode, payload_size, _is_dir, payload_bytes, payload_source_path in all_nodes_data:
                if payload_bytes is not None:
                    if signed:
                        write_payload_to_blocks(
                            out,
                            payload_bytes,
                            collect_signed_block_numbers(inode, block_size, indirect_block_records, signed_inode_bits),
                            block_size,
                        )
                    else:
                        out.seek(inode.db[0] * block_size)
                        out.write(payload_bytes)
                else:
                    if payload_source_path is None:
                        raise BuildError(f"Internal error: payload source is missing for inode {inode.number}")
                    if signed:
                        write_source_to_blocks(
                            out=out,
                            source_path=payload_source_path,
                            payload_size=payload_size,
                            blocks=collect_signed_block_numbers(
                                inode, block_size, indirect_block_records, signed_inode_bits
                            ),
                            block_size=block_size,
                        )
                    else:
                        write_source_to_offset(
                            out=out,
                            source_path=payload_source_path,
                            payload_size=payload_size,
                            offset=inode.db[0] * block_size,
                        )
                written_bytes += payload_size
                progress.step("write", written_bytes, total_write_bytes, bytes_processed=written_bytes)

            if signed:
                sign_key = pfs_gen_sign_key(resolved_ekpfs, seed)
                for level in range(5):
                    for target in (t for t in signature_targets if t.level == level):
                        block_data = bytearray(_read_exact(out, target.block * block_size, target.size))
                        sig_pos_in_block = target.sig_offset - (target.block * block_size)
                        if 0 <= sig_pos_in_block <= len(block_data) - consts.SIG_SIZE:
                            block_data[sig_pos_in_block : sig_pos_in_block + consts.SIG_SIZE] = (
                                b"\x00" * consts.SIG_SIZE
                            )
                        out.seek(target.sig_offset)
                        out.write(hmac_sha256(sign_key, bytes(block_data)))

            if encrypted:
                encrypt_image_filesystem(
                    out,
                    block_size=block_size,
                    total_blocks=final_ndblock,
                    ekpfs=resolved_ekpfs,
                    seed=seed,
                    new_crypt=new_crypt,
                    skip_block_numbers=reserved_empty_blocks,
                )

        # Validate the temporary file
        validate_image_quick(
            tmp_path,
            block_size,
            mode,
            pfs_version,
            ekpfs=resolved_ekpfs if encrypted else None,
            new_crypt=new_crypt,
        )

        # Rename temp file to final output path
        shutil.move(str(tmp_path), str(output_path))
        for temporary_payload_path in temporary_payload_paths:
            with suppress(FileNotFoundError):
                temporary_payload_path.unlink()
        progress.status(f"Successfully wrote {human_readable_size(image_size)} image")

    except Exception:
        # Broad exception handler is used here to ensure temporary file cleanup
        # for any failure that occurs during writing. We intentionally catch
        # ``Exception`` (not ``BaseException``) so cleanup runs for I/O and
        # runtime errors while allowing KeyboardInterrupt and SystemExit to
        # propagate. Re-raise the original exception after removing the temp
        # file so callers observe the original traceback.
        if tmp_path.exists():
            with suppress(FileNotFoundError):
                tmp_path.unlink()
        for temporary_payload_path in temporary_payload_paths:
            with suppress(FileNotFoundError):
                temporary_payload_path.unlink()
        raise

    stats.elapsed_seconds = time.time() - start
    return stats


def validate_image_quick(
    image_path: Path,
    expected_block_size: int,
    expected_mode: int,
    expected_version: int,
    ekpfs: bytes | None = None,
    new_crypt: bool = False,
) -> None:
    with image_path.open("rb") as f:
        header: ParsedHeader = parse_image_header(f)
        inodes: list[ParsedInode] = parse_image_inodes(f, header, ekpfs=ekpfs, new_crypt=new_crypt)

    if header.version != expected_version or header.magic != consts.PFS_MAGIC:
        raise BuildError("Post-write validation failed: invalid header magic/version")
    if header.block_size != expected_block_size:
        raise BuildError("Post-write validation failed: unexpected block size")
    if header.readonly != 1:
        raise BuildError("Post-write validation failed: header readonly byte is not set")
    if header.mode != expected_mode:
        raise BuildError("Post-write validation failed: unexpected mode flags")
    if header.dinode_count < 3 or header.dinode_block_count < 1:
        raise BuildError("Post-write validation failed: inode table looks invalid")
    signed: bool = (expected_mode & consts.PFS_MODE_SIGNED) != 0
    for inode in inodes:
        if inode.mode & consts.INODE_MODE_ANY_WRITE:
            raise BuildError(
                f"Post-write validation failed: inode {inode.number} has write bits set (mode=0x{inode.mode:04X})"
            )
        if not signed and (inode.flags & consts.INODE_FLAG_READONLY) == 0:
            raise BuildError(
                f"Post-write validation failed: inode {inode.number} missing readonly flag (flags=0x{inode.flags:08X})"
            )


def prompt_overwrite(output_path: Path) -> bool:
    """Prompt user if output file exists. Returns True if it should proceed."""
    if not output_path.exists():
        return True

    info(f"Output file already exists: {output_path}", icon_name="file")
    while True:
        response = input("Overwrite? [Y/n] ").strip().lower()
        if response in ["y", "yes", ""]:
            # Clean up any partial .tmp file if it exists
            tmp_path = Path(str(output_path) + ".tmp")
            if tmp_path.exists():
                with suppress(OSError):
                    tmp_path.unlink()
            return True
        elif response in ["n", "no"]:
            return False
        else:
            info("Please enter 'y' or 'n'")


@dataclass
class ParsedHeader:
    version: int
    magic: int
    mode: int
    block_size: int
    nblock: int
    dinode_count: int
    ndblock: int
    dinode_block_count: int
    readonly: int
    seed: bytes


@dataclass
class ParsedInode:
    number: int
    mode: int
    nlink: int
    flags: int
    size: int
    size_compressed: int
    blocks: int
    db: list[int]
    ib: list[int]
    db_sig: list[bytes] = field(default_factory=list)
    ib_sig: list[bytes] = field(default_factory=list)

    @property
    def is_dir(self) -> bool:
        return (self.mode & consts.INODE_MODE_DIR) != 0

    @property
    def is_file(self) -> bool:
        return (self.mode & consts.INODE_MODE_FILE) != 0

    @property
    def is_compressed(self) -> bool:
        return (self.flags & consts.INODE_FLAG_COMPRESSED) != 0

    @property
    def stored_size(self) -> int:
        return self.size if self.is_compressed else self.size_compressed

    @property
    def logical_size(self) -> int:
        return self.size_compressed if self.is_compressed else self.size


@dataclass
class ParsedDirent:
    inode_number: int
    type_code: int
    name: str


def parse_image_header(fh: BinaryIO) -> ParsedHeader:
    hdr = _read_exact(fh, 0, 0x400)
    version, magic = struct.unpack_from("<qq", hdr, 0x00)
    readonly = struct.unpack_from("<B", hdr, 0x1A)[0]
    mode = struct.unpack_from("<H", hdr, 0x1C)[0]
    block_size = struct.unpack_from("<I", hdr, 0x20)[0]
    nblock = struct.unpack_from("<q", hdr, 0x28)[0]
    dinode_count = struct.unpack_from("<q", hdr, 0x30)[0]
    ndblock = struct.unpack_from("<q", hdr, 0x38)[0]
    dinode_block_count = struct.unpack_from("<q", hdr, 0x40)[0]
    seed = hdr[0x370:0x380]
    return ParsedHeader(
        version=version,
        magic=magic,
        mode=mode,
        block_size=block_size,
        nblock=nblock,
        dinode_count=dinode_count,
        ndblock=ndblock,
        dinode_block_count=dinode_block_count,
        readonly=readonly,
        seed=seed,
    )


def parse_image_inode(blob: bytes, number: int, signed: bool, inode_bits: int = 32) -> ParsedInode:
    expected_size: int
    if signed:
        expected_size = signed_inode_layout(inode_bits).inode_size
    else:
        expected_size = consts.INODE_D32_SIZE
    if len(blob) != expected_size:
        raise ValueError(f"inode blob has invalid size {len(blob)}")

    mode, nlink, flags = struct.unpack_from("<HHI", blob, 0x00)
    size, size_compressed = struct.unpack_from("<qq", blob, 0x08)
    blocks = struct.unpack_from("<I", blob, 0x60)[0]

    if signed:
        layout: SignedInodeLayout = signed_inode_layout(inode_bits)
        db_sig: list[bytes] = []
        db: list[int] = []
        ib_sig: list[bytes] = []
        ib: list[int] = []
        offset: int = layout.pointer_table_offset
        for _ in range(consts.MAX_DIRECT_BLOCKS):
            db_sig.append(blob[offset : offset + consts.SIG_SIZE])
            db.append(struct.unpack_from(layout.block_format, blob, offset + consts.SIG_SIZE)[0])
            offset += layout.entry_size
        for _ in range(consts.MAX_INDIRECT_BLOCKS):
            ib_sig.append(blob[offset : offset + consts.SIG_SIZE])
            ib.append(struct.unpack_from(layout.block_format, blob, offset + consts.SIG_SIZE)[0])
            offset += layout.entry_size
        return ParsedInode(
            number=number,
            mode=mode,
            nlink=nlink,
            flags=flags,
            size=size,
            size_compressed=size_compressed,
            blocks=blocks,
            db=db,
            ib=ib,
            db_sig=db_sig,
            ib_sig=ib_sig,
        )

    db = list(struct.unpack_from("<12i", blob, 0x64))
    ib = list(struct.unpack_from("<5i", blob, 0x94))
    return ParsedInode(
        number=number,
        mode=mode,
        nlink=nlink,
        flags=flags,
        size=size,
        size_compressed=size_compressed,
        blocks=blocks,
        db=db,
        ib=ib,
    )


def parse_image_inodes(
    fh: BinaryIO,
    header: ParsedHeader,
    ekpfs: bytes | None = None,
    new_crypt: bool = False,
) -> list[ParsedInode]:
    inodes: list[ParsedInode] = []
    signed: bool = (header.mode & consts.PFS_MODE_SIGNED) != 0
    inode_bits: int = signed_inode_bits_from_mode(header.mode) if signed else 32
    inode_size: int = signed_inode_layout(inode_bits).inode_size if signed else consts.INODE_D32_SIZE
    inodes_per_block = header.block_size // inode_size
    if inodes_per_block <= 0:
        raise ValueError("block size too small for inode table")

    inode_idx = 0
    table_offset = header.block_size
    for block_idx in range(header.dinode_block_count):
        block = read_image_bytes(
            fh,
            header,
            table_offset + block_idx * header.block_size,
            header.block_size,
            ekpfs=ekpfs,
            new_crypt=new_crypt,
        )
        for i in range(inodes_per_block):
            if inode_idx >= header.dinode_count:
                return inodes
            off = i * inode_size
            inode_blob = block[off : off + inode_size]
            inodes.append(parse_image_inode(inode_blob, inode_idx, signed=signed, inode_bits=inode_bits))
            inode_idx += 1
    return inodes


def parse_sig_record_block(
    fh: BinaryIO,
    block_num: int,
    inode_bits: int,
    header: ParsedHeader | None = None,
    block_size: int | None = None,
    ekpfs: bytes | None = None,
    new_crypt: bool = False,
) -> list[tuple[bytes, int]]:
    """Parse one indirect signature-record block from an image.

    Args:
        fh: Open image file handle.
        block_num: Filesystem block number containing the record list.
        inode_bits: Signed inode width, 32 or 64.
        header: Parsed image header, or ``None`` when reading an already-decrypted
            raw block blob.
        block_size: Optional explicit block size for compatibility with older callers.
        ekpfs: Optional EKPFS key material. Defaults to the all-zero key.
        new_crypt: When True, use the alternate newCrypt key derivation path.

    Returns:
        Parsed `(signature, block_number)` tuples.
    """
    if header is None:
        if block_size is None:
            raise ValueError("block_size is required when header is not provided")
        resolved_block_size: int = block_size
        blob: bytes = _read_exact(fh, block_num * resolved_block_size, resolved_block_size)
    else:
        resolved_block_size = header.block_size if block_size is None else block_size
        blob = read_image_bytes(
            fh,
            header,
            block_num * resolved_block_size,
            resolved_block_size,
            ekpfs=ekpfs,
            new_crypt=new_crypt,
        )
    layout: SignedInodeLayout = signed_inode_layout(inode_bits)
    records: list[tuple[bytes, int]] = []
    for offset in range(0, resolved_block_size, layout.entry_size):
        if offset + layout.entry_size > resolved_block_size:
            break
        sig = blob[offset : offset + consts.SIG_SIZE]
        block = struct.unpack_from(layout.block_format, blob, offset + consts.SIG_SIZE)[0]
        records.append((sig, block))
    return records


def block_hmac_without_slot(block_data: bytes, sig_offset_in_block: int, size: int, signed: bool = True) -> bytes:
    chunk = bytearray(block_data[:size])
    if signed and 0 <= sig_offset_in_block <= len(chunk) - consts.SIG_SIZE:
        chunk[sig_offset_in_block : sig_offset_in_block + consts.SIG_SIZE] = b"\x00" * consts.SIG_SIZE
    return bytes(chunk)


def verify_signed_image_signatures(
    fh: BinaryIO,
    header: ParsedHeader,
    inodes: list[ParsedInode],
    errors: list[str],
    ekpfs: bytes | None = None,
    new_crypt: bool = False,
) -> None:
    if (header.mode & consts.PFS_MODE_SIGNED) == 0:
        return

    sign_key = pfs_gen_sign_key(resolve_ekpfs_key(ekpfs=ekpfs), header.seed)
    inode_bits: int = signed_inode_bits_from_mode(header.mode)
    layout: SignedInodeLayout = signed_inode_layout(inode_bits)

    for i in range(header.dinode_block_count):
        block_num = 1 + i
        block_data = read_image_bytes(
            fh, header, block_num * header.block_size, header.block_size, ekpfs=ekpfs, new_crypt=new_crypt
        )
        sig_offset = header_inode_block_sig_offset(i)
        expected = hmac_sha256(sign_key, block_hmac_without_slot(block_data, 0, header.block_size, signed=False))
        actual = _read_exact(fh, sig_offset, consts.SIG_SIZE)
        if actual != expected:
            errors.append(f"inode block signature mismatch for block {block_num}")

    header_region = bytearray(_read_exact(fh, 0, consts.HEADER_DIGEST_SIZE))
    header_region[consts.HEADER_DIGEST_OFFSET : consts.HEADER_DIGEST_OFFSET + consts.SIG_SIZE] = (
        b"\x00" * consts.SIG_SIZE
    )
    expected_header_sig = hmac_sha256(sign_key, bytes(header_region))
    actual_header_sig = _read_exact(fh, consts.HEADER_DIGEST_OFFSET, consts.SIG_SIZE)
    if actual_header_sig != expected_header_sig:
        errors.append("header signature region digest mismatch")

    for inode in inodes:
        remaining = inode.blocks
        direct_count = min(remaining, consts.MAX_DIRECT_BLOCKS)
        for idx in range(direct_count):
            block = inode.db[idx]
            if block <= 0:
                errors.append(f"inode {inode.number} has invalid direct block db[{idx}]={block}")
                continue
            block_data = read_image_bytes(
                fh, header, block * header.block_size, header.block_size, ekpfs=ekpfs, new_crypt=new_crypt
            )
            expected = hmac_sha256(sign_key, block_data)
            actual = inode.db_sig[idx]
            if actual != expected:
                errors.append(f"inode {inode.number} direct signature mismatch at db[{idx}] -> block {block}")
        remaining -= direct_count

        sigs_per_block = header.block_size // layout.entry_size
        if remaining > 0:
            ib0 = inode.ib[0]
            if ib0 <= 0:
                errors.append(f"inode {inode.number} missing ib[0] for signed block chain")
            else:
                ib0_data = read_image_bytes(
                    fh, header, ib0 * header.block_size, header.block_size, ekpfs=ekpfs, new_crypt=new_crypt
                )
                if inode.ib_sig[0] != hmac_sha256(sign_key, ib0_data):
                    errors.append(f"inode {inode.number} indirect signature mismatch at ib[0] -> block {ib0}")
                    records = parse_sig_record_block(
                        fh, ib0, inode_bits, header=header, ekpfs=ekpfs, new_crypt=new_crypt
                    )
                take = min(remaining, sigs_per_block)
                for rec_idx, (sig, block) in enumerate(records[:take]):
                    if block <= 0:
                        errors.append(f"inode {inode.number} ib[0] record {rec_idx} has invalid block {block}")
                        continue
                    expected = hmac_sha256(
                        sign_key,
                        read_image_bytes(
                            fh,
                            header,
                            block * header.block_size,
                            header.block_size,
                            ekpfs=ekpfs,
                            new_crypt=new_crypt,
                        ),
                    )
                    if sig != expected:
                        errors.append(
                            f"inode {inode.number} ib[0] record {rec_idx} signature mismatch for block {block}"
                        )
                remaining -= take

        if remaining > 0:
            ib1 = inode.ib[1]
            if ib1 <= 0:
                errors.append(f"inode {inode.number} missing ib[1] for signed block chain")
            else:
                ib1_data = read_image_bytes(
                    fh, header, ib1 * header.block_size, header.block_size, ekpfs=ekpfs, new_crypt=new_crypt
                )
                if inode.ib_sig[1] != hmac_sha256(sign_key, ib1_data):
                    errors.append(f"inode {inode.number} indirect signature mismatch at ib[1] -> block {ib1}")
                parent_records = parse_sig_record_block(
                    fh, ib1, inode_bits, header=header, ekpfs=ekpfs, new_crypt=new_crypt
                )
                for parent_idx, (parent_sig, child_indirect) in enumerate(parent_records):
                    if remaining <= 0:
                        break
                    if child_indirect <= 0:
                        errors.append(
                            f"inode {inode.number} ib[1] record {parent_idx} has invalid block {child_indirect}"
                        )
                        continue
                    child_data = read_image_bytes(
                        fh,
                        header,
                        child_indirect * header.block_size,
                        header.block_size,
                        ekpfs=ekpfs,
                        new_crypt=new_crypt,
                    )
                    if parent_sig != hmac_sha256(sign_key, child_data):
                        errors.append(
                            f"inode {inode.number} ib[1] record {parent_idx} "
                            f"signature mismatch for block {child_indirect}"
                        )
                    child_records = parse_sig_record_block(
                        fh, child_indirect, inode_bits, header=header, ekpfs=ekpfs, new_crypt=new_crypt
                    )
                    take = min(remaining, sigs_per_block)
                    for rec_idx, (sig, block) in enumerate(child_records[:take]):
                        if block <= 0:
                            errors.append(
                                f"inode {inode.number} ib[1][{parent_idx}] record {rec_idx} has invalid block {block}"
                            )
                            continue
                        expected = hmac_sha256(
                            sign_key,
                            read_image_bytes(
                                fh,
                                header,
                                block * header.block_size,
                                header.block_size,
                                ekpfs=ekpfs,
                                new_crypt=new_crypt,
                            ),
                        )
                        if sig != expected:
                            errors.append(
                                f"inode {inode.number} ib[1][{parent_idx}] record {rec_idx} "
                                f"signature mismatch for block {block}"
                            )
                    remaining -= take

        if remaining > 0:
            errors.append(f"inode {inode.number} exceeds supported signed verification depth")


def resolve_signed_inode_blocks(
    fh: BinaryIO,
    header: ParsedHeader,
    inode: ParsedInode,
    errors: list[str] | None = None,
    ekpfs: bytes | None = None,
    new_crypt: bool = False,
) -> list[int]:
    blocks: list[int] = []
    direct_count = min(inode.blocks, consts.MAX_DIRECT_BLOCKS)
    blocks.extend(inode.db[:direct_count])
    remaining = inode.blocks - direct_count
    inode_bits: int = signed_inode_bits_from_mode(header.mode)
    layout: SignedInodeLayout = signed_inode_layout(inode_bits)
    sigs_per_block: int = header.block_size // layout.entry_size

    if remaining > 0:
        if inode.ib[0] <= 0:
            if errors is not None:
                errors.append(f"inode {inode.number} missing ib[0] for signed block chain")
            return blocks
        records = parse_sig_record_block(fh, inode.ib[0], inode_bits, header=header, ekpfs=ekpfs, new_crypt=new_crypt)
        take = min(remaining, sigs_per_block)
        blocks.extend(block for _sig, block in records[:take])
        remaining -= take

    if remaining > 0:
        if inode.ib[1] <= 0:
            if errors is not None:
                errors.append(f"inode {inode.number} missing ib[1] for signed block chain")
            return blocks
        parent_records = parse_sig_record_block(
            fh, inode.ib[1], inode_bits, header=header, ekpfs=ekpfs, new_crypt=new_crypt
        )
        for _sig, child_block in parent_records:
            if remaining <= 0:
                break
            child_records = parse_sig_record_block(
                fh, child_block, inode_bits, header=header, ekpfs=ekpfs, new_crypt=new_crypt
            )
            take = min(remaining, sigs_per_block)
            blocks.extend(block for _sig2, block in child_records[:take])
            remaining -= take

    if remaining > 0 and errors is not None:
        errors.append(f"inode {inode.number} uses unsupported signed indirection depth")
    return blocks


def parse_image_dirents(blob: bytes, strict: bool = False) -> tuple[list[ParsedDirent], list[str]]:
    dirents: list[ParsedDirent] = []
    errors: list[str] = []
    offset = 0
    while offset + 16 <= len(blob):
        inode_number, type_code, name_len, ent_size = struct.unpack_from("<Iiii", blob, offset)
        if inode_number == 0 and type_code == 0 and name_len == 0 and ent_size == 0:
            break

        if ent_size < 17 or (ent_size % 8) != 0:
            msg = f"invalid dirent size {ent_size} at offset {offset}"
            if strict:
                errors.append(msg)
            break
        if name_len < 0 or name_len > ent_size - 16:
            msg = f"invalid dirent name length {name_len} at offset {offset}"
            if strict:
                errors.append(msg)
            break
        if offset + ent_size > len(blob):
            msg = f"dirent at offset {offset} exceeds payload boundary"
            if strict:
                errors.append(msg)
            break

        name_bytes = blob[offset + 16 : offset + 16 + name_len]
        try:
            name = name_bytes.decode("ascii", errors="strict")
        except UnicodeDecodeError:
            name = name_bytes.decode("ascii", errors="replace")
            if strict:
                errors.append(f"non-ascii dirent name at offset {offset}")

        dirents.append(ParsedDirent(inode_number=inode_number, type_code=type_code, name=name))
        offset += ent_size

    return dirents, errors


def read_image_inode_payload(
    fh: BinaryIO,
    header: ParsedHeader,
    inode: ParsedInode,
    ekpfs: bytes | None = None,
    new_crypt: bool = False,
) -> bytes:
    """Read one inode payload, decrypting encrypted images transparently.

    Args:
        fh: Open image file handle.
        header: Parsed image header.
        inode: Parsed inode whose payload should be read.
        ekpfs: Optional EKPFS key material. Defaults to the all-zero key.
        new_crypt: When True, use the alternate newCrypt key derivation path.

    Returns:
        Stored payload bytes for the inode.

    Raises:
        ValueError: If inode sizes are invalid or payload bytes are truncated.
    """
    if inode.blocks <= 0:
        return b""
    payload_size: int = inode.stored_size
    if payload_size < 0:
        raise ValueError(f"inode {inode.number} has negative stored payload size")
    if inode.db_sig or inode.ib_sig:
        block_numbers = resolve_signed_inode_blocks(
            fh,
            header,
            inode,
            ekpfs=ekpfs,
            new_crypt=new_crypt,
        )
        data = bytearray()
        for block in block_numbers:
            data += read_image_bytes(
                fh,
                header,
                block * header.block_size,
                header.block_size,
                ekpfs=ekpfs,
                new_crypt=new_crypt,
            )
        data = bytes(data[:payload_size])
    else:
        data = read_image_bytes(
            fh,
            header,
            inode.db[0] * header.block_size,
            payload_size,
            ekpfs=ekpfs,
            new_crypt=new_crypt,
        )
    if len(data) != payload_size:
        raise ValueError(f"inode {inode.number} payload truncated")
    return data


def parse_superroot_and_indexes(
    fh: BinaryIO,
    header: ParsedHeader,
    inodes: list[ParsedInode],
    errors: list[str],
    ekpfs: bytes | None = None,
    new_crypt: bool = False,
) -> tuple[int, dict[int, int], dict[int, list[ParsedDirent]], set[int]]:
    super_root_offset = (1 + header.dinode_block_count) * header.block_size
    blob: bytes = read_image_bytes(fh, header, super_root_offset, header.block_size, ekpfs=ekpfs, new_crypt=new_crypt)
    super_entries, parse_errors = parse_image_dirents(blob, strict=True)
    for e in parse_errors:
        errors.append(f"superroot: {e}")

    fpt_inode = None
    collision_inode = None
    uroot_inode = None
    special_inodes: set[int] = {0}
    for ent in super_entries:
        if ent.name == "flat_path_table":
            fpt_inode = ent.inode_number
        elif ent.name == "collision_resolver":
            collision_inode = ent.inode_number
        elif ent.name == "uroot":
            uroot_inode = ent.inode_number

    if fpt_inode is None:
        errors.append("superroot missing 'flat_path_table' entry")
    if uroot_inode is None:
        errors.append("superroot missing 'uroot' entry")

    if fpt_inode is not None:
        special_inodes.add(fpt_inode)
    if collision_inode is not None:
        special_inodes.add(collision_inode)
    if uroot_inode is not None:
        special_inodes.add(uroot_inode)

    fpt_map: dict[int, int] = {}
    collision_map: dict[int, list[ParsedDirent]] = {}

    if fpt_inode is not None and 0 <= fpt_inode < len(inodes):
        fpt_blob = read_image_inode_payload(fh, header, inodes[fpt_inode], ekpfs=ekpfs, new_crypt=new_crypt)
        if (len(fpt_blob) % 8) != 0:
            errors.append("flat_path_table size is not divisible by 8")

        for i in range(0, len(fpt_blob) - (len(fpt_blob) % 8), 8):
            h, v = struct.unpack_from("<II", fpt_blob, i)
            if h in fpt_map:
                errors.append(f"flat_path_table has duplicate hash 0x{h:08X}")
            fpt_map[h] = v

        if any((v & 0x80000000) for v in fpt_map.values()):
            if collision_inode is None:
                errors.append("flat_path_table has collision entries but no collision_resolver inode")
            elif 0 <= collision_inode < len(inodes):
                c_blob = read_image_inode_payload(
                    fh, header, inodes[collision_inode], ekpfs=ekpfs, new_crypt=new_crypt
                )
                for h, v in fpt_map.items():
                    if (v & 0x80000000) == 0:
                        continue
                    offset = v & 0x7FFFFFFF
                    if offset >= len(c_blob):
                        errors.append(f"collision_resolver offset {offset} out of range for hash 0x{h:08X}")
                        continue
                    entries, parse_err = parse_image_dirents(c_blob[offset:], strict=True)
                    if parse_err:
                        errors.extend([f"collision_resolver hash 0x{h:08X}: {e}" for e in parse_err])
                    collision_map[h] = entries

    return (uroot_inode if uroot_inode is not None else -1), fpt_map, collision_map, special_inodes


def build_tree_from_uroot(
    fh: BinaryIO,
    header: ParsedHeader,
    inodes: list[ParsedInode],
    uroot_inode: int,
    errors: list[str],
    ekpfs: bytes | None = None,
    new_crypt: bool = False,
) -> tuple[dict[str, int], dict[str, int], dict[int, list[ParsedDirent]]]:
    files: dict[str, int] = {}
    dirs: dict[str, int] = {"": uroot_inode}
    dirents_by_inode: dict[int, list[ParsedDirent]] = {}
    visited: set[int] = set()
    dir_path_by_inode: dict[int, str] = {uroot_inode: ""}

    def walk(dir_inode_num: int, rel_path: str, parent_inode_num: int, ancestors: set[int]) -> None:
        if dir_inode_num in visited:
            return
        visited.add(dir_inode_num)

        if not (0 <= dir_inode_num < len(inodes)):
            errors.append(f"directory inode {dir_inode_num} is out of range")
            return

        inode = inodes[dir_inode_num]
        if not inode.is_dir:
            errors.append(f"inode {dir_inode_num} referenced as directory but mode is 0x{inode.mode:04X}")
            return

        payload = read_image_inode_payload(fh, header, inode, ekpfs=ekpfs, new_crypt=new_crypt)
        entries, parse_errors = parse_image_dirents(payload, strict=True)
        dirents_by_inode[dir_inode_num] = entries
        for e in parse_errors:
            errors.append(f"inode {dir_inode_num}: {e}")

        dot_entries = [e for e in entries if e.name == "."]
        dotdot_entries = [e for e in entries if e.name == ".."]
        dot = dot_entries[0] if dot_entries else None
        dotdot = dotdot_entries[0] if dotdot_entries else None

        if len(dot_entries) != 1:
            errors.append(f"directory '{rel_path or '/'}' must contain exactly one '.' entry")
        if dot is None:
            errors.append(f"directory '{rel_path or '/'}' missing '.' entry")
        elif dot.inode_number != dir_inode_num:
            errors.append(f"directory '{rel_path or '/'}' has '.' -> {dot.inode_number}, expected {dir_inode_num}")
        elif dot.type_code != consts.DIRENT_TYPE_DOT:
            errors.append(f"directory '{rel_path or '/'}' has '.' with invalid type {dot.type_code}")

        if len(dotdot_entries) != 1:
            errors.append(f"directory '{rel_path or '/'}' must contain exactly one '..' entry")
        if dotdot is None:
            errors.append(f"directory '{rel_path or '/'}' missing '..' entry")
        else:
            expected_parent = dir_inode_num if rel_path == "" else parent_inode_num
            if dotdot.inode_number != expected_parent:
                errors.append(
                    f"directory '{rel_path or '/'}' has '..' -> {dotdot.inode_number}, expected {expected_parent}"
                )
            if dotdot.type_code != consts.DIRENT_TYPE_DOTDOT:
                errors.append(f"directory '{rel_path or '/'}' has '..' with invalid type {dotdot.type_code}")

        names_seen: set[str] = set()
        next_ancestors = set(ancestors)
        next_ancestors.add(dir_inode_num)
        for ent in entries:
            if ent.name in (".", ".."):
                continue
            if ent.name in names_seen:
                errors.append(f"directory '{rel_path or '/'}' has duplicate entry '{ent.name}'")
                continue
            names_seen.add(ent.name)
            if "/" in ent.name:
                errors.append(f"directory '{rel_path or '/'}' has invalid entry name containing '/': {ent.name}")
                continue

            child_path = ent.name if rel_path == "" else f"{rel_path}/{ent.name}"
            if not (0 <= ent.inode_number < len(inodes)):
                errors.append(f"entry '{child_path}' references out-of-range inode {ent.inode_number}")
                continue

            child_inode = inodes[ent.inode_number]
            if ent.type_code == consts.DIRENT_TYPE_DIRECTORY:
                if not child_inode.is_dir:
                    errors.append(f"entry '{child_path}' typed directory but inode mode is 0x{child_inode.mode:04X}")
                    continue
                if ent.inode_number in next_ancestors:
                    errors.append(f"directory cycle detected at '{child_path}' (inode {ent.inode_number})")
                    continue
                prev_path = dir_path_by_inode.get(ent.inode_number)
                if prev_path is not None and prev_path != child_path:
                    errors.append(
                        f"directory inode {ent.inode_number} is reachable from multiple paths: "
                        f"'{prev_path}' and '{child_path}'"
                    )
                    continue
                dir_path_by_inode[ent.inode_number] = child_path
                dirs[child_path] = ent.inode_number
                walk(ent.inode_number, child_path, dir_inode_num, next_ancestors)
            elif ent.type_code == consts.DIRENT_TYPE_FILE:
                if not child_inode.is_file:
                    errors.append(f"entry '{child_path}' typed file but inode mode is 0x{child_inode.mode:04X}")
                    continue
                files[child_path] = ent.inode_number
            else:
                errors.append(f"directory '{rel_path or '/'}' has unsupported dirent type {ent.type_code}")

    walk(uroot_inode, "", uroot_inode, set())
    return files, dirs, dirents_by_inode


def verify_file_payload_hashes(
    fh: BinaryIO,
    header: ParsedHeader,
    inodes: list[ParsedInode],
    file_inodes: dict[str, int],
    errors: list[str],
    ekpfs: bytes | None = None,
    new_crypt: bool = False,
) -> tuple[int, int, str]:
    manifest = hashlib.sha256()
    cumulative_crc = 0
    checked = 0
    for rel in sorted(file_inodes.keys()):
        inode_num = file_inodes[rel]
        inode = inodes[inode_num]
        try:
            payload = read_image_inode_payload(fh, header, inode, ekpfs=ekpfs, new_crypt=new_crypt)
        except Exception as exc:
            errors.append(f"failed to read file payload '{rel}' (inode {inode_num}): {exc}")
            continue

        try:
            logical_data = decode_inode_payload(payload=payload, inode=inode)
        except ValueError as exc:
            errors.append(f"file '{rel}' payload decode failed: {exc}")
            continue
        if inode.logical_size >= 0 and len(logical_data) != inode.logical_size:
            errors.append(f"file '{rel}' size {len(logical_data)} does not match inode size {inode.logical_size}")

        file_hash = hashlib.sha256(logical_data).digest()
        manifest.update(rel.encode("utf-8", errors="replace"))
        manifest.update(b"\0")
        manifest.update(file_hash)
        cumulative_crc = zlib.crc32(logical_data, cumulative_crc) & 0xFFFFFFFF
        checked += 1

    return checked, cumulative_crc, manifest.hexdigest()


def render_tree(dirents_by_inode: dict[int, list[ParsedDirent]], inode_num: int, prefix: str = "") -> list[str]:
    lines: list[str] = []
    entries = [e for e in dirents_by_inode.get(inode_num, []) if e.name not in (".", "..")]
    entries.sort(key=lambda e: (e.type_code != consts.DIRENT_TYPE_DIRECTORY, e.name.lower(), e.name))

    for idx, ent in enumerate(entries):
        last = idx == (len(entries) - 1)
        branch = "`-- " if last else "|-- "
        lines.append(prefix + branch + ent.name)
        if ent.type_code == consts.DIRENT_TYPE_DIRECTORY:
            child_prefix = prefix + ("    " if last else "|   ")
            lines.extend(render_tree(dirents_by_inode, ent.inode_number, child_prefix))
    return lines


def validate_inode_layout(
    header: ParsedHeader, inodes: list[ParsedInode], errors: list[str], warnings: list[str]
) -> None:
    if header.magic != consts.PFS_MAGIC:
        errors.append(f"header magic mismatch: 0x{header.magic:016X} != 0x{consts.PFS_MAGIC:016X}")
    if header.block_size <= 0 or (header.block_size & (header.block_size - 1)) != 0:
        errors.append(f"invalid block size {header.block_size}")
    if header.readonly != 1:
        warnings.append(f"header readonly byte is {header.readonly}, expected 1")
    if header.dinode_count != len(inodes):
        errors.append(f"inode count mismatch: header={header.dinode_count} parsed={len(inodes)}")

    used_ranges: list[tuple[int, int, int]] = []
    for inode in inodes:
        if inode.blocks <= 0:
            continue
        start = inode.db[0]
        end = start + inode.blocks - 1
        if start < 0:
            errors.append(f"inode {inode.number} has negative db[0]={start}")
            continue
        if end >= header.ndblock:
            errors.append(f"inode {inode.number} range [{start},{end}] exceeds ndblock {header.ndblock}")
        used_ranges.append((start, end, inode.number))

    used_ranges.sort()
    for i in range(1, len(used_ranges)):
        prev_start, prev_end, prev_ino = used_ranges[i - 1]
        curr_start, curr_end, curr_ino = used_ranges[i]
        if curr_start <= prev_end:
            errors.append(
                f"block overlap between inode {prev_ino} "
                f"[{prev_start},{prev_end}] and inode {curr_ino} [{curr_start},{curr_end}]"
            )


def build_expected_fpt(
    file_inodes: dict[str, int], dir_inodes: dict[str, int], case_insensitive: bool
) -> dict[int, list[tuple[str, bool, int]]]:
    out: dict[int, list[tuple[str, bool, int]]] = {}
    for rel_dir, inode_num in dir_inodes.items():
        if rel_dir == "":
            continue
        full = "/" + rel_dir
        h = fpt_hash(full, case_insensitive=case_insensitive)
        out.setdefault(h, []).append((full, True, inode_num))
    for rel_file, inode_num in file_inodes.items():
        full = "/" + rel_file
        h = fpt_hash(full, case_insensitive=case_insensitive)
        out.setdefault(h, []).append((full, False, inode_num))
    return out


def validate_fpt_maps(
    fpt_map: dict[int, int],
    collision_map: dict[int, list[ParsedDirent]],
    expected: dict[int, list[tuple[str, bool, int]]],
    errors: list[str],
) -> None:
    expected_hashes = set(expected.keys())
    table_hashes = set(fpt_map.keys())

    for h in sorted(expected_hashes - table_hashes):
        errors.append(f"flat_path_table missing hash 0x{h:08X}")
    for h in sorted(table_hashes - expected_hashes):
        errors.append(f"flat_path_table has unexpected hash 0x{h:08X}")

    for h in sorted(expected_hashes & table_hashes):
        exp_entries = expected[h]
        val = fpt_map[h]
        if len(exp_entries) == 1:
            exp_path, exp_is_dir, exp_inode = exp_entries[0]
            if val & 0x80000000:
                errors.append(f"hash 0x{h:08X} for {exp_path} unexpectedly points to collision resolver")
                continue
            act_is_dir = bool(val & 0x20000000)
            act_inode = val & 0x1FFFFFFF
            if act_is_dir != exp_is_dir or act_inode != exp_inode:
                errors.append(
                    f"hash 0x{h:08X} mismatch: actual inode={act_inode} dir={act_is_dir}, "
                    f"expected inode={exp_inode} dir={exp_is_dir} ({exp_path})"
                )
        else:
            if (val & 0x80000000) == 0:
                errors.append(f"hash 0x{h:08X} has collisions but does not point to collision resolver")
                continue
            actual_set = {
                (e.name, e.type_code == consts.DIRENT_TYPE_DIRECTORY, e.inode_number) for e in collision_map.get(h, [])
            }
            expected_set = set(exp_entries)
            if not expected_set.issubset(actual_set):
                errors.append(f"collision resolver for hash 0x{h:08X} is missing expected entries")


def validate_ps5_checklist(
    fh: BinaryIO,
    header: ParsedHeader,
    inodes: list[ParsedInode],
    file_inodes: dict[str, int],
    warnings: list[str],
    errors: list[str],
    ekpfs: bytes | None = None,
    new_crypt: bool = False,
) -> None:
    if "sce_sys/param.json" in file_inodes:
        inode = inodes[file_inodes["sce_sys/param.json"]]
        payload = read_image_inode_payload(fh, header, inode, ekpfs=ekpfs, new_crypt=new_crypt)
        if inode.is_compressed:
            try:
                payload = decode_inode_payload(payload=payload, inode=inode)
            except ValueError as exc:
                errors.append(f"sce_sys/param.json payload decode failed: {exc}")
                payload = b""
        if payload:
            try:
                parsed = json.loads(payload.decode("utf-8"))
                if not parsed.get("titleId") and not parsed.get("title_id"):
                    warnings.append("sce_sys/param.json missing titleId/title_id")
            except Exception as exc:
                errors.append(f"sce_sys/param.json invalid JSON: {exc}")
    else:
        warnings.append("sce_sys/param.json not found")

    if "eboot.bin" not in file_inodes:
        warnings.append("eboot.bin not found")
    if "sce_sys/pfs-version.dat" not in file_inodes:
        warnings.append("sce_sys/pfs-version.dat not found")


def validate_source_match(
    fh: BinaryIO,
    header: ParsedHeader,
    inodes: list[ParsedInode],
    file_inodes: dict[str, int],
    source: Path,
    errors: list[str],
    ekpfs: bytes | None = None,
    new_crypt: bool = False,
) -> None:
    if not source.exists() or not source.is_dir():
        errors.append(f"source path does not exist or is not a directory: {source}")
        return

    source_files = sorted(p for p in source.rglob("*") if p.is_file())
    source_rel = {p.relative_to(source).as_posix() for p in source_files}
    image_rel = set(file_inodes.keys())

    for rel in sorted(source_rel - image_rel):
        errors.append(f"missing in image: {rel}")
    for rel in sorted(image_rel - source_rel):
        errors.append(f"extra in image: {rel}")

    for rel in sorted(source_rel & image_rel):
        inode = inodes[file_inodes[rel]]
        payload = read_image_inode_payload(fh, header, inode, ekpfs=ekpfs, new_crypt=new_crypt)
        if inode.is_compressed:
            try:
                payload = decode_inode_payload(payload=payload, inode=inode)
            except ValueError as exc:
                errors.append(f"file '{rel}' marked compressed but failed to decode payload: {exc}")
                continue

        src_data = (source / rel).read_bytes()
        if hashlib.sha256(src_data).digest() != hashlib.sha256(payload).digest():
            errors.append(f"content mismatch for file: {rel}")


@dataclass
class PFSOperationResult:
    """Base result object for high-level PFS operations.

    Args:
        image: Input image path.
        errors: Collected fatal or validation errors.
        warnings: Collected non-fatal warnings.
    """

    image: Path
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


@dataclass
class PFSImageInfo(PFSOperationResult):
    """Lightweight PFS image metadata summary.

    Args:
        image: Input image path.
        errors: Collected fatal or validation errors.
        warnings: Collected non-fatal warnings.
        size_bytes: Image size on disk.
        header: Parsed image header, when available.
    """

    size_bytes: int = 0
    header: ParsedHeader | None = None

    @property
    def version_label(self) -> str:
        """Return the human-friendly version label."""
        if self.header is None:
            return ""
        return "PS5" if self.header.version == consts.PFS_VERSION_PS5 else "PS4"


@dataclass
class PFSImageInspection(PFSImageInfo):
    """Detailed PFS image inspection result.

    Args:
        image: Input image path.
        errors: Collected fatal or validation errors.
        warnings: Collected non-fatal warnings.
        size_bytes: Image size on disk.
        header: Parsed image header, when available.
        inodes: Parsed inode table.
        uroot_inode: Inode number of the filesystem root.
        file_inodes: Mapping of relative file paths to inode numbers.
        dir_inodes: Mapping of relative directory paths to inode numbers.
        dirents_by_inode: Parsed directory entries for each inode.
        fpt_map: Parsed flat_path_table entries.
        collision_map: Parsed collision resolver entries.
        special_inodes: Inodes reserved by the filesystem layout.
        checked_files: Number of payload hashes checked.
        data_crc32: Cumulative CRC32 of logical file payloads.
        manifest_sha256: SHA256 digest of the logical file manifest.
        compressed_files: Number of files stored compressed.
        logical_file_bytes: Total logical file payload bytes.
        stored_file_bytes: Total stored file payload bytes.
    """

    inodes: list[ParsedInode] = field(default_factory=list)
    uroot_inode: int = -1
    file_inodes: dict[str, int] = field(default_factory=dict)
    dir_inodes: dict[str, int] = field(default_factory=dict)
    dirents_by_inode: dict[int, list[ParsedDirent]] = field(default_factory=dict)
    fpt_map: dict[int, int] = field(default_factory=dict)
    collision_map: dict[int, list[ParsedDirent]] = field(default_factory=dict)
    special_inodes: set[int] = field(default_factory=set)
    checked_files: int = 0
    data_crc32: int = 0
    manifest_sha256: str = ""
    compressed_files: int = 0
    logical_file_bytes: int = 0
    stored_file_bytes: int = 0

    @property
    def has_tree(self) -> bool:
        """Return whether the inspection contains a parsed filesystem tree."""
        return self.uroot_inode >= 0 and len(self.dirents_by_inode) > 0


@dataclass
class PFSExtractionResult(PFSOperationResult):
    """Result of extracting a PFS image to a directory.

    Args:
        image: Input image path.
        errors: Collected fatal or validation errors.
        warnings: Collected non-fatal warnings.
        output_path: Destination directory path.
        files_written: Number of files written to disk.
        directories_created: Number of directories created or ensured.
        bytes_written: Total logical file bytes written to disk.
    """

    output_path: Path | None = None
    files_written: int = 0
    directories_created: int = 0
    bytes_written: int = 0


def _image_size_bytes(image: Path) -> int:
    """Return the size of a path on disk, or zero when unavailable."""
    try:
        return image.stat().st_size
    except OSError:
        return 0


def read_pfs_info(image: Path) -> PFSImageInfo:
    """Read lightweight metadata from a PFS image.

    Args:
        image: Input PFS image path.

    Returns:
        A structured summary containing the parsed header and any warnings or errors.
    """
    info = PFSImageInfo(image=image, size_bytes=_image_size_bytes(image))

    if not image.exists() or not image.is_file():
        info.errors.append(f"image path does not exist or is not a file: {image}")
        return info

    try:
        with image.open("rb") as fh:
            info.header = parse_image_header(fh)
    except (OSError, ValueError) as exc:
        info.errors.append(f"failed to read image header: {exc}")
        return info

    if info.header.magic != consts.PFS_MAGIC:
        info.errors.append(f"header magic mismatch: 0x{info.header.magic:016X} != 0x{consts.PFS_MAGIC:016X}")
    if info.header.block_size <= 0 or (info.header.block_size & (info.header.block_size - 1)) != 0:
        info.errors.append(f"invalid block size {info.header.block_size}")
    if info.header.readonly != 1:
        info.warnings.append(f"header readonly byte is {info.header.readonly}, expected 1")

    return info


def inspect_pfs_image(
    image: Path,
    source: Path | None = None,
    expected_crc32: int | None = None,
    expected_manifest_sha256: str | None = None,
    ekpfs: bytes | None = None,
    new_crypt: bool = False,
) -> PFSImageInspection:
    """Inspect a PFS image and collect structural validation details.

    Args:
        image: Input PFS image path.
        source: Optional source tree to compare against.
        expected_crc32: Optional expected cumulative payload CRC32.
        expected_manifest_sha256: Optional expected manifest SHA256 digest.
        ekpfs: Optional EKPFS key material for encrypted images.
        new_crypt: When True, use the alternate newCrypt key derivation path.

    Returns:
        A detailed inspection report with parsed tree data, warnings, and errors.
    """
    inspection: PFSImageInspection = PFSImageInspection(image=image, size_bytes=_image_size_bytes(image))

    if not image.exists() or not image.is_file():
        inspection.errors.append(f"image path does not exist or is not a file: {image}")
        return inspection

    try:
        with image.open("rb") as fh:
            header: ParsedHeader = parse_image_header(fh)
            inspection.header = header

            try:
                inodes: list[ParsedInode] = parse_image_inodes(fh, header, ekpfs=ekpfs, new_crypt=new_crypt)
            except (OSError, ValueError) as exc:
                inspection.errors.append(f"failed to parse inode table: {exc}")
                return inspection

            inspection.inodes = inodes
            validate_inode_layout(header, inodes, inspection.errors, inspection.warnings)

            try:
                verify_signed_image_signatures(fh, header, inodes, inspection.errors, ekpfs=ekpfs, new_crypt=new_crypt)
            except (OSError, ValueError) as exc:
                inspection.errors.append(f"failed to verify image signatures: {exc}")

            try:
                (
                    inspection.uroot_inode,
                    inspection.fpt_map,
                    inspection.collision_map,
                    inspection.special_inodes,
                ) = parse_superroot_and_indexes(
                    fh, header, inodes, inspection.errors, ekpfs=ekpfs, new_crypt=new_crypt
                )
            except (OSError, ValueError) as exc:
                inspection.errors.append(f"failed to parse superroot and indexes: {exc}")
                return inspection

            if inspection.uroot_inode >= 0:
                try:
                    inspection.file_inodes, inspection.dir_inodes, inspection.dirents_by_inode = build_tree_from_uroot(
                        fh,
                        header,
                        inodes,
                        inspection.uroot_inode,
                        inspection.errors,
                        ekpfs=ekpfs,
                        new_crypt=new_crypt,
                    )
                except (OSError, ValueError) as exc:
                    inspection.errors.append(f"failed to build filesystem tree: {exc}")
                    return inspection

                case_insensitive: bool = bool(header.mode & consts.PFS_MODE_CASE_INSENSITIVE)
                expected_fpt: dict = build_expected_fpt(
                    inspection.file_inodes, inspection.dir_inodes, case_insensitive
                )

                validate_fpt_maps(inspection.fpt_map, inspection.collision_map, expected_fpt, inspection.errors)
                validate_ps5_checklist(
                    fh,
                    header,
                    inodes,
                    inspection.file_inodes,
                    inspection.warnings,
                    inspection.errors,
                    ekpfs=ekpfs,
                    new_crypt=new_crypt,
                )

                try:
                    (
                        inspection.checked_files,
                        inspection.data_crc32,
                        inspection.manifest_sha256,
                    ) = verify_file_payload_hashes(
                        fh,
                        header,
                        inodes,
                        inspection.file_inodes,
                        inspection.errors,
                        ekpfs=ekpfs,
                        new_crypt=new_crypt,
                    )
                except (OSError, ValueError) as exc:
                    inspection.errors.append(f"failed to verify file payload hashes: {exc}")

                if expected_crc32 is not None and inspection.data_crc32 != expected_crc32:
                    inspection.errors.append(
                        f"CRC32 mismatch: actual 0x{inspection.data_crc32:08X}, expected 0x{expected_crc32:08X}"
                    )
                if (
                    expected_manifest_sha256 is not None
                    and inspection.manifest_sha256.lower() != expected_manifest_sha256.lower()
                ):
                    inspection.errors.append(
                        "Manifest SHA256 mismatch: actual "
                        f"{inspection.manifest_sha256}, expected {expected_manifest_sha256.lower()}"
                    )

                reachable = (
                    set(inspection.file_inodes.values())
                    | set(inspection.dir_inodes.values())
                    | set(inspection.special_inodes)
                )
                orphan_inodes = sorted(inode.number for inode in inodes if inode.number not in reachable)
                if orphan_inodes:
                    inspection.errors.append(
                        "orphan inodes not reachable from filesystem tree: "
                        + ", ".join(str(value) for value in orphan_inodes[:20])
                        + (" ..." if len(orphan_inodes) > 20 else "")
                    )

                if source is not None:
                    validate_source_match(
                        fh,
                        header,
                        inodes,
                        inspection.file_inodes,
                        source,
                        inspection.errors,
                        ekpfs=ekpfs,
                        new_crypt=new_crypt,
                    )

                inspection.compressed_files = sum(
                    1 for inode_num in inspection.file_inodes.values() if inodes[inode_num].is_compressed
                )
                inspection.logical_file_bytes = sum(
                    max(0, inodes[inode_num].logical_size) for inode_num in inspection.file_inodes.values()
                )
                inspection.stored_file_bytes = sum(
                    max(0, inodes[inode_num].stored_size) for inode_num in inspection.file_inodes.values()
                )
    except (OSError, ValueError) as exc:
        inspection.errors.append(f"failed to inspect image: {exc}")

    return inspection


def analyze_pfs_image(image: Path, new_crypt: bool = False) -> PFSImageInspection:
    """Analyze a PFS image without comparing it to a source tree.

    Args:
        image: Input PFS image path.
        new_crypt: When True, use the alternate newCrypt key derivation path.

    Returns:
        A detailed inspection report.
    """
    return inspect_pfs_image(image=image, new_crypt=new_crypt)


def verify_pfs_image(
    image: Path,
    source: Path | None = None,
    expected_crc32: int | None = None,
    expected_manifest_sha256: str | None = None,
    ekpfs: bytes | None = None,
    new_crypt: bool = False,
) -> PFSImageInspection:
    """Verify a PFS image against optional source and hash expectations.

    Args:
        image: Input PFS image path.
        source: Optional source tree to compare against.
        expected_crc32: Optional expected cumulative payload CRC32.
        expected_manifest_sha256: Optional expected manifest SHA256 digest.
        ekpfs: Optional EKPFS key material for encrypted images.
        new_crypt: When True, use the alternate newCrypt key derivation path.

    Returns:
        A detailed inspection report.
    """
    return inspect_pfs_image(
        image=image,
        source=source,
        expected_crc32=expected_crc32,
        expected_manifest_sha256=expected_manifest_sha256,
        ekpfs=ekpfs,
        new_crypt=new_crypt,
    )


def extract_pfs_image(
    image: Path,
    output_path: Path,
    progress: Progress | None = None,
    ekpfs: bytes | None = None,
    new_crypt: bool = False,
) -> PFSExtractionResult:
    """Extract all logical files from a PFS image.

    Args:
        image: Input PFS image path.
        output_path: Destination directory for extracted files.
        progress: Optional progress reporter.
        ekpfs: Optional EKPFS key material for encrypted images.
        new_crypt: When True, use the alternate newCrypt key derivation path.

    Returns:
        A structured extraction result.
    """
    result: PFSExtractionResult = PFSExtractionResult(image=image, output_path=output_path, bytes_written=0)
    inspection: PFSImageInspection = inspect_pfs_image(image=image, ekpfs=ekpfs, new_crypt=new_crypt)
    result.warnings.extend(inspection.warnings)
    result.errors.extend(inspection.errors)

    if result.errors:
        return result
    if inspection.header is None:
        result.errors.append("image header is not available")
        return result
    if output_path.exists() and not output_path.is_dir():
        result.errors.append(f"output path exists and is not a directory: {output_path}")
        return result

    directory_targets: list[Path] = [
        output_path / Path(rel_dir)
        for rel_dir in sorted(inspection.dir_inodes.keys(), key=lambda value: (value.count("/"), value.lower(), value))
        if rel_dir != ""
    ]
    file_targets: list[tuple[str, Path, int]] = [
        (rel_path, output_path / Path(rel_path), inode_num)
        for rel_path, inode_num in sorted(inspection.file_inodes.items())
    ]

    for directory_target in directory_targets:
        if directory_target.exists() and not directory_target.is_dir():
            result.errors.append(f"output path conflicts with a file: {directory_target}")
    for _rel_path, file_target, _inode_num in file_targets:
        if file_target.exists():
            result.errors.append(f"output file already exists: {file_target}")

    if result.errors:
        return result

    output_path.mkdir(parents=True, exist_ok=True)

    if progress is not None:
        progress.status(f"\nExtracting {len(file_targets)} files to {output_path}...")

    try:
        with image.open("rb") as fh:
            for directory_target in directory_targets:
                if not directory_target.exists():
                    directory_target.mkdir(parents=True, exist_ok=False)
                    result.directories_created += 1

            total_files: int = len(file_targets)
            for index, (rel_path, file_target, inode_num) in enumerate(file_targets, start=1):
                inode: ParsedInode = inspection.inodes[inode_num]
                payload = read_image_inode_payload(fh, inspection.header, inode, ekpfs=ekpfs, new_crypt=new_crypt)
                if inode.is_compressed:
                    try:
                        payload = decode_inode_payload(payload=payload, inode=inode)
                    except ValueError as exc:
                        result.errors.append(f"failed to decode file '{rel_path}' payload: {exc}")
                        return result

                file_target.parent.mkdir(parents=True, exist_ok=True)
                file_target.write_bytes(payload)
                result.files_written += 1
                result.bytes_written += len(payload)

                if progress is not None:
                    progress.step("extract", index, total_files, bytes_processed=result.bytes_written)
    except (OSError, ValueError) as exc:
        result.errors.append(f"failed to extract image: {exc}")

    return result


# Thin, stable wrapper APIs --------------------------------------------------
def pfs_build(
    source_root: Path,
    output_path: Path,
    block_size: int,
    pfs_version: int,
    inode_bits: int,
    case_insensitive: bool,
    signed: bool,
    compress: bool,
    threshold_gain: int,
    cpu_count: int,
    zlib_level: int,
    dry_run: bool,
    verbose: bool,
    encrypted: bool = False,
    ekpfs: bytes | None = None,
    skip_executable_compression: bool = False,
    min_file_gain: int = 0,
    min_compress_size: int = 0,
) -> BuildStats:
    """Stable thin wrapper around :func:`build_pfs`.

    This wrapper exists to provide a stable, short and predictable symbol for
    external callers that prefer the `pfs_` prefix.
    """
    return build_pfs(
        source_root=source_root,
        output_path=output_path,
        block_size=block_size,
        pfs_version=pfs_version,
        inode_bits=inode_bits,
        case_insensitive=case_insensitive,
        signed=signed,
        compress=compress,
        threshold_gain=threshold_gain,
        cpu_count=cpu_count,
        zlib_level=zlib_level,
        dry_run=dry_run,
        verbose=verbose,
        encrypted=encrypted,
        ekpfs=ekpfs,
        skip_executable_compression=skip_executable_compression,
        min_file_gain=min_file_gain,
        min_compress_size=min_compress_size,
    )


def pfs_inspect(
    image: Path,
    source: Path | None = None,
    expected_crc32: int | None = None,
    expected_manifest_sha256: str | None = None,
    ekpfs: bytes | None = None,
    new_crypt: bool = False,
) -> PFSImageInspection:
    """Thin wrapper around :func:`inspect_pfs_image` named with `pfs_` prefix."""
    return inspect_pfs_image(
        image=image,
        source=source,
        expected_crc32=expected_crc32,
        expected_manifest_sha256=expected_manifest_sha256,
        ekpfs=ekpfs,
        new_crypt=new_crypt,
    )


def pfs_read_info(image: Path) -> PFSImageInfo:
    """Thin wrapper around :func:`read_pfs_info` named with `pfs_` prefix."""
    return read_pfs_info(image)


def pfs_extract(
    image: Path,
    output_path: Path,
    progress: Progress | None = None,
    ekpfs: bytes | None = None,
    new_crypt: bool = False,
) -> PFSExtractionResult:
    """Thin wrapper around :func:`extract_pfs_image` named with `pfs_` prefix."""
    return extract_pfs_image(
        image=image,
        output_path=output_path,
        progress=progress,
        ekpfs=ekpfs,
        new_crypt=new_crypt,
    )


def pfs_verify(
    image: Path,
    source: Path | None = None,
    expected_crc32: int | None = None,
    expected_manifest_sha256: str | None = None,
    ekpfs: bytes | None = None,
    new_crypt: bool = False,
) -> PFSImageInspection:
    """Thin wrapper around :func:`verify_pfs_image` named with `pfs_` prefix."""
    return verify_pfs_image(
        image=image,
        source=source,
        expected_crc32=expected_crc32,
        expected_manifest_sha256=expected_manifest_sha256,
        ekpfs=ekpfs,
        new_crypt=new_crypt,
    )
