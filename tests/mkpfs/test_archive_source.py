from __future__ import annotations

import io
import json
import os
import shutil
import subprocess
import tempfile
import unittest
import unittest.mock
import zipfile
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

from mkpfs import archive_source
from mkpfs.ampr import AMPR_INDEX_NAME, build_ampr_index
from mkpfs.archive_source import (
    ArchiveError,
    ArchiveSource,
    is_archive_path,
    parse_unrar_listing,
    prepare_archive_subtree,
)
from mkpfs.cli import cli_mkpfs_main
from mkpfs.exfat_writer import iter_exfat_image
from mkpfs.pfs import BuildError

_FIXED_MTIME: int = 1_700_000_000  # even seconds: ZIP timestamps have 2 s resolution


class ArchiveSourceTestCase(unittest.TestCase):
    """Shared helpers: a representative game tree and a ZIP holding it."""

    def make_temp_path(self) -> Path:
        temp_dir: tempfile.TemporaryDirectory[str] = tempfile.TemporaryDirectory()
        self.addCleanup(temp_dir.cleanup)
        return Path(temp_dir.name)

    def build_game_tree(self, root: Path, *, title_id: str = "PPSA12345", apr_emu: bool = False) -> dict[str, bytes]:
        """Create a small game tree and return its expected (packed) files."""
        files: dict[str, bytes] = {
            "sce_sys/param.json": json.dumps(
                {"titleId": title_id, "contentId": f"UP0000-{title_id}_00-TEST"}
            ).encode(),
            "eboot.bin": b"BOOT" * 1000,
            "data/big.pak": bytes(range(256)) * 12_000,  # ~3 MiB, spans many clusters
            "data/sub/small.txt": b"hello archive",
            "data/empty.dat": b"",
        }
        if apr_emu:
            files["fakelib/libSceAmpr.sprx"] = b"\x7fELF-fake"
        for rel, data in files.items():
            target: Path = root / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(data)
            os.utime(target, (_FIXED_MTIME, _FIXED_MTIME))
        # OS metadata that must never be packed.
        (root / ".DS_Store").write_bytes(b"junk")
        (root / "data" / "Thumbs.db").write_bytes(b"junk")
        return files

    def zip_tree(self, root: Path, archive: Path, *, top: str = "GAME-app") -> Path:
        """Zip ``root`` under a top-level folder, the way release archives are laid out."""
        with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED) as zf:
            for path in sorted(root.rglob("*")):
                rel: str = path.relative_to(root).as_posix()
                if path.is_dir():
                    zf.write(path, f"{top}/{rel}/")
                else:
                    zf.write(path, f"{top}/{rel}")
        return archive


class TestArchiveDetection(ArchiveSourceTestCase):
    def test_is_archive_path(self) -> None:
        tmp = self.make_temp_path()
        for name in ("a.rar", "b.ZIP", "c.part1.rar", "d.r00"):
            (tmp / name).write_bytes(b"")
            self.assertTrue(is_archive_path(tmp / name), name)
        (tmp / "e.exfat").write_bytes(b"")
        self.assertFalse(is_archive_path(tmp / "e.exfat"))
        self.assertFalse(is_archive_path(tmp))  # directories are never archives
        self.assertFalse(is_archive_path(tmp / "missing.rar"))


