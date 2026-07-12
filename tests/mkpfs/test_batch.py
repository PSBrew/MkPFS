"""Tests for mkpfs.batch — discovery, orchestration, and reporting."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from mkpfs.batch import (
    BatchItem,
    BatchItemResult,
    BatchSummary,
    _validate_batch_dirs,
    discover_batch_items,
    run_batch,
)
from mkpfs.pfs import BuildStats


def _mock_build(output_path: Path, uncompressed: int = 1000, stored: int = 800) -> BuildStats:
    """Side-effect that writes a tiny output file and returns BuildStats."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_bytes(b"\x00" * stored)
    return BuildStats(
        input_path=output_path,
        output_path=output_path,
        uncompressed_total_size=uncompressed,
        stored_total_size=stored,
    )


def _populate_source_dir(root: Path, *, with_exfat: bool = False) -> list[str]:
    """Create a few game folders inside *root* and return expected item names."""
    (root / "GameA" / "sce_sys").mkdir(parents=True)
    (root / "GameA" / "sce_sys" / "param.json").write_text('{"titleId":"TEST0001"}')
    (root / "GameA" / "eboot.bin").write_bytes(b"ELF_PAYLOAD")

    (root / "GameB").mkdir(parents=True)
    (root / "GameB" / "file.txt").write_text("hello world")

    (root / "GameC" / "data").mkdir(parents=True)
    (root / "GameC" / "data" / "chunk.bin").write_bytes(b"\x00" * 500)
    if with_exfat:
        (root / "Prebuilt.exfat").write_bytes(b"EXFAT_IMAGE" * 100)

    return ["GameA", "GameB", "GameC"] + (["Prebuilt.exfat"] if with_exfat else [])


# ---------------------------------------------------------------------------
# BatchItem & BatchItemResult
# ---------------------------------------------------------------------------


class TestBatchItem(unittest.TestCase):
    def test_batch_item_attributes(self) -> None:
        item = BatchItem(name="GameA", source=Path("/tmp/GameA"), kind="folder")
        self.assertEqual(item.name, "GameA")
        self.assertEqual(item.kind, "folder")

    def test_batch_item_file_kind(self) -> None:
        item = BatchItem(name="Prebuilt.exfat", source=Path("/tmp/Prebuilt.exfat"), kind="file")
        self.assertEqual(item.kind, "file")


class TestBatchItemResult(unittest.TestCase):
    def test_converted_result(self) -> None:
        r = BatchItemResult(
            name="GameA",
            kind="folder",
            status="converted",
            output_path=Path("/out/GameA.ffpfsc"),
            raw_size=1000,
            compressed_size=800,
            elapsed_seconds=2.5,
        )
        self.assertAlmostEqual(r.savings_pct, 20.0)

    def test_skipped_result_zero_raw_size(self) -> None:
        r = BatchItemResult(
            name="GameB",
            kind="folder",
            status="skipped",
            raw_size=0,
            compressed_size=0,
        )
        self.assertEqual(r.savings_pct, 0.0)

    def test_dry_run_result(self) -> None:
        r = BatchItemResult(
            name="GameC",
            kind="folder",
            status="dry_run",
            raw_size=500,
            compressed_size=0,
        )
        self.assertEqual(r.status, "dry_run")
        self.assertEqual(r.compressed_size, 0)

    def test_error_result(self) -> None:
        r = BatchItemResult(
            name="Crash",
            kind="folder",
            status="error",
            error_message="disk full",
        )
        self.assertEqual(r.status, "error")
        self.assertEqual(r.error_message, "disk full")


# ---------------------------------------------------------------------------
# BatchSummary
# ---------------------------------------------------------------------------


