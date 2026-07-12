"""Batch conversion orchestration for mkpfs.

Discovers packable items in a source directory, packs each one into a
``.ffpfsc`` image in an output directory, and reports results.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .logging import info, warning
from .utils import human_readable_size, is_ignored_name

# ---------------------------------------------------------------------------
# Data types
# ---------------------------------------------------------------------------


@dataclass
class BatchItem:
    """A discovered packable item in the source directory."""

    name: str
    source: Path
    kind: str  # "folder" or "file"


@dataclass
class BatchItemResult:
    """The outcome of packing a single batch item."""

    name: str
    kind: str
    status: str  # "converted", "skipped", "dry_run" or "error"
    output_path: Path | None = None
    raw_size: int = 0
    compressed_size: int = 0
    elapsed_seconds: float = 0.0
    error_message: str | None = None

    @property
    def savings_pct(self) -> float:
        if self.raw_size == 0:
            return 0.0
        return ((self.raw_size - self.compressed_size) / self.raw_size) * 100.0


@dataclass
class BatchSummary:
    """Aggregate results of a batch conversion run."""

    results: list[BatchItemResult] = field(default_factory=list)
    elapsed_seconds: float = 0.0

    @property
    def total_items(self) -> int:
        return len(self.results)

    @property
    def converted(self) -> int:
        return sum(1 for r in self.results if r.status == "converted")

    @property
    def skipped(self) -> int:
        return sum(1 for r in self.results if r.status == "skipped")

    @property
    def errors(self) -> int:
        return sum(1 for r in self.results if r.status == "error")

    @property
    def dry_run(self) -> int:
        return sum(1 for r in self.results if r.status == "dry_run")

    @property
    def total_raw_size(self) -> int:
        return sum(r.raw_size for r in self.results if r.status in ("converted", "skipped"))

    @property
    def total_compressed_size(self) -> int:
        return sum(r.compressed_size for r in self.results if r.status in ("converted", "skipped"))


# ---------------------------------------------------------------------------
# Discovery
# ---------------------------------------------------------------------------


def discover_batch_items(source_dir: Path) -> list[BatchItem]:
    """Return the packable items found directly inside *source_dir*.

    Iterates ``source_dir.iterdir()``. For each entry:

    * Skip names starting with ``"."`` (covers dotfiles and hidden files).
    * Skip entries matching :func:`is_ignored_name` (OS metadata like
      ``.DS_Store``, ``Thumbs.db``, etc.).
    * Directories → ``BatchItem(kind="folder")``.
    * Files with suffix ``.exfat`` or ``.ffpkg`` (case-insensitive) →
      ``BatchItem(kind="file")``.
    * All other files are silently ignored.

    Returns items sorted by ``name.lower()`` for deterministic ordering.
    """
    items: list[BatchItem] = []
    for entry in source_dir.iterdir():
        name: str = entry.name
        if name.startswith(".") or is_ignored_name(name):
            continue
        if entry.is_dir():
            items.append(BatchItem(name=name, source=entry, kind="folder"))
        elif entry.is_file():
            suffix: str = entry.suffix.lower()
            if suffix in (".exfat", ".ffpkg"):
                items.append(BatchItem(name=name, source=entry, kind="file"))
    items.sort(key=lambda i: i.name.lower())
    return items


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------


def _validate_batch_dirs(*, source_dir: Path, output_dir: Path) -> None:
    """Validate source and output directory constraints.

    Raises:
        BuildError: If *source_dir* is missing, not a directory, or if
            *output_dir* resolves inside *source_dir*.
    """
    from .pfs import BuildError

    if not source_dir.is_dir():
        raise BuildError(f"source directory does not exist or is not a directory: {source_dir}")
    resolved_src: Path = source_dir.resolve()
    resolved_out: Path = output_dir.resolve()
    if resolved_out == resolved_src or resolved_src in resolved_out.parents:
        raise BuildError("output directory cannot be inside the source directory")


# ---------------------------------------------------------------------------
# Reporting
# ---------------------------------------------------------------------------


def print_batch_pre_stats(
    *,
    source_dir: Path,
    output_dir: Path,
    items: list[BatchItem],
    pack_flags: dict[str, Any],
) -> None:
    """Print a summary of the batch before starting."""
    folders: int = sum(1 for i in items if i.kind == "folder")
    files: int = sum(1 for i in items if i.kind == "file")

    info("╔═══════════════════════════════════════╗")
    info("║          BATCH CONVERSION             ║")
    info("╚═══════════════════════════════════════╝")
    info(f"  Source  : {source_dir}")
    info(f"  Output  : {output_dir}")
    info(f"  Items   : {folders} folder(s), {files} file(s) — {len(items)} total")
    version_label: str = "PS5" if pack_flags.get("pfs_version") == 0x5000000 else "PS4"
    cpu_val: int | None = pack_flags.get("cpu_count", 0)
    cpu_label: str = str(cpu_val) if cpu_val else "auto"
    comp_enabled: bool = pack_flags.get("compress", True)
    comp_label: str = f"yes  (level {pack_flags.get('zlib_level', 7)})" if comp_enabled else "no"
    info(f"  Version : {version_label}")
    info(f"  Compress: {comp_label}")
    info(f"  CPUs    : {cpu_label}")
    info("")


def print_item_status(*, index: int, total: int, result: BatchItemResult) -> None:
    """Print a one-line status after each item is processed."""
    icon: str
    if result.status == "converted":
        icon = "✅"
    elif result.status == "skipped":
        icon = "⏭"
    else:
        icon = "❌"

    parts: list[str] = [f"[{index}/{total}] {icon} {result.name}"]

    if result.status == "converted":
        parts.append(f"→ {human_readable_size(result.compressed_size)}")
        if result.savings_pct > 0:
            parts.append(f"({result.savings_pct:.1f}% saved)")
        parts.append(f"in {result.elapsed_seconds:.1f}s")
    elif result.status == "skipped":
        parts.append("→ skipped (output exists)")
    elif result.status == "error":
        msg: str = result.error_message or "unknown error"
        # Truncate long messages
        if len(msg) > 80:
            msg = msg[:77] + "..."
        parts.append(f"→ {msg}")

    info("  " + "  ".join(parts))


def print_batch_summary(summary: BatchSummary) -> None:
    """Print a formatted summary table of all batch results."""
    total: int = summary.total_items
    if total == 0:
        return

    # Determine column widths
    name_w: int = max(len(r.name) for r in summary.results) + 2
    name_w = max(name_w, 20)
    size_w: int = 11  # "12.34 GB" fits

    sep: str = f"├{'─' * name_w}┼{'─' * 10}┼{'─' * size_w}┼{'─' * size_w}┼{'─' * 9}┤"

    info(f"┌{'─' * name_w}┬{'─' * 10}┬{'─' * size_w}┬{'─' * size_w}┬{'─' * 9}┐")
    header_nm: str = f"│ {'Name'.ljust(name_w - 2)}"
    header_st: str = f"│ {'Status'.ljust(8)}"
    header_rw: str = f"│ {'Raw'.rjust(size_w - 2)}"
    header_cs: str = f"│ {'Compressed'.rjust(size_w - 2)}"
    header_sv: str = f"│ {'Savings'.rjust(7)}│"
    info(f"{header_nm}{header_st}{header_rw}{header_cs}{header_sv}")
    info(sep)

    for r in summary.results:
        status_text: str
        if r.status == "converted":
            status_text = "✅ Done"
        elif r.status == "skipped":
            status_text = "⏭ Skipped"
        elif r.status == "dry_run":
            status_text = "🔍 Planned"
        else:
            status_text = "❌ Error"

        raw_str: str = human_readable_size(r.raw_size) if r.raw_size > 0 else "—"
        comp_str: str = human_readable_size(r.compressed_size) if r.compressed_size > 0 else ""
        savings_str: str = f"{r.savings_pct:.1f}%" if r.status == "converted" and r.savings_pct > 0 else "—"

        info(
            f"│ {r.name[: name_w - 2].ljust(name_w - 2)}"
            f"│ {status_text.ljust(8)}"
            f"│ {raw_str.rjust(size_w - 2)}"
            f"│ {comp_str.rjust(size_w - 2)}"
            f"│ {savings_str.rjust(7)}│"
        )
    info(sep)

    done_str: str = f"{summary.converted} done"
    if summary.dry_run:
        done_str += f", {summary.dry_run} planned"
    if summary.skipped:
        done_str += f", {summary.skipped} skipped"
    if summary.errors:
        done_str += f", {summary.errors} error{'s' if summary.errors != 1 else ''}"

    total_raw_str: str = human_readable_size(summary.total_raw_size) if summary.total_raw_size > 0 else "—"
    total_comp_str: str = (
        human_readable_size(summary.total_compressed_size) if summary.total_compressed_size > 0 else "—"
    )
    overall_savings: float = (
        ((summary.total_raw_size - summary.total_compressed_size) / summary.total_raw_size) * 100.0
        if summary.total_raw_size > 0 and summary.total_compressed_size > 0
        else 0.0
    )
    overall_str: str = f"{overall_savings:.1f}%" if overall_savings > 0 else "—"

    info(
        f"│ {'TOTALS (' + str(total) + ' items)'.ljust(name_w - 2)}"
        f"│ {done_str.ljust(8)}"
        f"│ {total_raw_str.rjust(size_w - 2)}"
        f"│ {total_comp_str.rjust(size_w - 2)}"
        f"│ {overall_str.rjust(7)}│"
    )
    info(f"└{'─' * name_w}┴{'─' * 10}┴{'─' * size_w}┴{'─' * size_w}┴{'─' * 9}┘")


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------


def run_batch(
    *,
    source_dir: Path,
    output_dir: Path,
    overwrite: bool = False,
    pack_flags: dict[str, Any],
    progress: Any = None,
) -> BatchSummary:
    """Discover items, pack each one, and return a summary.

    For each discovered item:

    1. Compute ``output_path = output_dir / f"{item.name}.ffpfsc"``.
    2. If it exists and *overwrite* is False → skip.
    3. If ``item.kind == "folder"`` → call
       :func:`mkpfs.pfs.build_pfs_stream_from_exfat`.
    4. If ``item.kind == "file"`` → call
       :func:`mkpfs.pfs.build_pfs_stream_single_file`.
    5. Wrap each call in try/except; on error → record and continue.

    Returns:
        Aggregate results for all items.

    Raises:
        BuildError: If source or output directories fail validation.
    """
    from .pfs import BuildError, BuildStats, build_pfs_stream_from_exfat, build_pfs_stream_single_file

    _validate_batch_dirs(source_dir=source_dir, output_dir=output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    items: list[BatchItem] = discover_batch_items(source_dir)
    if not items:
        return BatchSummary(results=[], elapsed_seconds=0.0)

    batch_start: float = time.time()
    results: list[BatchItemResult] = []
    dry_run: bool = pack_flags.get("dry_run", False)

    for idx, item in enumerate(items, start=1):
        output_path: Path = output_dir / f"{item.name}.ffpfsc"
        item_start: float = time.time()

        if output_path.exists() and not overwrite:
            # Get raw size for reporting even on skipped items
            raw_size: int = _estimate_raw_size(item)
            result = BatchItemResult(
                name=item.name,
                kind=item.kind,
                status="skipped",
                output_path=output_path,
                raw_size=raw_size,
                compressed_size=output_path.stat().st_size,
            )
            results.append(result)
            print_item_status(index=idx, total=len(items), result=result)
            continue

        if dry_run:
            raw_size = _estimate_raw_size(item)
            result = BatchItemResult(
                name=item.name,
                kind=item.kind,
                status="dry_run",
                output_path=output_path,
                raw_size=raw_size,
                compressed_size=0,
                elapsed_seconds=0.0,
            )
            results.append(result)
            info(f"  [{idx}/{len(items)}] 🔍 {item.name} → would pack to {output_path}")
            continue

        try:
            stats: BuildStats
            if item.kind == "folder":
                stats = build_pfs_stream_from_exfat(
                    source_root=item.source,
                    output_path=output_path,
                    block_size=pack_flags["block_size"],
                    pfs_version=pack_flags["pfs_version"],
                    case_insensitive=pack_flags.get("case_insensitive", True),
                    zlib_level=pack_flags["zlib_level"],
                    threshold_gain=pack_flags["threshold_gain"],
                    cpu_count=pack_flags["cpu_count"],
                    verbose=pack_flags.get("verbose", False),
                )
            else:
                stats = build_pfs_stream_single_file(
                    source_file=item.source,
                    output_path=output_path,
                    block_size=pack_flags["block_size"],
                    pfs_version=pack_flags["pfs_version"],
                    case_insensitive=pack_flags.get("case_insensitive", True),
                    zlib_level=pack_flags["zlib_level"],
                    threshold_gain=pack_flags["threshold_gain"],
                    min_file_gain=pack_flags["min_file_gain"],
                    min_compress_size=pack_flags["min_compress_size"],
                    cpu_count=pack_flags["cpu_count"],
                    compress=pack_flags["compress"],
                    verbose=pack_flags.get("verbose", False),
                    skip_executable_compression=pack_flags.get("skip_executable_compression", False),
                    inner_file_name=None,
                )

            elapsed: float = time.time() - item_start
            comp_size: int = output_path.stat().st_size
            result = BatchItemResult(
                name=item.name,
                kind=item.kind,
                status="converted",
                output_path=output_path,
                raw_size=stats.uncompressed_total_size,
                compressed_size=comp_size,
                elapsed_seconds=elapsed,
            )
            results.append(result)
            print_item_status(index=idx, total=len(items), result=result)

        except BuildError as exc:
            elapsed = time.time() - item_start
            results.append(
                BatchItemResult(
                    name=item.name,
                    kind=item.kind,
                    status="error",
                    output_path=output_path,
                    raw_size=0,
                    compressed_size=0,
                    elapsed_seconds=elapsed,
                    error_message=str(exc),
                )
            )
            warning(f"  [{idx}/{len(items)}] ❌ {item.name} failed: {exc}")
            continue
        except Exception as exc:
            elapsed = time.time() - item_start
            results.append(
                BatchItemResult(
                    name=item.name,
                    kind=item.kind,
                    status="error",
                    output_path=output_path,
                    raw_size=0,
                    compressed_size=0,
                    elapsed_seconds=elapsed,
                    error_message=str(exc),
                )
            )
            warning(f"  [{idx}/{len(items)}] ❌ {item.name} failed: {exc}")
            continue

    batch_elapsed: float = time.time() - batch_start
    return BatchSummary(results=results, elapsed_seconds=batch_elapsed)


def _estimate_raw_size(item: BatchItem) -> int:
    """Return a rough estimate of the uncompressed input size for an item.

    For files, use ``st_size``. For directories, sum file sizes recursively.
    """
    if item.kind == "file":
        return item.source.stat().st_size
    total: int = 0
    for fp in item.source.rglob("*"):
        if fp.is_file() and not fp.name.startswith(".") and not is_ignored_name(fp.name):
            total += fp.stat().st_size
    return total
