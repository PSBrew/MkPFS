from __future__ import annotations

import io
import json
import random
import struct
import subprocess
import sys
import tempfile
import unittest
from collections.abc import Callable
from pathlib import Path
from unittest.mock import patch

import mkpfs.consts as c
import mkpfs.pfs as pfs_mod
from mkpfs.cli import run_image_check
from mkpfs.pbar import Progress
from mkpfs.pfs import (
    BuildError,
    Dirent,
    DirNode,
    FileNode,
    Inode,
    build_pfs,
    extract_pfs_image,
    fpt_hash,
    inspect_pfs_image,
    make_fpt_and_collision_blob,
    parse_ekpfs_key_hex,
    parse_image_header,
    parse_image_inodes,
    pfs_gen_enc_keys,
    scan_source_tree,
    validate_d32_ranges,
)


# Fixture builders
def make_minimal_app(tmp_path: Path) -> Path:
    """Create a minimal valid app tree under ``tmp_path``."""
    app: Path = tmp_path / "app"
    sce: Path = app / "sce_sys"
    sce.mkdir(parents=True)
    (sce / "param.json").write_text(json.dumps({"titleId": "NPXS99999"}), encoding="utf-8")
    (app / "eboot.bin").write_bytes(b"\x00" * 128)
    return app


def make_app_with_nested_dirs(tmp_path: Path) -> Path:
    """Create a valid app tree with nested files for traversal tests."""
    app: Path = tmp_path / "app"
    sce: Path = app / "sce_sys"
    sce.mkdir(parents=True)
    (sce / "param.json").write_text(json.dumps({"titleId": "NPXS99999"}), encoding="utf-8")
    (app / "eboot.bin").write_bytes(b"x" * 200)
    sub: Path = app / "data" / "levels"
    sub.mkdir(parents=True)
    (sub / "level1.bin").write_bytes(b"L" * 300)
    (sub / "level2.bin").write_bytes(b"M" * 400)
    (app / "data" / "config.json").write_text('{"v":1}', encoding="utf-8")
    return app


def _build(tmp_path: Path, signed: bool = False, encrypted: bool = False, ekpfs: bytes | None = None) -> Path:
    """Build a PFS image from minimal test app.

    Args:
        tmp_path: Temporary directory path.
        signed: Whether to build a signed image.
        encrypted: Whether to encrypt filesystem blocks.
        ekpfs: Optional EKPFS key material for encrypted images.

    Returns:
        Path to the output image file.
    """
    src: Path = make_minimal_app(tmp_path / "src")
    out: Path = tmp_path / "out.ffpfs"
    with _build_clock_patch():
        build_pfs(
            source_root=src,
            output_path=out,
            block_size=65536,
            pfs_version=c.PFS_VERSION_PS4,
            inode_bits=32,
            case_insensitive=True,
            signed=signed,
            compress=False,
            threshold_gain=20,
            cpu_count=1,
            zlib_level=9,
            dry_run=False,
            verbose=False,
            encrypted=encrypted,
            ekpfs=ekpfs,
        )
    return out


class PfsTestCase(unittest.TestCase):
    """Shared helpers for unittest-style PFS tests."""

    def make_temp_path(self) -> Path:
        """Create and register a temporary directory path for the current test."""
        temp_dir: tempfile.TemporaryDirectory[str] = tempfile.TemporaryDirectory()
        self.addCleanup(temp_dir.cleanup)
        return Path(temp_dir.name)


def assert_raises_build_error(operation: Callable[[], None]) -> None:
    """Assert that the provided callable raises ``BuildError``."""
    try:
        operation()
    except BuildError:
        return
    raise AssertionError("Expected BuildError was not raised")


# Signed/unsigned flag behavior
class TestUnsignedInodeFlags(PfsTestCase):
    """Tests for inode flags in unsigned images."""

    def test_unsigned_superroot_flags(self) -> None:
        """Superroot in unsigned image must have INTERNAL and READONLY."""
        tmp_path: Path = self.make_temp_path()
        out: Path = _build(tmp_path, signed=False)
        with out.open("rb") as fh:
            hdr = parse_image_header(fh)
            inodes = parse_image_inodes(fh, hdr)
        # inode 0 is superroot
        sr = inodes[0]
        assert sr.flags & c.INODE_FLAG_INTERNAL
        assert sr.flags & c.INODE_FLAG_READONLY
        assert not (sr.flags & c.INODE_FLAG_SIGNED_EXTRA)

    def test_unsigned_uroot_flags(self) -> None:
        """Uroot in unsigned image must have READONLY, not SIGNED_EXTRA."""
        tmp_path: Path = self.make_temp_path()
        out: Path = _build(tmp_path, signed=False)
        with out.open("rb") as fh:
            hdr = parse_image_header(fh)
            inodes = parse_image_inodes(fh, hdr)
        # uroot is inode 2 (no collision in minimal app)
        uroot = inodes[2]
        assert uroot.flags & c.INODE_FLAG_READONLY
        assert not (uroot.flags & c.INODE_FLAG_SIGNED_EXTRA)

    def test_file_inode_flags_unsigned(self) -> None:
        """All file inodes in unsigned image must have READONLY, not SIGNED_EXTRA."""
        tmp_path: Path = self.make_temp_path()
        out: Path = _build(tmp_path, signed=False)
        with out.open("rb") as fh:
            hdr = parse_image_header(fh)
            inodes = parse_image_inodes(fh, hdr)
        # All file inodes must have READONLY set and no SIGNED_EXTRA
        file_inodes = [i for i in inodes if i.mode & c.INODE_MODE_FILE]
        for fi in file_inodes:
            assert fi.flags & c.INODE_FLAG_READONLY, f"inode {fi.number} missing READONLY"
            assert not (fi.flags & c.INODE_FLAG_SIGNED_EXTRA), f"inode {fi.number} has SIGNED_EXTRA in unsigned image"


class TestSignedInodeFlags(PfsTestCase):
    """Tests for inode flags in signed images."""

    def test_signed_superroot_flags(self) -> None:
        """Superroot in signed image must have INTERNAL and SIGNED_EXTRA, not READONLY."""
        tmp_path: Path = self.make_temp_path()
        out: Path = _build(tmp_path, signed=True)
        with out.open("rb") as fh:
            hdr = parse_image_header(fh)
            inodes = parse_image_inodes(fh, hdr)
        sr = inodes[0]
        assert sr.flags & c.INODE_FLAG_INTERNAL
        assert not (sr.flags & c.INODE_FLAG_READONLY)  # cleared for signed
        assert sr.flags & c.INODE_FLAG_SIGNED_EXTRA

    def test_signed_uroot_flags(self) -> None:
        """Uroot in signed image must have SIGNED_EXTRA, not READONLY."""
        tmp_path: Path = self.make_temp_path()
        out: Path = _build(tmp_path, signed=True)
        with out.open("rb") as fh:
            hdr = parse_image_header(fh)
            inodes = parse_image_inodes(fh, hdr)
        uroot = inodes[2]
        assert not (uroot.flags & c.INODE_FLAG_READONLY)
        assert uroot.flags & c.INODE_FLAG_SIGNED_EXTRA

    def test_file_inode_flags_signed(self) -> None:
        """All file inodes in signed image must have SIGNED_EXTRA and READONLY."""
        tmp_path: Path = self.make_temp_path()
        out: Path = _build(tmp_path, signed=True)
        with out.open("rb") as fh:
            hdr = parse_image_header(fh)
            inodes = parse_image_inodes(fh, hdr)
        file_inodes = [i for i in inodes if i.mode & c.INODE_MODE_FILE and not (i.flags & c.INODE_FLAG_INTERNAL)]
        for fi in file_inodes:
            assert fi.flags & c.INODE_FLAG_READONLY, f"inode {fi.number} missing READONLY"
            assert fi.flags & c.INODE_FLAG_SIGNED_EXTRA, f"inode {fi.number} missing SIGNED_EXTRA"

    def test_directory_inode_flags_signed(self) -> None:
        """All directory inodes in signed image must have SIGNED_EXTRA."""
        tmp_path: Path = self.make_temp_path()
        out: Path = _build(tmp_path, signed=True)
        with out.open("rb") as fh:
            hdr = parse_image_header(fh)
            inodes = parse_image_inodes(fh, hdr)
        # Non-superroot directories should have SIGNED_EXTRA
        dir_inodes = [
            i
            for i in inodes
            if (i.mode & c.INODE_MODE_DIR) and not (i.flags & c.INODE_FLAG_INTERNAL) and i.number != 0
        ]
        for di in dir_inodes:
            assert di.flags & c.INODE_FLAG_SIGNED_EXTRA, f"dir inode {di.number} missing SIGNED_EXTRA"


class TestSignedImageRoundTrip(PfsTestCase):
    """Round-trip tests for signed images."""

    def test_signed_image_passes_check(self) -> None:
        """A newly built signed image must pass check with zero errors."""
        from mkpfs.cli import run_image_check

        tmp_path: Path = self.make_temp_path()
        out: Path = _build(tmp_path, signed=True)
        errors, _warnings, _tree, _uroot = run_image_check(image=out, source=None, print_tree=False, emit_report=False)
        assert errors == [], f"signed image check produced errors: {errors}"

    def test_signed_image_mode_bit_set(self) -> None:
        """Built signed image must have PFS_MODE_SIGNED in the header mode field."""
        tmp_path: Path = self.make_temp_path()
        out: Path = _build(tmp_path, signed=True)
        with out.open("rb") as fh:
            hdr = parse_image_header(fh)
        assert hdr.mode & c.PFS_MODE_SIGNED

    def test_signed_image_with_nested_dirs_passes_check(self) -> None:
        """Signed image with nested dirs must pass check."""
        from mkpfs.cli import run_image_check

        tmp_path: Path = self.make_temp_path()
        src: Path = make_app_with_nested_dirs(tmp_path / "src")
        out: Path = tmp_path / "out.ffpfs"
        build_pfs(
            source_root=src,
            output_path=out,
            block_size=65536,
            pfs_version=c.PFS_VERSION_PS4,
            inode_bits=32,
            case_insensitive=True,
            signed=True,
            compress=False,
            threshold_gain=20,
            cpu_count=1,
            zlib_level=9,
            dry_run=False,
            verbose=False,
        )
        errors, _warnings, _tree, _uroot = run_image_check(image=out, source=None, print_tree=False, emit_report=False)
        assert errors == [], f"nested signed image errors: {errors}"

    def test_signed_image_source_match(self) -> None:
        """Signed image must pass source-match validation."""
        from mkpfs.cli import run_image_check

        tmp_path: Path = self.make_temp_path()
        src: Path = make_app_with_nested_dirs(tmp_path / "src")
        out: Path = tmp_path / "out.ffpfs"
        build_pfs(
            source_root=src,
            output_path=out,
            block_size=65536,
            pfs_version=c.PFS_VERSION_PS4,
            inode_bits=32,
            case_insensitive=True,
            signed=True,
            compress=False,
            threshold_gain=20,
            cpu_count=1,
            zlib_level=9,
            dry_run=False,
            verbose=False,
        )
        errors, _warnings, _tree, _uroot = run_image_check(image=out, source=src, print_tree=False, emit_report=False)
        assert errors == [], f"source-match errors: {errors}"