class TestBatchSummary(unittest.TestCase):
    def _summary(self, results: list[BatchItemResult]) -> BatchSummary:
        return BatchSummary(results=results, elapsed_seconds=10.0)

    def test_total_items(self) -> None:
        s = self._summary(
            [
                BatchItemResult("a", "folder", "converted"),
                BatchItemResult("b", "folder", "skipped"),
            ]
        )
        self.assertEqual(s.total_items, 2)

    def test_converted_skipped_errors_dry_run_counts(self) -> None:
        s = self._summary(
            [
                BatchItemResult("a", "folder", "converted"),
                BatchItemResult("b", "folder", "skipped"),
                BatchItemResult("c", "folder", "error"),
                BatchItemResult("d", "folder", "dry_run"),
                BatchItemResult("e", "folder", "converted"),
            ]
        )
        self.assertEqual(s.converted, 2)
        self.assertEqual(s.skipped, 1)
        self.assertEqual(s.errors, 1)
        self.assertEqual(s.dry_run, 1)

    def test_total_raw_and_compressed_size_exclude_dry_run(self) -> None:
        """dry_run items must not contribute to aggregate sizes."""
        s = self._summary(
            [
                BatchItemResult("a", "folder", "converted", raw_size=1000, compressed_size=800),
                BatchItemResult("b", "folder", "skipped", raw_size=500, compressed_size=400),
                BatchItemResult("c", "folder", "dry_run", raw_size=300, compressed_size=0),
            ]
        )
        self.assertEqual(s.total_raw_size, 1500)  # 1000 + 500
        self.assertEqual(s.total_compressed_size, 1200)  # 800 + 400

    def test_total_sizes_only_converted_and_skipped(self) -> None:
        """Error items also excluded from size aggregates."""
        s = self._summary(
            [
                BatchItemResult("a", "folder", "converted", raw_size=1000, compressed_size=800),
                BatchItemResult("b", "folder", "error", raw_size=0, compressed_size=0),
                BatchItemResult("c", "folder", "skipped", raw_size=500, compressed_size=400),
            ]
        )
        self.assertEqual(s.total_raw_size, 1500)
        self.assertEqual(s.total_compressed_size, 1200)

    def test_empty_summary(self) -> None:
        s = self._summary([])
        self.assertEqual(s.total_items, 0)
        self.assertEqual(s.converted, 0)
        self.assertEqual(s.skipped, 0)
        self.assertEqual(s.errors, 0)
        self.assertEqual(s.dry_run, 0)
        self.assertEqual(s.total_raw_size, 0)
        self.assertEqual(s.total_compressed_size, 0)


# ---------------------------------------------------------------------------
# Discovery
# ---------------------------------------------------------------------------


class TestDiscoverBatchItems(unittest.TestCase):
    def _make_temp_dir(self) -> Path:
        td = tempfile.TemporaryDirectory()
        self.addCleanup(td.cleanup)
        return Path(td.name)

    def test_discovers_folders(self) -> None:
        root = self._make_temp_dir()
        (root / "GameA").mkdir()
        (root / "GameB").mkdir()
        items = discover_batch_items(root)
        self.assertEqual(len(items), 2)
        self.assertTrue(all(i.kind == "folder" for i in items))

    def test_discovers_exfat_files(self) -> None:
        root = self._make_temp_dir()
        (root / "image.exfat").write_bytes(b"x")
        (root / "prebuilt.EXFAT").write_bytes(b"x")  # case-insensitive — base name differs
        items = discover_batch_items(root)
        self.assertEqual(len(items), 2)
        self.assertTrue(all(i.kind == "file" for i in items))

    def test_discovers_ffpkg_files(self) -> None:
        root = self._make_temp_dir()
        (root / "pkg.ffpkg").write_bytes(b"x")
        (root / "other.FFPKG").write_bytes(b"x")  # distinct base name to avoid APFS collision
        items = discover_batch_items(root)
        self.assertEqual(len(items), 2)
        self.assertTrue(all(i.kind == "file" for i in items))

    def test_skips_dotfiles(self) -> None:
        root = self._make_temp_dir()
        (root / ".hidden").mkdir()
        (root / ".gitignore").write_bytes(b"")
        (root / "GameA").mkdir()
        items = discover_batch_items(root)
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0].name, "GameA")

    def test_skips_ignored_names(self) -> None:
        root = self._make_temp_dir()
        (root / ".DS_Store").write_bytes(b"")
        (root / "Thumbs.db").write_bytes(b"")
        (root / "GameA").mkdir()
        items = discover_batch_items(root)
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0].name, "GameA")

    def test_skips_unknown_files(self) -> None:
        root = self._make_temp_dir()
        (root / "readme.txt").write_bytes(b"")
        (root / "notes.md").write_bytes(b"")
        (root / "GameA").mkdir()
        items = discover_batch_items(root)
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0].name, "GameA")

    def test_sorted_by_name_lowercase(self) -> None:
        root = self._make_temp_dir()
        (root / "Beta").mkdir()
        (root / "alpha").mkdir()
        (root / "Gamma").mkdir()
        items = discover_batch_items(root)
        names = [i.name for i in items]
        self.assertEqual(names, ["alpha", "Beta", "Gamma"])

    def test_empty_directory(self) -> None:
        root = self._make_temp_dir()
        items = discover_batch_items(root)
        self.assertEqual(items, [])


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------


