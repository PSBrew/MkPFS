from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from mkpfs import ampr


class AmprTestCase(unittest.TestCase):
    """Shared helpers for AMPR index tests."""

    def make_temp_path(self) -> Path:
        temp_dir: tempfile.TemporaryDirectory[str] = tempfile.TemporaryDirectory()
        self.addCleanup(temp_dir.cleanup)
        return Path(temp_dir.name)


class TestAmprHashing(AmprTestCase):
    """The FNV-1a hash must match the resolver's known values."""

    def test_fnv1a64_known_values(self) -> None:
        self.assertEqual(ampr.fnv1a64_path_hash("/app0/a.txt"), 0xD7A87E24EF2D648B)
        self.assertEqual(ampr.fnv1a64_path_hash("/app0/sub/b.bin"), 0x5FA3B2A474A731A6)

    def test_fnv1a64_is_case_and_separator_insensitive(self) -> None:
        self.assertEqual(
            ampr.fnv1a64_path_hash("/APP0/A.TXT"),
            ampr.fnv1a64_path_hash("/app0/a.txt"),
        )
        self.assertEqual(
            ampr.fnv1a64_path_hash("\\app0\\a.txt"),
            ampr.fnv1a64_path_hash("/app0/a.txt"),
        )

    def test_hash_slot_count_is_next_pow2_of_double(self) -> None:
        self.assertEqual(ampr.ampr_hash_slot_count(0), 0)
        self.assertEqual(ampr.ampr_hash_slot_count(1), 2)
        self.assertEqual(ampr.ampr_hash_slot_count(2), 4)
        self.assertEqual(ampr.ampr_hash_slot_count(3), 8)
        self.assertEqual(ampr.ampr_hash_slot_count(8), 16)


class TestAmprIndexFormat(AmprTestCase):
    """The on-disk AMPRIDX3 layout must be well-formed and resolvable."""

    def _make_tree(self, root: Path) -> None:
        (root / "sub").mkdir(parents=True)
        (root / "a.txt").write_bytes(b"hello")
        (root / "sub" / "b.bin").write_bytes(b"x" * 1000)

    def _resolve(self, index: bytes, path: str) -> tuple[int, int] | None:
        """Resolve a path through the hash table; return (size, mtime) or None."""
        magic, version, rec_size, num_rows, _blob_len, hash_off, slot_size, num_slots = ampr.HEADER_STRUCT.unpack_from(
            index, 0
        )
        assert magic == b"AMPRIDX3" and version == 3
        records_off = ampr.HEADER_STRUCT.size
        blob_off = records_off + num_rows * rec_size
        mask = num_slots - 1
        h = ampr.fnv1a64_path_hash(path)
        pos = h & mask
        for _ in range(num_slots):
            slot_hash, index_plus_one, _flags = ampr.HASH_SLOT_STRUCT.unpack_from(index, hash_off + pos * slot_size)
            if index_plus_one == 0:
                return None
            if slot_hash == h:
                rec_i = index_plus_one - 1
                p_off, p_len, size, mtime = ampr.RECORD_STRUCT.unpack_from(index, records_off + rec_i * rec_size)
                name = index[blob_off + p_off : blob_off + p_off + p_len].decode("utf-8")
                if ampr.ampr_key_for(name) == ampr.ampr_key_for(path):
                    return size, mtime
            pos = (pos + 1) & mask
        return None

    def test_header_and_record_count(self) -> None:
        root = self.make_temp_path()
        self._make_tree(root)
        out = root / "ampr_emu.index"
        count = ampr.build_ampr_index(root, out)
        self.assertEqual(count, 2)
        data = out.read_bytes()
        magic, version, rec_size, num_rows, _blob, _hoff, slot_size, num_slots = ampr.HEADER_STRUCT.unpack_from(
            data, 0
        )
        self.assertEqual(magic, b"AMPRIDX3")
        self.assertEqual(version, 3)
        self.assertEqual(rec_size, 24)
        self.assertEqual(num_rows, 2)
        self.assertEqual(slot_size, 16)
        self.assertEqual(num_slots, 4)  # next pow2 of 2*2

    def test_paths_are_app0_prefixed_and_resolvable(self) -> None:
        root = self.make_temp_path()
        self._make_tree(root)
        out = root / "ampr_emu.index"
        ampr.build_ampr_index(root, out)
        data = out.read_bytes()
        self.assertEqual(self._resolve(data, "/app0/a.txt"), (5, self._resolve(data, "/app0/a.txt")[1]))
        self.assertIsNotNone(self._resolve(data, "/app0/sub/b.bin"))
        self.assertEqual(self._resolve(data, "/app0/sub/b.bin")[0], 1000)
        self.assertIsNone(self._resolve(data, "/app0/missing.dat"))

    def test_index_excludes_itself(self) -> None:
        root = self.make_temp_path()
        self._make_tree(root)
        out = root / "ampr_emu.index"
        out.write_bytes(b"stale")  # pre-existing index must not be indexed
        count = ampr.build_ampr_index(root, out)
        data = out.read_bytes()
        self.assertIsNone(self._resolve(data, "/app0/ampr_emu.index"))
        self.assertEqual(count, 2)

    def test_deterministic_bytes(self) -> None:
        root = self.make_temp_path()
        self._make_tree(root)
        out = root / "ampr_emu.index"
        ampr.build_ampr_index(root, out)
        first = out.read_bytes()
        ampr.build_ampr_index(root, out)  # rebuilding excludes its own output by path
        second = out.read_bytes()
        self.assertEqual(first, second)

    def test_empty_tree_writes_nothing(self) -> None:
        root = self.make_temp_path()
        out = root / "ampr_emu.index"
        count = ampr.build_ampr_index(root, out)
        self.assertEqual(count, 0)
        self.assertFalse(out.exists())


