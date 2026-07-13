"""Thin ctypes wrapper for the Oodle SDK (Kraken compressor/decompressor).

This wrapper tries to load a compatible liboo2core runtime and expose two helpers:

- compress_kraken_block(data: bytes, level: int = 7) -> bytes
- decompress_kraken_block(comp: bytes, expected_size: int) -> bytes

On Windows the loader will prefer WinDLL (stdcall) and fall back to CDLL (cdecl)
if needed. Call failures that look like ABI mismatches attempt a single retry
with the alternate loader where feasible.
"""

from __future__ import annotations

import ctypes
import os
import platform
from ctypes import c_int, c_void_p
from ctypes import c_ssize_t
from typing import Optional

KRAKEN_COMPRESSOR_ID = 8

# Candidate library names to probe. OODLE_LIB env overrides probe order when set.
_CANDIDATE_LIB_NAMES = [
    os.environ.get("OODLE_LIB") if os.environ.get("OODLE_LIB") else None,
    # macOS candidates
    "liboo2core.dylib",
    "liboo2core_9_macOS.dylib",
    "liboo2core_9.dylib",
    # Unix/Linux candidates
    "liboo2core.so",
    "liboo2corelinux64.so.9",
    "liboo2core_9_linux.so",
    # Windows names
    "oo2core_9_win64.dll",
    "oo2core_8_win64.dll",
]


def _find_oodle_lib() -> Optional[str]:
    for name in _CANDIDATE_LIB_NAMES:
        if not name:
            continue
        if os.path.isabs(name) and os.path.exists(name):
            return name
        try:
            # Try to load by name via default loader search path
            # We attempt a platform-appropriate loader to test availability.
            if platform.system() == "Windows":
                ctypes.WinDLL(name)
            else:
                ctypes.CDLL(name)
            return name
        except Exception:
            continue
    return None


def _load_lib_with_loader(lib_path: str, prefer_windll: bool = False):
    """Attempt to load the library. On Windows try WinDLL first (if prefer_windll),
    otherwise use CDLL. Returns tuple(lib, loader_name).
    """
    loaders = []
    if platform.system() == "Windows":
        if prefer_windll:
            loaders = [ctypes.WinDLL, ctypes.CDLL]
        else:
            loaders = [ctypes.CDLL, ctypes.WinDLL]
    else:
        loaders = [ctypes.CDLL]

    last_exc = None
    for loader in loaders:
        try:
            lib = loader(lib_path)
            return lib, loader.__name__
        except Exception as e:
            last_exc = e
            continue
    raise ImportError(f"Failed to load Oodle library '{lib_path}' with loaders {loaders}: {last_exc}")


