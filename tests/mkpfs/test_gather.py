"""Tests for mkpfs.gather.

Cover all code paths in gather_files_scandir, including cross-platform
edge cases: symlinks, ignored names at any nesting depth, and OSError
tolerance.
"""

from __future__ import annotations

import os
import platform
from pathlib import Path

import pytest

from mkpfs.gather import gather_files_scandir
from mkpfs.pbar import Progress
from mkpfs.pfs import BuildError, scan_source_tree
from mkpfs.utils import is_ignored_name


def _sorted_rel_paths(root: Path, paths: list[Path]) -> list[str]:
    """Convert absolute Paths to sorted relative strings for assertion."""
    return sorted(p.relative_to(root).as_posix() for p in paths)


_posix = pytest.mark.skipif(
    platform.system() == "Windows",
    reason="symlink creation needs elevated privileges on Windows",
)


# ---------------------------------------------------------------------------
# Basic traversal equivalence with rglob
# ---------------------------------------------------------------------------


def test_scandir_equals_rglob_small_tree(tmp_path: Path) -> None:
    """Results must match rglob on a small, clean tree."""
    (tmp_path / "a").mkdir()
    (tmp_path / "a" / "file1.txt").write_text("x")
    (tmp_path / "b").mkdir()
    (tmp_path / "b" / "file2.txt").write_text("y")
    (tmp_path / "b" / "sub").mkdir()
    (tmp_path / "b" / "sub" / "file3.txt").write_text("z")

    rglob_files = [
        p
        for p in tmp_path.rglob("*")
        if p.is_file() and not any(is_ignored_name(part) for part in p.relative_to(tmp_path).parts)
    ]
    scandir_files = gather_files_scandir(tmp_path)

    assert _sorted_rel_paths(tmp_path, scandir_files) == _sorted_rel_paths(tmp_path, rglob_files)


# ---------------------------------------------------------------------------
# Empty trees
# ---------------------------------------------------------------------------


def test_empty_directory_returns_empty(tmp_path: Path) -> None:
    """An empty directory should yield no files."""
    assert gather_files_scandir(tmp_path) == []


def test_empty_tree_with_ignored_files_only(tmp_path: Path) -> None:
    """A directory containing only ignored entries produces nothing."""
    (tmp_path / ".DS_Store").write_text("x")
    (tmp_path / "Thumbs.db").write_text("y")
    assert gather_files_scandir(tmp_path) == []


# ---------------------------------------------------------------------------
# Ignored names: top-level and nested
# ---------------------------------------------------------------------------


def test_ignored_names_are_excluded(tmp_path: Path) -> None:
    """Top-level ignored files must not appear in results."""
    (tmp_path / "a").mkdir()
    (tmp_path / "a" / ".DS_Store").write_text("x")
    (tmp_path / "b").mkdir()
    (tmp_path / "b" / "file.txt").write_text("y")

    scandir_files = gather_files_scandir(tmp_path)
    rels = [p.relative_to(tmp_path).as_posix() for p in scandir_files]
    assert ".DS_Store" not in rels
    assert "b/file.txt" in rels


def test_ignored_name_prefix_dot_underscore(tmp_path: Path) -> None:
    """Files matching ._* prefix must be excluded."""
    (tmp_path / "._preamble").write_text("x")
    (tmp_path / "normal.txt").write_text("y")
    (tmp_path / "sub").mkdir()
    (tmp_path / "sub" / "._other").write_text("z")
    (tmp_path / "sub" / "ok.txt").write_text("w")

    scandir_files = gather_files_scandir(tmp_path)
    rels = [p.relative_to(tmp_path).as_posix() for p in scandir_files]
    assert "._preamble" not in rels
    assert "sub/._other" not in rels
    assert "normal.txt" in rels
    assert "sub/ok.txt" in rels


def test_ignored_dir_nested_files_excluded(tmp_path: Path) -> None:
    """Files nested under an ignored directory must not appear.

    When gather encounters __MACOSX/, it never descends into it, so
    everything under it is automatically excluded.
    """
    (tmp_path / "__MACOSX").mkdir()
    (tmp_path / "__MACOSX" / "._bad.txt").write_text("x")
    (tmp_path / "__MACOSX" / "sub").mkdir()
    (tmp_path / "__MACOSX" / "sub" / "data.dat").write_text("y")
    (tmp_path / "normal").mkdir()
    (tmp_path / "normal" / "good.txt").write_text("z")

    scandir_files = gather_files_scandir(tmp_path)
    rels = [p.relative_to(tmp_path).as_posix() for p in scandir_files]
    assert "normal/good.txt" in rels
    assert "__MACOSX" not in rels
    assert "__MACOSX/._bad.txt" not in rels
    assert "__MACOSX/sub/data.dat" not in rels


# ---------------------------------------------------------------------------
# Symlinks (POSIX only: Linux, macOS)
# ---------------------------------------------------------------------------


