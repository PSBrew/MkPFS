from pathlib import Path

import pytest

from mkpfs.gather import gather_files_scandir
from mkpfs.pbar import Progress
from mkpfs.pfs import BuildError, scan_source_tree
from mkpfs.utils import is_ignored_name


def _sorted_rel_paths(root: Path, paths: list[Path]) -> list[str]:
    return sorted([p.relative_to(root).as_posix() for p in paths])


def test_scandir_equals_rglob_small_tree(tmp_path: Path) -> None:
    # Create tree
    (tmp_path / "a").mkdir()
    (tmp_path / "a" / "file1.txt").write_text("x")
    (tmp_path / "b").mkdir()
    (tmp_path / "b" / "file2.txt").write_text("y")
    (tmp_path / "b" / "sub").mkdir()
    (tmp_path / "b" / "sub" / "file3.txt").write_text("z")

    # rglob baseline
    rglob_files = [
        p
        for p in tmp_path.rglob("*")
        if p.is_file() and not any(is_ignored_name(part) for part in p.relative_to(tmp_path).parts)
    ]
    rglob_sorted = _sorted_rel_paths(tmp_path, rglob_files)

    # scandir gather
    scandir_files = gather_files_scandir(tmp_path)
    scandir_sorted = _sorted_rel_paths(tmp_path, scandir_files)

    assert rglob_sorted == scandir_sorted


def test_ignored_names_are_excluded(tmp_path: Path) -> None:
    (tmp_path / "a").mkdir()
    (tmp_path / "a" / ".DS_Store").write_text("x")
    (tmp_path / "b").mkdir()
    (tmp_path / "b" / "file.txt").write_text("y")

    scandir_files = gather_files_scandir(tmp_path)
    rels = [p.relative_to(tmp_path).as_posix() for p in scandir_files]
    assert ".DS_Store" not in rels
    assert "b/file.txt" in rels


def test_scan_source_tree_non_ascii_raises(tmp_path: Path) -> None:
    # Create a file with non-ascii name
    (tmp_path / "dir").mkdir()
    bad_name = "não.txt"
    (tmp_path / "dir" / bad_name).write_text("x")

    # scan_source_tree should detect non-ascii names and raise BuildError
    with pytest.raises(BuildError):
        scan_source_tree(tmp_path, progress=Progress(enabled=False))
