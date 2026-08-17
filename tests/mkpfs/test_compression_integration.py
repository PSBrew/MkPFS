"""Integration tests for mkpfs.compression module.

These tests build small compressed payloads with different backends and verify that
decompressed output matches the original data (functional compatibility). They also test
the module-level bootstrap behaviour.
"""

from __future__ import annotations

import atexit

import pytest


@pytest.fixture(autouse=True)
def _reset_comp() -> None:
    """Reset the compression module state between tests."""
    import mkpfs.compression as comp

    comp._backend_name = "zlib-ng"  # type: ignore[union-attribute]
    comp._backend = None  # type: ignore[union-attribute]


class TestCompressionModuleBootstrap:
    """Test that the module bootstraps correctly at import time."""

    def test_default_backend_is_zlib_ng_or_fallback(self) -> None:
        import mkpfs.compression as comp

        name = comp.get_backend_name()
        assert name in ("zlib-ng", "zlib")  # fallback if zlib-ng missing

    def test_compress_works_after_import(self) -> None:
        """After module bootstrap, compress/decompress should work."""
        import mkpfs.compression as comp

        data = b"bootstrap test" * 50
        compressed = comp.compress_block(data)
        decompressed = comp.decompress_block(compressed)
        assert decompressed == data


class TestCompressionBackendRoundtrip:
    """Test compress/decompress round-trip for each available backend."""

    def setUp(self) -> None:
        import mkpfs.compression as comp

        comp._backend_name = "zlib-ng"  # type: ignore[union-attribute]
        comp._backend = None  # type: ignore[union-attribute]

    def test_zlib_ng_roundtrip(self) -> None:
        import mkpfs.compression as comp

        comp.set_backend("zlib-ng")
        data = b"zlib-ng roundtrip test " * 100
        compressed = comp.compress_block(data)
        decompressed = comp.decompress_block(compressed)
        assert decompressed == data

    def test_zlib_ng_compress_with_all_levels(self) -> None:
        """Test levels 1-9 produce valid output."""
        import mkpfs.compression as comp

        comp.set_backend("zlib-ng")
        data = b"levels test " * 50
        for level in range(1, 10):
            compressed = comp.compress_block(data, level=level)
            decompressed = comp.decompress_block(compressed)
            assert decompressed == data

    def test_zlib_roundtrip(self) -> None:
        import mkpfs.compression as comp

        try:
            comp.set_backend("zlib")
        except ImportError:
            pytest.skip("stdlib zlib backend is not available in this environment")
        data = b"stdlib zlib roundtrip " * 100
        compressed = comp.compress_block(data)
        decompressed = comp.decompress_block(compressed)
        assert decompressed == data

    def test_isal_roundtrip(self) -> None:
        import mkpfs.compression as comp

        try:
            comp.set_backend("isal")
        except ImportError:
            pytest.skip("isal backend is not available in this environment")
        data = b"isal roundtrip test " * 100
        compressed = comp.compress_block(data, level=6)
        decompressed = comp.decompress_block(compressed)
        assert decompressed == data


class TestCompressionCrossBackendDecompress:
    """Test that a backend can decompress output from another backend."""

    def setUp(self) -> None:
        import mkpfs.compression as comp

        comp._backend_name = "zlib-ng"  # type: ignore[union-attribute]
        comp._backend = None  # type: ignore[union-attribute]

    def test_cross_backend_decompress(self) -> None:
        """Compressed by zlib-ng, decompressed by stdlib zlib."""
        import mkpfs.compression as comp

        original_data = b"cross-backend " * 100
        compressed_by_zlib_ng = comp.compress_block(original_data, level=9)

        # Switch to stdlib zlib backend and decompress the zlib-ng output.
        try:
            comp.set_backend("zlib")
        except ImportError:
            pytest.skip("stdlib zlib backend is not available in this environment")
        decompressed = comp.decompress_block(compressed_by_zlib_ng)
        assert decompressed == original_data


class TestCompressionWorkerInit:
    """Test init_worker sets up the backend correctly."""

    def setUp(self) -> None:
        import mkpfs.compression as comp

        comp._backend_name = "zlib-ng"  # type: ignore[union-attribute]
        comp._backend = None  # type: ignore[union-attribute]

    def test_init_worker_with_explicit_backend(self) -> None:
        import mkpfs.compression as comp

        comp._backend = None  # type: ignore[union-attribute]
        comp.init_worker("zlib-ng")
        assert comp.get_backend_name() == "zlib-ng"

    def test_init_worker_fallback(self) -> None:
        """init_worker with no name should try fallbacks."""
        import mkpfs.compression as comp

        # Simulate that no backend is loaded yet (this won't actually set it).
        comp._backend_name = "nonexistent"  # type: ignore[union-attribute]
        comp._backend = None  # type: ignore[union-attribute]
        comp.init_worker(None)  # no name passed — should try fallbacks.
        assert comp.get_backend_name() in ("isal", "zlib-ng", "zlib")


def _reset_comp_at_exit() -> None:
    import mkpfs.compression as comp

    comp._backend_name = "zlib-ng"
    comp._backend = None


atexit.register(_reset_comp_at_exit)
