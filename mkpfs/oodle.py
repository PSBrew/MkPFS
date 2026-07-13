"""Thin ctypes wrapper for the Oodle SDK (Kraken compressor/decompressor).

This module mirrors the calling conventions used by go-oodle
(https://github.com/new-world-tools/go-oodle) so the same prebuilt
release artifacts are compatible.

Library discovery order:
  1. OODLE_LIB environment variable (absolute path)
  2. ~/.oodle-libs/ directory
  3. Current working directory

If the library is not found on a supported platform (Windows x64, Linux x64),
the user is offered an auto-download from the go-oodle project releases.
macOS is not supported (no prebuilt library available) and raises ImportError.

The user is responsible for ensuring they have the appropriate license
for the Oodle SDK libraries. The libraries are not bundled with this
source code.
"""

from __future__ import annotations

import ctypes
import hashlib
import os
import platform
import urllib.request
from ctypes import c_int, c_void_p, c_longlong, c_size_t
from pathlib import Path
from typing import Optional

# --- Constants (match go-oodle) ---------------------------------------------

KRAKEN_COMPRESSOR_ID = 8

# Compression levels (go-oodle)
COMPRESSION_LEVEL_NORMAL = 4
COMPRESSION_LEVEL_OPTIMAL2 = 6
COMPRESSION_LEVEL_OPTIMAL3 = 7

# Decompress flags (go-oodle uses No/0)
FUZZ_SAFE_NO = 0
CHECK_CRC_NO = 0
VERBOSITY_NONE = 0
DECODE_THREAD_PHASE_ALL = 3

# --- Platform-specific download metadata ------------------------------------

# SHA256 hashes of the go-oodle v0.2.3-files release artifacts
_PLATFORM_INFO = {
    "windows": {
        "lib_name": "oo2core_9_win64.dll",
        "download_url": (
            "https://github.com/new-world-tools/go-oodle/releases/download/"
            "v0.2.3-files/oo2core_9_win64.dll"
        ),
        "sha256": "6f5d41a7892ea6b2db420f2458dad2f84a63901c9a93ce9497337b16c195f457",
    },
    "linux": {
        "lib_name": "liboo2corelinux64.so.9",
        "download_url": (
            "https://github.com/new-world-tools/go-oodle/releases/download/"
            "v0.2.3-files/liboo2corelinux64.so.9"
        ),
        "sha256": "7354655eb25b587dc34cbf98696b91e30e6d7a3f0eefad3872e6c1b76ef86a6e",
    },
}


def _get_platform_key() -> Optional[str]:
    """Return 'windows', 'linux', or None (unsupported like macOS)."""
    system = platform.system().lower()
    if system == "windows":
        return "windows"
    if system == "linux":
        return "linux"
    return None


def _oodle_libs_dir() -> Path:
    """Return the ~/.oodle-libs directory path."""
    return Path.home() / ".oodle-libs"


def _download_lib(info: dict) -> Path:
    """Download the library from go-oodle releases into ~/.oodle-libs/.

    Verifies SHA256 after download. If the hash mismatches, emits a warning
    but keeps the file (tries anyway).
    """
    dest_dir = _oodle_libs_dir()
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest_path = dest_dir / info["lib_name"]

    if dest_path.exists():
        return dest_path

    print(f"[oodle] Downloading {info['lib_name']} from go-oodle releases...")
    print(
        "[oodle] NOTE: The Oodle SDK is proprietary. It is YOUR responsibility "
        "to ensure you have the appropriate license to use this library."
    )
    urllib.request.urlretrieve(info["download_url"], str(dest_path))

    # Verify SHA256
    actual_hash = _sha256_file(dest_path)
    expected_hash = info["sha256"]
    if actual_hash != expected_hash:
        print(
            f"[oodle] WARNING: SHA256 mismatch! Expected {expected_hash}, "
            f"got {actual_hash}. The downloaded file may be corrupted or "
            f"tampered. Proceeding anyway, but use with caution."
        )
    else:
        print(f"[oodle] SHA256 verified: {actual_hash}")

    return dest_path