class TestRarArguments(unittest.TestCase):
    def test_member_argument_uses_platform_separator(self) -> None:
        self.assertEqual(archive_source.rar_member_argument("a/b/c.bin", windows=False), "a/b/c.bin")
        self.assertEqual(archive_source.rar_member_argument("a/b/c.bin", windows=True), "a\\b\\c.bin")

    def test_listing_requests_all_volumes(self) -> None:
        seen: list[list[str]] = []

        def fake_run(argv: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
            seen.append(argv)
            return subprocess.CompletedProcess(
                argv, 0, stdout="Details: RAR 5\n\n        Name: x.bin\n        Size: 1\n", stderr=""
            )

        with (
            unittest.mock.patch.object(archive_source.subprocess, "run", fake_run),
            unittest.mock.patch.object(archive_source, "unrar_executable", lambda: "unrar"),
        ):
            entries, _solid, _encrypted = archive_source._list_rar(Path("set.part1.rar"), None)
        self.assertEqual([e.rel_path for e in entries], ["x.bin"])
        self.assertIn("-v", seen[0])
        self.assertEqual(seen[0][1], "lt")


class TestZipSource(ArchiveSourceTestCase):
    def test_listing_game_roots_and_streaming(self) -> None:
        tmp = self.make_temp_path()
        src = tmp / "src"
        src.mkdir()
        expected = self.build_game_tree(src)
        archive = self.zip_tree(src, tmp / "game.zip")

        source = ArchiveSource(archive)
        self.assertEqual(source.kind, "zip")
        self.assertFalse(source.encrypted)
        self.assertEqual(source.game_roots(), ["GAME-app"])

        subtree = source.subtree("GAME-app")
        packed = {e.rel_path for e in subtree.entries() if not e.is_dir}
        self.assertEqual(packed, set(expected))  # OS metadata excluded, nothing else lost
        self.assertEqual(subtree.title_id(), "PPSA12345")
        self.assertEqual(subtree.image_basename(), "PPSA12345")
        self.assertEqual(subtree.total_size(), sum(len(v) for v in expected.values()))
        for rel, data in expected.items():
            with subtree.open(rel) as fh:
                self.assertEqual(fh.read(), data, rel)
        self.assertEqual(subtree.read_bytes("data/sub/small.txt"), b"hello archive")
        with self.assertRaises(ArchiveError):
            source.open("GAME-app/data")  # a directory is not readable
        with self.assertRaises(ArchiveError):
            source.subtree("nope")

    def test_exfat_stream_identical_to_folder(self) -> None:
        """The exFAT image built from the archive must equal the one built from the folder."""
        tmp = self.make_temp_path()
        src = tmp / "src"
        src.mkdir()
        self.build_game_tree(src)
        archive = self.zip_tree(src, tmp / "game.zip")

        from_folder: bytes = b"".join(iter_exfat_image(src))
        from_archive: bytes = b"".join(iter_exfat_image(ArchiveSource(archive).subtree("GAME-app")))
        self.assertEqual(len(from_folder), len(from_archive))
        self.assertEqual(from_folder, from_archive)

    def test_prepare_generates_matching_ampr_index(self) -> None:
        tmp = self.make_temp_path()
        src = tmp / "src"
        src.mkdir()
        self.build_game_tree(src, apr_emu=True)
        archive = self.zip_tree(src, tmp / "game.zip")

        with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
            subtree = prepare_archive_subtree(archive)
        self.assertIn(AMPR_INDEX_NAME, subtree.extra_files)
        self.assertTrue(subtree.has_file(AMPR_INDEX_NAME))

        # The folder workflow writes the same index for the same sizes/mtimes/paths.
        index_path: Path = tmp / "folder.index"
        count: int = build_ampr_index(src, index_path)
        self.assertEqual(count, 6)
        self.assertEqual(subtree.extra_files[AMPR_INDEX_NAME], index_path.read_bytes())

        # And the in-memory member is served like any other file.
        with subtree.open(AMPR_INDEX_NAME) as fh:
            self.assertEqual(fh.read(), index_path.read_bytes())
        packed = {e.rel_path for e in subtree.entries() if not e.is_dir}
        self.assertIn(AMPR_INDEX_NAME, packed)

    def test_prepare_without_ampr_flag_adds_nothing(self) -> None:
        tmp = self.make_temp_path()
        src = tmp / "src"
        src.mkdir()
        self.build_game_tree(src, apr_emu=True)
        archive = self.zip_tree(src, tmp / "game.zip")
        with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
            subtree = prepare_archive_subtree(archive, ampr_index=False)
        self.assertEqual(subtree.extra_files, {})

    def test_multiple_game_roots_require_selection(self) -> None:
        tmp = self.make_temp_path()
        a = tmp / "a"
        b = tmp / "b"
        a.mkdir()
        b.mkdir()
        self.build_game_tree(a, title_id="PPSA00001")
        self.build_game_tree(b, title_id="PPSA00002")
        archive = tmp / "two.zip"
        with zipfile.ZipFile(archive, "w") as zf:
            for root, top in ((a, "ONE-app"), (b, "TWO-app")):
                for path in sorted(root.rglob("*")):
                    if path.is_file():
                        zf.write(path, f"{top}/{path.relative_to(root).as_posix()}")
        source = ArchiveSource(archive)
        self.assertEqual(source.game_roots(), ["ONE-app", "TWO-app"])
        with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
            with self.assertRaises(ArchiveError):
                prepare_archive_subtree(archive)
            chosen = prepare_archive_subtree(archive, archive_root="TWO-app")
        self.assertEqual(chosen.title_id(), "PPSA00002")

    def test_archive_without_game_uses_root(self) -> None:
        tmp = self.make_temp_path()
        archive = tmp / "plain.zip"
        with zipfile.ZipFile(archive, "w") as zf:
            zf.writestr("readme.txt", "no game here")
        with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
            subtree = prepare_archive_subtree(archive)
        self.assertEqual(subtree.prefix, "")
        self.assertEqual(subtree.image_basename(), "plain")

    def test_unsupported_and_broken_inputs(self) -> None:
        tmp = self.make_temp_path()
        bogus = tmp / "x.zip"
        bogus.write_bytes(b"not a zip")
        with self.assertRaises(ArchiveError):
            ArchiveSource(bogus)
        other = tmp / "x.7z"
        other.write_bytes(b"")
        with self.assertRaises(ArchiveError):
            ArchiveSource(other)


class TestEncryptedZip(ArchiveSourceTestCase):
    """AES ZIP round trip; needs pyzipper to create the archive."""

    def setUp(self) -> None:
        try:
            import pyzipper  # type: ignore[import-not-found]  # ruff: ignore[unused-import]
        except ImportError:
            self.skipTest("pyzipper not installed")

    def test_password_required_and_checked(self) -> None:
        import pyzipper  # type: ignore[import-not-found]

        tmp = self.make_temp_path()
        archive = tmp / "secret.zip"
        with pyzipper.AESZipFile(archive, "w", compression=pyzipper.ZIP_DEFLATED, encryption=pyzipper.WZ_AES) as zf:
            zf.setpassword(b"hunter2")
            zf.writestr("GAME-app/sce_sys/param.json", json.dumps({"titleId": "PPSA77777"}))
            zf.writestr("GAME-app/eboot.bin", b"BOOT")
        with self.assertRaises(ArchiveError):
            ArchiveSource(archive)
        with self.assertRaises(ArchiveError):
            ArchiveSource(archive, password="wrong")
        source = ArchiveSource(archive, password="hunter2")
        self.assertTrue(source.encrypted)
        self.assertEqual(source.subtree("GAME-app").title_id(), "PPSA77777")


class TestUnrarListingParser(unittest.TestCase):
    def test_parse_rar5_listing(self) -> None:
        text = """
UNRAR 7.00 freeware      Copyright (c) 1993-2024 Alexander Roshal

Archive: /tmp/Game.part1.rar
Details: RAR 5, volume, solid

        Name: GAME-app/sce_sys/param.json
        Type: File
        Size: 120
 Packed size: 90
       Ratio: 75%
       mtime: 2025-09-24 03:36:58,651621100
  Attributes: ..A....
       CRC32: D4879F86
     Host OS: Windows
 Compression: RAR 5.0(v50) -m3 -md=32m

        Name: GAME-app/data/big.pak
        Type: File
        Size: 5000000
 Packed size: 2000000
       Ratio: 40%
       mtime: 2025-09-24 03:36:58,000000000
  Attributes: ..A....
       Flags: split_after
     Host OS: Windows
 Compression: RAR 5.0(v50) -m3 -md=32m

        Name: GAME-app/data/big.pak
        Type: File
        Size: 5000000
 Packed size: 3000000
       Ratio: 60%
       mtime: 2025-09-24 03:36:58,000000000
  Attributes: ..A....
       Flags: split_before, encrypted
     Host OS: Windows
 Compression: RAR 5.0(v50) -m3 -md=32m

        Name: GAME-app
        Type: Directory
       mtime: 2025-09-24 17:22:10,000000000
  Attributes: ...D...
     Host OS: Windows
"""
        entries, solid, encrypted = parse_unrar_listing(text)
        self.assertTrue(solid)
        self.assertTrue(encrypted)
        by_path = {e.rel_path: e for e in entries}
        self.assertEqual(set(by_path), {"GAME-app/sce_sys/param.json", "GAME-app/data/big.pak", "GAME-app"})
        self.assertEqual(by_path["GAME-app/data/big.pak"].size, 5_000_000)  # split volumes collapsed
        self.assertTrue(by_path["GAME-app"].is_dir)
        self.assertEqual(by_path["GAME-app"].size, 0)
        self.assertGreater(by_path["GAME-app/sce_sys/param.json"].mtime, 0)


@unittest.skipUnless(os.environ.get("MKPFS_TEST_RAR") and archive_source.unrar_executable(), "set MKPFS_TEST_RAR")
class TestRealRar(unittest.TestCase):
    """Opt-in smoke test against a real RAR named by ``MKPFS_TEST_RAR``."""

    def test_list_and_stream_smallest_member(self) -> None:
        source = ArchiveSource(Path(os.environ["MKPFS_TEST_RAR"]), password=os.environ.get("MKPFS_TEST_RAR_PASSWORD"))
        self.assertEqual(source.kind, "rar")
        files = sorted((e for e in source.files() if e.size > 0), key=lambda e: e.size)
        self.assertTrue(files)
        smallest = files[0]
        with source.open(smallest.rel_path) as fh:
            data: bytes = fh.read()
        self.assertEqual(len(data), smallest.size)


class TestCliArchivePack(ArchiveSourceTestCase):
    def _run(self, argv: list[str]) -> tuple[int, str]:
        out = io.StringIO()
        err = io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code: int = cli_mkpfs_main(argv)
        return code, out.getvalue() + err.getvalue()

    def test_pack_folder_from_zip_round_trips(self) -> None:
        tmp = self.make_temp_path()
        src = tmp / "src"
        src.mkdir()
        expected = self.build_game_tree(src, apr_emu=True)
        archive = self.zip_tree(src, tmp / "game.zip")
        output = tmp / "out" / "game.ffpfsc"

        code, text = self._run(["pack", "folder", str(archive), str(output), "--cpu-count", "1"])
        self.assertEqual(code, 0, text)
        self.assertTrue(output.is_file())
        self.assertIn("no temp image", text)  # streamed straight from the archive

        unpacked = tmp / "unpacked"
        code, text = self._run(["unpack", "--deep", str(output), str(unpacked)])
        self.assertEqual(code, 0, text)
        for rel, data in expected.items():
            self.assertEqual((unpacked / rel).read_bytes(), data, rel)
        self.assertTrue((unpacked / AMPR_INDEX_NAME).is_file())
        self.assertFalse((unpacked / ".DS_Store").exists())
        self.assertFalse((unpacked / "data" / "Thumbs.db").exists())

    def test_dry_run_and_errors(self) -> None:
        tmp = self.make_temp_path()
        src = tmp / "src"
        src.mkdir()
        self.build_game_tree(src)
        archive = self.zip_tree(src, tmp / "game.zip")
        output = tmp / "game.ffpfsc"

        code, text = self._run(["pack", "folder", str(archive), str(output), "--dry-run"])
        self.assertEqual(code, 0, text)
        self.assertFalse(output.exists())
        self.assertIn("Dry run", text)

        # Invalid combinations surface as BuildError, like the rest of the pack CLI.
        with self.assertRaises(BuildError) as raw_ctx:
            self._run(["pack", "folder", str(archive), str(output), "--raw"])
        self.assertIn("--raw", str(raw_ctx.exception))

        with self.assertRaises(BuildError):
            self._run(["pack", "folder", str(archive), str(output), "--archive-root", "missing"])

    def test_batch_discovers_archives(self) -> None:
        from mkpfs.batch import discover_batch_items

        tmp = self.make_temp_path()
        src = tmp / "src"
        src.mkdir()
        self.build_game_tree(src)
        self.zip_tree(src, tmp / "Alpha.zip")
        (tmp / "Beta.part1.rar").write_bytes(b"")
        (tmp / "Beta.part2.rar").write_bytes(b"")
        (tmp / "Gamma.r00").write_bytes(b"")
        (tmp / "notes.txt").write_bytes(b"")
        shutil.copytree(src, tmp / "Delta-app")

        items = discover_batch_items(tmp)
        kinds = {item.name: item.kind for item in items}
        self.assertEqual(kinds, {"Alpha": "archive", "Beta": "archive", "Delta-app": "folder", "src": "folder"})
