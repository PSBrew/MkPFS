"""Gather helpers for MkPFS.

Provide a scandir-based file gather implementation as a faster, low-level
alternative to Path.rglob("*"). Keep this module minimal and dependency-free
other than mkpfs.utils.is_ignored_name.
"""

from __future__ import annotations

import os
from pathlib import Path

from .utils import is_ignored_name


def gather_files_scandir(root: Path) -> list[Path]:
    """Walk ``root`` using os.scandir and return a list of file Paths.

    Rules:
    - Skip names where ``is_ignored_name(name)`` is True (applies to files and
      directories).
    - Do NOT follow directory symlinks (to avoid loops). File symlinks are
      included (entry.is_file() follows symlinks).
    - Return Path objects (not resolved); the caller is responsible for any
      normalization or resolution.

    The caller is responsible for any additional validation (non-ASCII names,
    deterministic global sorting, etc.). This helper focuses on fast traversal.
    """
    root = Path(root)
    abs_files: list[Path] = []
    stack: list[Path] = [root]

    while stack:
        dir_path = stack.pop()
        try:
            with os.scandir(dir_path) as it:
                entries = list(it)
        except OSError:
            # Mirror conservative behavior: skip directories we cannot access
            # or that disappear during traversal (PermissionError,
            # FileNotFoundError, NotADirectoryError, etc.).
            continue

        for entry in entries:
            name = entry.name
            if is_ignored_name(name):
                continue

            try:
                # Directories: descend but do NOT follow symlinks
                if entry.is_dir(follow_symlinks=False):
                    stack.append(dir_path / name)
                    continue

                # Files: include regular files and file symlinks
                if entry.is_file():
                    abs_files.append(dir_path / name)
            except OSError:
                # If the entry disappears or cannot be inspected, skip it.
                continue

    return abs_files
