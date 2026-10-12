from __future__ import annotations

import io
import json
import os
import shutil
import tempfile
import unittest
import zipfile
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from typing import ClassVar

from mkpfs.ampr import AMPR_INDEX_NAME, build_ampr_index
from mkpfs.archive_source import ArchiveError, ArchiveSource
from mkpfs.cli import cli_mkpfs_main
from mkpfs.exfat_writer import iter_exfat_image
from mkpfs.layered_source import (
    FolderLayer,
    LayeredSource,
    detect_layer_root,
    open_layer,
    parse_layer_spec,
    prepare_layered_source,
)
from mkpfs.pfs import BuildError

_FIXED_MTIME: int = 1_700_000_000


def _write_tree(root: Path, files: dict[str, bytes]) -> None:
    for rel, data in files.items():
        target: Path = root / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
        os.utime(target, (_FIXED_MTIME, _FIXED_MTIME))


def _zip_tree(files: dict[str, bytes], archive: Path, *, top: str) -> Path:
    with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        if top:
            zf.writestr(f"{top}/", "")
        for rel, data in files.items():
            name: str = f"{top}/{rel}" if top else rel
            zi = zipfile.ZipInfo(name, date_time=(2023, 11, 14, 22, 13, 20))
            zi.compress_type = zipfile.ZIP_DEFLATED
            zf.writestr(zi, data)
    return archive


def _overlay(*layers: dict[str, bytes]) -> dict[str, bytes]:
    merged: dict[str, bytes] = {}
    for layer in layers:
        merged.update(layer)
    return merged


class LayeredTestCase(unittest.TestCase):
    """A synthetic base game, an update, a backport and a DLC (nothing real)."""

    BASE: ClassVar[dict[str, bytes]] = {
        "sce_sys/param.json": json.dumps({"titleId": "PPSA12345", "contentVersion": "01.000.000"}).encode(),
        "eboot.bin": b"BASE-BOOT" * 500,
        "data/level1.pak": bytes(range(256)) * 8_000,
        "data/level2.pak": bytes(reversed(range(256))) * 4_000,
        "data/text/en.txt": b"hello",
        "data/empty.dat": b"",
    }
    UPDATE: ClassVar[dict[str, bytes]] = {
        "sce_sys/param.json": json.dumps({"titleId": "PPSA12345", "contentVersion": "01.050.000"}).encode(),
        "eboot.bin": b"UPDATE-BOOT" * 500,
        "data/level1.pak": b"patched-level" * 20_000,
        "data/level3.pak": b"new-level" * 10_000,
    }
    DLC: ClassVar[dict[str, bytes]] = {
        "data/dlc/outfit.pak": b"outfit" * 30_000,
        "data/dlc/map.pak": b"map" * 20_000,
        "readme.txt": b"dlc readme",
    }

    def make_temp_path(self) -> Path:
        temp_dir: tempfile.TemporaryDirectory[str] = tempfile.TemporaryDirectory()
        self.addCleanup(temp_dir.cleanup)
        return Path(temp_dir.name)

    def make_set(self, tmp: Path) -> tuple[Path, Path, Path]:
        """Return (base folder, update folder with a GAME-app subfolder, DLC zip with a GAME-app folder)."""
        base = tmp / "base"
        _write_tree(base, self.BASE)
        (base / ".DS_Store").write_bytes(b"junk")
        update = tmp / "update"
        _write_tree(update / "PPSA12345-app", self.UPDATE)
        (update / "release.nfo").write_bytes(b"notes")
        dlc = _zip_tree(self.DLC, tmp / "dlc.zip", top="PPSA12345-app")
        return base, update, dlc

    @staticmethod
    def files_of(source: LayeredSource) -> dict[str, bytes]:
        result: dict[str, bytes] = {}
        for entry in source.entries():
            if not entry.is_dir:
                with source.open(entry.rel_path) as fh:
                    result[entry.rel_path] = fh.read()
        return result


class TestLayerSpecs(unittest.TestCase):
    def test_parse_layer_spec(self) -> None:
        self.assertEqual(parse_layer_spec("/x/update"), (Path("/x/update"), None))
        self.assertEqual(parse_layer_spec("/x/update.zip::GAME-app"), (Path("/x/update.zip"), "GAME-app"))
        self.assertEqual(parse_layer_spec("/x/update.zip::"), (Path("/x/update.zip"), ""))
        self.assertEqual(parse_layer_spec(r"C:\games\u.rar::a\b"), (Path(r"C:\games\u.rar"), "a/b"))