class TestEncryptedImageRoundTrip(PfsTestCase):
    """Round-trip tests for encrypted images."""

    def test_encrypted_image_sets_mode_bit_and_passes_check(self) -> None:
        """Encrypted builds should set the encrypted mode bit and verify cleanly."""
        tmp_path: Path = self.make_temp_path()
        out: Path = _build(tmp_path, encrypted=True)
        with out.open("rb") as fh:
            header = parse_image_header(fh)
        assert header.mode & c.PFS_MODE_ENCRYPTED
        errors, _warnings, _tree, _uroot = run_image_check(image=out, source=None, print_tree=False, emit_report=False)
        assert errors == [], f"encrypted image check produced errors: {errors}"

    def test_signed_and_encrypted_image_passes_check(self) -> None:
        """Signed encrypted builds should still verify cleanly."""
        tmp_path: Path = self.make_temp_path()
        out: Path = _build(tmp_path, signed=True, encrypted=True)
        errors, _warnings, _tree, _uroot = run_image_check(image=out, source=None, print_tree=False, emit_report=False)
        assert errors == [], f"signed encrypted image check produced errors: {errors}"

    def test_encrypted_image_source_match_and_extract_round_trip(self) -> None:
        """Encrypted images should compare against source and extract logical bytes correctly."""
        tmp_path: Path = self.make_temp_path()
        src: Path = make_app_with_nested_dirs(tmp_path / "src")
        out: Path = tmp_path / "encrypted.ffpfs"
        extracted_path: Path = tmp_path / "extracted"
        build_pfs(
            source_root=src,
            output_path=out,
            block_size=65536,
            pfs_version=c.PFS_VERSION_PS4,
            inode_bits=32,
            case_insensitive=True,
            signed=False,
            compress=False,
            threshold_gain=20,
            cpu_count=1,
            zlib_level=9,
            dry_run=False,
            verbose=False,
            encrypted=True,
        )
        errors, _warnings, _tree, _uroot = run_image_check(image=out, source=src, print_tree=False, emit_report=False)
        assert errors == [], f"encrypted source-match errors: {errors}"

        extraction_result: pfs_mod.PFSExtractionResult = extract_pfs_image(image=out, output_path=extracted_path)
        assert extraction_result.errors == []
        for source_file in sorted(path for path in src.rglob("*") if path.is_file()):
            rel_path: Path = source_file.relative_to(src)
            extracted_file: Path = extracted_path / rel_path
            assert extracted_file.read_bytes() == source_file.read_bytes()

    def test_encrypted_image_with_compression_is_readable(self) -> None:
        """Encrypted images should remain readable when stored payloads are compressed."""
        tmp_path: Path = self.make_temp_path()
        src: Path = make_app_with_nested_dirs(tmp_path / "src")
        large_file: Path = src / "data" / "large.bin"
        large_file.write_bytes(b"A" * 200000)
        out: Path = tmp_path / "compressed-encrypted.ffpfs"
        build_pfs(
            source_root=src,
            output_path=out,
            block_size=65536,
            pfs_version=c.PFS_VERSION_PS4,
            inode_bits=32,
            case_insensitive=True,
            signed=False,
            compress=True,
            threshold_gain=1,
            cpu_count=1,
            zlib_level=9,
            dry_run=False,
            verbose=False,
            encrypted=True,
        )
        inspection: pfs_mod.PFSImageInspection = inspect_pfs_image(image=out, source=src)
        assert inspection.errors == []
        assert inspection.compressed_files > 0

    def test_compressed_images_store_direct_pfsc_payloads(self) -> None:
        """Compressed builds should store PFSC payloads directly in compressed file inodes."""
        tmp_path: Path = self.make_temp_path()
        src: Path = make_app_with_nested_dirs(tmp_path / "src")
        large_file: Path = src / "data" / "large.bin"
        large_file.write_bytes(b"A" * 200000)
        out: Path = tmp_path / "global-pfsc.ffpfs"
        build_pfs(
            source_root=src,
            output_path=out,
            block_size=65536,
            pfs_version=c.PFS_VERSION_PS4,
            inode_bits=32,
            case_insensitive=True,
            signed=False,
            compress=True,
            threshold_gain=1,
            cpu_count=1,
            zlib_level=9,
            dry_run=False,
            verbose=False,
            encrypted=False,
        )
        with out.open("rb") as fh:
            header: pfs_mod.ParsedHeader = parse_image_header(fh)
            inodes: list[pfs_mod.ParsedInode] = parse_image_inodes(fh, header)
            superroot_payload: bytes = pfs_mod.read_image_inode_payload(fh, header, inodes[0])
            superroot_dirents, _parse_errors = pfs_mod.parse_image_dirents(superroot_payload, strict=True)
            superroot_names: set[str] = {entry.name for entry in superroot_dirents}
            assert "global_pfsc_data" not in superroot_names

            inspection: pfs_mod.PFSImageInspection = inspect_pfs_image(image=out, source=src)
            assert inspection.errors == []
            compressed_inode_number: int = inspection.file_inodes["data/large.bin"]
            compressed_inode: pfs_mod.ParsedInode = inspection.inodes[compressed_inode_number]
            assert compressed_inode.is_compressed
            assert compressed_inode.size < compressed_inode.size_compressed
            assert compressed_inode.size_compressed == len(large_file.read_bytes())
            compressed_payload: bytes = pfs_mod.read_image_inode_payload(fh, header, compressed_inode)
            assert len(compressed_payload) == compressed_inode.size
            assert compressed_payload[:4] == b"PFSC"

    def test_build_pfs_uses_custom_temp_folder_for_pfsc_spool_files(self) -> None:
        """Compressed builds should route PFSC spool files through the configured temp folder."""
        tmp_path: Path = self.make_temp_path()
        src: Path = make_app_with_nested_dirs(tmp_path / "src")
        large_file: Path = src / "data" / "large.bin"
        large_file.write_bytes(b"A" * 200000)
        out: Path = tmp_path / "custom-temp-folder.ffpfs"
        custom_temp_folder: Path = tmp_path / "pack-temp"
        expected_temp_folder: Path = custom_temp_folder.resolve()

        def fake_make_compression_spool_path(*, source_path: Path, temp_folder: Path | None = None) -> Path:
            self.assertEqual(temp_folder, expected_temp_folder)
            return expected_temp_folder / f"mkpfs-{source_path.name}.pfsc"

        with patch.object(pfs_mod, "_make_compression_spool_path", side_effect=fake_make_compression_spool_path):
            build_pfs(
                source_root=src,
                output_path=out,
                block_size=65536,
                pfs_version=c.PFS_VERSION_PS4,
                inode_bits=32,
                case_insensitive=True,
                signed=False,
                compress=True,
                threshold_gain=1,
                cpu_count=1,
                zlib_level=9,
                dry_run=False,
                verbose=False,
                encrypted=False,
                temp_folder=expected_temp_folder,
            )

        assert out.is_file()

    def test_executable_compression_skip_keeps_eboot_prx_and_sprx_raw(self) -> None:
        """Requested executable compression skips should leave eboot*.bin, *.prx, and *.sprx inodes raw."""
        tmp_path: Path = self.make_temp_path()
        src: Path = make_app_with_nested_dirs(tmp_path / "src")
        eboot_path: Path = src / "eboot_patch.bin"
        prx_path: Path = src / "modules" / "libsample.prx"
        sprx_path: Path = src / "modules" / "libsample.sprx"
        normal_path: Path = src / "data" / "large.bin"
        prx_path.parent.mkdir(parents=True)
        eboot_payload: bytes = b"E" * 200000
        prx_payload: bytes = b"P" * 200000
        sprx_payload: bytes = b"X" * 200000
        normal_payload: bytes = b"N" * 200000
        eboot_path.write_bytes(eboot_payload)
        prx_path.write_bytes(prx_payload)
        sprx_path.write_bytes(sprx_payload)
        normal_path.write_bytes(normal_payload)
        out: Path = tmp_path / "skip-executables.ffpfs"
        build_pfs(
            source_root=src,
            output_path=out,
            block_size=65536,
            pfs_version=c.PFS_VERSION_PS4,
            inode_bits=32,
            case_insensitive=True,
            signed=False,
            compress=True,
            threshold_gain=1,
            cpu_count=1,
            zlib_level=9,
            dry_run=False,
            verbose=False,
            encrypted=False,
            skip_executable_compression=True,
        )

        with out.open("rb") as fh:
            header: pfs_mod.ParsedHeader = parse_image_header(fh)
            inspection: pfs_mod.PFSImageInspection = inspect_pfs_image(image=out, source=src)
            assert inspection.errors == []

            eboot_inode: pfs_mod.ParsedInode = inspection.inodes[inspection.file_inodes["eboot_patch.bin"]]
            prx_inode: pfs_mod.ParsedInode = inspection.inodes[inspection.file_inodes["modules/libsample.prx"]]
            sprx_inode: pfs_mod.ParsedInode = inspection.inodes[inspection.file_inodes["modules/libsample.sprx"]]
            normal_inode: pfs_mod.ParsedInode = inspection.inodes[inspection.file_inodes["data/large.bin"]]

            assert not eboot_inode.is_compressed
            assert not prx_inode.is_compressed
            assert not sprx_inode.is_compressed
            assert normal_inode.is_compressed
            assert pfs_mod.read_image_inode_payload(fh, header, eboot_inode) == eboot_payload
            assert pfs_mod.read_image_inode_payload(fh, header, prx_inode) == prx_payload
            assert pfs_mod.read_image_inode_payload(fh, header, sprx_inode) == sprx_payload
            assert pfs_mod.read_image_inode_payload(fh, header, normal_inode)[:4] == b"PFSC"

    def test_min_file_gain_keeps_low_gain_files_raw(self) -> None:
        """Whole-file gain thresholds should reject PFSC payloads below the requested gain."""
        tmp_path: Path = self.make_temp_path()
        src: Path = make_app_with_nested_dirs(tmp_path / "src")
        rng: random.Random = random.Random(12345)
        low_gain_payload: bytes = (b"\x00" * (c.PFSC_LOGICAL_BLOCK_SIZE * 4)) + bytes(
            rng.randrange(0, 256) for _ in range(c.PFSC_LOGICAL_BLOCK_SIZE)
        )
        high_gain_payload: bytes = b"H" * (c.PFSC_LOGICAL_BLOCK_SIZE * 100)
        low_gain_path: Path = src / "data" / "low_gain.bin"
        high_gain_path: Path = src / "data" / "high_gain.bin"
        low_gain_path.write_bytes(low_gain_payload)
        high_gain_path.write_bytes(high_gain_payload)
        out: Path = tmp_path / "whole-file-gain.ffpfs"

        build_pfs(
            source_root=src,
            output_path=out,
            block_size=65536,
            pfs_version=c.PFS_VERSION_PS4,
            inode_bits=32,
            case_insensitive=True,
            signed=False,
            compress=True,
            threshold_gain=1,
            min_file_gain=95,
            cpu_count=1,
            zlib_level=9,
            dry_run=False,
            verbose=False,
            encrypted=False,
        )

        with out.open("rb") as fh:
            header: pfs_mod.ParsedHeader = parse_image_header(fh)
            inspection: pfs_mod.PFSImageInspection = inspect_pfs_image(image=out, source=src)
            assert inspection.errors == []
            low_gain_inode: pfs_mod.ParsedInode = inspection.inodes[inspection.file_inodes["data/low_gain.bin"]]
            high_gain_inode: pfs_mod.ParsedInode = inspection.inodes[inspection.file_inodes["data/high_gain.bin"]]
            assert not low_gain_inode.is_compressed
            assert high_gain_inode.is_compressed
            assert pfs_mod.read_image_inode_payload(fh, header, low_gain_inode) == low_gain_payload
            assert pfs_mod.read_image_inode_payload(fh, header, high_gain_inode)[:4] == b"PFSC"

    def test_min_compress_size_skips_small_files_before_pfsc(self) -> None:
        """Files below the requested compression size floor should be stored raw."""
        tmp_path: Path = self.make_temp_path()
        src: Path = make_app_with_nested_dirs(tmp_path / "src")
        small_path: Path = src / "data" / "small_repeated.bin"
        large_path: Path = src / "data" / "large_repeated.bin"
        small_payload: bytes = b"S" * 4096
        large_payload: bytes = b"L" * 200000
        small_path.write_bytes(small_payload)
        large_path.write_bytes(large_payload)
        out: Path = tmp_path / "min-compress-size.ffpfs"

        build_pfs(
            source_root=src,
            output_path=out,
            block_size=65536,
            pfs_version=c.PFS_VERSION_PS4,
            inode_bits=32,
            case_insensitive=True,
            signed=False,
            compress=True,
            threshold_gain=1,
            cpu_count=1,
            zlib_level=9,
            dry_run=False,
            verbose=False,
            encrypted=False,
            min_compress_size=65536,
        )

        with out.open("rb") as fh:
            header: pfs_mod.ParsedHeader = parse_image_header(fh)
            inspection: pfs_mod.PFSImageInspection = inspect_pfs_image(image=out, source=src)
            assert inspection.errors == []
            small_inode: pfs_mod.ParsedInode = inspection.inodes[inspection.file_inodes["data/small_repeated.bin"]]
            large_inode: pfs_mod.ParsedInode = inspection.inodes[inspection.file_inodes["data/large_repeated.bin"]]
            assert not small_inode.is_compressed
            assert large_inode.is_compressed
            assert pfs_mod.read_image_inode_payload(fh, header, small_inode) == small_payload
            assert pfs_mod.read_image_inode_payload(fh, header, large_inode)[:4] == b"PFSC"

    def test_build_pfs_handles_fpt_collision_inode_renumbering(self) -> None:
        """Forced FPT collisions should not break inode renumbering during build."""
        tmp_path: Path = self.make_temp_path()
        src: Path = make_app_with_nested_dirs(tmp_path / "src")
        out: Path = tmp_path / "collision-renumbering.ffpfs"

        with patch.object(pfs_mod, "fpt_hash", return_value=0x12345678):
            build_pfs(
                source_root=src,
                output_path=out,
                block_size=65536,
                pfs_version=c.PFS_VERSION_PS4,
                inode_bits=32,
                case_insensitive=True,
                signed=False,
                compress=True,
                threshold_gain=1,
                cpu_count=1,
                zlib_level=9,
                dry_run=False,
                verbose=False,
                encrypted=False,
            )

        assert out.is_file()
        assert out.stat().st_size > 0

    def test_pfsc_encode_decode_round_trip(self) -> None:
        """PFSC payload encoding and decoding should preserve logical bytes."""
        raw: bytes = (b"A" * 65536) + (b"B" * 65536) + (b"C" * 1234)
        encoded: bytes
        gain_pct: float
        hypothetical_size: int
        encoded, gain_pct, hypothetical_size = pfs_mod.encode_pfsc_payload(
            raw=raw,
            threshold_gain=1,
            zlib_level=9,
            logical_block_size=c.PFSC_LOGICAL_BLOCK_SIZE,
        )
        assert encoded != raw
        assert gain_pct > 0.0
        assert hypothetical_size >= len(encoded)
        assert encoded[:4] == b"PFSC"
        decoded: bytes = pfs_mod.decode_pfsc_payload(payload=encoded, expected_logical_size=len(raw))
        assert decoded == raw
        magic, unk4, unk8, block_size, block_size2, block_offsets, data_start, data_length = struct.unpack_from(
            "<iiiiqqQq", encoded, 0
        )
        assert magic == c.PFSC_MAGIC
        assert unk4 == c.PFSC_UNK4
        assert unk8 == c.PFSC_UNK8
        assert block_size == c.PFSC_LOGICAL_BLOCK_SIZE
        assert block_size2 == c.PFSC_LOGICAL_BLOCK_SIZE
        assert block_offsets == c.PFSC_BLOCK_OFFSETS_OFFSET
        assert data_start >= c.PFSC_INITIAL_DATA_OFFSET
        assert data_length == 3 * c.PFSC_LOGICAL_BLOCK_SIZE

    def test_pfsc_encode_reports_incremental_progress_bytes(self) -> None:
        """PFSC encoding should report raw bytes as each logical block is processed."""
        raw: bytes = (b"A" * c.PFSC_LOGICAL_BLOCK_SIZE) + (b"B" * 1234)
        reported_deltas: list[int] = []

        pfs_mod.encode_pfsc_payload(
            raw=raw,
            threshold_gain=1,
            zlib_level=9,
            logical_block_size=c.PFSC_LOGICAL_BLOCK_SIZE,
            progress_callback=reported_deltas.append,
        )

        assert reported_deltas == [c.PFSC_LOGICAL_BLOCK_SIZE, 1234]
        assert sum(reported_deltas) == len(raw)

    def test_compute_file_storage_worker_batches_progress_updates(self) -> None:
        """Compression workers should batch byte deltas before reporting them upstream."""

        class FakeProgressQueue:
            """Collect worker progress deltas without multiprocessing."""

            def __init__(self) -> None:
                self.items: list[int] = []

            def put(self, item: int) -> None:
                """Record a worker progress delta."""
                self.items.append(item)

        tmp_path: Path = self.make_temp_path()
        file_path: Path = tmp_path / "large.bin"
        raw: bytes = b"A" * (c.PFSC_LOGICAL_BLOCK_SIZE * 20 + 123)
        file_path.write_bytes(raw)
        progress_queue: FakeProgressQueue = FakeProgressQueue()

        result: tuple[Path, Path, bool, int, bool, float, int] = pfs_mod._compute_file_storage_worker(
            (
                file_path,
                1,
                0,
                0,
                True,
                c.PFSC_LOGICAL_BLOCK_SIZE,
                9,
                False,
                progress_queue,
                None,
            )
        )

        assert result[0] == file_path
        assert isinstance(result[1], Path)
        assert isinstance(result[2], bool)
        assert sum(progress_queue.items) == len(raw)
        assert len(progress_queue.items) >= 2
        assert progress_queue.items[0] == pfs_mod.PFSC_PROGRESS_REPORT_BYTES
        assert progress_queue.items[-1] <= pfs_mod.PFSC_PROGRESS_REPORT_BYTES

    def test_resolve_compression_worker_count_auto_uses_cpu_count(self) -> None:
        """Auto worker resolution should use ``max(1, cpu_count())``."""
        with patch.object(pfs_mod.mp, "cpu_count", return_value=8):
            assert pfs_mod.resolve_compression_worker_count(requested_cpu_count=0) == 8

        with patch.object(pfs_mod.mp, "cpu_count", return_value=1):
            assert pfs_mod.resolve_compression_worker_count(requested_cpu_count=0) == 1

    def test_resolve_compression_worker_count_keeps_explicit_request(self) -> None:
        """Explicit worker requests should be normalized with ``max(1, user)``."""
        assert pfs_mod.resolve_compression_worker_count(requested_cpu_count=10) == 10
        assert pfs_mod.resolve_compression_worker_count(requested_cpu_count=2) == 2

    def test_resolve_block_compression_worker_count_is_thresholded(self) -> None:
        """Block-level workers should only activate for files above the size threshold."""
        threshold_size: int = pfs_mod.PFSC_SINGLE_FILE_PARALLEL_MIN_SIZE
        assert (
            pfs_mod.resolve_block_compression_worker_count(
                requested_cpu_count=8,
                file_size=threshold_size - 1,
            )
            == 1
        )
        assert (
            pfs_mod.resolve_block_compression_worker_count(
                requested_cpu_count=8,
                file_size=threshold_size,
            )
            == 8
        )

    def test_single_file_dry_run_uses_block_workers_above_threshold(self) -> None:
        """Single-file dry run should request multiple block workers above threshold."""
        tmp_path: Path = self.make_temp_path()
        src: Path = tmp_path / "src"
        src.mkdir(parents=True)
        file_path: Path = src / "large.bin"
        file_path.write_bytes(b"A" * (c.PFSC_LOGICAL_BLOCK_SIZE * 3))
        out: Path = tmp_path / "out.ffpfs"
        observed_block_workers: list[int] = []

        def fake_analyze_pfsc_file_storage(
            *,
            abs_path: Path,
            threshold_gain: int,
            min_file_gain: int,
            zlib_level: int,
            logical_block_size: int,
            block_worker_count: int = 1,
            progress_callback: Callable[[int], None] | None = None,
        ) -> tuple[int, bool, float, int]:
            """Capture requested block worker count and return uncompressed metadata."""
            observed_block_workers.append(block_worker_count)
            raw_size: int = abs_path.stat().st_size
            if progress_callback is not None:
                progress_callback(raw_size)
            _ = threshold_gain
            _ = min_file_gain
            _ = zlib_level
            _ = logical_block_size
            return raw_size, False, 0.0, 0

        with patch.object(pfs_mod, "PFSC_SINGLE_FILE_PARALLEL_MIN_SIZE", 1), patch.object(
            pfs_mod,
            "_analyze_pfsc_file_storage",
            side_effect=fake_analyze_pfsc_file_storage,
        ):
            build_pfs(
                source_root=src,
                output_path=out,
                block_size=65536,
                pfs_version=c.PFS_VERSION_PS4,
                inode_bits=32,
                case_insensitive=True,
                signed=False,
                compress=True,
                threshold_gain=1,
                zlib_level=7,
                dry_run=True,
                cpu_count=4,
                verbose=False,
                encrypted=False,
            )

        assert observed_block_workers
        assert observed_block_workers[0] == 4

    def test_parallel_pfsc_spool_matches_single_worker_output(self) -> None:
        """Parallel PFSC spool encoding should match single-worker output bytes."""
        tmp_path: Path = self.make_temp_path()
        source_path: Path = tmp_path / "source.bin"
        raw_payload: bytes = (b"A" * c.PFSC_LOGICAL_BLOCK_SIZE) + (b"ABCD" * 2048) + (b"\x00" * 12345)
        source_path.write_bytes(raw_payload)
        sequential_spool: Path = tmp_path / "sequential.pfsc"
        parallel_spool: Path = tmp_path / "parallel.pfsc"

        sequential_result: tuple[int, bool, float, int] = pfs_mod._encode_pfsc_file_to_spool(
            abs_path=source_path,
            spool_path=sequential_spool,
            threshold_gain=1,
            min_file_gain=0,
            zlib_level=7,
            logical_block_size=c.PFSC_LOGICAL_BLOCK_SIZE,
            block_worker_count=1,
        )
        parallel_result: tuple[int, bool, float, int] = pfs_mod._encode_pfsc_file_to_spool(
            abs_path=source_path,
            spool_path=parallel_spool,
            threshold_gain=1,
            min_file_gain=0,
            zlib_level=7,
            logical_block_size=c.PFSC_LOGICAL_BLOCK_SIZE,
            block_worker_count=2,
        )

        assert sequential_result == parallel_result
        assert sequential_spool.read_bytes() == parallel_spool.read_bytes()

    def test_compression_phase_emits_intermediate_progress_for_single_worker(self) -> None:
        """Single-worker compression should emit intermediate progress updates."""
        tmp_path: Path = self.make_temp_path()
        src: Path = tmp_path / "src"
        src.mkdir(parents=True)
        raw_size: int = c.PFSC_LOGICAL_BLOCK_SIZE * 4 + 123
        (src / "large.bin").write_bytes(b"A" * raw_size)
        out: Path = tmp_path / "out.ffpfsc"

        with patch.object(pfs_mod.Progress, "step", autospec=True) as step_mock:
            build_pfs(
                source_root=src,
                output_path=out,
                block_size=65536,
                pfs_version=c.PFS_VERSION_PS4,
                inode_bits=32,
                case_insensitive=True,
                signed=False,
                compress=True,
                threshold_gain=1,
                cpu_count=1,
                zlib_level=7,
                dry_run=False,
                verbose=False,
                encrypted=False,
            )

        compress_calls: list[tuple[int, int]] = [
            (int(call.args[2]), int(call.args[3])) for call in step_mock.call_args_list if call.args[1] == "compress"
        ]
        assert compress_calls
        assert any(done == 0 for done, _total in compress_calls)
        assert any(0 < done < total for done, total in compress_calls)
        assert any(done == total for done, total in compress_calls)

    def test_pfsc_decode_rejects_invalid_magic(self) -> None:
        """PFSC decoding should fail when the payload magic is invalid."""
        raw: bytes = b"A" * 70000
        encoded: bytes
        _gain_pct: float
        _hypothetical_size: int
        encoded, _gain_pct, _hypothetical_size = pfs_mod.encode_pfsc_payload(
            raw=raw,
            threshold_gain=1,
            zlib_level=9,
            logical_block_size=c.PFSC_LOGICAL_BLOCK_SIZE,
        )
        broken_payload: bytearray = bytearray(encoded)
        broken_payload[0:4] = b"BAD!"
        try:
            pfs_mod.decode_pfsc_payload(payload=bytes(broken_payload), expected_logical_size=len(raw))
        except ValueError as exc:
            assert "magic" in str(exc)
            return
        raise AssertionError("Expected ValueError for invalid PFSC magic")

    def test_decode_inode_payload_rejects_legacy_whole_file_zlib(self) -> None:
        """Compressed inode payloads must use PFSC, legacy whole-file zlib payloads are invalid."""
        raw: bytes = b"A" * 100000
        legacy_payload: bytes = pfs_mod.zlib.compress(raw)
        inode: pfs_mod.ParsedInode = pfs_mod.ParsedInode(
            number=99,
            mode=c.INODE_MODE_FILE | c.INODE_RX_ONLY,
            nlink=1,
            flags=c.INODE_FLAG_COMPRESSED,
            size=len(legacy_payload),
            size_compressed=len(raw),
            blocks=1,
            db=[0] * c.MAX_DIRECT_BLOCKS,
            ib=[0] * c.MAX_INDIRECT_BLOCKS,
        )
        try:
            pfs_mod.decode_inode_payload(payload=legacy_payload, inode=inode)
        except ValueError as exc:
            assert "magic" in str(exc)
            return
        raise AssertionError("Expected ValueError for legacy whole-file compressed payload")

    def test_parse_ekpfs_key_hex_defaults_to_zero_key(self) -> None:
        """Omitted EKPFS input should resolve to the all-zero fallback key."""
        parsed_key: bytes = parse_ekpfs_key_hex()
        assert parsed_key == c.ZERO_EKPFS

    def test_pfs_gen_enc_keys_uses_expected_zero_key_seed_pair(self) -> None:
        """Encryption key derivation should split the HMAC digest into tweak and data keys."""
        tweak_key: bytes
        data_key: bytes
        tweak_key, data_key = pfs_gen_enc_keys(ekpfs=c.ZERO_EKPFS, seed=c.ZERO_PFS_SEED)
        assert len(tweak_key) == 16
        assert len(data_key) == 16
        assert tweak_key != data_key


