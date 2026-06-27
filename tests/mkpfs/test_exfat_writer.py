from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path

from mkpfs import exfat
from mkpfs.exfat_writer import iter_exfat_image, write_exfat_image


class ExfatWriterTestCase(unittest.TestCase):
    """Shared helpers for exFAT writer tests."""

    def make_temp_path(self) -> Path:
        temp_dir: tempfile.TemporaryDirectory[str] = tempfile.TemporaryDirectory()
        self.addCleanup(temp_dir.cleanup)
        return Path(temp_dir.name)

    def _build_tree(self, root: Path) -> dict[str, bytes]:
        """Create a representative source tree and return its expected files."""
        (root / "sub").mkdir()
        (root / "empty_dir").mkdir()
        files: dict[str, bytes] = {
            "eboot.bin": b"BOOT" * 100,
            "sub/data.bin": bytes(range(256)) * 1000,  # spans clusters
            "sub/note.txt": b"hello",
            "empty.dat": b"",  # zero-length file
        }
        for rel, data in files.items():
            (root / rel).parent.mkdir(parents=True, exist_ok=True)
            (root / rel).write_bytes(data)
        return files


class TestExfatWriterRoundTrip(ExfatWriterTestCase):
    """A written exFAT image must read back identically through the reader."""

    def test_round_trip_matches_source(self) -> None:
        tmp = self.make_temp_path()
        src = tmp / "src"
        src.mkdir()
        expected = self._build_tree(src)
        image = tmp / "out.exfat"
        write_exfat_image(src, image)

        with image.open("rb") as fh:
            reader = exfat.ExfatReader(fh)
            by_path = {f.rel_path: f for f in reader.iter_files()}
            # zero-length files carry no clusters but still appear as entries
            self.assertEqual(set(by_path), set(expected))
            for rel, data in expected.items():
                self.assertEqual(b"".join(reader.read_file(by_path[rel])), data, rel)

    def test_directories_preserved_including_empty(self) -> None:
        tmp = self.make_temp_path()
        src = tmp / "src"
        src.mkdir()
        self._build_tree(src)
        image = tmp / "out.exfat"
        write_exfat_image(src, image)
        with image.open("rb") as fh:
            reader = exfat.ExfatReader(fh)
            dir_names = {e.name for e in reader.root_entries() if e.is_dir}
        self.assertEqual(dir_names, {"sub", "empty_dir"})

    def test_excludes_os_metadata(self) -> None:
        tmp = self.make_temp_path()
        src = tmp / "src"
        src.mkdir()
        (src / "keep.bin").write_bytes(b"x")
        (src / ".DS_Store").write_bytes(b"junk")
        (src / "._keep.bin").write_bytes(b"junk")
        (src / "__MACOSX").mkdir()
        (src / "__MACOSX" / "buried").write_bytes(b"junk")
        image = tmp / "out.exfat"
        write_exfat_image(src, image)
        with image.open("rb") as fh:
            files = {f.rel_path for f in exfat.ExfatReader(fh).iter_files()}
        self.assertEqual(files, {"keep.bin"})


class TestExfatWriterFormat(ExfatWriterTestCase):
    """The writer's geometry and output must be well-formed and deterministic."""

    def test_deterministic_output(self) -> None:
        tmp = self.make_temp_path()
        src = tmp / "src"
        src.mkdir()
        self._build_tree(src)
        first = b"".join(iter_exfat_image(src))
        second = b"".join(iter_exfat_image(src))
        self.assertEqual(first, second)

    def test_boot_signature_and_geometry(self) -> None:
        tmp = self.make_temp_path()
        src = tmp / "src"
        src.mkdir()
        self._build_tree(src)
        image = tmp / "out.exfat"
        write_exfat_image(src, image)
        with image.open("rb") as fh:
            geo = exfat.ExfatReader(fh).geometry
        self.assertEqual(geo.bytes_per_sector, 512)
        self.assertIn(geo.cluster_size, (32 * 1024, 64 * 1024))

    def test_large_files_select_64k_clusters(self) -> None:
        tmp = self.make_temp_path()
        src = tmp / "src"
        src.mkdir()
        (src / "big.bin").write_bytes(os.urandom(2 * 1024 * 1024))  # avg >= 1 MiB
        image = tmp / "out.exfat"
        write_exfat_image(src, image)
        with image.open("rb") as fh:
            self.assertEqual(exfat.ExfatReader(fh).geometry.cluster_size, 64 * 1024)


class TestExfatWriterAutoName(ExfatWriterTestCase):
    """Writing to a directory names the image from the titleId."""

    def test_writes_titleid_named_image_into_directory(self) -> None:
        tmp = self.make_temp_path()
        src = tmp / "game"
        (src / "sce_sys").mkdir(parents=True)
        (src / "sce_sys" / "param.json").write_text('{"titleId": "PPSA25872"}', encoding="utf-8")
        (src / "eboot.bin").write_bytes(b"BOOT" * 100)
        out_dir = tmp / "out"
        out_dir.mkdir()
        written = write_exfat_image(src, out_dir)
        self.assertEqual(written.name, "PPSA25872.exfat")
        self.assertTrue(written.is_file())
        with written.open("rb") as fh:
            files = {f.rel_path for f in exfat.ExfatReader(fh).iter_files()}
        self.assertEqual(files, {"eboot.bin", "sce_sys/param.json"})


if __name__ == "__main__":
    unittest.main()