class TestDetectLayerRoot(LayeredTestCase):
    def test_root_itself(self) -> None:
        tmp = self.make_temp_path()
        _write_tree(tmp, self.BASE)
        self.assertEqual(detect_layer_root(FolderLayer(tmp).entries()), "")

    def test_app_folder_and_markers(self) -> None:
        tmp = self.make_temp_path()
        _write_tree(tmp / "Release-GRP" / "PPSA12345-app", self.DLC)  # no eboot, found by its name
        self.assertEqual(detect_layer_root(FolderLayer(tmp).entries()), "Release-GRP/PPSA12345-app")
        other = self.make_temp_path()
        _write_tree(other / "patch", self.UPDATE)  # found by eboot.bin / sce_sys
        self.assertEqual(detect_layer_root(FolderLayer(other).entries()), "patch")

    def test_descends_single_folders_past_release_notes(self) -> None:
        tmp = self.make_temp_path()
        _write_tree(tmp / "Game.DLC-GRP" / "content", self.DLC)
        (tmp / "Game.DLC-GRP" / "grp.nfo").write_bytes(b"nfo")
        self.assertEqual(detect_layer_root(FolderLayer(tmp).entries()), "Game.DLC-GRP/content")
        (tmp / "Game.DLC-GRP" / "loose.bin").write_bytes(b"x")  # a real file stops the descent
        self.assertEqual(detect_layer_root(FolderLayer(tmp).entries()), "Game.DLC-GRP")

    def test_ambiguous_roots_raise(self) -> None:
        tmp = self.make_temp_path()
        _write_tree(tmp / "ONE-app", self.UPDATE)
        _write_tree(tmp / "TWO-app", self.UPDATE)
        with self.assertRaises(ArchiveError) as ctx:
            detect_layer_root(FolderLayer(tmp).entries())
        self.assertIn("::FOLDER", str(ctx.exception))
        self.assertEqual(open_layer(tmp, "TWO-app").path, tmp / "TWO-app")


class TestMerge(LayeredTestCase):
    def test_folder_over_folder(self) -> None:
        tmp = self.make_temp_path()
        base, update, _dlc = self.make_set(tmp)
        source = LayeredSource([FolderLayer(base), open_layer(update, None)])
        self.assertEqual(self.files_of(source), _overlay(self.BASE, self.UPDATE))
        self.assertEqual(source.layer_of("eboot.bin"), 1)  # replaced by the update
        self.assertEqual(source.layer_of("data/level2.pak"), 0)  # only in the base
        self.assertEqual(source.layer_of("data/level3.pak"), 1)  # only in the update
        self.assertIsNone(source.layer_of("release.nfo"))  # outside the update's game folder
        self.assertEqual(source.replaced, 3)  # param.json, eboot.bin, level1.pak
        self.assertEqual(source.title_id(), "PPSA12345")
        self.assertEqual(source.image_basename(), "PPSA12345")
        self.assertEqual(source.path, base)
        self.assertTrue(source.has_file("data/dlc/outfit.pak") is False)
        self.assertIn("1 layer", source.display())

    def test_folder_over_zip_and_zip_over_folder(self) -> None:
        tmp = self.make_temp_path()
        _base, update, dlc = self.make_set(tmp)
        base_zip = _zip_tree(self.BASE, tmp / "base.zip", top="GAME-app")
        source = LayeredSource(
            [ArchiveSource(base_zip).subtree("GAME-app"), open_layer(update, None), open_layer(dlc, None)]
        )
        self.assertEqual(self.files_of(source), _overlay(self.BASE, self.UPDATE, self.DLC))
        self.assertEqual(source.layer_of("data/dlc/map.pak"), 2)
        self.assertEqual(source.read_bytes("readme.txt"), b"dlc readme")
        with self.assertRaises(ArchiveError):
            source.open("data")  # a directory
        with self.assertRaises(ArchiveError):
            source.read_bytes("missing.bin")

    def test_directory_structure_is_merged(self) -> None:
        tmp = self.make_temp_path()
        base, _update, _dlc = self.make_set(tmp)
        extra = tmp / "extra"
        _write_tree(extra, {"data/text/fr.txt": b"bonjour", "data/sound/music.bank": b"la" * 100})
        source = LayeredSource([FolderLayer(base), FolderLayer(extra)])
        dirs = {e.rel_path for e in source.entries() if e.is_dir}
        self.assertEqual(dirs, {"sce_sys", "data", "data/text", "data/dlc", "data/sound"} - {"data/dlc"})
        files = self.files_of(source)
        self.assertEqual(files["data/text/en.txt"], b"hello")
        self.assertEqual(files["data/text/fr.txt"], b"bonjour")

    def test_file_replaces_directory_and_directory_replaces_file(self) -> None:
        tmp = self.make_temp_path()
        lower = tmp / "lower"
        _write_tree(lower, {"thing": b"file below", "pack/a.bin": b"a", "pack/sub/b.bin": b"b"})
        upper = tmp / "upper"
        _write_tree(upper, {"thing/inside.txt": b"now a folder", "pack": b"now a file"})
        source = LayeredSource([FolderLayer(lower), FolderLayer(upper)])
        files = self.files_of(source)
        self.assertEqual(files, {"thing/inside.txt": b"now a folder", "pack": b"now a file"})
        self.assertEqual(source.replaced, 3)  # thing, pack/a.bin, pack/sub/b.bin
        dirs = {e.rel_path for e in source.entries() if e.is_dir}
        self.assertEqual(dirs, {"thing"})

    def test_empty_layers_rejected(self) -> None:
        with self.assertRaises(ArchiveError):
            LayeredSource([])


