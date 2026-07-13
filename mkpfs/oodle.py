"""ctypes wrapper for Oodle LZ (Kraken) used by MkPFS.

This wrapper attempts to load a native liboo2core (user-provided) and expose
small helpers for compressing/decompressing blocks with Kraken. It aims to
mirror the calling conventions used by community wrappers (go-oodle) while
staying defensive: symbol resolution failures raise clear ImportError.

Notes:
- The native SDK exposes multiple variants historically; this wrapper sets
  argtypes conservatively to match common public bindings and passes NULL/0
  for optional pointer parameters.
- If you supply a DLL built for a different ABI/architecture than the host
  process, loading will fail or the native call may crash; ensure you use the
  correct platform binary.
"""

from __future__ import annotations

import ctypes
from ctypes import c_int, c_void_p, c_ssize_t, c_longlong
import os
import platform
from pathlib import Path
from typing import Optional

# Known Kraken compressor id
KRAKEN_COMPRESSOR_ID = 8

# Candidate lib names (OODLE_LIB env var overrides this list)
_CANDIDATE_LIB_NAMES = [
    os.environ.get("OODLE_LIB") if os.environ.get("OODLE_LIB") else None,
    # macOS
    "liboo2core.dylib",
    "liboo2core_9_macOS.dylib",
    "liboo2core_9.dylib",
    # Linux
    "liboo2core.so",
    "liboo2corelinux64.so.9",
    "liboo2core_9_linux.so",
    # Windows
    "oo2core_9_win64.dll",
    "oo2core_8_win64.dll",
]


def _find_oodle_lib() -> Optional[str]:
    """Locate a candidate Oodle library name or absolute path.

    Returns the first candidate that appears loadable via ctypes.
    """
    for name in _CANDIDATE_LIB_NAMES:
        if not name:
            continue
        p = Path(name)
        if p.is_absolute() and p.exists():
            return str(p)
        # Try to let the system loader resolve it by name
        try:
            ctypes.CDLL(name)
            return name
        except Exception:
            if platform.system() == "Windows":
                try:
                    ctypes.WinDLL(name)
                    return name
                except Exception:
                    pass
            continue
    return None


def _load_lib(lib_path: str):
    """Load library, preferring CDLL (cdecl). Returns (lib, loader_name)."""
    try:
        lib = ctypes.CDLL(lib_path)
        return lib, "CDLL"
    except Exception as exc:
        if platform.system() == "Windows":
            try:
                lib = ctypes.WinDLL(lib_path)
                return lib, "WinDLL"
            except Exception as exc2:
                raise ImportError(f"failed to load {lib_path}: {exc2}") from exc2
        raise


class OodleWrapper:
    """Runtime wrapper that exposes compress/decompress helpers."""

    def __init__(self, lib_path: Optional[str] = None) -> None:
        self.lib_path = lib_path or _find_oodle_lib()
        if not self.lib_path:
            raise ImportError(
                "Oodle library not found. Set OODLE_LIB env var to the path of liboo2core.*"
            )

        self._lib, self._loader = _load_lib(self.lib_path)

        # Resolve symbols
        try:
            self._compress_fn = getattr(self._lib, "OodleLZ_Compress")
        except AttributeError as exc:
            raise ImportError(f"Oodle library loaded from {self.lib_path} but OodleLZ_Compress symbol missing") from exc

        self._decompress_fn = getattr(self._lib, "OodleLZ_Decompress", None)

        # Return types: native functions return pointer-sized count (use signed)
        self._compress_fn.restype = c_ssize_t
        if self._decompress_fn is not None:
            self._decompress_fn.restype = c_ssize_t

        # Set argtypes to common, well-known bindings. Wrap in try/except so
        # the module still imports on variants that differ (we'll still call).
        try:
            # Compress signature (common binding / go-oodle):
            #   (int compressor, void* rawBuf, OO_SINTa rawSize, void* compBuf, OO_SINTa compBufSize,
            #    int level, uintptr options, uintptr dictionaryBase, uintptr lrm, uintptr scratchMem, uintptr scratchSize)
            self._compress_fn.argtypes = [
                c_int,      # compressor
                c_void_p,   # rawBuf
                c_ssize_t,  # rawSize
                c_void_p,   # compBuf
                c_ssize_t,  # compBufSize
                c_int,      # level
                c_void_p,   # options (uintptr)
                c_void_p,   # dictionaryBase (uintptr)
                c_void_p,   # lrm (uintptr)
                c_void_p,   # scratchMem (uintptr)
                c_void_p,   # scratchSize (uintptr)
            ]
        except Exception:
            # If the native ABI differs, fall back to a dynamic call without argtypes.
            pass

        if self._decompress_fn is not None:
            try:
                # Decompress signature (14 args variant)
                self._decompress_fn.argtypes = [
                    c_void_p,    # compBuf
                    c_ssize_t,   # compBufSize
                    c_void_p,    # rawBuf
                    c_longlong,  # rawBufSize (int64)
                    c_int,       # fuzzSafe
                    c_int,       # checkCRC
                    c_int,       # verbosity
                    c_void_p,    # decBufBase
                    c_longlong,  # decBufSize (int64)
                    c_void_p,    # fpCallback
                    c_void_p,    # callbackUserData
                    c_void_p,    # decoderMemory (uintptr)
                    c_longlong,  # decoderMemorySize (int64)
                    c_int,       # threadPhase
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

        # Build args matching the (compressor, rawBuf, rawSize, compBuf, compSize, level, ...)
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
            c_void_p(0),  # scratchSize
        )

        # Call
        ret = self._compress_fn(*args)
        if ret <= 0:
            raise RuntimeError(f"Oodle compression failed (return={ret})")

        return bytes(dst_buf.raw[: int(ret)])

    def decompress_kraken(self, comp: bytes, expected_size: int) -> bytes:
        """Decompress a Kraken-compressed block using Oodle.

        expected_size must be known in advance by the caller.
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
            c_longlong(expected_size),
            c_int(1),      # fuzzSafe
            c_int(1),      # checkCRC
            c_int(0),      # verbosity
            c_void_p(0),   # decBufBase
            c_longlong(0), # decBufSize
            c_void_p(0),   # fpCallback
            c_void_p(0),   # callbackUserData
            c_void_p(0),   # decoderMemory
            c_longlong(0), # decoderMemorySize
            c_int(3),      # threadPhase
        )

        ret = self._decompress_fn(*args)
        if ret < 0:
            raise RuntimeError(f"Oodle decompression failed (return={ret})")
        if int(ret) != expected_size:
            raise RuntimeError(f"Oodle decompressed {int(ret)} bytes but expected {expected_size}")

        return bytes(dst_buf.raw[: expected_size])


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