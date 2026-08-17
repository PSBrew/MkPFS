"""Benchmark compression backends on a 1 GB mixed-pattern file.

Generates (or reuses from cache) a 1 GB file with a mix of:
  - Zeros (very compressible)
  - Random/incompressible data (unique per run, not repeated)
  - FS-like metadata (semi-compressible)
  - Repeating text / log lines (very compressible)

Then runs each available backend 5 times and prints a summary.

Usage:

    uv run python scripts/bench_compression.py          # normal run, reuses cached file
    uv run python scripts/bench_compression.py --fresh   # regenerate test file
"""

from __future__ import annotations

import os
import struct
import sys
import time
from pathlib import Path

# Add project root so ``import mkpfs.compression`` works
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import mkpfs.compression as comp

TARGET = 1_073_741_824  # 1 GiB


# ---------------------------------------------------------------------------
# Generate a 1 GB mixed-pattern data block
# ---------------------------------------------------------------------------


def _make_patterns(size: int = TARGET) -> bytes:
    """Assemble *size* bytes from a mix of easy, hard, and realistic data."""
    parts: list[bytes] = []
    written = 0

    # 1. Zeros (very compressible) — 25%
    zeros = b"\x00" * 65536
    with memoryview(zeros) as mv:
        while written < size // 4:
            take = min(size // 4 - written, len(mv))
            parts.append(mv[:take].tobytes())
            written += take

    # 2. Random (incompressible) — 25%; unique chunks, not repeated
    while written < size // 2:
        need = min(size // 2 - written, 1_048_576)  # 1 MiB unique blocks
        parts.append(os.urandom(need))
        written += need

    # 3. FS-like metadata (semi-compressible) — 25%
    meta = b"".join(struct.pack("<IIII", i, i + 1, 0, 0x80000000) + b"\x00" * 48 for i in range(512))
    while written < size * 3 // 4:
        parts.append(meta)
        written += len(meta)

    # 4. Repeating text / log lines (very compressible) — 25%
    text = b"[INFO] test\n" * 5000
    while written < size:
        need = min(size - written, len(text))
        parts.append(text[:need])
        written += need

    return b"".join(parts)


CACHE_DIR = Path(__file__).resolve().parent.parent / "tmp"
CACHE_FILE = CACHE_DIR / "bench_1gib.dat"


def load_or_generate(fresh: bool = False) -> bytes:
    """Return cached 1 GiB data or generate + cache it."""
    if not fresh and CACHE_FILE.is_file():
        with CACHE_FILE.open("rb") as f:
            print(f"Reading cached file ({CACHE_FILE}) ...", end=" ", flush=True)
            data = f.read()
            print(f"{len(data) / 1_048_576:.0f} MiB")
            return data

    print(f"Generating {TARGET / 1_048_576:.0f} MiB mixed-pattern data...")
    before = time.perf_counter()
    data = _make_patterns(TARGET)
    gen_time = time.perf_counter() - before
    print(f"  Done in {gen_time:.2f}s")

    CACHE_DIR.mkdir(exist_ok=True, parents=True)
    with CACHE_FILE.open("wb") as f:
        f.write(data)
    print(f"  Cached to {CACHE_FILE}")

    return data


# ---------------------------------------------------------------------------
# Benchmark helpers
# ---------------------------------------------------------------------------


def bench_backend(backend: str, data: bytes, trials: int = 5) -> dict[str, float | str]:
    """Run *trials* of compress + decompress for *backend*.

    Returns a dict with timing / ratio info or an error string.
    """
    try:
        comp.set_backend(backend)
    except (ImportError, ValueError) as exc:
        return {"error": str(exc)}

    # warmup
    _ = comp.compress_block(data[:4096])

    # --- compress ---
    comp_times: list[float] = []
    compressed: bytes | None = None
    for _ in range(trials):
        before = time.perf_counter()
        compressed = comp.compress_block(data)
        elapsed = time.perf_counter() - before
        comp_times.append(elapsed)

    assert compressed is not None

    ratio = len(compressed) / len(data)

    # --- decompress ---
    decomp_times: list[float] = []
    for _ in range(trials):
        before = time.perf_counter()
        result = comp.decompress_block(compressed)
        elapsed = time.perf_counter() - before
        decomp_times.append(elapsed)

    assert result == data, f"Roundtrip mismatch for {backend}"

    def _stats(seq: list[float]) -> dict[str, float]:
        seq_s = sorted(seq)
        return {
            "avg_s": sum(seq_s) / len(seq_s),
            "min_s": seq_s[0],
            "max_s": seq_s[-1],
        }

    comp_stats = _stats(comp_times)
    decomp_stats = _stats(decomp_times)

    return {
        "original_mb": round(len(data) / 1_048_576, 1),
        "compressed_mb": round(len(compressed) / 1_048_576, 1),
        "ratio": round(ratio, 4),
        "compress": comp_stats,
        "decompress": decomp_stats,
    }


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> None:
    fresh = "--fresh" in sys.argv[1:]

    backends = ["zlib", "zlib-ng", "isal"]

    data = load_or_generate(fresh=fresh)
    print(f"Test data: {len(data) / 1_048_576:.0f} MiB\n")

    results: dict[str, dict] = {}

    for backend in backends:
        print(f"Benchmarking backend: {backend} ...", end=" ", flush=True)
        before = time.perf_counter()
        r = bench_backend(backend, data, trials=5)
        elapsed = time.perf_counter() - before
        results[backend] = r
        if "error" in r:
            print(f"ERROR — {r['error']}")
        else:
            print(f"done in {elapsed:.1f}s")

    # Print summary
    print()
    print("=" * 90)
    print(
        f"{'Backend':<12} {'Orig (MiB)':>10} {'Comp (MiB)':>10}"
        f" {'Ratio':>8} {'Cmp avg (s)':>11} {'Cmp MB/s':>9}"
        f" {'Dcmp avg (s)':>11} {'Dcmp MB/s':>9}"
    )
    print("-" * 90)

    for backend in backends:
        r = results.get(backend, {})
        if "error" in r:
            print(f"{backend:<12} {'ERROR':>10}  {r['error']}")
            continue
        comp_mbs = TARGET / 1_048_576 / r["compress"]["avg_s"] if r["compress"]["avg_s"] > 0 else 0
        decomp_mbs = TARGET / 1_048_576 / r["decompress"]["avg_s"] if r["decompress"]["avg_s"] > 0 else 0
        print(
            f"{backend:<12} {r['original_mb']:>10.0f} {r['compressed_mb']:>10.2f}"
            f" {r['ratio']:>8.4f} {r['compress']['avg_s']:>11.4f} {comp_mbs:>9.1f}"
            f" {r['decompress']['avg_s']:>11.4f} {decomp_mbs:>9.1f}"
        )

    # Speedup vs zlib
    print()
    print("Speedup vs stdlib zlib (compress):")
    z = results.get("zlib", {})
    if "error" not in z:
        z_avg = z["compress"]["avg_s"]
        for backend in [b for b in backends if b != "zlib"]:
            r = results.get(backend, {})
            if "error" in r:
                continue
            factor = z_avg / r["compress"]["avg_s"] if r["compress"]["avg_s"] > 0 else 0
            comp_mbs = TARGET / 1_048_576 / r["compress"]["avg_s"]
            print(f"  {backend:<12} {comp_mbs:>8.1f} MB/s  {factor:.2f}x  (ratio {r['ratio']})")

    print()
    print("All backends tested. Roundtrip verified.")


if __name__ == "__main__":
    main()