def _make_simple_inode(number: int) -> Inode:
    """Create a minimal inode for testing."""
    return Inode(
        number=number,
        mode=c.INODE_MODE_FILE | c.INODE_RX_ONLY,
        nlink=1,
        flags=c.INODE_FLAG_READONLY,
        size=0,
        size_compressed=0,
        blocks=1,
    )


class TestFptHash(PfsTestCase):
    """Tests for the flat path table hash function."""

    def test_fpt_hash_case_insensitive_known(self) -> None:
        """Hash of '/eboot.bin' case-insensitive must match legacy algorithm."""
        name: str = "/eboot.bin"
        expected: int = 0
        for ch in name:
            expected = (ord(ch.upper()) + 31 * expected) & 0xFFFFFFFF
        assert fpt_hash(name, case_insensitive=True) == expected

    def test_fpt_hash_case_sensitive(self) -> None:
        """Hash of '/eboot.bin' case-sensitive must match legacy algorithm."""
        name: str = "/eboot.bin"
        expected: int = 0
        for ch in name:
            expected = (ord(ch) + 31 * expected) & 0xFFFFFFFF
        assert fpt_hash(name, case_insensitive=False) == expected

    def test_fpt_hash_differs_by_case_when_case_sensitive(self) -> None:
        """Upper and lower case hashes differ when case-sensitive."""
        assert fpt_hash("/ABC", case_insensitive=False) != fpt_hash("/abc", case_insensitive=False)

    def test_fpt_hash_same_by_case_when_case_insensitive(self) -> None:
        """Upper and lower case hashes match when case-insensitive."""
        assert fpt_hash("/ABC", case_insensitive=True) == fpt_hash("/abc", case_insensitive=True)

    def test_fpt_hash_empty_string(self) -> None:
        """Hash of empty string must be 0."""
        assert fpt_hash("", case_insensitive=True) == 0

    def test_fpt_hash_single_char(self) -> None:
        """Hash of single character is the character's ord value."""
        assert fpt_hash("A", case_insensitive=False) == ord("A")
        assert fpt_hash("a", case_insensitive=False) == ord("a")
        assert fpt_hash("A", case_insensitive=True) == ord("A")
        assert fpt_hash("a", case_insensitive=True) == ord("A")