def _sha256_file(path: Path) -> str:
    """Compute SHA256 hex digest of a file."""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def _find_oodle_lib() -> Optional[str]:
    """Locate the Oodle library using the search order.

    1. OODLE_LIB env var
    2. ~/.oodle-libs/
    3. Current working directory
    """
    plat_key = _get_platform_key()

    # 1) Environment variable override
    env_path = os.environ.get("OODLE_LIB")
    if env_path:
        p = Path(env_path)
        if p.exists():
            return str(p)

    # 2) ~/.oodle-libs/
    if plat_key:
        lib_name = _PLATFORM_INFO[plat_key]["lib_name"]
        home_path = _oodle_libs_dir() / lib_name
        if home_path.exists():
            return str(home_path)

    # 3) Current working directory
    if plat_key:
        lib_name = _PLATFORM_INFO[plat_key]["lib_name"]
        cwd_path = Path.cwd() / lib_name
        if cwd_path.exists():
            return str(cwd_path)

    # Not found — offer download on supported platforms
    if plat_key is None:
        raise ImportError(
            f"Oodle is not available on {platform.system()}. "
            "No prebuilt library exists for this platform. "
            "Set OODLE_LIB to a compatible liboo2core if you have one."
        )

    # Supported platform but lib not found — offer to download
    info = _PLATFORM_INFO[plat_key]
    print(
        f"[oodle] Library '{info['lib_name']}' not found.\n"
        f"[oodle] Searched:\n"
        f"  1. OODLE_LIB env var: {env_path or '(not set)'}\n"
        f"  2. {_oodle_libs_dir() / info['lib_name']}\n"
        f"  3. {Path.cwd() / info['lib_name']}\n"
        f"[oodle] The Oodle SDK is proprietary. It is YOUR responsibility "
        f"to ensure you have the appropriate license.\n"
        f"[oodle] Downloading from go-oodle project releases..."
    )
    dest = _download_lib(info)
    return str(dest)