class OodleWrapper:
    def __init__(self, lib_path: Optional[str] = None):
        self.lib_path = lib_path or _find_oodle_lib()
        if not self.lib_path:
            raise ImportError(
                "Oodle library not found. Set OODLE_LIB env var to the path of liboo2core.dylib/.so/.dll"
            )

        # On Windows prefer WinDLL first; elsewhere use CDLL
        prefer_windll = platform.system() == "Windows"
        self._lib, self._loader = _load_lib_with_loader(self.lib_path, prefer_windll=prefer_windll)

        # Bind symbols
        try:
            self._compress_fn = getattr(self._lib, "OodleLZ_Compress")
        except AttributeError as exc:
            raise ImportError(f"Oodle library loaded from {self.lib_path} but OodleLZ_Compress symbol missing") from exc

        self._decompress_fn = getattr(self._lib, "OodleLZ_Decompress", None)

        # Restypes
        self._compress_fn.restype = c_ssize_t
        if self._decompress_fn is not None:
            self._decompress_fn.restype = c_ssize_t

        # Try to set argtypes (best-effort)
        try:
            self._compress_fn.argtypes = [
                c_int,      # compressor
                c_void_p,   # rawBuf
                c_ssize_t,  # rawLen
                c_void_p,   # compBuf
                c_ssize_t,  # compBufSize
                c_int,      # level
                c_int,      # fuzzSafe
                c_void_p,   # pOptions
                c_void_p,   # pLZBuffer
            ]
        except Exception:
            pass

        if self._decompress_fn is not None:
            try:
                self._decompress_fn.argtypes = [
                    c_void_p,   # compBuf
                    c_ssize_t,  # compBufSize
                    c_void_p,   # rawBuf
                    c_ssize_t,  # rawBufSize
                    c_int,      # fuzzSafe
                    c_int,      # checkCRC
                    c_int,      # verbosity
                    c_void_p,   # decBufBase
                    c_ssize_t,  # decBufSize
                    c_void_p,   # fpCallback
                    c_void_p,   # callbackUserData
                    c_ssize_t,  # decoderMemorySize
                    c_int,      # threadPhase
                ]
            except Exception:
                pass

    def _reload_with_alternate_loader(self):
        """Attempt to reload the library using the alternate loader (WinDLL vs CDLL) and rebind symbols."""
        alt_prefer_windll = (self._loader != 'WinDLL')
        self._lib, self._loader = _load_lib_with_loader(self.lib_path, prefer_windll=alt_prefer_windll)
        # rebind
        self._compress_fn = getattr(self._lib, "OodleLZ_Compress")
        self._compress_fn.restype = c_ssize_t
        try:
            self._compress_fn.argtypes = [
                c_int, c_void_p, c_ssize_t, c_void_p, c_ssize_t, c_int, c_int, c_void_p, c_void_p
            ]
        except Exception:
            pass
        self._decompress_fn = getattr(self._lib, "OodleLZ_Decompress", None)
        if self._decompress_fn is not None:
            self._decompress_fn.restype = c_ssize_t
            try:
                self._decompress_fn.argtypes = [
                    c_void_p, c_ssize_t, c_void_p, c_ssize_t, c_int, c_int, c_int, c_void_p, c_ssize_t, c_void_p, c_void_p, c_ssize_t, c_int
                ]
            except Exception:
                pass

    def compress_kraken(self, data: bytes, level: int = 7) -> bytes:
        if not data:
            return b""
        src_len = len(data)
        dst_capacity = src_len + max(4096, src_len // 100)
        src_buf = ctypes.create_string_buffer(data, src_len)
        dst_buf = ctypes.create_string_buffer(dst_capacity)
        src_ptr = ctypes.c_void_p(ctypes.addressof(src_buf))
        dst_ptr = ctypes.c_void_p(ctypes.addressof(dst_buf))

        args = (
            c_int(KRAKEN_COMPRESSOR_ID),
            src_ptr,
            c_ssize_t(src_len),
            dst_ptr,
            c_ssize_t(dst_capacity),
            c_int(level),
            c_int(0),
            c_void_p(0),
            c_void_p(0),
        )

        try:
            ret = self._compress_fn(*args)
        except OSError as e:
            # Try one automatic retry with alternate loader on Windows if ABI/conv mismatch suspected
            if platform.system() == 'Windows':
                try:
                    self._reload_with_alternate_loader()
                    ret = self._compress_fn(*args)
                except Exception:
                    raise
            else:
                raise

        if ret <= 0:
            raise RuntimeError(f"Oodle compression failed (return={ret})")

        return bytes(dst_buf.raw[: int(ret) ])

    def decompress_kraken(self, comp: bytes, expected_size: int) -> bytes:
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
            c_int(1),
            c_int(1),
            c_int(0),
            c_void_p(0),
            c_ssize_t(0),
            c_void_p(0),
            c_void_p(0),
            c_ssize_t(0),
            c_int(3),
        )

        try:
            ret = self._decompress_fn(*args)
        except OSError:
            if platform.system() == 'Windows':
                self._reload_with_alternate_loader()
                if self._decompress_fn is None:
                    raise ImportError("Oodle library does not export OodleLZ_Decompress after reload")
                ret = self._decompress_fn(*args)
            else:
                raise

        if ret < 0:
            raise RuntimeError(f"Oodle decompression failed (return={ret})")
        if int(ret) != expected_size:
            raise RuntimeError(f"Oodle decompressed {int(ret)} bytes but expected {expected_size}")

        return bytes(dst_buf.raw[: expected_size ])


# Module cache
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


__all__ = ["compress_kraken_block", "decompress_kraken_block", "has_oodle", "OodleWrapper"]