class TestMakeFptAndCollisionBlob(PfsTestCase):
    """Tests for FPT and collision blob generation."""

    def test_fpt_no_collision_single_file(self) -> None:
        """Single file produces one FPT entry, no collision blob."""
        root_dir: DirNode = DirNode(rel_dir="", name="uroot", parent_rel_dir=None)
        f: FileNode = FileNode(
            rel_path="eboot.bin",
            abs_path=Path("/fake/eboot.bin"),
            parent_rel_dir="",
            name="eboot.bin",
            raw_size=0,
        )
        f_ino: Inode = _make_simple_inode(3)
        f.inode = f_ino

        inode_by_path: dict[str, Inode] = {"file:eboot.bin": f_ino}
        fpt: bytes
        collision: bytes | None
        has_collision: bool
        fpt, collision, has_collision = make_fpt_and_collision_blob(
            dirs_sorted=[root_dir],
            files_sorted=[f],
            inode_by_path=inode_by_path,
            case_insensitive=True,
        )
        assert not has_collision
        assert collision is None
        # FPT must have exactly one entry: 8 bytes (hash + value)
        assert len(fpt) == 8
        h: int
        val: int
        h, val = struct.unpack_from("<II", fpt, 0)
        assert h == fpt_hash("/eboot.bin", case_insensitive=True)
        # value = inode_number (no dir flag)
        assert val == 3

    def test_fpt_dir_flag_set(self) -> None:
        """Directory entries set bit 29 (0x20000000) in the FPT value."""
        d: DirNode = DirNode(rel_dir="sce_sys", name="sce_sys", parent_rel_dir="")
        d_ino: Inode = Inode(
            number=4,
            mode=c.INODE_MODE_DIR | c.INODE_RX_ONLY,
            nlink=2,
            flags=c.INODE_FLAG_READONLY,
            size=65536,
            size_compressed=65536,
            blocks=1,
        )
        d.inode = d_ino

        inode_by_path: dict[str, Inode] = {"dir:sce_sys": d_ino}
        fpt: bytes
        collision: bytes | None
        fpt, collision, _ = make_fpt_and_collision_blob(
            dirs_sorted=[DirNode(rel_dir="", name="uroot", parent_rel_dir=None), d],
            files_sorted=[],
            inode_by_path=inode_by_path,
            case_insensitive=True,
        )
        assert collision is None
        _h: int
        val: int
        _h, val = struct.unpack_from("<II", fpt, 0)
        # dir entries have 0x20000000 ORed in
        assert val == (4 | 0x20000000)

    def test_fpt_collision_blob_terminator(self) -> None:
        """Collision blob entries end with 0x18 bytes of zero padding."""
        # Force a collision by monkey-patching fpt_hash
        original_fpt_hash = pfs_mod.fpt_hash

        try:
            # Monkeypatch to force all to same hash
            pfs_mod.fpt_hash = lambda name, case_insensitive=True: 0xDEADBEEF
            f1: FileNode = FileNode(
                rel_path="a",
                abs_path=Path("/fake/a"),
                parent_rel_dir="",
                name="a",
                raw_size=0,
            )
            f1.inode = _make_simple_inode(3)
            f2: FileNode = FileNode(
                rel_path="b",
                abs_path=Path("/fake/b"),
                parent_rel_dir="",
                name="b",
                raw_size=0,
            )
            f2.inode = _make_simple_inode(4)
            inode_by_path: dict[str, Inode] = {"file:a": f1.inode, "file:b": f2.inode}
            root: DirNode = DirNode(rel_dir="", name="uroot", parent_rel_dir=None)
            fpt: bytes
            blob: bytes | None
            has_collision: bool
            fpt, blob, has_collision = make_fpt_and_collision_blob(
                dirs_sorted=[root],
                files_sorted=[f1, f2],
                inode_by_path=inode_by_path,
                case_insensitive=True,
            )
            assert has_collision
            assert blob is not None
            # blob ends with 0x18 zero bytes per collision group
            assert blob[-0x18:] == b"\x00" * 0x18
            # FPT entry value must have 0x80000000 set (collision pointer)
            _h: int
            val: int
            _h, val = struct.unpack_from("<II", fpt, 0)
            assert val & 0x80000000 != 0
        finally:
            pfs_mod.fpt_hash = original_fpt_hash

    def test_fpt_no_collision_multiple_files(self) -> None:
        """Multiple files with different hashes produce multiple FPT entries."""
        f1: FileNode = FileNode(
            rel_path="eboot.bin",
            abs_path=Path("/fake/eboot.bin"),
            parent_rel_dir="",
            name="eboot.bin",
            raw_size=0,
        )
        f1.inode = _make_simple_inode(3)
        f2: FileNode = FileNode(
            rel_path="config.json",
            abs_path=Path("/fake/config.json"),
            parent_rel_dir="",
            name="config.json",
            raw_size=0,
        )
        f2.inode = _make_simple_inode(4)
        inode_by_path: dict[str, Inode] = {"file:eboot.bin": f1.inode, "file:config.json": f2.inode}
        root: DirNode = DirNode(rel_dir="", name="uroot", parent_rel_dir=None)
        fpt: bytes
        collision: bytes | None
        has_collision: bool
        fpt, collision, has_collision = make_fpt_and_collision_blob(
            dirs_sorted=[root],
            files_sorted=[f1, f2],
            inode_by_path=inode_by_path,
            case_insensitive=True,
        )
        assert not has_collision
        assert collision is None
        # FPT must have 2 entries: 16 bytes
        assert len(fpt) == 16