class TestEnsureAmprIndex(AmprTestCase):
    """Gating: generate only with the fakelib marker, when enabled, and when absent."""

    def _seed(self, root: Path, *, with_marker: bool) -> None:
        (root / "a.txt").write_bytes(b"data")
        if with_marker:
            (root / "fakelib").mkdir(parents=True, exist_ok=True)
            (root / "fakelib" / "libSceAmpr.sprx").write_bytes(b"\x00")

    def test_no_marker_no_index(self) -> None:
        root = self.make_temp_path()
        self._seed(root, with_marker=False)
        self.assertIsNone(ampr.ensure_ampr_index(root))
        self.assertFalse((root / "ampr_emu.index").exists())

    def test_marker_generates_index(self) -> None:
        root = self.make_temp_path()
        self._seed(root, with_marker=True)
        result = ampr.ensure_ampr_index(root)
        self.assertIsNotNone(result)
        self.assertTrue((root / "ampr_emu.index").exists())

    def test_existing_index_is_refreshed(self) -> None:
        root = self.make_temp_path()
        self._seed(root, with_marker=True)
        index = root / "ampr_emu.index"
        index.write_bytes(b"stale-index")
        result = ampr.ensure_ampr_index(root)
        self.assertEqual(result, index)
        self.assertEqual(index.read_bytes()[:8], b"AMPRIDX3")  # rebuilt, not the stale bytes

    def test_disabled_preserves_existing_index(self) -> None:
        root = self.make_temp_path()
        self._seed(root, with_marker=True)
        index = root / "ampr_emu.index"
        index.write_bytes(b"keep-me")
        self.assertIsNone(ampr.ensure_ampr_index(root, enabled=False))
        self.assertEqual(index.read_bytes(), b"keep-me")


if __name__ == "__main__":
    unittest.main()


class TestAmprExcludesOsMetadata(AmprTestCase):
    """AMPR index must not include OS-generated metadata, consistent with packing."""

    def test_junk_is_not_indexed(self) -> None:
        root = self.make_temp_path()
        (root / "data.bin").write_bytes(b"DATA")
        (root / ".DS_Store").write_bytes(b"junk")
        (root / "._data.bin").write_bytes(b"junk")
        (root / "__MACOSX").mkdir()
        (root / "__MACOSX" / "x.plist").write_bytes(b"junk")
        out = root / "ampr_emu.index"
        count = ampr.build_ampr_index(root, out)
        self.assertEqual(count, 1)  # only data.bin
        blob = out.read_bytes()
        self.assertNotIn(b"DS_Store", blob)
        self.assertNotIn(b"MACOSX", blob)
        self.assertNotIn(b"._data", blob)
