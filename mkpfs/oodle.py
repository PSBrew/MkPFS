"""Thin ctypes wrapper for the Oodle SDK (Kraken compressor/decompressor).

This wrapper locates a compatible liboo2core runtime and exposes two helpers:

- compress_kraken_block(data: bytes, level: int = 7) -> bytes
- decompress_kraken_block(comp: bytes, expected_size: int) -> bytes

It prefers the platform default C loader (cdecl) when probing libraries and
uses pointer-sized integer types (OO_SINTa -> ctypes.c_ssize_t) for length
arguments to match the SDK typedefs.
"""

from __future__ import annotations

import ctypes
import os
import pathlib
import platform
from ctypes import c_int, c_ssize_t, c_void_p
from typing import Optional

# Kraken compressor id
KRAKEN_COMPRESSOR_ID = 8

# Candidate library names to probe. OODLE_LIB env overrides probe order when set.
_CANDIDATE_LIB_NAMES = [
    os.environ.get("OODLE_LIB") if os.environ.get("OODLE_LIB") else None,
    # macOS candidates
    "liboo2core.dylib",
    "liboo2core_9_macOS.dylib",
    "liboo2core_9.dylib",
    # Linux/Unix candidates
    "liboo2core.so",
    "liboo2corelinux64.so.9",
    "liboo2core_9_linux.so",
    # Windows names
    "oo2core_9_win64.dll",
    "oo2core_8_win64.dll",
]


def _find_oodle_lib() -> Optional[str]:
    """Return a path/name for a candidate Oodle library or None if none found."""
    for name in _CANDIDATE_LIB_NAMES:
        if not name:
            continue
        # Absolute path
        if pathlib.Path(name).is_absolute() and pathlib.Path(name).exists():
            return name
        # Try to load by name via the default search path using CDLL first.
        try:
            ctypes.CDLL(name)
            return name
        except Exception:
            # on Windows we may try the same name with WinDLL when CDLL fails
            if platform.system() == "Windows":
                try:
                    ctypes.WinDLL(name)
                    return name
                except Exception:
                    pass
            continue
    return None


def _load_lib(lib_path: str):
    """Load the native library. Prefer CDLL (cdecl) then fallback to WinDLL on Windows.

    Returns: (lib_handle, loader_name)
    """
    last_exc = None
    try:
        lib = ctypes.CDLL(lib_path)
        return lib, "CDLL"
    except Exception as e:
        last_exc = e
        if platform.system() == "Windows":
            try:
                lib = ctypes.WinDLL(lib_path)
                return lib, "WinDLL"
            except Exception as e2:
                last_exc = e2
    raise ImportError(f"Failed to load Oodle library '{lib_path}': {last_exc}")