LEGACY_SCRIPT: Path = Path(__file__).resolve().parents[2] / "legacy" / "ffpfs.py"
FIXED_BUILD_TIME: int = 1_700_000_000
LEGACY_SCRIPT_PATH: str = str(LEGACY_SCRIPT)
LEGACY_AVAILABLE: bool = LEGACY_SCRIPT.is_file()


def _build_clock_patch() -> object:
    """Return a patch object that freezes build timestamps for parity tests."""
    return patch.object(pfs_mod.time, "time", return_value=FIXED_BUILD_TIME)


def _run_legacy_build(src: Path, out: Path, extra_args: list[str] | None = None) -> subprocess.CompletedProcess[str]:
    """Run legacy ffpfs.py create command with specified arguments.

    Args:
        src: Source directory containing app to package.
        out: Output image path.
        extra_args: Additional command-line arguments (e.g., --signed).

    Returns:
        CompletedProcess with return code, stdout, and stderr.
    """
    cmd: list[str] = [
        sys.executable,
        "-c",
        (
            "import importlib.util, pathlib, sys\n"
            "spec = importlib.util.spec_from_file_location(\n"
            "    'legacy_ffpfs_for_tests',\n"
            f"    pathlib.Path({LEGACY_SCRIPT_PATH!r}),\n"
            ")\n"
            "module = importlib.util.module_from_spec(spec)\n"
            "assert spec is not None and spec.loader is not None\n"
            "sys.modules[spec.name] = module\n"
            "spec.loader.exec_module(module)\n"
            f"module.time.time = lambda: {FIXED_BUILD_TIME}\n"
            "raise SystemExit(module.main(sys.argv[1:]))\n"
        ),
        "create",
        "--path",
        str(src),
        "--output",
        str(out),
        "--no-compress",
        "--block-size",
        "65536",
        "--version",
        "PS4",
        "--inode-bits",
        "32",
        "--case-insensitive",
    ] + (extra_args or [])
    return subprocess.run(cmd, capture_output=True, text=True)


def _build_new(src: Path, out: Path, signed: bool = False) -> None:
    """Build image using new mkpfs implementation.

    Args:
        src: Source directory containing app to package.
        out: Output image path.
        signed: Whether to create a signed image.
    """
    with _build_clock_patch():
        build_pfs(
            source_root=src,
            output_path=out,
            block_size=65536,
            pfs_version=c.PFS_VERSION_PS4,
            inode_bits=32,
            case_insensitive=True,
            signed=signed,
            compress=False,
            threshold_gain=20,
            cpu_count=1,
            zlib_level=9,
            dry_run=False,
            verbose=False,
        )


def parity_tmp(tmp_path: Path) -> Path:
    """Ensure tmp/parity directory exists for temporary test artifacts.

    Args:
        tmp_path: Temporary directory path for the test.

    Returns:
        Path to parity directory.
    """
    parity: Path = Path("tmp/parity")
    parity.mkdir(parents=True, exist_ok=True)
    return parity


def assert_unsigned_image_byte_identical(tmp_path: Path) -> None:
    """Unsigned image bytes must be identical between legacy and new build.

    Args:
        tmp_path: Temporary directory path for the test.
    """
    src: Path = make_minimal_app(tmp_path / "src")

    legacy_out: Path = tmp_path / "legacy.ffpfs"
    result: subprocess.CompletedProcess[str] = _run_legacy_build(src, legacy_out)
    assert result.returncode == 0, f"Legacy build failed: {result.stderr}"

    new_out: Path = tmp_path / "new.ffpfs"
    _build_new(src, new_out)

    assert legacy_out.read_bytes() == new_out.read_bytes(), (
        "Unsigned image bytes differ between legacy and new implementation"
    )


def assert_unsigned_check_agrees(tmp_path: Path) -> None:
    """New check command accepts legacy-built unsigned image.

    Args:
        tmp_path: Temporary directory path for the test.
    """
    src: Path = make_minimal_app(tmp_path / "src")

    legacy_out: Path = tmp_path / "legacy.ffpfs"
    result: subprocess.CompletedProcess[str] = _run_legacy_build(src, legacy_out)
    assert result.returncode == 0

    errors, _warnings, _tree, _uroot = run_image_check(
        image=legacy_out, source=None, print_tree=False, emit_report=False
    )
    assert errors == [], f"New check found errors in legacy-built image: {errors}"


