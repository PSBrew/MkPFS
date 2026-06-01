from __future__ import annotations

import json
import tempfile
import unittest
from io import BytesIO
from pathlib import Path

from mkpfs import utils


class TestUtilityFormatting(unittest.TestCase):
    """Tests for small formatting and math utility helpers."""

    def test_human_readable_size_formats_common_units(self) -> None:
        """The size formatter should emit readable strings for bytes, kilobytes, and megabytes."""
        self.assertTrue(utils.human_readable_size(0).startswith("0.00"))
        self.assertIn("KB", utils.human_readable_size(1024))
        self.assertIn("MB", utils.human_readable_size(1024 * 1024))

    def test_ceil_div_returns_the_ceiling_for_integer_division(self) -> None:
        """The ceil division helper should round fractional division results upward."""
        self.assertEqual(utils.ceil_div(1, 1), 1)
        self.assertEqual(utils.ceil_div(3, 2), 2)
        self.assertEqual(utils.ceil_div(0, 5), 0)

    def test_is_power_of_two_accepts_only_positive_power_values(self) -> None:
        """The power-of-two helper should accept only positive powers of two."""
        self.assertTrue(utils.is_power_of_two(1))
        self.assertTrue(utils.is_power_of_two(2))
        self.assertFalse(utils.is_power_of_two(0))
        self.assertFalse(utils.is_power_of_two(3))


class TestUtilityFileHelpers(unittest.TestCase):
    """Tests for filesystem and binary I/O utility helpers."""

    def test_normalize_output_path_keeps_existing_ffpfs_suffix(self) -> None:
        """Normalizing an existing FFPFS path should keep the suffix and avoid a warning."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path: Path = Path(tmp_dir)
            normalized_upper: tuple[Path, bool] = utils.normalize_output_path(str(tmp_path / "out.FFPFS"), ".ffpfs")
            normalized_lower: tuple[Path, bool] = utils.normalize_output_path(str(tmp_path / "image.ffpfs"), ".ffpfs")

        self.assertEqual(normalized_upper[0].suffix.lower(), ".ffpfs")
        self.assertFalse(normalized_upper[1])
        self.assertEqual(normalized_lower[0].suffix, ".ffpfs")
        self.assertFalse(normalized_lower[1])

    def test_normalize_output_path_adjusts_suffix_only_when_enabled(self) -> None:
        """Normalizing should only rewrite the suffix when adjustment is enabled."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path: Path = Path(tmp_dir)
            adjusted: tuple[Path, bool] = utils.normalize_output_path(str(tmp_path / "out.bin"), ".ffpfsc")
            kept: tuple[Path, bool] = utils.normalize_output_path(str(tmp_path / "out.bin"), ".ffpfsc", adjust=False)

        self.assertEqual(adjusted[0].suffix, ".ffpfsc")
        self.assertTrue(adjusted[1])
        self.assertEqual(kept[0].suffix, ".bin")
        self.assertFalse(kept[1])

    def test_read_param_json_returns_data_and_rejects_invalid_json(self) -> None:
        """Reading param JSON should return parsed data and raise for malformed files."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path: Path = Path(tmp_dir)
            valid_path: Path = tmp_path / "params.json"
            invalid_path: Path = tmp_path / "bad.json"
            valid_path.write_text(json.dumps({"a": 1}), encoding="utf-8")
            invalid_path.write_text("notjson", encoding="utf-8")

            data: dict[str, object] = utils.read_param_json(valid_path)

            self.assertEqual(data["a"], 1)
            with self.assertRaises(ValueError):
                utils.read_param_json(invalid_path)

    def test_read_exact_returns_requested_bytes_and_raises_on_truncation(self) -> None:
        """Reading exact bytes should return the slice and fail for truncated input."""
        buffer: BytesIO = BytesIO(b"0123456789")
        self.assertEqual(utils._read_exact(buffer, 2, 4), b"2345")

        truncated: BytesIO = BytesIO(b"abc")
        with self.assertRaises(ValueError):
            utils._read_exact(truncated, 0, 10)