class OodleWrapper:
    """Runtime wrapper around a loaded Oodle library.

    The wrapper sets conservative restype/argtypes matching the SDK's OO_SINTa
    typedef and the function signatures used by go-oodle.
    """

    def __init__(self, lib_path: Optional[str] = None):
        self.lib_path = lib_path or _find_oodle_lib()
        if not self.lib_path:
            raise ImportError(
                "Oodle library not found. Set OODLE_LIB env var to the path of liboo2core.* or install a compatible runtime"
            )

        self._lib, self._loader = _load_lib(self.lib_path)

        # Resolve symbols
        try:
            self._compress_fn = self._lib.OodleLZ_Compress
        except AttributeError as exc:
            raise ImportError(
                f"Oodle library loaded from {self.lib_path} but OodleLZ_Compress symbol missing"
            ) from exc

        self._decompress_fn = getattr(self._lib, "OodleLZ_Decompress", None)

        # Restypes
        self._compress_fn.restype = c_ssize_t
        if self._decompress_fn is not None:
            self._decompress_fn.restype = c_ssize_t

        # Set argtypes to match go-oodle / SDK declarations
        # Compress signature (11 args):
        #   compressor, rawBuf, rawSize, compBuf, compSize, level,
        #   options, dictionaryBase, lrm, scratchMem, scratchSize
        try:
            self._compress_fn.argtypes = [
                c_int,  # compressor
                c_void_p,  # rawBuf
                c_ssize_t,  # rawSize
                c_void_p,  # compBuf
                c_ssize_t,  # compSize
                c_int,  # level
                c_void_p,  # options
                c_void_p,  # dictionaryBase
                c_void_p,  # lrm
                c_void_p,  # scratchMem
                c_ssize_t,  # scratchSize
            ]
        except Exception:
            # best-effort: continue without strict argtypes
            pass

        # Decompress signature (14 args):
        # compBuf, compBufSize, rawBuf, rawBufSize,
        # fuzzSafe, checkCRC, verbosity,
        # decBufBase, decBufSize, fpCallback, callbackUserData,
        # decoderMemory, decoderMemorySize, threadPhase
        if self._decompress_fn is not None:
            try:
                self._decompress_fn.argtypes = [
                    c_void_p,  # compBuf
                    c_ssize_t,  # compBufSize
                    c_void_p,  # rawBuf
                    c_ssize_t,  # rawBufSize
                    c_int,  # fuzzSafe
                    c_int,  # checkCRC
                    c_int,  # verbosity
                    c_void_p,  # decBufBase
                    c_ssize_t,  # decBufSize
                    c_void_p,  # fpCallback
                    c_void_p,  # callbackUserData
                    c_void_p,  # decoderMemory
                    c_ssize_t,  # decoderMemorySize
                    c_int,  # threadPhase
                ]
            except Exception:
                pass

    def compress_kraken(self, data: bytes, level: int = 7) -> bytes:
        """Compress bytes with Kraken via Oodle.

        Returns compressed bytes or raises RuntimeError on failure.
        """
        if not data:
            return b""
        src_len = len(data)
        dst_capacity = src_len + max(4096, src_len // 100)
        src_buf = ctypes.create_string_buffer(data, src_len)
        dst_buf = ctypes.create_string_buffer(dst_capacity)
        src_ptr = ctypes.c_void_p(ctypes.addressof(src_buf))
        dst_ptr = ctypes.c_void_p(ctypes.addressof(dst_buf))

        # Build args matching the 11-arg signature. Pass NULL for optional pointers.
        args = (
            c_int(KRAKEN_COMPRESSOR_ID),
            src_ptr,
            c_ssize_t(src_len),
            dst_ptr,
            c_ssize_t(dst_capacity),
            c_int(level),
            c_void_p(0),  # options
            c_void_p(0),  # dictionaryBase
            c_void_p(0),  # lrm
            c_void_p(0),  # scratchMem
            c_ssize_t(0),  # scratchSize
        )

        ret = self._compress_fn(*args)
        if ret <= 0:
            raise RuntimeError(f"Oodle compression failed (return={ret})")
        return bytes(dst_buf.raw[: int(ret)])

    def decompress_kraken(self, comp: bytes, expected_size: int) -> bytes:
        """Decompress a Kraken-compressed block using Oodle.

        expected_size is required by the native API (the caller must know the
        uncompressed size). Raises RuntimeError on failure.
        """
        if self._decompress_fn is None:
            raise ImportError("Oodle library does not export OodleLZ_Decompress")

        comp_len = len(comp)
        if expected_size < 0:
            raise ValueError("expected_size must be non-negative")

        src_buf = ctypes.create_string_buffer(comp, comp_len)
        dst_buf = ctypes.create_string_buffer(expected_size)
        src_ptr = ctypes.c_void_p(ctypes.addressof(src_buf))
        dst_ptr = ctypes.c_void_p(ctypes.addressof(dst_buf))

        args = (
            src_ptr,
            c_ssize_t(comp_len),
            dst_ptr,
            c_ssize_t(expected_size),
            c_int(1),  # fuzzSafe
            c_int(1),  # checkCRC
            c_int(0),  # verbosity
            c_void_p(0),  # decBufBase
            c_ssize_t(0),  # decBufSize
            c_void_p(0),  # fpCallback
            c_void_p(0),  # callbackUserData
            c_void_p(0),  # decoderMemory
            c_ssize_t(0),  # decoderMemorySize
            c_int(3),  # threadPhase
        )

        ret = self._decompress_fn(*args)
        if ret < 0:
            raise RuntimeError(f"Oodle decompression failed (return={ret})")
        if int(ret) != expected_size:
            raise RuntimeError(f"Oodle decompressed {int(ret)} bytes but expected {expected_size}")
        return bytes(dst_buf.raw[:expected_size])


# Module-level cache
_oodle: Optional[OodleWrapper] = None


def has_oodle() -> bool:
    try:
        _ = OodleWrapper()
        return True
    except Exception:
        return False


def compress_kraken_block(data: bytes, level: int = 7) -> bytes:
    global _oodle
    if _oodle is None:
        _oodle = OodleWrapper()
    return _oodle.compress_kraken(data, level=level)


def decompress_kraken_block(comp: bytes, expected_size: int) -> bytes:
    global _oodle
    if _oodle is None:
        _oodle = OodleWrapper()
    return _oodle.decompress_kraken(comp, expected_size)


__all__ = ["OodleWrapper", "compress_kraken_block", "decompress_kraken_block", "has_oodle"]