def assert_legacy_check_accepts_new_image(tmp_path: Path) -> None:
    """Legacy check command accepts new-built unsigned image.

    Args:
        tmp_path: Temporary directory path for the test.
    """
    src: Path = make_minimal_app(tmp_path / "src")
    new_out: Path = tmp_path / "new.ffpfs"
    _build_new(src, new_out)

    result: subprocess.CompletedProcess[str] = subprocess.run(
        [sys.executable, str(LEGACY_SCRIPT), "check", "--image", str(new_out)],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, f"Legacy check rejected new image: {result.stdout}\n{result.stderr}"


def assert_nested_dirs_unsigned_byte_identical(tmp_path: Path) -> None:
    """Nested directory unsigned image bytes identical between implementations.

    Args:
        tmp_path: Temporary directory path for the test.
    """
    src: Path = make_app_with_nested_dirs(tmp_path / "src")

    legacy_out: Path = tmp_path / "legacy.ffpfs"
    result: subprocess.CompletedProcess[str] = _run_legacy_build(src, legacy_out)
    assert result.returncode == 0, f"Legacy build failed: {result.stderr}"

    new_out: Path = tmp_path / "new.ffpfs"
    _build_new(src, new_out)

    assert legacy_out.read_bytes() == new_out.read_bytes(), "Nested-dir unsigned image bytes differ"


def assert_signed_image_byte_identical(tmp_path: Path) -> None:
    """Signed image bytes must be identical between legacy and new build.

    Args:
        tmp_path: Temporary directory path for the test.
    """
    src: Path = make_minimal_app(tmp_path / "src")

    legacy_out: Path = tmp_path / "legacy_signed.ffpfs"
    result: subprocess.CompletedProcess[str] = _run_legacy_build(src, legacy_out, extra_args=["--signed"])
    assert result.returncode == 0, f"Legacy signed build failed: {result.stderr}"

    new_out: Path = tmp_path / "new_signed.ffpfs"
    _build_new(src, new_out, signed=True)

    assert legacy_out.read_bytes() == new_out.read_bytes(), (
        "Signed image bytes differ between legacy and new implementation"
    )


def assert_signed_legacy_check_accepts_new_signed(tmp_path: Path) -> None:
    """Legacy check accepts new-built signed image.

    Args:
        tmp_path: Temporary directory path for the test.
    """
    src: Path = make_minimal_app(tmp_path / "src")
    new_out: Path = tmp_path / "new_signed.ffpfs"
    _build_new(src, new_out, signed=True)

    result: subprocess.CompletedProcess[str] = subprocess.run(
        [sys.executable, str(LEGACY_SCRIPT), "check", "--image", str(new_out)],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, f"Legacy check rejected new signed image:\n{result.stdout}\n{result.stderr}"


def assert_nested_dirs_signed_byte_identical(tmp_path: Path) -> None:
    """Nested directory signed image bytes identical between implementations.

    Args:
        tmp_path: Temporary directory path for the test.
    """
    src: Path = make_app_with_nested_dirs(tmp_path / "src")

    legacy_out: Path = tmp_path / "legacy_signed.ffpfs"
    result: subprocess.CompletedProcess[str] = _run_legacy_build(src, legacy_out, extra_args=["--signed"])
    assert result.returncode == 0, f"Legacy signed build failed: {result.stderr}"

    new_out: Path = tmp_path / "new_signed.ffpfs"
    _build_new(src, new_out, signed=True)

    assert legacy_out.read_bytes() == new_out.read_bytes(), "Nested-dir signed image bytes differ"


def _build_signed(
    tmp_path: Path, src_fn: Callable[[Path], Path] = make_minimal_app, inode_bits: int = 32
) -> tuple[Path, Path]:
    """Build a signed PFS image from test app.

    Args:
        tmp_path: Temporary directory path.
        src_fn: Fixture function to create test app structure.
        inode_bits: Signed inode width to build, 32 or 64.

    Returns:
        Tuple of (output image path, source app path).
    """
    src: Path = src_fn(tmp_path / "src")
    out: Path = tmp_path / "signed.ffpfs"
    with _build_clock_patch():
        build_pfs(
            source_root=src,
            output_path=out,
            block_size=65536,
            pfs_version=c.PFS_VERSION_PS4,
            inode_bits=inode_bits,
            case_insensitive=True,
            signed=True,
            compress=False,
            threshold_gain=20,
            cpu_count=1,
            zlib_level=9,
            dry_run=False,
            verbose=False,
        )
    return out, src


class TestSignedImageBasic(PfsTestCase):
    """Basic tests for signed image structure."""

    def test_signed_image_passes_check(self) -> None:
        """A newly built signed image must pass check with zero errors."""
        tmp_path: Path = self.make_temp_path()
        out, _src = _build_signed(tmp_path)
        errors, _warnings, _tree, _uroot = run_image_check(image=out, source=None, print_tree=False, emit_report=False)
        assert errors == [], f"signed image check produced errors: {errors}"

    def test_signed_image_mode_bit_set(self) -> None:
        """Built signed image must have PFS_MODE_SIGNED in the header mode field."""
        tmp_path: Path = self.make_temp_path()
        out, _src = _build_signed(tmp_path)
        with out.open("rb") as fh:
            hdr = parse_image_header(fh)
        assert hdr.mode & c.PFS_MODE_SIGNED

    def test_signed_image_readonly_flag_set(self) -> None:
        """Built signed image must have readonly flag set."""
        tmp_path: Path = self.make_temp_path()
        out, _src = _build_signed(tmp_path)
        with out.open("rb") as fh:
            hdr = parse_image_header(fh)
        assert hdr.readonly


class TestSignedImageWithNestedDirs(PfsTestCase):
    """Tests for signed images with complex directory structures."""

    def test_signed_image_with_nested_dirs_passes_check(self) -> None:
        """Signed image with nested dirs must pass check."""
        tmp_path: Path = self.make_temp_path()
        out, _src = _build_signed(tmp_path, src_fn=make_app_with_nested_dirs)
        errors, _warnings, _tree, _uroot = run_image_check(image=out, source=None, print_tree=False, emit_report=False)
        assert errors == [], f"nested signed image errors: {errors}"

    def test_signed_image_source_match(self) -> None:
        """Signed image must pass source-match validation."""
        tmp_path: Path = self.make_temp_path()
        out, src = _build_signed(tmp_path, src_fn=make_app_with_nested_dirs)
        errors, _warnings, _tree, _uroot = run_image_check(image=out, source=src, print_tree=False, emit_report=False)
        assert errors == [], f"source-match errors: {errors}"


class TestSigned64ImageBasic(PfsTestCase):
    """Tests for signed 64-bit inode images."""

    def test_signed_64_image_passes_check(self) -> None:
        """A newly built signed 64-bit image must pass check with zero errors."""
        tmp_path: Path = self.make_temp_path()
        out, _src = _build_signed(tmp_path, inode_bits=64)
        errors, _warnings, _tree, _uroot = run_image_check(image=out, source=None, print_tree=False, emit_report=False)
        assert errors == [], f"signed 64-bit image check produced errors: {errors}"

    def test_signed_64_image_sets_both_header_mode_bits(self) -> None:
        """A signed 64-bit image must advertise both signed and 64-bit mode bits."""
        tmp_path: Path = self.make_temp_path()
        out, _src = _build_signed(tmp_path, inode_bits=64)
        with out.open("rb") as fh:
            hdr = parse_image_header(fh)
        assert hdr.mode & c.PFS_MODE_SIGNED
        assert hdr.mode & c.PFS_MODE_64BIT_INODES

    def test_signed_64_image_source_match(self) -> None:
        """A signed 64-bit image must pass source-match validation."""
        tmp_path: Path = self.make_temp_path()
        out, src = _build_signed(tmp_path, src_fn=make_app_with_nested_dirs, inode_bits=64)
        errors, _warnings, _tree, _uroot = run_image_check(image=out, source=src, print_tree=False, emit_report=False)
        assert errors == [], f"signed 64-bit source-match errors: {errors}"


class TestSignedImageHeaderDigest(PfsTestCase):
    """Tests for signed image header digest computation."""

    def test_header_digest_offset_used(self) -> None:
        """Verify HEADER_DIGEST_OFFSET constant is defined."""
        # This is a sanity check that the constant exists
        assert hasattr(c, "HEADER_DIGEST_OFFSET")
        assert c.HEADER_DIGEST_OFFSET == 0x380

    def test_header_digest_size_used(self) -> None:
        """Verify HEADER_DIGEST_SIZE constant is defined."""
        assert hasattr(c, "HEADER_DIGEST_SIZE")
        assert c.HEADER_DIGEST_SIZE == 0x5A0


def assert_dirent_to_bytes_known_vector() -> None:
    """Encode a file dirent for inode 5, name "eboot.bin" (9 chars)."""
    d: Dirent = Dirent(inode_number=5, type_code=c.DIRENT_TYPE_FILE, name="eboot.bin")
    assert d.name_length == 9
    assert d.ent_size == 32  # (9 + 17 = 26) -> round up to next 8 -> 32
    b: bytes = d.to_bytes()
    assert len(b) == 32
    ino_num, type_code, name_len, ent_sz = struct.unpack_from("<Iiii", b, 0)
    assert ino_num == 5
    assert type_code == c.DIRENT_TYPE_FILE
    assert name_len == 9
    assert ent_sz == 32
    assert b[16:25] == b"eboot.bin"
    assert b[25:32] == b"\x00" * 7


def assert_dirent_dot() -> None:
    """Directory entry for "." (current directory)."""
    d: Dirent = Dirent(inode_number=2, type_code=c.DIRENT_TYPE_DOT, name=".")
    # name_length=1, ent_size = (1 + 17 = 18) -> round up to 24
    assert d.ent_size == 24
    b: bytes = d.to_bytes()
    assert len(b) == 24


def assert_dirent_dotdot() -> None:
    """Directory entry for ".." (parent directory)."""
    d: Dirent = Dirent(inode_number=0, type_code=c.DIRENT_TYPE_DOTDOT, name="..")
    # name_length=2, ent_size = (2 + 17 = 19) -> round up to 24
    assert d.ent_size == 24
    b: bytes = d.to_bytes()
    assert len(b) == 24


def assert_dirent_directory() -> None:
    """Directory entry for a subdirectory."""
    d: Dirent = Dirent(inode_number=10, type_code=c.DIRENT_TYPE_DIRECTORY, name="sce_sys")
    # name_length=7, ent_size = (7 + 17 = 24) -> already aligned
    assert d.ent_size == 24
    b: bytes = d.to_bytes()
    assert len(b) == 24


def assert_inode_d32_size() -> None:
    """D32 inode serialization must produce exactly INODE_D32_SIZE bytes."""
    ino: Inode = Inode(
        number=1,
        mode=0x81A9,
        nlink=1,
        flags=c.INODE_FLAG_READONLY,
        size=1024,
        size_compressed=1024,
        blocks=1,
    )
    b: bytes = ino.to_bytes()
    assert len(b) == c.INODE_D32_SIZE


def assert_inode_d32_field_layout() -> None:
    """Verify D32 inode field positions match legacy parse_image_inode offsets.

    Legacy offsets:
    - mode at 0x00
    - nlink at 0x02
    - flags at 0x04
    - size at 0x08
    - size_compressed at 0x10
    - blocks at 0x60
    - db[0..11] at 0x64
    - ib[0..4] at 0x94
    """
    ino: Inode = Inode(
        number=7,
        mode=0x8000,
        nlink=3,
        flags=0x10,
        size=512,
        size_compressed=512,
        blocks=1,
    )
    ino.db[0] = 42
    ino.ib[0] = 99
    b: bytes = ino.to_bytes()
    assert struct.unpack_from("<H", b, 0x00)[0] == 0x8000  # mode
    assert struct.unpack_from("<H", b, 0x02)[0] == 3  # nlink
    assert struct.unpack_from("<I", b, 0x04)[0] == 0x10  # flags
    assert struct.unpack_from("<q", b, 0x08)[0] == 512  # size
    assert struct.unpack_from("<q", b, 0x10)[0] == 512  # size_compressed
    assert struct.unpack_from("<I", b, 0x60)[0] == 1  # blocks
    assert struct.unpack_from("<i", b, 0x64)[0] == 42  # db[0]
    assert struct.unpack_from("<i", b, 0x64 + 12 * 4)[0] == 99


def assert_inode_s32_size() -> None:
    """S32 signed inode serialization must produce exactly INODE_S32_SIZE bytes."""
    ino: Inode = Inode(
        number=1,
        mode=0x81A9,
        nlink=1,
        flags=0,
        size=0,
        size_compressed=0,
        blocks=1,
    )
    b: bytes = ino.to_bytes_signed32()
    assert len(b) == c.INODE_S32_SIZE


def assert_inode_s32_db_layout() -> None:
    """In S32 layout: each db entry is 32-byte sig + 4-byte block pointer.

    db[0] starts at 0x64: sig at 0x64..0x83, block at 0x84.
    """
    ino: Inode = Inode(
        number=1,
        mode=0x8000,
        nlink=1,
        flags=0,
        size=0,
        size_compressed=0,
        blocks=1,
    )
    ino.db[0] = 55
    b: bytes = ino.to_bytes_signed32()
    # sig at 0x64 (32 bytes of zeros)
    assert b[0x64 : 0x64 + 32] == b"\x00" * 32
    # block pointer at 0x64 + 32 = 0x84
    assert struct.unpack_from("<i", b, 0x84)[0] == 55


def assert_inode_s32_ib_layout() -> None:
    """In S32 layout: indirect blocks follow direct blocks."""
    ino: Inode = Inode(
        number=1,
        mode=0x8000,
        nlink=1,
        flags=0,
        size=0,
        size_compressed=0,
        blocks=1,
    )
    # db takes up 12 entries * 36 bytes (sig + block) = 432 bytes
    # ib[0] starts at 0x64 + 432 = 0x1E0
    ino.ib[0] = 77
    b: bytes = ino.to_bytes_signed32()
    ib_offset: int = 0x64 + 12 * c.SIG_ENTRY_SIZE
    assert struct.unpack_from("<i", b, ib_offset + c.SIG_SIZE)[0] == 77


def assert_inode_s64_size() -> None:
    """S64 signed inode serialization must produce exactly INODE_S64_SIZE bytes."""
    ino: Inode = Inode(
        number=1,
        mode=0x81A9,
        nlink=1,
        flags=0,
        size=0,
        size_compressed=0,
        blocks=1,
    )
    b: bytes = ino.to_bytes_signed64()
    assert len(b) == c.INODE_S64_SIZE


def assert_inode_s64_db_layout() -> None:
    """In S64 layout: each db entry is 32-byte sig plus an 8-byte block pointer."""
    ino: Inode = Inode(
        number=1,
        mode=0x8000,
        nlink=1,
        flags=0,
        size=0,
        size_compressed=0,
        blocks=1,
    )
    ino.db[0] = 55
    b: bytes = ino.to_bytes_signed64()
    assert b[0x68 : 0x68 + 32] == b"\x00" * 32
    assert struct.unpack_from("<q", b, 0x68 + c.SIG_SIZE)[0] == 55


def assert_inode_s64_ib_layout() -> None:
    """In S64 layout: indirect blocks follow the 12 direct 40-byte entries."""
    ino: Inode = Inode(
        number=1,
        mode=0x8000,
        nlink=1,
        flags=0,
        size=0,
        size_compressed=0,
        blocks=1,
    )
    ino.ib[0] = 77
    b: bytes = ino.to_bytes_signed64()
    ib_offset: int = 0x68 + 12 * c.SIG_ENTRY_S64_SIZE
    assert struct.unpack_from("<q", b, ib_offset + c.SIG_SIZE)[0] == 77


def assert_parse_image_inode_s64_layout() -> None:
    """Parsing an S64 inode blob should preserve 64-bit pointer values."""
    ino: Inode = Inode(
        number=3,
        mode=0x8000,
        nlink=2,
        flags=0,
        size=123,
        size_compressed=123,
        blocks=2,
    )
    ino.db[0] = 0x1_0000_0001
    ino.ib[0] = 0x1_0000_0002
    parsed = pfs_mod.parse_image_inode(ino.to_bytes_signed64(), number=3, signed=True, inode_bits=64)
    assert parsed.blocks == 2
    assert parsed.db[0] == 0x1_0000_0001
    assert parsed.ib[0] == 0x1_0000_0002


def assert_parse_sig_record_block_s64_layout() -> None:
    """Parsing S64 signature-record blocks should read 64-bit block pointers."""
    block_size: int = 4096
    blocks: list[int] = [0x1_0000_0001, 0x1_0000_0002]
    blob: bytes = pfs_mod.make_sig_records_blob(blocks=blocks, block_size=block_size, inode_bits=64)
    fh: io.BytesIO = io.BytesIO(blob)
    records: list[tuple[bytes, int]] = pfs_mod.parse_sig_record_block(
        fh=fh, block_num=0, inode_bits=64, block_size=block_size
    )
    assert records[0][1] == blocks[0]
    assert records[1][1] == blocks[1]


def assert_parse_image_header_field_offsets() -> None:
    """Build a minimal 0x400-byte header blob with known values.

    Verify parse_image_header reads all fields from correct offsets
    matching legacy/ffpfs.py:parse_image_header.
    """
    hdr: bytearray = bytearray(0x400)
    struct.pack_into("<qq", hdr, 0x00, 1, 20130315)  # version=1, magic
    struct.pack_into("<B", hdr, 0x1A, 1)  # readonly=1
    struct.pack_into("<H", hdr, 0x1C, 0x8)  # mode=case-insensitive
    struct.pack_into("<I", hdr, 0x20, 65536)  # block_size
    struct.pack_into("<q", hdr, 0x28, 100)  # nblock
    struct.pack_into("<q", hdr, 0x30, 50)  # dinode_count
    struct.pack_into("<q", hdr, 0x38, 200)  # ndblock
    struct.pack_into("<q", hdr, 0x40, 2)  # dinode_block_count
    seed_val: bytes = bytes(range(16))
    hdr[0x370:0x380] = seed_val

    fh: io.BytesIO = io.BytesIO(bytes(hdr))
    h = parse_image_header(fh)
    assert h.version == 1
    assert h.magic == 20130315
    assert h.readonly == 1
    assert h.mode == 0x8
    assert h.block_size == 65536
    assert h.nblock == 100
    assert h.dinode_count == 50
    assert h.ndblock == 200
    assert h.dinode_block_count == 2
    assert h.seed == seed_val


def _make_inode(
    number: int = 0,
    mode: int = 0,
    nlink: int = 1,
    flags: int = 0,
    blocks: int = 1,
) -> Inode:
    """Helper to create a minimal Inode for testing."""
    return Inode(
        number=number,
        mode=mode,
        nlink=nlink,
        flags=flags,
        size=0,
        size_compressed=0,
        blocks=blocks,
    )


def assert_inode_number_at_uint32_max_passes() -> None:
    """Legacy: 0 <= ino.number <= UINT32_MAX."""
    ino: Inode = _make_inode(number=c.UINT32_MAX)
    validate_d32_ranges([ino], final_ndblock=0)


def assert_inode_number_above_uint32_max_raises() -> None:
    """Inode number exceeding UINT32_MAX must raise."""
    ino: Inode = _make_inode(number=c.UINT32_MAX + 1)
    assert_raises_build_error(lambda: validate_d32_ranges([ino], final_ndblock=0))


def assert_inode_mode_at_uint16_max_passes() -> None:
    """Mode must fit in uint16."""
    ino: Inode = _make_inode(mode=0xFFFF)
    validate_d32_ranges([ino], final_ndblock=0)


def assert_inode_mode_above_uint16_max_raises() -> None:
    """Mode exceeding uint16 must raise."""
    ino: Inode = _make_inode(mode=0x10000)
    assert_raises_build_error(lambda: validate_d32_ranges([ino], final_ndblock=0))


def assert_inode_nlink_at_uint16_max_passes() -> None:
    """Nlink must fit in uint16."""
    ino: Inode = _make_inode(nlink=0xFFFF)
    validate_d32_ranges([ino], final_ndblock=0)


def assert_inode_nlink_above_uint16_max_raises() -> None:
    """Nlink exceeding uint16 must raise."""
    ino: Inode = _make_inode(nlink=0x10000)
    assert_raises_build_error(lambda: validate_d32_ranges([ino], final_ndblock=0))


def assert_inode_flags_at_uint32_max_passes() -> None:
    """Legacy: 0 <= ino.flags <= UINT32_MAX."""
    ino: Inode = _make_inode(flags=c.UINT32_MAX)
    validate_d32_ranges([ino], final_ndblock=0)


def assert_inode_flags_above_uint32_max_raises() -> None:
    """Flags exceeding UINT32_MAX must raise."""
    ino: Inode = _make_inode(flags=c.UINT32_MAX + 1)
    assert_raises_build_error(lambda: validate_d32_ranges([ino], final_ndblock=0))


def assert_inode_blocks_at_uint32_max_passes() -> None:
    """Legacy: 0 <= ino.blocks <= UINT32_MAX."""
    ino: Inode = _make_inode(blocks=c.UINT32_MAX)
    validate_d32_ranges([ino], final_ndblock=0)


def assert_inode_blocks_above_uint32_max_raises() -> None:
    """Blocks exceeding UINT32_MAX must raise."""
    ino: Inode = _make_inode(blocks=c.UINT32_MAX + 1)
    assert_raises_build_error(lambda: validate_d32_ranges([ino], final_ndblock=0))


def assert_final_ndblock_at_int32_max_passes() -> None:
    """Final ndblock must fit in int32."""
    ino: Inode = _make_inode()
    validate_d32_ranges([ino], final_ndblock=c.INT32_MAX)


def assert_final_ndblock_above_int32_max_raises() -> None:
    """Final ndblock exceeding INT32_MAX must raise."""
    ino: Inode = _make_inode()
    assert_raises_build_error(lambda: validate_d32_ranges([ino], final_ndblock=c.INT32_MAX + 1))


def assert_direct_block_pointer_at_int32_max_passes() -> None:
    """Direct block pointer must fit in signed int32."""
    ino: Inode = _make_inode()
    ino.db[0] = c.INT32_MAX
    validate_d32_ranges([ino], final_ndblock=0)


def assert_direct_block_pointer_at_minus_one_passes() -> None:
    """Direct block pointer -1 is the sentinel and must pass."""
    ino: Inode = _make_inode()
    ino.db[0] = -1
    validate_d32_ranges([ino], final_ndblock=0)


def assert_direct_block_pointer_above_int32_max_raises() -> None:
    """Direct block pointer exceeding INT32_MAX must raise."""
    ino: Inode = _make_inode()
    ino.db[0] = c.INT32_MAX + 1
    assert_raises_build_error(lambda: validate_d32_ranges([ino], final_ndblock=0))


def assert_direct_block_pointer_below_minus_one_raises() -> None:
    """Direct block pointer < -1 is invalid."""
    ino: Inode = _make_inode()
    ino.db[0] = -2
    assert_raises_build_error(lambda: validate_d32_ranges([ino], final_ndblock=0))


def assert_indirect_block_pointer_at_int32_max_passes() -> None:
    """Indirect block pointer must fit in signed int32."""
    ino: Inode = _make_inode()
    ino.ib[0] = c.INT32_MAX
    validate_d32_ranges([ino], final_ndblock=0)


def assert_indirect_block_pointer_at_minus_one_passes() -> None:
    """Indirect block pointer -1 is the sentinel and must pass."""
    ino: Inode = _make_inode()
    ino.ib[0] = -1
    validate_d32_ranges([ino], final_ndblock=0)


def assert_indirect_block_pointer_above_int32_max_raises() -> None:
    """Indirect block pointer exceeding INT32_MAX must raise."""
    ino: Inode = _make_inode()
    ino.ib[0] = c.INT32_MAX + 1
    assert_raises_build_error(lambda: validate_d32_ranges([ino], final_ndblock=0))


def assert_indirect_block_pointer_below_minus_one_raises() -> None:
    """Indirect block pointer < -1 is invalid."""
    ino: Inode = _make_inode()
    ino.ib[0] = -2
    assert_raises_build_error(lambda: validate_d32_ranges([ino], final_ndblock=0))


def assert_multiple_inodes_all_valid() -> None:
    """Multiple valid inodes must all pass."""
    inodes: list[Inode] = [
        _make_inode(number=1),
        _make_inode(number=2),
        _make_inode(number=3),
    ]
    validate_d32_ranges(inodes, final_ndblock=100)


def assert_multiple_inodes_one_invalid_raises() -> None:
    """If any inode is invalid, validation must raise."""
    inodes: list[Inode] = [
        _make_inode(number=1),
        _make_inode(number=c.UINT32_MAX + 1),
        _make_inode(number=3),
    ]
    assert_raises_build_error(lambda: validate_d32_ranges(inodes, final_ndblock=100))


def assert_scan_source_tree(tmp_path: Path) -> None:
    """Scan source tree returns expected directories, files, and total count."""
    root: Path = tmp_path / "src"
    root.mkdir()
    (root / "a").mkdir()
    (root / "a" / "file1.txt").write_text("x", encoding="utf-8")
    (root / "b").mkdir()
    (root / "b" / "file2.txt").write_text("y", encoding="utf-8")

    progress: Progress = Progress(enabled=False)
    dirs: dict[str, int]
    files: dict[str, int]
    total: int
    dirs, files, total = scan_source_tree(root, progress)
    assert total == 2
    assert "a/file1.txt" in files
    assert "b/file2.txt" in files
    assert "a" in dirs
    assert "b" in dirs


class TestDirentSerialization(PfsTestCase):
    """Tests for dirent serialization behavior and encoded sizes."""

    def test_file_dirent_matches_the_known_encoding_vector(self) -> None:
        """A file dirent should serialize to the expected known byte vector."""
        assert_dirent_to_bytes_known_vector()

    def test_current_directory_dirent_uses_the_expected_size(self) -> None:
        """A current-directory dirent should serialize to the expected aligned size."""
        assert_dirent_dot()

    def test_parent_directory_dirent_uses_the_expected_size(self) -> None:
        """A parent-directory dirent should serialize to the expected aligned size."""
        assert_dirent_dotdot()

    def test_subdirectory_dirent_serializes_with_directory_metadata(self) -> None:
        """A subdirectory dirent should serialize with the expected metadata layout."""
        assert_dirent_directory()


class TestInodeSerialization(PfsTestCase):
    """Tests for inode serialization helpers and header parsing offsets."""

    def test_d32_inode_serialization_uses_the_expected_size(self) -> None:
        """A D32 inode should serialize to the exact D32 structure size."""
        assert_inode_d32_size()

    def test_d32_inode_fields_serialize_at_the_expected_offsets(self) -> None:
        """A D32 inode should place key fields at the expected legacy offsets."""
        assert_inode_d32_field_layout()

    def test_s32_inode_serialization_uses_the_expected_size(self) -> None:
        """An S32 inode should serialize to the exact signed-32 structure size."""
        assert_inode_s32_size()

    def test_s32_inode_direct_blocks_follow_the_expected_layout(self) -> None:
        """An S32 inode should serialize direct-block signatures and pointers in order."""
        assert_inode_s32_db_layout()

    def test_s32_inode_indirect_blocks_follow_the_expected_layout(self) -> None:
        """An S32 inode should serialize indirect blocks after all direct blocks."""
        assert_inode_s32_ib_layout()

    def test_s64_inode_serialization_uses_the_expected_size(self) -> None:
        """An S64 inode should serialize to the exact signed-64 structure size."""
        assert_inode_s64_size()

    def test_s64_inode_direct_blocks_follow_the_expected_layout(self) -> None:
        """An S64 inode should serialize direct-block signatures and 64-bit pointers in order."""
        assert_inode_s64_db_layout()

    def test_s64_inode_indirect_blocks_follow_the_expected_layout(self) -> None:
        """An S64 inode should serialize indirect blocks after all direct blocks."""
        assert_inode_s64_ib_layout()

    def test_s64_inode_parser_reads_64_bit_block_pointers(self) -> None:
        """The S64 parser should preserve 64-bit direct and indirect block pointers."""
        assert_parse_image_inode_s64_layout()

    def test_s64_signature_record_parser_reads_64_bit_block_numbers(self) -> None:
        """S64 signature-record parsing should use the 64-bit block entry width."""
        assert_parse_sig_record_block_s64_layout()

    def test_image_header_parser_reads_known_offsets_correctly(self) -> None:
        """The image header parser should read key fields from their known offsets."""
        assert_parse_image_header_field_offsets()


class TestD32RangeValidation(PfsTestCase):
    """Tests for D32 inode range validation boundaries and error cases."""

    def test_inode_number_accepts_the_uint32_upper_bound(self) -> None:
        """The inode number validator should accept the UINT32 upper bound."""
        assert_inode_number_at_uint32_max_passes()

    def test_inode_number_rejects_values_above_uint32(self) -> None:
        """The inode number validator should reject values above UINT32."""
        assert_inode_number_above_uint32_max_raises()

    def test_inode_mode_accepts_the_uint16_upper_bound(self) -> None:
        """The inode mode validator should accept the UINT16 upper bound."""
        assert_inode_mode_at_uint16_max_passes()

    def test_inode_mode_rejects_values_above_uint16(self) -> None:
        """The inode mode validator should reject values above UINT16."""
        assert_inode_mode_above_uint16_max_raises()

    def test_inode_nlink_accepts_the_uint16_upper_bound(self) -> None:
        """The inode nlink validator should accept the UINT16 upper bound."""
        assert_inode_nlink_at_uint16_max_passes()

    def test_inode_nlink_rejects_values_above_uint16(self) -> None:
        """The inode nlink validator should reject values above UINT16."""
        assert_inode_nlink_above_uint16_max_raises()

    def test_inode_flags_accept_the_uint32_upper_bound(self) -> None:
        """The inode flags validator should accept the UINT32 upper bound."""
        assert_inode_flags_at_uint32_max_passes()

    def test_inode_flags_reject_values_above_uint32(self) -> None:
        """The inode flags validator should reject values above UINT32."""
        assert_inode_flags_above_uint32_max_raises()

    def test_inode_blocks_accept_the_uint32_upper_bound(self) -> None:
        """The inode blocks validator should accept the UINT32 upper bound."""
        assert_inode_blocks_at_uint32_max_passes()

    def test_inode_blocks_reject_values_above_uint32(self) -> None:
        """The inode blocks validator should reject values above UINT32."""
        assert_inode_blocks_above_uint32_max_raises()

    def test_final_ndblock_accepts_the_int32_upper_bound(self) -> None:
        """The final ndblock validator should accept the INT32 upper bound."""
        assert_final_ndblock_at_int32_max_passes()

    def test_final_ndblock_rejects_values_above_int32(self) -> None:
        """The final ndblock validator should reject values above INT32."""
        assert_final_ndblock_above_int32_max_raises()

    def test_direct_block_pointer_accepts_the_int32_upper_bound(self) -> None:
        """The direct block pointer validator should accept the INT32 upper bound."""
        assert_direct_block_pointer_at_int32_max_passes()

    def test_direct_block_pointer_accepts_the_negative_one_sentinel(self) -> None:
        """The direct block pointer validator should accept the -1 sentinel."""
        assert_direct_block_pointer_at_minus_one_passes()

    def test_direct_block_pointer_rejects_values_above_int32(self) -> None:
        """The direct block pointer validator should reject values above INT32."""
        assert_direct_block_pointer_above_int32_max_raises()

    def test_direct_block_pointer_rejects_values_below_negative_one(self) -> None:
        """The direct block pointer validator should reject values below -1."""
        assert_direct_block_pointer_below_minus_one_raises()

    def test_indirect_block_pointer_accepts_the_int32_upper_bound(self) -> None:
        """The indirect block pointer validator should accept the INT32 upper bound."""
        assert_indirect_block_pointer_at_int32_max_passes()

    def test_indirect_block_pointer_accepts_the_negative_one_sentinel(self) -> None:
        """The indirect block pointer validator should accept the -1 sentinel."""
        assert_indirect_block_pointer_at_minus_one_passes()

    def test_indirect_block_pointer_rejects_values_above_int32(self) -> None:
        """The indirect block pointer validator should reject values above INT32."""
        assert_indirect_block_pointer_above_int32_max_raises()

    def test_indirect_block_pointer_rejects_values_below_negative_one(self) -> None:
        """The indirect block pointer validator should reject values below -1."""
        assert_indirect_block_pointer_below_minus_one_raises()

    def test_multiple_valid_inodes_pass_validation(self) -> None:
        """The D32 validator should accept a list of valid inodes."""
        assert_multiple_inodes_all_valid()

    def test_a_single_invalid_inode_fails_validation(self) -> None:
        """The D32 validator should fail when any inode in the list is invalid."""
        assert_multiple_inodes_one_invalid_raises()


class TestSourceTreeScanning(PfsTestCase):
    """Tests for source-tree scanning helpers used during image building."""

    def test_scan_source_tree_returns_expected_directory_and_file_maps(self) -> None:
        """Scanning a small source tree should return the expected files, directories, and count."""
        assert_scan_source_tree(self.make_temp_path())

    def test_auto_fit_block_size_prefers_small_blocks_for_small_files(self) -> None:
        """Auto-fit block-size selection should minimize estimated file-data footprint."""
        tmp_path: Path = self.make_temp_path()
        src: Path = tmp_path / "src"
        src.mkdir()
        for idx in range(10):
            (src / f"small_{idx}.bin").write_bytes(b"x" * 100)

        assert pfs_mod.choose_auto_fit_block_size(src) == 4096