class TestExfatAndAmpr(LayeredTestCase):
    def test_exfat_image_identical_to_merged_folder(self) -> None:
        """The image built from the layers must equal the one built from a hand-merged folder."""
        tmp = self.make_temp_path()
        base, update, dlc = self.make_set(tmp)
        merged_dir = tmp / "merged"
        shutil.copytree(base, merged_dir)
        shutil.copytree(update / "PPSA12345-app", merged_dir, dirs_exist_ok=True)
        with zipfile.ZipFile(dlc) as zf:
            for name in zf.namelist():
                if not name.endswith("/"):
                    target = merged_dir / name.split("/", 1)[1]
                    target.parent.mkdir(parents=True, exist_ok=True)
                    target.write_bytes(zf.read(name))
        for path in merged_dir.rglob("*"):
            os.utime(path, (_FIXED_MTIME, _FIXED_MTIME))
        (merged_dir / ".DS_Store").write_bytes(b"junk")

        with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
            source = prepare_layered_source(base, [str(update), str(dlc)])
        from_layers: bytes = b"".join(iter_exfat_image(source))
        from_folder: bytes = b"".join(iter_exfat_image(merged_dir))
        self.assertEqual(len(from_layers), len(from_folder))
        self.assertEqual(from_layers, from_folder)

    def test_ampr_index_generated_from_merged_listing(self) -> None:
        tmp = self.make_temp_path()
        base, update, dlc = self.make_set(tmp)
        _write_tree(base, {"fakelib/libSceAmpr.sprx": b"\x7fELF-fake", AMPR_INDEX_NAME: b"stale"})
        with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
            source = prepare_layered_source(base, [str(update), str(dlc)])
        self.assertIn(AMPR_INDEX_NAME, source.extra_files)
        self.assertNotEqual(source.read_bytes(AMPR_INDEX_NAME), b"stale")  # the stale index is replaced

        # Same index as the folder workflow would write for the hand-merged tree.
        merged_dir = tmp / "merged"
        shutil.copytree(base, merged_dir)
        (merged_dir / AMPR_INDEX_NAME).unlink()
        shutil.copytree(update / "PPSA12345-app", merged_dir, dirs_exist_ok=True)
        with zipfile.ZipFile(dlc) as zf:
            for name in zf.namelist():
                if not name.endswith("/"):
                    target = merged_dir / name.split("/", 1)[1]
                    target.parent.mkdir(parents=True, exist_ok=True)
                    target.write_bytes(zf.read(name))
                    os.utime(target, (1_700_000_000, 1_700_000_000))
        index_path = tmp / "folder.index"
        count: int = build_ampr_index(merged_dir, index_path)
        self.assertEqual(count, 11)
        self.assertEqual(source.extra_files[AMPR_INDEX_NAME], index_path.read_bytes())

    def test_ampr_disabled(self) -> None:
        tmp = self.make_temp_path()
        base, update, _dlc = self.make_set(tmp)
        _write_tree(base, {"fakelib/libSceAmpr.sprx": b"\x7fELF-fake"})
        with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
            source = prepare_layered_source(base, [str(update)], ampr_index=False)
        self.assertEqual(source.extra_files, {})


