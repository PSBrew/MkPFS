#!/usr/bin/env python3
"""Generate multi-size ICO from source PNG for CI.

This script is deliberately small and dependency-light. It expects Pillow
to be available in the runtime environment; the workflow ensures installation
before calling this script.
"""

import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Any


def make_icon(src: Path, out: Path, sizes: Sequence[tuple[int, int]]) -> None:
    """Read PNG from src and write an ICO file to out containing the sizes."""
    try:
        from PIL import Image
    except ImportError as exc:  # pragma: no cover - runtime dependency
        print("Pillow not available:", exc, file=sys.stderr)
        raise

    if not src.exists():
        raise FileNotFoundError(f"source icon not found: {src}")

    img = Image.open(src).convert("RGBA")

    # Explicitly create each icon resolution to ensure multi-size ICO output.
    # Some Pillow/ICO combinations do not reliably embed multiple sizes when
    # only `sizes=` is provided without append_images.
    normalized_sizes: list[tuple[int, int]] = sorted(
        {(int(width), int(height)) for (width, height) in sizes},
        key=lambda size: (size[0], size[1]),
    )
    if not normalized_sizes:
        raise ValueError("at least one icon size must be provided")

    try:
        resample: Any = Image.Resampling.LANCZOS
    except AttributeError:  # pragma: no cover - Pillow compatibility
        resample = Image.LANCZOS

    resized_images: list[Image.Image] = [img.resize(size, resample=resample) for size in normalized_sizes]
    # Keep the largest image as the primary frame; Pillow's ICO writer may
    # only emit one frame when the base image is smallest.
    base_image: Image.Image = resized_images[-1]
    extra_images: list[Image.Image] = resized_images[:-1]

    out.parent.mkdir(parents=True, exist_ok=True)
    base_image.save(out, sizes=normalized_sizes, append_images=extra_images)
    print("Wrote", out)


def main() -> int:
    repo_root = Path(__file__).resolve().parents[1]
    src = repo_root / "assets" / "images" / "icon.png"
    out = repo_root / "dist" / "icon.ico"
    sizes = [(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)]

    try:
        make_icon(src=src, out=out, sizes=sizes)
    except Exception as exc:
        print("Icon generation failed:", exc, file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
