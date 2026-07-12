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

    def test_run_batch_handles_plain_exception(self) -> None:
        """A plain RuntimeError on the first item is recorded as an error and the batch continues."""
        src = self._make_temp_dir()
        (src / "Good").mkdir()
        (src / "Good" / "f.txt").write_text("ok")
        (src / "Bad").mkdir()
        (src / "Bad" / "f.txt").write_text("trouble")

        out = self._make_temp_dir()

        call_count = 0

        def raising_build(**kw: object) -> BuildStats:
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                # "Bad" sorts before "Good" → first call raises a plain RuntimeError
                raise RuntimeError("unexpected crash")
            return _mock_build(Path(str(kw["output_path"])), 1000, 800)

        with patch(
            "mkpfs.pfs.build_pfs_stream_from_exfat",
            side_effect=raising_build,
        ):
            summary = run_batch(
                source_dir=src,
                output_dir=out,
                pack_flags=self._default_pack_flags(),
            )

        self.assertEqual(summary.errors, 1)
        self.assertEqual(summary.converted, 1)
        self.assertEqual(summary.total_items, 2)

    def test__estimate_raw_size_file_kind_returns_file_size(self) -> None:
        """For items with kind 'file', _estimate_raw_size must return the file's st_size."""
        import tempfile

        from mkpfs import batch as batch_module

        td = tempfile.TemporaryDirectory()
        self.addCleanup(td.cleanup)
        p = Path(td.name) / "image.exfat"
        data = b"X" * 1234
        p.write_bytes(data)

        item = batch_module.BatchItem(name="image.exfat", source=p, kind="file")
        size = batch_module._estimate_raw_size(item)
        self.assertEqual(size, p.stat().st_size)

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