class TestCliLayeredPack(LayeredTestCase):
    def _run(self, argv: list[str]) -> tuple[int, str]:
        out = io.StringIO()
        err = io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code: int = cli_mkpfs_main(argv)
        return code, out.getvalue() + err.getvalue()

    def test_pack_folder_with_layers_round_trips(self) -> None:
        tmp = self.make_temp_path()
        base, update, dlc = self.make_set(tmp)
        _write_tree(base, {"fakelib/libSceAmpr.sprx": b"\x7fELF-fake"})
        output = tmp / "out" / "game.ffpfsc"
        code, text = self._run(
            [
                "pack",
                "folder",
                str(base),
                str(output),
                "--layer",
                str(update),
                "--layer",
                f"{dlc}::PPSA12345-app",
                "--cpu-count",
                "1",
            ]
        )
        self.assertEqual(code, 0, text)
        self.assertIn("Layer 2:", text)
        self.assertIn("Merged view:", text)
        self.assertFalse((base / AMPR_INDEX_NAME).exists())  # the source folder is never modified

        unpacked = tmp / "unpacked"
        code, text = self._run(["unpack", "--deep", str(output), str(unpacked)])
        self.assertEqual(code, 0, text)
        expected = _overlay(self.BASE, self.UPDATE, self.DLC)
        expected["fakelib/libSceAmpr.sprx"] = b"\x7fELF-fake"
        for rel, data in expected.items():
            self.assertEqual((unpacked / rel).read_bytes(), data, rel)
        self.assertTrue((unpacked / AMPR_INDEX_NAME).is_file())
        self.assertFalse((unpacked / "release.nfo").exists())
        self.assertFalse((unpacked / ".DS_Store").exists())
        found = {p.relative_to(unpacked).as_posix() for p in unpacked.rglob("*") if p.is_file()}
        self.assertEqual(found, set(expected) | {AMPR_INDEX_NAME})

    def test_archive_base_with_folder_layer(self) -> None:
        tmp = self.make_temp_path()
        _base, update, _dlc = self.make_set(tmp)
        base_zip = _zip_tree(self.BASE, tmp / "base.zip", top="GAME-app")
        output = tmp / "game.ffpfsc"
        code, text = self._run(
            ["pack", "folder", str(base_zip), str(output), "--layer", str(update), "--cpu-count", "1"]
        )
        self.assertEqual(code, 0, text)
        unpacked = tmp / "unpacked"
        code, text = self._run(["unpack", "--deep", str(output), str(unpacked)])
        self.assertEqual(code, 0, text)
        self.assertEqual((unpacked / "eboot.bin").read_bytes(), self.UPDATE["eboot.bin"])
        self.assertEqual((unpacked / "data/level2.pak").read_bytes(), self.BASE["data/level2.pak"])

    def test_dry_run_and_errors(self) -> None:
        tmp = self.make_temp_path()
        base, update, _dlc = self.make_set(tmp)
        output = tmp / "game.ffpfsc"
        code, text = self._run(["pack", "folder", str(base), str(output), "--layer", str(update), "--dry-run"])
        self.assertEqual(code, 0, text)
        self.assertFalse(output.exists())
        self.assertIn("Dry run", text)

        with self.assertRaises(BuildError) as raw_ctx:
            self._run(["pack", "folder", str(base), str(output), "--layer", str(update), "--raw"])
        self.assertIn("--layer", str(raw_ctx.exception))
        with self.assertRaises(BuildError):
            self._run(["pack", "folder", str(base), str(output), "--layer", str(tmp / "missing")])
        with self.assertRaises(BuildError):
            self._run(["pack", "folder", str(base), str(output), "--layer", f"{update}::nope"])
        no_boot = tmp / "no-boot"
        _write_tree(no_boot, self.DLC)
        with self.assertRaises(BuildError) as strict_ctx:
            self._run(["pack", "folder", str(no_boot), str(output), "--layer", str(no_boot), "--require-game-files"])
        self.assertIn("--require-game-files", str(strict_ctx.exception))