class TestValidateBatchDirs(unittest.TestCase):
    def _make_temp_dir(self) -> Path:
        td = tempfile.TemporaryDirectory()
        self.addCleanup(td.cleanup)
        return Path(td.name)

    def test_valid_dirs(self) -> None:
        src = self._make_temp_dir()
        out = self._make_temp_dir()
        _validate_batch_dirs(source_dir=src, output_dir=out)  # no raise

    def test_missing_source(self) -> None:
        from mkpfs.pfs import BuildError

        src = Path("/nonexistent/path/12345")
        out = self._make_temp_dir()
        with self.assertRaises(BuildError) as ctx:
            _validate_batch_dirs(source_dir=src, output_dir=out)
        self.assertIn("does not exist", str(ctx.exception))

    def test_output_inside_source(self) -> None:
        from mkpfs.pfs import BuildError

        src = self._make_temp_dir()
        out = src / "sub"
        out.mkdir()
        with self.assertRaises(BuildError) as ctx:
            _validate_batch_dirs(source_dir=src, output_dir=out)
        self.assertIn("output directory cannot be inside", str(ctx.exception))


# ---------------------------------------------------------------------------
# Orchestration — run_batch
# ---------------------------------------------------------------------------


class TestRunBatch(unittest.TestCase):
    def _make_temp_dir(self) -> Path:
        td = tempfile.TemporaryDirectory()
        self.addCleanup(td.cleanup)
        return Path(td.name)

    def _default_pack_flags(self, **overrides: object) -> dict[str, object]:
        flags: dict[str, object] = {
            "block_size": 65536,
            "pfs_version": 0x5000000,
            "case_insensitive": True,
            "zlib_level": 7,
            "threshold_gain": 0.0,
            "cpu_count": 0,
            "compress": True,
            "min_file_gain": 0.0,
            "min_compress_size": 128,
            "verbose": False,
            "skip_executable_compression": False,
            "dry_run": False,
        }
        flags.update(overrides)
        return flags

    def test_run_batch_empty_source(self) -> None:
        src = self._make_temp_dir()
        out = self._make_temp_dir()
        summary = run_batch(
            source_dir=src,
            output_dir=out,
            pack_flags=self._default_pack_flags(),
        )
        self.assertEqual(summary.total_items, 0)
        self.assertEqual(summary.converted, 0)

    def test_run_batch_converts_items(self) -> None:
        src = self._make_temp_dir()
        _populate_source_dir(src)
        out = self._make_temp_dir()

        with patch(
            "mkpfs.pfs.build_pfs_stream_from_exfat",
            side_effect=lambda **kw: _mock_build(kw["output_path"], 1000, 800),
        ):
            summary = run_batch(
                source_dir=src,
                output_dir=out,
                pack_flags=self._default_pack_flags(),
            )

        self.assertEqual(summary.converted, 3)
        self.assertEqual(summary.skipped, 0)
        self.assertEqual(summary.errors, 0)
        self.assertEqual(summary.dry_run, 0)
        self.assertEqual(summary.total_raw_size, 3000)
        self.assertEqual(summary.total_compressed_size, 2400)
        for name in ("GameA", "GameB", "GameC"):
            self.assertTrue((out / f"{name}.ffpfsc").exists(), f"Expected {out / f'{name}.ffpfsc'} to exist")

    def test_run_batch_skips_existing_output(self) -> None:
        src = self._make_temp_dir()
        (src / "GameA").mkdir()
        (src / "GameA" / "f.txt").write_text("hi")
        out = self._make_temp_dir()
        (out / "GameA.ffpfsc").write_bytes(b"\x00" * 500)

        summary = run_batch(
            source_dir=src,
            output_dir=out,
            pack_flags=self._default_pack_flags(),
        )

        self.assertEqual(summary.converted, 0)
        self.assertEqual(summary.skipped, 1)
        self.assertEqual(summary.errors, 0)

    def test_run_batch_overwrite(self) -> None:
        src = self._make_temp_dir()
        (src / "GameA").mkdir()
        (src / "GameA" / "f.txt").write_text("hi")
        out = self._make_temp_dir()
        (out / "GameA.ffpfsc").write_bytes(b"\x00" * 500)

        with patch(
            "mkpfs.pfs.build_pfs_stream_from_exfat",
            side_effect=lambda **kw: _mock_build(kw["output_path"], 1000, 600),
        ):
            summary = run_batch(
                source_dir=src,
                output_dir=out,
                overwrite=True,
                pack_flags=self._default_pack_flags(),
            )

        self.assertEqual(summary.converted, 1)
        self.assertEqual(summary.skipped, 0)
        # Overwritten -> new compressed size, not old
        self.assertEqual(summary.total_compressed_size, 600)

    def test_run_batch_dry_run(self) -> None:
        """--dry-run: no files written, all items status='dry_run', summary excludes them."""
        src = self._make_temp_dir()
        (src / "GameA").mkdir()
        (src / "GameA" / "f.txt").write_text("data")
        (src / "GameB").mkdir()
        (src / "GameB" / "g.txt").write_text("more")
        out = self._make_temp_dir()

        summary = run_batch(
            source_dir=src,
            output_dir=out,
            pack_flags=self._default_pack_flags(dry_run=True),
        )

        # No .ffpfsc files written
        ffpfsc_files = list(out.glob("*.ffpfsc"))
        self.assertEqual(ffpfsc_files, [], "No .ffpfsc files should be created in dry-run mode")

        self.assertEqual(summary.converted, 0)
        self.assertEqual(summary.skipped, 0)
        self.assertEqual(summary.errors, 0)
        self.assertEqual(summary.dry_run, 2)
        self.assertEqual(summary.total_items, 2)

        for r in summary.results:
            self.assertEqual(r.status, "dry_run")

        # dry_run items excluded from size aggregates
        self.assertEqual(summary.total_raw_size, 0)
        self.assertEqual(summary.total_compressed_size, 0)

    def test_run_batch_mixed_skip_and_dry_run(self) -> None:
        """Pre-existing output + --dry-run: skipped items counted, dry_run excluded from sizes."""
        src = self._make_temp_dir()
        (src / "GameA").mkdir()
        (src / "GameA" / "f.txt").write_text("data")
        (src / "GameB").mkdir()
        (src / "GameB" / "g.txt").write_text("more")
        out = self._make_temp_dir()
        (out / "GameA.ffpfsc").write_bytes(b"\x00" * 500)

        summary = run_batch(
            source_dir=src,
            output_dir=out,
            pack_flags=self._default_pack_flags(dry_run=True),
        )

        self.assertEqual(summary.converted, 0)
        self.assertEqual(summary.skipped, 1)
        self.assertEqual(summary.dry_run, 1)
        self.assertEqual(summary.errors, 0)

        # Only skipped item contributes to sizes; dry_run excluded
        self.assertGreater(summary.total_raw_size, 0, "Skipped item raw size should be estimated")
        # compressed = existing file size (500 bytes), raw = _estimate_raw_size
        self.assertAlmostEqual(summary.total_compressed_size, 500)
        self.assertGreater(summary.total_raw_size, 0)

    def test_run_batch_error_resilience(self) -> None:
        """One failing item does not abort the batch; others still convert."""
        src = self._make_temp_dir()
        (src / "Good").mkdir()
        (src / "Good" / "f.txt").write_text("ok")
        (src / "Bad").mkdir()
        (src / "Bad" / "f.txt").write_text("trouble")

        out = self._make_temp_dir()

        call_count = 0

        def selective_build(**kw: object) -> BuildStats:
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                # Second alphabetically "Bad" comes first (B < G)
                from mkpfs.pfs import BuildError

                raise BuildError("simulated failure")
            return _mock_build(Path(str(kw["output_path"])), 1000, 800)

        with patch(
            "mkpfs.pfs.build_pfs_stream_from_exfat",
            side_effect=selective_build,
        ):
            summary = run_batch(
                source_dir=src,
                output_dir=out,
                pack_flags=self._default_pack_flags(),
            )

        self.assertEqual(summary.converted, 1)
        self.assertEqual(summary.errors, 1)
        self.assertEqual(summary.skipped, 0)
        # Only the converted item contributes to sizes
        self.assertEqual(summary.total_raw_size, 1000)
        self.assertEqual(summary.total_compressed_size, 800)

    def test_run_batch_converts_exfat_files(self) -> None:
        """File items (.exfat, .ffpkg) use build_pfs_stream_single_file."""
        src = self._make_temp_dir()
        (src / "Image.exfat").write_bytes(b"DISK" * 2000)
        (src / "Pkg.ffpkg").write_bytes(b"PKG" * 1000)
        out = self._make_temp_dir()
        with patch(
            "mkpfs.pfs.build_pfs_stream_single_file",
            side_effect=lambda **kw: _mock_build(Path(str(kw["output_path"])), 8000, 6000),
        ):
            summary = run_batch(
                source_dir=src,
                output_dir=out,
                pack_flags=self._default_pack_flags(),
            )

        self.assertEqual(summary.converted, 2)
        self.assertEqual(summary.errors, 0)
        self.assertTrue((out / "Image.exfat.ffpfsc").exists())
        self.assertTrue((out / "Pkg.ffpkg.ffpfsc").exists())

    def test_run_batch_output_inside_source_rejected(self) -> None:
        src = self._make_temp_dir()
        out = src / "sub"
        out.mkdir()

        from mkpfs.pfs import BuildError

        with self.assertRaises(BuildError):
            run_batch(
                source_dir=src,
                output_dir=out,
                pack_flags=self._default_pack_flags(),
            )