@_posix
def test_directory_symlink_not_followed(tmp_path: Path) -> None:
    """Directory symlinks must not be descended into (loop prevention)."""
    real_dir = tmp_path / "real"
    real_dir.mkdir()
    (real_dir / "file.txt").write_text("content")

    link_dir = tmp_path / "link_to_real"
    link_dir.symlink_to(real_dir, target_is_directory=True)

    scandir_files = gather_files_scandir(tmp_path)
    rels = _sorted_rel_paths(tmp_path, scandir_files)

    # The file inside the real dir is found because it is traversed directly.
    assert "real/file.txt" in rels
    # The directory symlink itself is not a file and should not leak items.
    assert "link_to_real/file.txt" not in rels


@_posix
def test_directory_symlink_to_external_target(tmp_path: Path) -> None:
    """A directory symlink pointing outside root must not be followed."""
    outside = tmp_path / ".." / "external_dir"
    outside = outside.resolve()
    outside.mkdir(exist_ok=True)
    (outside / "leaked.txt").write_text("should_not_appear")

    (tmp_path / "real").mkdir()
    (tmp_path / "real" / "keep.txt").write_text("ok")

    link = tmp_path / "ext_link"
    link.symlink_to(outside, target_is_directory=True)

    scandir_files = gather_files_scandir(tmp_path)
    rels = _sorted_rel_paths(tmp_path, scandir_files)

    assert "real/keep.txt" in rels
    # The symlink points outside; with follow_symlinks=False it is not a
    # directory, so is_file() also returns False → skipped.
    assert "leaked.txt" not in rels


@_posix
def test_file_symlink_included(tmp_path: Path) -> None:
    """File symlinks must be included (is_file() follows symlinks by default)."""
    real_file = tmp_path / "real.txt"
    real_file.write_text("original")

    link_file = tmp_path / "mylink.txt"
    link_file.symlink_to(real_file)

    scandir_files = gather_files_scandir(tmp_path)
    rels = _sorted_rel_paths(tmp_path, scandir_files)
    assert "real.txt" in rels
    assert "mylink.txt" in rels


@_posix
def test_broken_symlink_excluded(tmp_path: Path) -> None:
    """A broken symlink (target does not exist) should be skipped."""
    target = tmp_path / "nonexistent.txt"
    link = tmp_path / "broken.link"
    link.symlink_to(target)

    scandir_files = gather_files_scandir(tmp_path)
    assert _sorted_rel_paths(tmp_path, scandir_files) == []


# ---------------------------------------------------------------------------
# OSError tolerance
# ---------------------------------------------------------------------------


def test_unreadable_subdirectory_skipped(tmp_path: Path) -> None:
    """A directory without read permission must be skipped."""
    good = tmp_path / "good"
    good.mkdir()
    (good / "file.txt").write_text("x")

    bad = tmp_path / "nope"
    bad.mkdir()
    (bad / "lost.txt").write_text("y")
    bad.chmod(0o000)

    try:
        scandir_files = gather_files_scandir(tmp_path)
        rels = _sorted_rel_paths(tmp_path, scandir_files)
        assert "good/file.txt" in rels
        assert "nope/lost.txt" not in rels
    finally:
        # Restore so tmp_path cleanup works on all platforms.
        if bad.exists():
            bad.chmod(0o755)


def test_non_directory_root_returns_empty(tmp_path: Path) -> None:
    """Passing a file path as root should yield empty results (OSError)."""
    regular_file = tmp_path / "just_a_file.txt"
    regular_file.write_text("hello")
    result = gather_files_scandir(regular_file)
    assert result == []


def test_nonexistent_root_returns_empty(tmp_path: Path) -> None:
    """Passing a nonexistent path as root should yield empty results."""
    nowhere = tmp_path / "does_not_exist"
    result = gather_files_scandir(nowhere)
    assert result == []


def test_entry_inspection_oserror_skipped(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """An entry whose is_dir or is_file raises OSError must be skipped.

    Monkey-patch os.DirEntry.is_dir on a specific entry to raise OSError,
    simulating a disappearing or unreadable entry during inspection.
    """
    (tmp_path / "a.txt").write_text("good")
    (tmp_path / "b.txt").write_text("should be skipped")

    real_is_dir = os.DirEntry.is_dir

    def broken_is_dir(self: os.DirEntry, **kwargs: object) -> bool:
        if self.name == "b.txt":
            msg = "simulated inspection failure"
            raise OSError(msg)
        return real_is_dir(self, **kwargs)

    monkeypatch.setattr(os.DirEntry, "is_dir", broken_is_dir)

    scandir_files = gather_files_scandir(tmp_path)
    rels = _sorted_rel_paths(tmp_path, scandir_files)
    assert "a.txt" in rels
    assert "b.txt" not in rels


# ---------------------------------------------------------------------------
# scan_source_tree integration
# ---------------------------------------------------------------------------


def test_scan_source_tree_non_ascii_raises(tmp_path: Path) -> None:
    """scan_source_tree must detect non-ASCII names and raise BuildError."""
    (tmp_path / "dir").mkdir()
    bad_name = "não.txt"
    (tmp_path / "dir" / bad_name).write_text("x")

    with pytest.raises(BuildError):
        scan_source_tree(tmp_path, progress=Progress(enabled=False))
