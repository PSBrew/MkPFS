"""Compression backend adapter for MkPFS.

Provides a small, testable API to select a zlib-compatible compression backend
(zlib-ng by default) and wrap the compress/decompress primitives used throughout
pfs.py so callsites can stay simple.

API::

    set_backend(name: str) -> None   # pick "zlib-ng", "isal", or "zlib"
    get_backend_name() -> str         # returns current backend name
    init_worker(backend_name=None)    # per-process bootstrap for multiprocessing
    compress_block(data, level=6)     # compress bytes (level 1-9, std zlib scale)
    decompress_block(data)            # decompress any zlib-stream-compatible data

Backends
--------
* ``"zlib-ng"`` — uses ``zlib_ng.zlib_ng`` (default, already a hard dep).
* ``"isal"`` — ISA-L via ``isal.isal_zlib``.  Level mapping: std 1-9 -> isal 0-3.
* ``"zlib"`` — stdlib ``zlib`` as last-resort fallback when zlib-ng is missing.

Notes:
-----
* Does not implement PFSC framing; only wraps the compression primitive used by
  PFSC in mkpfs.pfs. The PFSC encoder/decoder lives entirely in pfs.py.
* Decompression is backend-agnostic: any backend can decompress output from any
  other because the zlib stream format is interoperable.
"""

from __future__ import annotations

# ---------------------------------------------------------------------------
# Module-level state — set by ``set_backend`` / ``init_worker``.
# ---------------------------------------------------------------------------

_backend_name: str = "zlib-ng"
_backend: object | None = None


class CompressionError(Exception):
    """Raised when a compression operation fails."""


# ---------------------------------------------------------------------------
# Backend loaders (lazy, isolated try/except per backend).
# ---------------------------------------------------------------------------


def _load_zlib_ng() -> object:
    from zlib_ng import zlib_ng  # type: ignore[import-not-found]

    return zlib_ng


def _load_zlib() -> object:
    import zlib as _zlib

    return _zlib


def _load_isal() -> object:
    try:
        from isal import isal_zlib  # type: ignore[import-not-found]
    except ModuleNotFoundError as exc:
        raise ImportError("isal backend requires the 'isal' package; install it first") from exc

    return isal_zlib


# ---------------------------------------------------------------------------
# Public API — set_backend / get_backend_name / init_worker.
# ---------------------------------------------------------------------------


def set_backend(name: str) -> None:
    """Select the compression backend.

    Supported names (case-insensitive): ``"auto"``, ``"zlib-ng"``, ``"isal"``, ``"zlib"``.

    Raises:
        ValueError: *name* is not a recognised backend name.
        ImportError: The requested backend cannot be loaded in this environment.
    """
    global _backend_name, _backend

    normalised = name.lower()
    # Auto-selection tries backends in preferred order: isal > zlib-ng > zlib
    if normalised == "auto":
        for candidate in ("isal", "zlib-ng", "zlib"):
            try:
                set_backend(candidate)
                return
            except ImportError:
                continue
        raise ImportError("no available compression backend (isal, zlib-ng, zlib)")

    if normalised == "zlib-ng":
        loader = _load_zlib_ng
    elif normalised in ("zlib",):
        loader = _load_zlib
    elif normalised in ("isal",):
        loader = _load_isal
    else:
        raise ValueError(f"Unsupported compression backend: {name}")

    try:
        module = loader()
    except Exception as exc:
        raise ImportError(f"{name} backend is not available ({exc})") from exc

    _backend_name = normalised
    _backend = module


def get_backend_name() -> str:
    """Return the name of the currently selected backend."""
    return _backend_name