class OodleWrapper:
    """Runtime wrapper around a loaded Oodle library.

    The argtypes match the go-oodle Go function declarations exactly:
      compress: (int compressor, void* rawBuf, int rawSize, void* compBuf,
                 int level, uintptr options, uintptr dictionaryBase,
                 uintptr lrm, uintptr scratchMem, uintptr scratchSize) -> uintptr
      decompress: (void* compBuf, int compBufSize, void* rawBuf, int64 rawBufSize,
                   uintptr fuzzSafe, uintptr checkCRC, uintptr verbosity,
                   uintptr decBufBase, uintptr decBufSize, uintptr fpCallback,
                   uintptr callbackUserData, uintptr decoderMemory,
                   uintptr decoderMemorySize, uintptr threadPhase) -> uintptr
    """

    def __init__(self, lib_path: Optional[str] = None) -> None:
        if lib_path is None:
            lib_path = _find_oodle_lib()
        if not lib_path:
            raise ImportError(
                "Oodle library not found. Set OODLE_LIB or place the library "
                "in ~/.oodle-libs/ or the current directory."
            )

        self.lib_path = lib_path

        # Load library — CDLL (cdecl) on all platforms (x64 has one convention)
        try:
            self._lib = ctypes.CDLL(lib_path)
        except Exception:
            if platform.system() == "Windows":
                try:
                    self._lib = ctypes.WinDLL(lib_path)
                except Exception as exc:
                    raise ImportError(
                        f"Failed to load Oodle library '{lib_path}': {exc}"
                    ) from exc
            else:
                raise

        # Resolve symbols
        try:
            self._compress_fn = self._lib.OodleLZ_Compress
        except AttributeError as exc:
            raise ImportError(
                f"Oodle library loaded from {lib_path} but "
                f"OodleLZ_Compress symbol is missing"
            ) from exc

        self._decompress_fn = getattr(self._lib, "OodleLZ_Decompress", None)

        # Return type: pointer-sized unsigned (go-oodle uses uintptr)
        self._compress_fn.restype = c_size_t
        if self._decompress_fn is not None:
            self._decompress_fn.restype = c_size_t

        # Set argtypes to match go-oodle exactly
        # compress: 10 args (NO compBufSize — go-oodle omits it)
        try:
            self._compress_fn.argtypes = [
                c_int,      # compressor
                c_void_p,   # rawBuf
                c_int,      # rawSize (Go int → C int)
                c_void_p,   # compBuf
                c_int,      # level (Go int → C int)
                c_void_p,   # options (uintptr)
                c_void_p,   # dictionaryBase (uintptr)
                c_void_p,   # lrm (uintptr)
                c_void_p,   # scratchMem (uintptr)
                c_void_p,   # scratchSize (uintptr)
            ]
        except Exception:
            pass

        if self._decompress_fn is not None:
            # decompress: 14 args
            try:
                self._decompress_fn.argtypes = [
                    c_void_p,    # compBuf
                    c_int,       # compBufSize (Go int → C int)
                    c_void_p,    # rawBuf
                    c_longlong,  # rawBufSize (Go int64 → C int64)
                    c_void_p,    # fuzzSafe (uintptr)
                    c_void_p,    # checkCRC (uintptr)
                    c_void_p,    # verbosity (uintptr)
                    c_void_p,    # decBufBase (uintptr)
                    c_void_p,    # decBufSize (uintptr)
                    c_void_p,    # fpCallback (uintptr)
                    c_void_p,    # callbackUserData (uintptr)
                    c_void_p,    # decoderMemory (uintptr)
                    c_void_p,    # decoderMemorySize (uintptr)
                    c_void_p,    # threadPhase (uintptr)
                ]
            except Exception:
                pass

    def compress_kraken(self, data: bytes, level: int = 7) -> bytes:
        """Compress bytes with Kraken via Oodle.

        Matches go-oodle Compress(): output buffer = inputSize * 2, 10 args
        (no compBufSize passed to native).
        """
        if not data:
            return b""

        src_len = len(data)
        # go-oodle: outputSize = inputSize * 2
        dst_capacity = src_len * 2
        src_buf = ctypes.create_string_buffer(data, src_len)
        dst_buf = ctypes.create_string_buffer(dst_capacity)
        src_ptr = ctypes.c_void_p(ctypes.addressof(src_buf))
        dst_ptr = ctypes.c_void_p(ctypes.addressof(dst_buf))

        # 10 args matching go-oodle (NO compBufSize)
        ret = self._compress_fn(
            c_int(KRAKEN_COMPRESSOR_ID),
            src_ptr,
            c_int(src_len),
            dst_ptr,
            c_int(level),
            c_void_p(0),  # options
            c_void_p(0),  # dictionaryBase
            c_void_p(0),  # lrm
            c_void_p(0),  # scratchMem
            c_void_p(0),  # scratchSize
        )

        # go-oodle checks r1 == 0 for failure
        if ret == 0:
            raise RuntimeError("Oodle compression failed (return=0)")

        return bytes(dst_buf.raw[: int(ret)])

    def decompress_kraken(self, comp: bytes, expected_size: int) -> bytes:
        """Decompress a Kraken block using Oodle.

        Matches go-oodle Decompress(): uses FuzzSafeNo, CheckCRCNo, etc.
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

        ret = self._decompress_fn(
            src_ptr,
            c_int(comp_len),
            dst_ptr,
            c_longlong(expected_size),
            c_void_p(FUZZ_SAFE_NO),
            c_void_p(CHECK_CRC_NO),
            c_void_p(VERBOSITY_NONE),
            c_void_p(0),              # decBufBase
            c_void_p(0),              # decBufSize
            c_void_p(0),              # fpCallback
            c_void_p(0),              # callbackUserData
            c_void_p(0),              # decoderMemory
            c_void_p(0),              # decoderMemorySize
            c_void_p(DECODE_THREAD_PHASE_ALL),
        )

        # go-oodle checks r1 == 0 for failure
        if ret == 0:
            raise RuntimeError("Oodle decompression failed (return=0)")

        return bytes(dst_buf.raw[:expected_size])


# Module-level cache
_oodle: Optional[OodleWrapper] = None


def has_oodle() -> bool:
    """Return True if an Oodle library can be loaded."""
    try:
        _ = OodleWrapper()
        return True
    except Exception:
        return False


def compress_kraken_block(data: bytes, level: int = 7) -> bytes:
    """Compress a block using Kraken. Raises ImportError if no library."""
    global _oodle
    if _oodle is None:
        _oodle = OodleWrapper()
    return _oodle.compress_kraken(data, level=level)


def decompress_kraken_block(comp: bytes, expected_size: int) -> bytes:
    """Decompress a Kraken block. Raises ImportError if no library."""
    global _oodle
    if _oodle is None:
        _oodle = OodleWrapper()
    return _oodle.decompress_kraken(comp, expected_size)


__all__ = [
    "OodleWrapper",
    "compress_kraken_block",
    "decompress_kraken_block",
    "has_oodle",
]
