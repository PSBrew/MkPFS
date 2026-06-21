from __future__ import annotations

import gzip
import io
import os
import unittest
from pathlib import Path

from mkpfs import exfat

# A minimal real exFAT image (produced by newfs_exfat) holding:
#   hello.txt          -> b"hello exfat"
#   sub/inner.bin      -> b"nested data here"
#   big.bin            -> b"AB" * 5000  (spans multiple clusters)
_FIXTURE: Path = Path(__file__).parent / "fixtures" / "tiny.exfat.gz"


def _load_reader() -> exfat.ExfatReader:
    data: bytes = gzip.decompress(_FIXTURE.read_bytes())
    return exfat.ExfatReader(io.BytesIO(data))


class TestExfatBootSector(unittest.TestCase):
    """The reader must parse exFAT volume geometry from the boot sector."""

    def test_geometry_fields(self) -> None:
        geo = _load_reader().geometry
        self.assertEqual(geo.bytes_per_sector, 512)
        self.assertEqual(geo.cluster_size, geo.bytes_per_sector * geo.sectors_per_cluster)
        self.assertGreaterEqual(geo.root_dir_cluster, 2)
        self.assertGreater(geo.cluster_count, 0)

    def test_rejects_non_exfat_source(self) -> None:
        with self.assertRaises(exfat.ExfatError):
            exfat.ExfatReader(io.BytesIO(b"\x00" * 512))

    def test_rejects_truncated_source(self) -> None:
        with self.assertRaises(exfat.ExfatError):
            exfat.ExfatReader(io.BytesIO(b"\xeb"))


class TestExfatTraversal(unittest.TestCase):
    """The reader must enumerate the directory tree and extract file contents."""

    def test_lists_all_files_with_paths(self) -> None:
        files = {f.rel_path for f in _load_reader().iter_files()}
        self.assertEqual(files, {"hello.txt", "sub/inner.bin", "big.bin"})

    def test_directory_structure(self) -> None:
        roots = {e.name: e for e in _load_reader().root_entries()}
        self.assertIn("sub", roots)
        self.assertTrue(roots["sub"].is_dir)
        child_names = {c.name for c in roots["sub"].children}
        self.assertEqual(child_names, {"inner.bin"})

    def test_extracts_file_contents(self) -> None:
        reader = _load_reader()
        by_path = {f.rel_path: f for f in reader.iter_files()}
        self.assertEqual(b"".join(reader.read_file(by_path["hello.txt"])), b"hello exfat")
        self.assertEqual(b"".join(reader.read_file(by_path["sub/inner.bin"])), b"nested data here")

    def test_extracts_multi_cluster_file(self) -> None:
        reader = _load_reader()
        big = next(f for f in reader.iter_files() if f.rel_path == "big.bin")
        payload = b"".join(reader.read_file(big))
        self.assertEqual(payload, b"AB" * 5000)
        self.assertEqual(len(payload), big.length)

    def test_read_file_chunking_is_bounded(self) -> None:
        reader = _load_reader()
        big = next(f for f in reader.iter_files() if f.rel_path == "big.bin")
        chunks = list(reader.read_file(big, chunk_size=4096))
        self.assertTrue(all(len(c) <= 4096 for c in chunks))
        self.assertEqual(b"".join(chunks), b"AB" * 5000)

    def test_read_file_on_directory_raises(self) -> None:
        reader = _load_reader()
        sub = next(e for e in reader.root_entries() if e.name == "sub")
        with self.assertRaises(exfat.ExfatError):
            list(reader.read_file(sub))


class TestExfatRealImage(unittest.TestCase):
    """Optional cross-check against a real PS5 image when MKPFS_EXFAT_SAMPLE is set."""

    def test_real_image_round_trip(self) -> None:
        sample: str | None = os.environ.get("MKPFS_EXFAT_SAMPLE")
        if not sample or not Path(sample).is_file():
            self.skipTest("set MKPFS_EXFAT_SAMPLE to a real .exfat to run this check")
        with open(sample, "rb") as fh:
            reader = exfat.ExfatReader(fh)
            count = 0
            for f in reader.iter_files():
                read = sum(len(c) for c in reader.read_file(f))
                self.assertEqual(read, f.length, f.rel_path)
                count += 1
            self.assertGreater(count, 0)


if __name__ == "__main__":
    unittest.main()