def init_worker(backend_name: str | None = None) -> None:
    """Bootstrap per-process state for multiprocessing workers.

    Call this as ``Pool(initializer=init_worker, initargs=(name,))`` so each
    spawned process loads the correct backend before compressing data.

    Args:
        backend_name: Name of the backend to load (e.g. ``"zlib-ng"``).  If
            *None*, re-uses whatever was last set on the parent side or falls
            back to ``"isal"`` / ``"zlib-ng"`` / ``"zlib"`` in that order.
    """
    global _backend, _backend_name

    if backend_name is not None:
        try:
            set_backend(backend_name)
            return
        except ImportError:
            # Explicit request failed; fall through and try auto selection below.
            pass

    # If nothing was passed (or explicit load failed) and default wasn't loaded, attempt preferred fallbacks.
    if _backend is None:
        for fallback in ("isal", "zlib-ng", "zlib"):
            try:
                set_backend(fallback)
                break
            except ImportError:
                continue


# ---------------------------------------------------------------------------
# Compression helpers — level mapping for ISA-L backend.
# ---------------------------------------------------------------------------


def _isal_level_map(level: int) -> int:
    """Map a standard zlib-level (1-9) into the ISA-L range (0-3).

    ISA-L levels are 0 = lowest, 3 = highest compression. The mapping is::

        level 1-2 → 0   (lowest / fastest)
        level 3-5 → 1   (medium)
        level 6-8 → 2   (high)
        level 9   → 3   (highest)

    Args:
        level: zlib-style compression level (intended range 0-9).

    Returns:
        An ISA-L compatible level in ``{0, 1, 2, 3}``.
    """
    if level <= 0:
        return 0
    if level >= 9:
        return 3
    if level <= 2:
        return 0
    if level <= 5:
        return 1
    # level 6-8
    return 2


# ---------------------------------------------------------------------------
# Public API — compress_block / decompress_block.
# ---------------------------------------------------------------------------


def compress_block(data: bytes, level: int = 6) -> bytes:
    """Compress a block of data using the selected backend.

    Args:
        data: Data to compress (arbitrary length).
        level: Compression level on the standard zlib scale (1-9).  Passed
            through verbatim for ``zlib-ng`` / ``zlib``, mapped via
            :func:`_isal_level_map` when the backend is ``"isal"``.

    Returns:
        Compressed bytes in the stream-compressed format of the selected backend.

    Raises:
        CompressionError: If compression fails and the underlying exception does
            not already carry a meaningful message.
    """
    global _backend

    if _backend is None:
        set_backend(_backend_name)

    name = get_backend_name()

    try:
        if name == "isal":
            compressed_data = _compress_with_isal(data, level)
        else:
            # zlib-ng or stdlib zlib — both accept ``(data, level)``.
            func = _backend.compress  # type: ignore[union-attribute]
            compressed_data = func(data, level)
    except Exception as exc:
        raise CompressionError(f"{name} compress() failed: {exc}") from exc

    return compressed_data


def _compress_with_isal(data: bytes, zlib_level: int = 6) -> bytes:
    """Compress using the ISA-L backend with level mapping.

    Args:
        data: Data to compress.
        zlib_level: Standard zlib-style compression level (0-9).

    Returns:
        Compressed bytes via ``isal_zlib``.
    """
    module = _backend  # type: ignore[union-attribute] — already set in compress_block
    mapped_level = _isal_level_map(zlib_level)
    return module.compress(data, level=mapped_level)


def decompress_block(data: bytes) -> bytes:
    """Decompress a zlib-stream block.

    Decompression is backend-agnostic since the zlib stream format is
    interoperable across backends.

    Args:
        data: Compressed bytes from any zlib-compatible backend.

    Returns:
        Decompressed original data.

    Raises:
        CompressionError: If decompression fails.
    """
    global _backend

    if _backend is None:
        set_backend(_backend_name)

    try:
        func = _backend.decompress  # type: ignore[union-attribute]
        return func(data)
    except Exception as exc:
        raise CompressionError(f"decompress() failed: {exc}") from exc


# ---------------------------------------------------------------------------
# Module-level bootstrap — try zlib-ng first, fall back to stdlib zlib.
# ---------------------------------------------------------------------------

try:
    set_backend("auto")
except ImportError:
    try:
        set_backend("zlib")
    except Exception:
        _backend_name = "zlib"


__all__ = [
    "CompressionError",
    "compress_block",
    "decompress_block",
    "get_backend_name",
    "init_worker",
    "set_backend",
]
