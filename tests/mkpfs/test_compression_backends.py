"""Unit tests for mkpfs.compression module backends."""

from __future__ import annotations

import atexit
from typing import Any, NoReturn

import pytest


@pytest.fixture(autouse=True)
def _reset_comp() -> None:
    """Reset the compression module state between tests."""
    import mkpfs.compression as comp

    comp._backend_name = "zlib-ng"  # type: ignore[union-attribute]
    comp._backend = None  # type: ignore[union-attribute]


class TestCompressionBackends:
    """Test the compression module public API."""

    def test_set_backend_raises_value_error_for_unknown(self) -> None:
        import mkpfs.compression as comp

        with pytest.raises(ValueError):
            comp.set_backend("nonexistent")

    def test_get_backend_name_returns_string(self) -> None:
        import mkpfs.compression as comp

        assert isinstance(comp.get_backend_name(), str)

    def test_set_backend_updates_name(self) -> None:
        import mkpfs.compression as comp

        comp.set_backend("zlib-ng")
        assert comp.get_backend_name() == "zlib-ng"

    def test_compress_decompress_roundtrip(self) -> None:
        import mkpfs.compression as comp

        data = b"Hello, World!" * 100
        compressed = comp.compress_block(data)
        decompressed = comp.decompress_block(compressed)
        assert decompressed == data

    def test_compress_block_with_explicit_level(self) -> None:
        import mkpfs.compression as comp

        data = b"AABBCC" * 50
        c1 = comp.compress_block(data, level=1)
        c9 = comp.compress_block(data, level=9)
        assert len(c9) <= len(c1)

    def test_compress_empty_data(self) -> None:
        import mkpfs.compression as comp

        compressed = comp.compress_block(b"")
        decompressed = comp.decompress_block(compressed)
        assert decompressed == b""

    def test_compress_repeated_bytes(self) -> None:
        import mkpfs.compression as comp

        data = b"\x00" * 1000 + b"\xff" * 1000
        compressed = comp.compress_block(data)
        decompressed = comp.decompress_block(compressed)
        assert decompressed == data

    def test_compress_large_data(self) -> None:
        import random

        import mkpfs.compression as comp

        rng = random.Random(42)
        data = bytes(rng.randint(0, 255) for _ in range(1_000_000))
        compressed = comp.compress_block(data)
        decompressed = comp.decompress_block(compressed)
        assert decompressed == data

    def test_compression_error_raised_on_fail(self) -> None:
        """CompressionError is raised when the backend raises."""
        import mkpfs.compression as comp

        class BadBackend:
            def compress(self, *args: Any, **kwargs: Any) -> NoReturn:
                raise RuntimeError("boom")

            def decompress(self, data: bytes) -> bytes:
                return b"ok"

        comp._backend = BadBackend()
        comp._backend_name = "zlib-ng"

        with pytest.raises(comp.CompressionError):
            comp.compress_block(b"data", level=1)

    def test_decompress_error_raised_on_fail(self) -> None:
        """CompressionError is raised when decompress raises."""
        import mkpfs.compression as comp

        class BadBackendDecomp:
            def compress(self, *args: Any, **kwargs: Any) -> bytes:
                return b"compressed"

            def decompress(self, data: bytes) -> NoReturn:
                raise RuntimeError("decomp fail")

        comp._backend = BadBackendDecomp()
        comp._backend_name = "zlib-ng"

        with pytest.raises(comp.CompressionError):
            comp.decompress_block(b"compressed")


class TestIsalLevelMap:
    """Test _isal_level_map level mapping."""

    def test_zero_one_two(self) -> None:
        import mkpfs.compression as comp

        assert comp._isal_level_map(0) == 0
        assert comp._isal_level_map(1) == 0
        assert comp._isal_level_map(2) == 0

    def test_three_to_five(self) -> None:
        import mkpfs.compression as comp

        for lvl in (3, 4, 5):
            assert comp._isal_level_map(lvl) == 1

    def test_six_to_eight(self) -> None:
        import mkpfs.compression as comp

        for lvl in (6, 7, 8):
            assert comp._isal_level_map(lvl) == 2

    def test_nine(self) -> None:
        import mkpfs.compression as comp

        assert comp._isal_level_map(9) == 3


def _reset_comp_at_exit() -> None:
    import mkpfs.compression as comp

    comp._backend_name = "zlib-ng"
    comp._backend = None


atexit.register(_reset_comp_at_exit)