class TestBatchReporting(unittest.TestCase):
    def test_print_batch_pre_stats_calls_info(self) -> None:
        import tempfile

        from mkpfs import batch as batch_module

        td = tempfile.TemporaryDirectory()
        self.addCleanup(td.cleanup)
        base = Path(td.name)
        src = base / "src"
        out = base / "out"
        src.mkdir()
        out.mkdir()

        items = [
            batch_module.BatchItem(name="GameA", source=src / "GameA", kind="folder"),
            batch_module.BatchItem(name="Image.exfat", source=src / "Image.exfat", kind="file"),
        ]
        pack_flags = {"pfs_version": 0x5000000, "cpu_count": 4, "compress": True, "zlib_level": 9}

        with patch("mkpfs.batch.info") as mock_info:
            batch_module.print_batch_pre_stats(source_dir=src, output_dir=out, items=items, pack_flags=pack_flags)

        called = " ".join(c.args[0] for c in mock_info.call_args_list)
        self.assertIn("Source", called)
        self.assertIn("Output", called)
        self.assertIn("Items", called)
        self.assertIn("Version", called)
        self.assertIn("Compress", called)

    def test_print_batch_pre_stats_no_compress_folders_only(self) -> None:
        """When --no-compress and only folder items, banner notes folders always compress."""
        import tempfile

        from mkpfs import batch as batch_module

        td = tempfile.TemporaryDirectory()
        self.addCleanup(td.cleanup)
        base = Path(td.name)
        src = base / "src"
        out = base / "out"
        src.mkdir()
        out.mkdir()

        items = [
            batch_module.BatchItem(name="GameA", source=src / "GameA", kind="folder"),
        ]
        pack_flags = {"pfs_version": 0x5000000, "cpu_count": 0, "compress": False, "zlib_level": 7}

        with patch("mkpfs.batch.info") as mock_info:
            batch_module.print_batch_pre_stats(source_dir=src, output_dir=out, items=items, pack_flags=pack_flags)

        called = " ".join(c.args[0] for c in mock_info.call_args_list)
        self.assertIn("folders always compressed", called)

    def test_print_batch_pre_stats_no_compress_mixed_items(self) -> None:
        """When --no-compress with both folders and files, banner shows mixed."""
        import tempfile

        from mkpfs import batch as batch_module

        td = tempfile.TemporaryDirectory()
        self.addCleanup(td.cleanup)
        base = Path(td.name)
        src = base / "src"
        out = base / "out"
        src.mkdir()
        out.mkdir()

        items = [
            batch_module.BatchItem(name="GameA", source=src / "GameA", kind="folder"),
            batch_module.BatchItem(name="Image.exfat", source=src / "Image.exfat", kind="file"),
        ]
        pack_flags = {"pfs_version": 0x5000000, "cpu_count": 0, "compress": False, "zlib_level": 7}

        with patch("mkpfs.batch.info") as mock_info:
            batch_module.print_batch_pre_stats(source_dir=src, output_dir=out, items=items, pack_flags=pack_flags)

        called = " ".join(c.args[0] for c in mock_info.call_args_list)
        self.assertIn("mixed", called)

    def test_print_batch_pre_stats_no_compress_files_only(self) -> None:
        """When --no-compress and only file items, banner shows 'no'."""
        import tempfile

        from mkpfs import batch as batch_module

        td = tempfile.TemporaryDirectory()
        self.addCleanup(td.cleanup)
        base = Path(td.name)
        src = base / "src"
        out = base / "out"
        src.mkdir()
        out.mkdir()

        items = [
            batch_module.BatchItem(name="Image.exfat", source=src / "Image.exfat", kind="file"),
        ]
        pack_flags = {"pfs_version": 0x5000000, "cpu_count": 0, "compress": False, "zlib_level": 7}

        with patch("mkpfs.batch.info") as mock_info:
            batch_module.print_batch_pre_stats(source_dir=src, output_dir=out, items=items, pack_flags=pack_flags)

        called = " ".join(c.args[0] for c in mock_info.call_args_list)
        self.assertIn("Compress: no", called)

    def test_print_item_status_variants_and_truncation(self) -> None:
        from mkpfs import batch as batch_module

        # Converted
        r_conv = batch_module.BatchItemResult(
            name="GameA",
            kind="folder",
            status="converted",
            output_path=Path("/out/GameA.ffpfsc"),
            raw_size=1000,
            compressed_size=800,
            elapsed_seconds=1.2,
        )

        # Skipped
        r_skip = batch_module.BatchItemResult(name="GameB", kind="folder", status="skipped")

        # Error with long message (to trigger truncation)
        long_msg = "E" * 200
        r_err = batch_module.BatchItemResult(name="GameC", kind="folder", status="error", error_message=long_msg)

        with patch("mkpfs.batch.info") as mock_info:
            batch_module.print_item_status(index=1, total=3, result=r_conv)
            batch_module.print_item_status(index=2, total=3, result=r_skip)
            batch_module.print_item_status(index=3, total=3, result=r_err)

        msgs = [c.args[0] for c in mock_info.call_args_list]
        combined = " ".join(msgs)
        self.assertIn("[1/3]", combined)
        self.assertIn("→", combined)
        # Savings percentage formatted
        self.assertIn("saved", combined)
        # Skipped text
        self.assertIn("skipped", combined)
        # Ensure long error got truncated (ends with '...')
        self.assertIn("...", combined)

    def test_print_batch_summary_outputs_table_and_rows(self) -> None:
        from mkpfs import batch as batch_module

        results = [
            batch_module.BatchItemResult(
                name="Short",
                kind="folder",
                status="converted",
                raw_size=1000,
                compressed_size=800,
            ),
            batch_module.BatchItemResult(
                name="SkippedLongNameExceedingTwentyChars",
                kind="folder",
                status="skipped",
                raw_size=500,
                compressed_size=400,
            ),
            batch_module.BatchItemResult(
                name="Planned",
                kind="folder",
                status="dry_run",
                raw_size=300,
                compressed_size=0,
            ),
            batch_module.BatchItemResult(name="Err", kind="folder", status="error", error_message="oops"),
        ]

        summary = batch_module.BatchSummary(results=results, elapsed_seconds=5.0)

        with patch("mkpfs.batch.info") as mock_info:
            batch_module.print_batch_summary(summary)

        called = " ".join(c.args[0] for c in mock_info.call_args_list)
        self.assertIn("Name", called)
        self.assertIn("Status", called)
        # All names should appear somewhere in the output
        for r in results:
            self.assertIn(r.name, called)
        # The totals row should include all status counts without overflowing
        self.assertIn("TOTALS", called)
        self.assertIn("1 done", called)
        self.assertIn("1 planned", called)
        self.assertIn("1 skipped", called)
        self.assertIn("1 error", called)

    def test_print_batch_summary_totals_inline_when_short(self) -> None:
        from mkpfs import batch as batch_module

        results = [
            batch_module.BatchItemResult(
                name="A", kind="folder", status="converted", raw_size=1000, compressed_size=800
            ),
            batch_module.BatchItemResult(name="B", kind="folder", status="skipped", raw_size=500, compressed_size=400),
        ]

        summary = batch_module.BatchSummary(results=results, elapsed_seconds=2.0)
        with patch("mkpfs.batch.info") as mock_info:
            batch_module.print_batch_summary(summary)

        called = " ".join(c.args[0] for c in mock_info.call_args_list)
        # Totals should appear inline (not on a separate line) for short totals_label
        self.assertIn("TOTALS (2 items)", called)
        self.assertIn("1 done, 1 skipped", called)

    def test_print_batch_summary_empty_returns_quietly(self) -> None:
        from mkpfs import batch as batch_module

        summary = batch_module.BatchSummary(results=[], elapsed_seconds=0.0)
        with patch("mkpfs.batch.info") as mock_info:
            batch_module.print_batch_summary(summary)
            mock_info.assert_not_called()
