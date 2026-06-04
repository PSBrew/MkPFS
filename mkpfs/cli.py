"""Command-line interface for mkpfs package."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
import tempfile
import time
from collections.abc import Iterator
from contextlib import contextmanager, suppress
from pathlib import Path

from . import consts
from .logging import error, info, warning
from .pfs import (
    BuildError,
    BuildStats,
    ParsedDirent,
    PFSExtractionResult,
    PFSImageInfo,
    PFSImageInspection,
    build_expected_fpt,
    build_pfs,
    build_tree_from_uroot,
    choose_auto_fit_block_size,
    compose_pfs_mode_with_sign,
    estimate_file_data_footprint,
    extract_pfs_image,
    human_readable_size,
    inspect_pfs_image,
    parse_ekpfs_key_hex,
    parse_image_header,
    parse_image_inodes,
    parse_superroot_and_indexes,
    read_pfs_info,
    render_tree,
    validate_fpt_maps,
    validate_inode_layout,
    validate_input,
    validate_ps5_checklist,
    validate_source_match,
    verify_file_payload_hashes,
    verify_signed_image_signatures,
)
from .utils import (
    is_power_of_two,
    normalize_output_path,
    read_param_json,
    resolve_temp_root,
)


def print_build_parameters(
    source_path: Path,
    output_path: Path,
    temp_folder: Path,
    block_size: int,
    pfs_version: int,
    inode_bits: int,
    case_insensitive: bool,
    signed: bool,
    encrypted: bool,
    new_crypt: bool,
    compress: bool,
    threshold_gain: int,
    cpu_count: int,
    zlib_level: int,
    max_compressed_ratio: int | None,
    min_compress_size: int,
    dry_run: bool,
    require_game_files: bool,
    skip_executable_compression: bool = True,
) -> None:
    """Print build configuration at the start.

    Args:
        source_path: Original source path shown to the user.
        output_path: Final output image path.
        temp_folder: Temporary folder used for pack artifacts.
        block_size: PFS block size in bytes.
        pfs_version: PFS profile version number.
        inode_bits: Inode width in bits.
        case_insensitive: Whether case-insensitive mode is enabled.
        signed: Whether signed mode is enabled.
        encrypted: Whether encryption is enabled.
        new_crypt: Whether the alternate encryption derivation is enabled.
        compress: Whether PFSC compression is enabled.
        threshold_gain: Minimum per-block compression gain.
        cpu_count: Requested CPU worker count.
        zlib_level: Zlib compression level.
        max_compressed_ratio: Optional maximum compressed ratio.
        min_compress_size: Minimum file size eligible for compression.
        dry_run: Whether the build is a dry run.
        require_game_files: Whether strict game-file validation is enabled.
        skip_executable_compression: Whether executable-like files are stored raw.
    """
    mode: int = compose_pfs_mode_with_sign(inode_bits, case_insensitive, signed)
    if encrypted:
        mode |= consts.PFS_MODE_ENCRYPTED
    info("" + "=" * 70)
    info("PFS Image Builder - Parameters")
    info("" + "=" * 70)
    info(f"  Source path:       {source_path}")
    info(f"  Output path:       {output_path}")
    info(f"  Temp folder:       {temp_folder}")
    ver_label: str = "PS5" if pfs_version == consts.PFS_VERSION_PS5 else "PS4"
    info(f"  Version:           {pfs_version} ({ver_label})")
    compression_magic: str = describe_magic(magic=consts.PFSC_MAGIC) if compress else "none"
    info(f"  Header magic:      {describe_magic(magic=consts.PFS_MAGIC)}")
    info(f"  Compression Setup: {compression_magic}")
    info(f"  Block size:        {block_size:,} bytes ({block_size // 1024} KiB)")
    info(f"  Inode width:       {inode_bits}-bit")
    info(
        f"  PFS mode:          0x{mode:04X}  (Bit 0=signed, Bit 1=64-bit inodes, "
        "Bit 2=encrypted, Bit 3=case insensitive)"
    )
    info(f"    Signed:          {'yes' if mode & consts.PFS_MODE_SIGNED else 'no'}")
    info(f"    64-bit inodes:   {'yes' if mode & consts.PFS_MODE_64BIT_INODES else 'no'}")
    info(f"    Encrypted:       {'yes' if mode & consts.PFS_MODE_ENCRYPTED else 'no'}")
    info(f"    New crypt:       {'yes' if new_crypt else 'no'}")
    info(f"    Case insensitive: {'yes' if mode & consts.PFS_MODE_CASE_INSENSITIVE else 'no'}")
    info(f"  Compression:       {'enabled' if compress else 'disabled'}")
    if compress:
        info(f"    Skip executables: {'yes' if skip_executable_compression else 'no'}")
    info(f"  Game-file checks:   {'required' if require_game_files else 'disabled'}")
    if compress:
        info(f"  Threshold gain:    {threshold_gain}%")
        cpu_label: str = "auto (max(1, cpu_count()))" if cpu_count == 0 else str(max(1, cpu_count))
        info(f"  CPU cores:         {cpu_label}")
        info(f"  Zlib level:        {zlib_level}")
        if max_compressed_ratio is not None:
            info(f"  Max PFSC ratio:    {max_compressed_ratio}%")
        info(f"  Min compress size: {human_readable_size(min_compress_size)}")
    info(f"  Dry run:           {'yes' if dry_run else 'no'}")
    info("" + "=" * 70)


def format_magic_value(*, magic: int, width: int = 16) -> str:
    """Return a zero-padded hexadecimal representation of a magic value.

    Args:
        magic: Integer magic value to render.
        width: Hex digit width for zero-padding.

    Returns:
        Formatted hexadecimal string with ``0x`` prefix.
    """
    return f"0x{magic:0{width}X}"


def describe_magic(*, magic: int) -> str:
    """Return a human-friendly label for known PFS-related magic values.

    Args:
        magic: Integer magic value to describe.

    Returns:
        String label for known PFS or PFSC magic values, or a hex fallback for
        unknown values.
    """
    if magic == consts.PFS_MAGIC:
        return f"PFS ({magic})"
    if magic == consts.PFSC_MAGIC:
        return f"PFSC ({format_magic_value(magic=magic, width=8)})"
    return format_magic_value(magic=magic)


def _detect_title_id_from_source(source_path: Path) -> str | None:
    """Return the title ID from a source tree when ``sce_sys/param.json`` exists.

    Args:
        source_path: Source tree root to inspect.

    Returns:
        The trimmed title ID when the tree exposes a valid ``titleId`` or
        ``title_id`` entry, otherwise ``None``.
    """
    param_json: Path = source_path / "sce_sys" / "param.json"
    if not param_json.exists():
        return None

    try:
        parsed: dict[str, object] = read_param_json(param_json)
    except ValueError:
        return None

    title_id_value: object | None = parsed.get("titleId") or parsed.get("title_id")
    if isinstance(title_id_value, str):
        title_id: str = title_id_value.strip()
        if title_id:
            return title_id
    return None


def print_summary(stats: BuildStats) -> None:
    info("" + "=" * 70)
    info("Build Summary")
    info("" + "=" * 70)
    info(f"  Input path:              {stats.input_path}")
    info(f"  Output path:             {stats.output_path}")
    info(f"  Total files:             {stats.total_files:,}")
    info(f"  Total uncompressed size: {human_readable_size(stats.uncompressed_total_size)}")
    info(f"  Total stored size:       {human_readable_size(stats.stored_total_size)}")

    if stats.compression_enabled:
        info("\n  Compression Statistics:")
        info(f"    Compressed files:       {stats.compressed_files:,}")
        info(f"    Uncompressed files:     {stats.uncompressed_files:,}")
        info(f"    Actual gain achieved:   {stats.actual_gain_pct:.2f}%")
        info(
            "    All-PFSC gain:          "
            f"{stats.max_possible_gain_pct:.2f}%  "
            f"({human_readable_size(stats.all_compressed_total_size)} if every file used PFSC)"
        )
    else:
        info("\n  Compression:             disabled")

    aligned_total: int = stats.stored_total_size + stats.block_alignment_waste
    waste_pct: float = (stats.block_alignment_waste / aligned_total * 100.0) if aligned_total > 0 else 0.0
    info("\n  Block Alignment Waste:")
    info(f"    Block size:             {stats.block_size // 1024} KiB ({stats.block_size:,} bytes)")
    info(
        "    Wasted space:           "
        f"{human_readable_size(stats.block_alignment_waste)} "
        f"({waste_pct:.2f}% of file data blocks)"
    )

    info(f"\n  Elapsed time:            {stats.elapsed_seconds:.2f}s")

    if stats.total_files > 0:
        throughput: float = stats.uncompressed_total_size / (stats.elapsed_seconds + 0.001)
        info(f"  Throughput:              {human_readable_size(int(throughput))}/s")

    info("" * 70 + "\n")


def resolve_disk_usage_probe_path(*, output_path: Path) -> Path:
    """Resolve an existing path suitable for destination disk usage checks.

    Args:
        output_path: Requested output image path, possibly inside a directory
            tree that does not exist yet.

    Returns:
        Existing directory path to probe with ``shutil.disk_usage``.
    """
    probe_path: Path = output_path.parent
    root_path: Path = (probe_path.anchor and Path(probe_path.anchor)) or Path("/")
    while not probe_path.exists() and probe_path != root_path:
        probe_path = probe_path.parent
    return probe_path if probe_path.exists() else root_path


def calculate_source_raw_size_bytes(*, source_root: Path) -> int:
    """Calculate total raw byte size for all files inside a source tree.

    Args:
        source_root: Directory used as pack source.

    Returns:
        Sum of raw ``st_size`` values for all files in the source tree.
    """
    total_raw_size_bytes: int = 0
    candidate_path: Path
    for candidate_path in source_root.rglob("*"):
        if candidate_path.is_file():
            total_raw_size_bytes += candidate_path.stat().st_size
    return total_raw_size_bytes


def get_destination_space_error_message(*, source_root: Path, output_path: Path) -> str | None:
    """Build an insufficient-destination-space error for pack preflight.

    Args:
        source_root: Source directory whose raw file bytes must fit.
        output_path: Requested output image destination.

    Returns:
        Error text when free destination space is insufficient, otherwise
        ``None``.
    """
    required_raw_size_bytes: int = calculate_source_raw_size_bytes(source_root=source_root)
    probe_path: Path = resolve_disk_usage_probe_path(output_path=output_path)
    free_space_bytes: int = shutil.disk_usage(path=probe_path).free
    if free_space_bytes >= required_raw_size_bytes:
        return None
    required_size_gb: float = required_raw_size_bytes / float(1024**3)
    return (
        "ERROR: The destination file is on a disk that does not have enough space "
        f"({required_size_gb:.1f} GB) to perform the operation.\n"
        "Operation cancelled."
    )


def prompt_overwrite(output_path: Path) -> bool:
    """Prompt for overwrite and remove existing output artifacts when accepted.

    Args:
        output_path: Target output image path.

    Returns:
        ``True`` when the build should proceed, otherwise ``False``.
    """
    if not output_path.exists():
        return True

    info(f"Output file already exists: {output_path}")
    while True:
        response = input("Overwrite? [Y/n] ").strip().lower()
        if response in ("y", "yes", ""):
            with suppress(OSError):
                output_path.unlink()
            # Clean up any partial .tmp file if it exists
            tmp_path = Path(str(output_path) + ".tmp")
            if tmp_path.exists():
                with suppress(OSError):
                    tmp_path.unlink()
            return True
        if response in ("n", "no"):
            return False
        info("Please enter 'y' or 'n'")


def cleanup_pack_temp_artifacts(
    *, output_path: Path, temp_folder: Path | None = None, stale_age_seconds: int = 300
) -> None:
    """Remove stale temporary artifacts from interrupted pack runs.

    Args:
        output_path: Final output image path for the current run.
        temp_folder: Optional temporary folder to scan for stale spool files.
        stale_age_seconds: Minimum age in seconds for temp spool files to qualify
            as stale cleanup candidates.
    """
    tmp_path: Path = Path(str(output_path) + ".tmp")
    if tmp_path.exists():
        with suppress(OSError):
            tmp_path.unlink()

    temp_root: Path = resolve_temp_root(temp_folder=temp_folder)
    stale_cutoff_epoch: float = time.time() - max(0, stale_age_seconds)
    spool_path: Path
    for spool_path in temp_root.glob("mkpfs-*.pfsc"):
        if not spool_path.is_file():
            continue
        try:
            spool_mtime_epoch: float = spool_path.stat().st_mtime
        except OSError:
            continue
        if spool_mtime_epoch > stale_cutoff_epoch:
            continue
        with suppress(OSError):
            spool_path.unlink()


def run_image_check(
    image: Path,
    source: Path | None,
    print_tree: bool,
    expected_crc32: int | None = None,
    expected_manifest_sha256: str | None = None,
    emit_report: bool = True,
    ekpfs: bytes | None = None,
    new_crypt: bool = False,
) -> tuple[list[str], list[str], dict[int, list[ParsedDirent]], int]:
    errors: list[str] = []
    warnings: list[str] = []
    tree: dict[int, list[ParsedDirent]] = {}
    uroot_inode = -1

    if not image.exists() or not image.is_file():
        return [f"image path does not exist or is not a file: {image}"], [], tree, uroot_inode

    with image.open("rb") as fh:
        header = parse_image_header(fh)
        inodes = parse_image_inodes(fh, header, ekpfs=ekpfs, new_crypt=new_crypt)

        validate_inode_layout(header, inodes, errors, warnings)
        verify_signed_image_signatures(fh, header, inodes, errors, ekpfs=ekpfs, new_crypt=new_crypt)
        uroot_inode, fpt_map, collision_map, special_inodes = parse_superroot_and_indexes(
            fh,
            header,
            inodes,
            errors,
            ekpfs=ekpfs,
            new_crypt=new_crypt,
        )

        if uroot_inode >= 0:
            file_inodes, dir_inodes, tree = build_tree_from_uroot(
                fh,
                header,
                inodes,
                uroot_inode,
                errors,
                ekpfs=ekpfs,
                new_crypt=new_crypt,
            )

            case_insensitive = bool(header.mode & consts.PFS_MODE_CASE_INSENSITIVE)
            expected_fpt = build_expected_fpt(file_inodes, dir_inodes, case_insensitive)
            validate_fpt_maps(fpt_map, collision_map, expected_fpt, errors)
            validate_ps5_checklist(fh, header, inodes, file_inodes, warnings, errors, ekpfs=ekpfs, new_crypt=new_crypt)

            checked_files, data_crc32, manifest_sha256 = verify_file_payload_hashes(
                fh,
                header,
                inodes,
                file_inodes,
                errors,
                ekpfs=ekpfs,
                new_crypt=new_crypt,
            )

            if expected_crc32 is not None and data_crc32 != expected_crc32:
                errors.append(f"CRC32 mismatch: actual 0x{data_crc32:08X}, expected 0x{expected_crc32:08X}")
            if expected_manifest_sha256 is not None and manifest_sha256.lower() != expected_manifest_sha256.lower():
                errors.append(
                    f"Manifest SHA256 mismatch: actual {manifest_sha256}, expected {expected_manifest_sha256.lower()}"
                )

            reachable = set(file_inodes.values()) | set(dir_inodes.values()) | set(special_inodes)
            orphan_inodes = sorted(i.number for i in inodes if i.number not in reachable)
            if orphan_inodes:
                errors.append(
                    "orphan inodes not reachable from filesystem tree: "
                    + ", ".join(str(v) for v in orphan_inodes[:20])
                    + (" ..." if len(orphan_inodes) > 20 else "")
                )

            if source is not None:
                validate_source_match(
                    fh, header, inodes, file_inodes, source, errors, ekpfs=ekpfs, new_crypt=new_crypt
                )

            compressed_count = sum(1 for i in file_inodes.values() if inodes[i].is_compressed)
            total_logical = sum(max(0, inodes[i].logical_size) for i in file_inodes.values())
            total_stored = sum(max(0, inodes[i].stored_size) for i in file_inodes.values())

            if emit_report:
                payload_magic: str = describe_magic(magic=consts.PFSC_MAGIC) if compressed_count > 0 else "none"
                info("" + "=" * 70)
                info("PFS Check Report")
                info("" + "=" * 70)
                info(f"Image:                 {image}")
                ver_label: str = "PS5" if header.version == consts.PFS_VERSION_PS5 else "PS4"
                info(f"Version:               {header.version} ({ver_label})")
                info(f"Header magic:          {describe_magic(magic=header.magic)}")
                info(f"Compression Setup:     {payload_magic}")
                info(f"Read-only:             {'yes' if header.readonly else 'no'}")
                info(
                    "Mode:                  "
                    f"0x{header.mode:04X}  (Bit 0=signed, Bit 1=64-bit inodes, "
                    "Bit 2=encrypted, Bit 3=case insensitive)"
                )
                info(f"  Signed:              {'yes' if header.mode & consts.PFS_MODE_SIGNED else 'no'}")
                info(f"  64-bit inodes:       {'yes' if header.mode & consts.PFS_MODE_64BIT_INODES else 'no'}")
                info(f"  Encrypted:           {'yes' if header.mode & consts.PFS_MODE_ENCRYPTED else 'no'}")
                info(f"  Case insensitive:    {'yes' if header.mode & consts.PFS_MODE_CASE_INSENSITIVE else 'no'}")
                info(f"Block size:            {header.block_size:,} bytes")
                info(f"Inodes:                {len(inodes):,}")
                info(f"Directories:           {len(dir_inodes):,}")
                info(f"Files:                 {len(file_inodes):,}")
                info(f"Compressed files:      {compressed_count:,}")
                info(f"Files hash-checked:    {checked_files:,}")
                info(f"Data CRC32:            0x{data_crc32:08X}")
                info(f"Manifest SHA256:       {manifest_sha256}")
                info(f"Logical file bytes:    {total_logical:,}")
                info(f"Stored file bytes:     {total_stored:,}")
                info(f"flat_path_table keys:  {len(fpt_map):,}")
                info(f"Warnings:              {len(warnings)}")
                info(f"Errors:                {len(errors)}")
                info("=" * 70)

            if print_tree:
                info("/")
                for line in render_tree(tree, uroot_inode):
                    info(line)

    return errors, warnings, tree, uroot_inode


def cli_mkpfs_add_create_args(
    parser: argparse.ArgumentParser,
    *,
    source_arg_name: str = "source_dir",
    source_help: str = "Source app or homebrew folder",
    include_require_game_files: bool = True,
) -> None:
    """Add pack command arguments for folder or file workflows.

    Args:
        parser: Parser that receives the pack arguments.
        source_arg_name: Name of the positional source argument to add.
        source_help: Help text for the source positional argument.
        include_require_game_files: When True, expose the strict preflight flag.
    """
    parser.add_argument(source_arg_name, help=source_help)
    parser.add_argument("image_file", help="Output image file path")

    adjust_group = parser.add_mutually_exclusive_group()
    adjust_group.add_argument(
        "--adjust-output-file-extension",
        dest="adjust_output_file_extension",
        action="store_true",
        default=True,
        help="Automatically adjust the output extension to match the pack mode (default)",
    )
    adjust_group.add_argument(
        "--no-adjust-output-file-extension",
        dest="adjust_output_file_extension",
        action="store_false",
        help="Keep the requested output file name unchanged",
    )

    comp_group = parser.add_mutually_exclusive_group()
    comp_group.add_argument(
        "--compress", action="store_true", default=True, help="Enable PFSC block compression (default)"
    )
    comp_group.add_argument("--no-compress", action="store_true", help="Disable PFSC block compression")

    parser.add_argument(
        "--threshold-gain",
        type=int,
        default=0,
        help="Minimum per-block gain percent to keep PFSC-compressed blocks (default: 0)",
    )
    parser.add_argument(
        "--block-size",
        default="auto",
        help="PFS block size in bytes, 'auto' (65536), or 'auto-fit' to minimize estimated file-data padding",
    )
    parser.add_argument(
        "--temp-folder",
        help="Directory for temporary pack artifacts (defaults to the system temp folder)",
    )
    parser.add_argument("--version", choices=["PS4", "PS5"], default="PS4", help="PFS profile version (default: PS4)")
    parser.add_argument(
        "--inode-bits", type=int, choices=[32, 64], default=32, help="Inode width mode bit (32 or 64, default: 32)"
    )

    case_group = parser.add_mutually_exclusive_group()
    case_group.add_argument("--case-sensitive", action="store_true", help="Build a case-sensitive image")
    case_group.add_argument("--case-insensitive", action="store_true", help="Set case-insensitive mode bit (default)")

    parser.add_argument(
        "--cpu-count",
        type=int,
        default=0,
        help="Number of CPU cores for PFSC compression (0 = auto max(1, cpu_count()), non-zero = max(1, user value))",
    )
    parser.add_argument("--compression-level", type=int, default=9, help="Zlib compression level (0-9, default: 9)")
    parser.add_argument(
        "--max-compressed-ratio",
        type=int,
        default=None,
        help="Maximum PFSC size as percent of the raw file size (0-100)",
    )
    parser.add_argument(
        "--min-compress-size",
        type=int,
        default=0,
        help="Store files smaller than this many bytes raw without trying PFSC compression (default: 0)",
    )
    parser.add_argument(
        "--skip-executable-compression",
        action="store_true",
        default=True,
        help="Store eboot*.bin, *.prx, and *.sprx files raw even when PFSC compression is enabled",
    )
    parser.add_argument("--signed", action="store_true", help="Build a signed PFS image using zero EKPFS/seed")
    parser.add_argument("--encrypted", action="store_true", help="Encrypt filesystem blocks with AES-XTS")
    parser.add_argument("--ekpfs-key", help="Optional 64-hex EKPFS key, defaults to all zeros when omitted")
    if include_require_game_files:
        parser.add_argument(
            "--require-game-files",
            action="store_true",
            help="Require sce_sys/param.json and eboot.bin before packing",
        )
    parser.add_argument("--verbose", action="store_true", help="Verbose per-file decisions")
    parser.add_argument("--dry-run", action="store_true", help="Scan/layout/report only; do not write image")
    parser.add_argument("--verify", action="store_true", help="Run 'verify' after a successful pack")


def _resolve_pack_temp_folder(args: argparse.Namespace) -> Path:
    """Resolve the temporary folder used by pack workflows.

    Args:
        args: Parsed CLI arguments with an optional ``temp_folder`` attribute.

    Returns:
        Existing directory path used for temporary pack artifacts.
    """
    temp_folder_arg: str | None = getattr(args, "temp_folder", None)
    temp_folder: Path | None = Path(temp_folder_arg) if temp_folder_arg else None
    return resolve_temp_root(temp_folder=temp_folder)


def _run_pack_build(
    *,
    args: argparse.Namespace,
    build_source_root: Path,
    compare_source_root: Path,
    display_source_path: Path,
    temp_folder: Path,
    require_game_files: bool,
    desired_output_suffix: str,
    output_adjustment_message: str,
) -> int:
    """Execute a pack build from a prepared source directory.

    Args:
        args: Parsed CLI arguments shared by pack folder and pack file.
        build_source_root: Directory passed into the builder.
        compare_source_root: Directory used for optional post-build verification.
        display_source_path: Original user-facing source path shown in reports.
        temp_folder: Directory used for temporary pack artifacts.
        require_game_files: Whether to enforce the strict game-file preflight.
        desired_output_suffix: Output suffix to use when adjustment is enabled.
        output_adjustment_message: Log message emitted when the output suffix changes.

    Returns:
        Process exit code for the packing workflow.
    """
    output_path: Path
    output_changed: bool
    output_path, output_changed = normalize_output_path(
        args.image_file,
        desired_output_suffix,
        adjust=bool(getattr(args, "adjust_output_file_extension", True)),
    )
    output_path = output_path.expanduser().resolve()

    if output_changed:
        info(output_adjustment_message)

    if args.threshold_gain < 0 or args.threshold_gain > 100:
        raise BuildError("--threshold-gain must be within 0..100")

    block_size_arg: str = str(args.block_size).strip().lower() if isinstance(args.block_size, str) else ""
    if block_size_arg == "auto":
        block_size: int = 65536
    elif block_size_arg in {"auto-fit", "auto_small_files", "auto-small-files"}:
        block_size = choose_auto_fit_block_size(build_source_root)
        file_sizes = [p.stat().st_size for p in build_source_root.rglob("*") if p.is_file()]
        default_footprint: int = estimate_file_data_footprint(file_sizes=file_sizes, block_size=65536)
        selected_footprint: int = estimate_file_data_footprint(file_sizes=file_sizes, block_size=block_size)
        saved_bytes: int = max(0, default_footprint - selected_footprint)
        info(
            "Auto-fit block size selected: "
            f"{block_size:,} bytes ({block_size // 1024} KiB), "
            f"estimated file-data saving vs 64 KiB: {human_readable_size(saved_bytes)}"
        )
    else:
        try:
            block_size = int(args.block_size)
        except (TypeError, ValueError) as exc:
            raise BuildError("--block-size must be an integer value, 'auto', or 'auto-fit'") from exc

    if not is_power_of_two(block_size):
        raise BuildError("--block-size must be a power of two")
    if block_size < 0x1000 or block_size > 0x200000:
        raise BuildError("--block-size must be between 4096 and 2097152")

    if args.cpu_count < 0:
        raise BuildError("--cpu-count must be non-negative")

    if args.compression_level < 0 or args.compression_level > 9:
        raise BuildError("--compression-level must be within 0..9")

    if args.max_compressed_ratio is not None and (args.max_compressed_ratio < 0 or args.max_compressed_ratio > 100):
        raise BuildError("--max-compressed-ratio must be within 0..100")
    if args.min_compress_size < 0:
        raise BuildError("--min-compress-size must be non-negative")

    _title_id: str | None
    warnings: list[str]
    _title_id, warnings = validate_input(build_source_root, require_game_files=require_game_files)
    for w in warnings:
        warning(w)

    compress: bool = not args.no_compress
    min_file_gain: int = 100 - int(args.max_compressed_ratio) if args.max_compressed_ratio is not None else 0
    case_insensitive: bool = args.case_insensitive or not args.case_sensitive
    pfs_version: int = consts.PFS_VERSION_PS5 if args.version == "PS5" else consts.PFS_VERSION_PS4
    encrypted: bool = bool(getattr(args, "encrypted", False))
    new_crypt: bool = bool(getattr(args, "new_crypt", False))
    ekpfs_key: bytes = parse_ekpfs_key_hex(getattr(args, "ekpfs_key", None))
    if getattr(args, "ekpfs_key", None) and not encrypted:
        raise BuildError("--ekpfs-key requires --encrypted")

    print_build_parameters(
        display_source_path,
        output_path,
        temp_folder,
        block_size,
        pfs_version,
        args.inode_bits,
        case_insensitive,
        args.signed,
        encrypted,
        new_crypt,
        compress,
        args.threshold_gain,
        args.cpu_count,
        args.compression_level,
        args.max_compressed_ratio,
        args.min_compress_size,
        args.dry_run,
        require_game_files,
        bool(getattr(args, "skip_executable_compression", False)),
    )

    if not args.dry_run:
        destination_space_error: str | None = get_destination_space_error_message(
            source_root=build_source_root,
            output_path=output_path,
        )
        if destination_space_error is not None:
            error(destination_space_error)
            return 1

    if not args.dry_run:
        cleanup_pack_temp_artifacts(output_path=output_path, temp_folder=temp_folder)
    if not args.dry_run and not prompt_overwrite(output_path):
        info("Operation cancelled.")
        return 0

    stats: BuildStats = build_pfs(
        source_root=build_source_root,
        output_path=output_path,
        block_size=block_size,
        pfs_version=pfs_version,
        inode_bits=args.inode_bits,
        case_insensitive=case_insensitive,
        signed=args.signed,
        compress=compress,
        threshold_gain=args.threshold_gain,
        cpu_count=args.cpu_count,
        zlib_level=args.compression_level,
        dry_run=args.dry_run,
        verbose=args.verbose,
        encrypted=encrypted,
        new_crypt=new_crypt,
        ekpfs=ekpfs_key,
        skip_executable_compression=bool(getattr(args, "skip_executable_compression", False)),
        min_file_gain=min_file_gain,
        min_compress_size=args.min_compress_size,
        temp_folder=temp_folder,
    )

    stats.input_path = display_source_path
    print_summary(stats)
    if args.dry_run or not args.verify:
        return 0

    info("Running post-create check...")
    errors, warnings, _tree, _uroot = run_image_check(
        output_path,
        compare_source_root,
        print_tree=False,
        ekpfs=ekpfs_key,
        new_crypt=new_crypt,
    )

    for w in warnings:
        warning(w)
    for e in errors:
        error(e)
    return 1 if errors else 0


@contextmanager
def _stage_single_file_source_root(*, source_file: Path, temp_folder: Path | None = None) -> Iterator[Path]:
    """Yield a temporary source root exposing one file without copying data.

    The staged file is created as a hard link when possible, with a symlink
    fallback when hard linking is unavailable in the current environment.

    On Windows, hard links cannot cross drives (WinError 17) and symlinks
    require the "Create Symbolic Links" privilege (WinError 1314), which
    most users lack. If ``source_file`` and ``temp_folder`` reside on
    different devices, the staging directory is created next to the source
    file instead so the hard link succeeds.

    Args:
        source_file: Existing source file that should appear at the temporary
            root path.
        temp_folder: Optional temporary folder where the staging directory should
            be created.

    Yields:
        Temporary directory path containing exactly one file entry with the
        same file name as ``source_file``.

    Raises:
        BuildError: If no link strategy can stage the file.
    """
    # Determine the best location for the staging directory.
    # On Windows, hardlinks cannot cross drives (WinError 17) and symlinks
    # require the "Create Symbolic Links" privilege (WinError 1314), which
    # most users lack. Prefer the user's temp_folder, but fall back to
    # the source file's parent directory when they are on different drives.
    staging_base: Path = temp_folder if temp_folder is not None else source_file.parent
    try:
        if source_file.stat().st_dev != staging_base.stat().st_dev:
            staging_base = source_file.parent
    except OSError:
        pass  # stat failed, keep original base

    with tempfile.TemporaryDirectory(dir=str(staging_base)) as staging_dir_name:
        staging_root: Path = Path(staging_dir_name)
        staging_file: Path = staging_root / source_file.name
        try:
            os.link(src=source_file, dst=staging_file)
        except OSError:
            try:
                staging_file.symlink_to(target=source_file)
            except OSError as exc:
                raise BuildError(
                    "Unable to stage source file without copying, hard link and symlink both failed"
                ) from exc
        yield staging_root


def cli_mkpfs_create_run(args: argparse.Namespace) -> int:
    """Pack a folder into a PFS image.

    Args:
        args: Parsed CLI arguments with ``source_dir`` and ``image_file``.

    Returns:
        Process exit code for the folder packing workflow.
    """
    source_path: Path = Path(args.source_dir).expanduser().resolve()
    temp_folder: Path = _resolve_pack_temp_folder(args)
    title_id: str | None = _detect_title_id_from_source(source_path)
    desired_output_suffix: str = ".ffpfs" if title_id is not None else ".ffpfsc"
    output_adjustment_message: str
    if title_id is not None:
        output_adjustment_message = (
            "Raw game files detected inside the source folder, adjusting output file extension to .ffpfs"
        )
    else:
        output_adjustment_message = (
            "The folder does not seem to contain any direct game information, "
            "adjusting output file extension to .ffpfsc"
        )
    return _run_pack_build(
        args=args,
        build_source_root=source_path,
        compare_source_root=source_path,
        display_source_path=source_path,
        temp_folder=temp_folder,
        require_game_files=bool(getattr(args, "require_game_files", False)),
        desired_output_suffix=desired_output_suffix,
        output_adjustment_message=output_adjustment_message,
    )


def cli_mkpfs_pack_file_run(args: argparse.Namespace) -> int:
    """Pack a single file into a PFS image.

    Args:
        args: Parsed CLI arguments with ``source_file`` and ``image_file``.

    Returns:
        Process exit code for the file packing workflow.
    """
    source_file: Path = Path(args.source_file).expanduser().resolve()
    temp_folder: Path = _resolve_pack_temp_folder(args)
    if not source_file.exists() or not source_file.is_file():
        raise BuildError(f"--source-file must be an existing file: {source_file}")

    with _stage_single_file_source_root(source_file=source_file, temp_folder=temp_folder) as staging_root:
        return _run_pack_build(
            args=args,
            build_source_root=staging_root,
            compare_source_root=staging_root,
            display_source_path=source_file,
            temp_folder=temp_folder,
            require_game_files=False,
            desired_output_suffix=".ffpfsc",
            output_adjustment_message=(
                "Single file compression mode enabled, adjusting output file extension "
                "to match the container mode .ffpfsc"
            ),
        )


def cli_mkpfs_check_run(args: argparse.Namespace) -> int:
    image: Path = Path(args.image_file).expanduser().resolve()
    source_dir_arg: str | None = getattr(args, "source_dir", None)
    source_file_arg: str | None = getattr(args, "source_file", None)
    if source_dir_arg and source_file_arg:
        info("--source-dir and --source-file cannot be used together")
        return 2

    source: Path | None = None
    if source_dir_arg:
        source = Path(source_dir_arg).expanduser().resolve()
    elif source_file_arg:
        source_file: Path = Path(source_file_arg).expanduser().resolve()
        if not source_file.exists() or not source_file.is_file():
            info(f"--source-file must be an existing file: {source_file}")
            return 2
        with _stage_single_file_source_root(source_file=source_file) as staging_root:
            source = staging_root
            return _run_verify_check(
                image=image,
                source=source,
                args=args,
            )

    return _run_verify_check(
        image=image,
        source=source,
        args=args,
    )


def _run_verify_check(*, image: Path, source: Path | None, args: argparse.Namespace) -> int:
    """Run verify checks for a given image and optional source tree.

    Args:
        image: Image path to verify.
        source: Optional source directory used for comparison.
        args: Parsed CLI arguments with expected hash options and key settings.

    Returns:
        Process exit code, 0 when verification passes, 1 on verify errors, 2 on
        invalid argument values.
    """
    expected_crc32: int | None = None
    if args.expect_crc32:
        crc_text: str = args.expect_crc32.strip().lower()
        if crc_text.startswith("0x"):
            crc_text = crc_text[2:]
        if len(crc_text) == 0 or len(crc_text) > 8:
            info("--expected-crc32 must be a 32-bit hex value")
            return 2
        try:
            expected_crc32 = int(crc_text, 16)
        except ValueError:
            info("--expected-crc32 must be hex (example: 7F528D1F or 0x7F528D1F)")
            return 2
        if expected_crc32 < 0 or expected_crc32 > 0xFFFFFFFF:
            info("--expected-crc32 out of range")
            return 2

    expected_manifest_sha256: str | None = None
    if args.expect_manifest_sha256:
        digest: str = args.expect_manifest_sha256.strip().lower()
        if len(digest) != 64 or any(c not in "0123456789abcdef" for c in digest):
            info("--expected-manifest-sha256 must be a 64-hex SHA256 digest")
            return 2
        expected_manifest_sha256 = digest
    ekpfs_key: bytes = parse_ekpfs_key_hex(getattr(args, "ekpfs_key", None))
    new_crypt: bool = bool(getattr(args, "new_crypt", False))

    errors, warnings, _tree, _uroot = run_image_check(
        image,
        source,
        print_tree=False,
        expected_crc32=expected_crc32,
        expected_manifest_sha256=expected_manifest_sha256,
        ekpfs=ekpfs_key,
        new_crypt=new_crypt,
    )
    for w in warnings:
        warning(w)
    for e in errors:
        error(e)
    return 1 if errors else 0


def cli_mkpfs_ls_run(args: argparse.Namespace) -> int:
    image: Path = Path(args.image_file).expanduser().resolve()
    errors: list[str]
    _warnings: list[str]
    tree: dict[int, list[ParsedDirent]]
    uroot: int
    errors, _warnings, tree, uroot = run_image_check(
        image,
        source=None,
        print_tree=False,
        emit_report=False,
        ekpfs=parse_ekpfs_key_hex(getattr(args, "ekpfs_key", None)),
        new_crypt=bool(getattr(args, "new_crypt", False)),
    )
    if errors:
        for e in errors:
            error(e)
        return 1
    info("/")
    for line in render_tree(tree, uroot):
        info(line)
    return 0


def cli_mkpfs_info_run(args: argparse.Namespace) -> int:
    """Show lightweight PFS image metadata.

    Args:
        args: Parsed CLI arguments with `image` attribute.
    """
    image: Path = Path(args.image_file).expanduser().resolve()
    info_result: PFSImageInfo = read_pfs_info(image)

    # Print header-level metadata and any warnings/errors
    info("=" * 70)
    info("PFS Image Info")
    info("=" * 70)
    info(f"Image:       {image}")
    info(f"Size (bytes):{info_result.size_bytes}")
    if info_result.header is not None:
        info(f"Version:     {info_result.version_label} ({info_result.header.version})")
        info(f"Block size:  {info_result.header.block_size}")
        info(f"Header magic:{describe_magic(magic=info_result.header.magic)}")

    for w in info_result.warnings:
        warning(w)
    for e in info_result.errors:
        error(e)

    return 1 if info_result.errors else 0


def cli_mkpfs_analyze_run(args: argparse.Namespace) -> int:
    """Inspect a PFS image and emit a detailed report.

    Args:
        args: Parsed CLI arguments (image, source, expected hashes, print-tree).
    """
    image: Path = Path(args.image).expanduser().resolve()
    source: Path | None = Path(args.source).expanduser().resolve() if getattr(args, "source", None) else None

    # Parse optional expected CRC32
    expected_crc32: int | None = None
    if getattr(args, "expected_crc32", None):
        crc_text: str = args.expected_crc32.strip().lower()
        if crc_text.startswith("0x"):
            crc_text = crc_text[2:]
        try:
            expected_crc32 = int(crc_text, 16)
        except ValueError:
            info("--expected-crc32 must be hex (example: 7F528D1F or 0x7F528D1F)")
            return 2

    # Parse optional expected manifest digest
    expected_manifest_sha256: str | None = None
    if getattr(args, "expected_manifest_sha256", None):
        digest: str = args.expected_manifest_sha256.strip().lower()
        if len(digest) != 64 or any(c not in "0123456789abcdef" for c in digest):
            info("--expected-manifest-sha256 must be a 64-hex SHA256 digest")
            return 2
        expected_manifest_sha256 = digest

    # Run library inspection
    inspection: PFSImageInspection = inspect_pfs_image(
        image=image,
        source=source,
        expected_crc32=expected_crc32,
        expected_manifest_sha256=expected_manifest_sha256,
        ekpfs=parse_ekpfs_key_hex(getattr(args, "ekpfs_key", None)),
        new_crypt=bool(getattr(args, "new_crypt", False)),
    )

    # Emit report
    info("=" * 70)
    info("PFS Image Inspection")
    info("=" * 70)
    info(f"Image:    {image}")
    if inspection.header is not None:
        ver_label: str = "PS5" if inspection.header.version == consts.PFS_VERSION_PS5 else "PS4"
        info(f"Version:  {inspection.header.version} ({ver_label})")
        info(f"Magic:    {describe_magic(magic=inspection.header.magic)}")
        info(f"Block:    {inspection.header.block_size}")

    info(f"Warnings: {len(inspection.warnings)}")
    info(f"Errors:   {len(inspection.errors)}")

    for w in inspection.warnings:
        info(w)
    for e in inspection.errors:
        info(e)

    if getattr(args, "print_tree", False) and inspection.has_tree:
        info("/")
        for line in render_tree(inspection.dirents_by_inode, inspection.uroot_inode):
            info(line)

    return 1 if inspection.errors else 0


def cli_mkpfs_extract_run(args: argparse.Namespace) -> int:
    """Extract all files from a PFS image into a directory.

    Args:
        args: Parsed CLI arguments with `image`, `output`, and optional `overwrite`.
    """
    image: Path = Path(args.image_file).expanduser().resolve()
    output_path: Path = Path(args.output_dir).expanduser().resolve()

    if output_path.exists() and not args.overwrite:
        info(f"output path {output_path} exists (use --overwrite to force)")
        return 2

    # Perform extraction via library API
    result: PFSExtractionResult = extract_pfs_image(
        image=image,
        output_path=output_path,
        progress=None,
        ekpfs=parse_ekpfs_key_hex(getattr(args, "ekpfs_key", None)),
        new_crypt=bool(getattr(args, "new_crypt", False)),
    )

    for w in result.warnings:
        info(w)
    for e in result.errors:
        info(e)

    if result.errors:
        return 1

    info("Extraction complete:")
    info(f"  Output:       {result.output_path}")
    info(f"  Files written: {result.files_written}")
    info(f"  Dirs created:  {result.directories_created}")
    info(f"  Bytes written: {result.bytes_written}")
    return 0


def cli_mkpfs_main_parsers() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="mkpfs",
        description="CLI for pack folder/file, verify, inspect, tree, and unpack PFS operations",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    pack_parser = sub.add_parser("pack", help="Pack a folder or file into an image")
    pack_sub = pack_parser.add_subparsers(dest="pack_command", required=True)

    folder_parser = pack_sub.add_parser("folder", help="Build image from a source directory")
    cli_mkpfs_add_create_args(folder_parser)
    folder_parser.set_defaults(func=cli_mkpfs_create_run)

    file_parser = pack_sub.add_parser("file", help="Build image from a single source file")
    cli_mkpfs_add_create_args(
        file_parser,
        source_arg_name="source_file",
        source_help="Single source file to pack",
        include_require_game_files=False,
    )
    file_parser.set_defaults(
        inode_bits=32,
        func=cli_mkpfs_pack_file_run,
    )

    check_parser = sub.add_parser("verify", help="Validate image structure and payload checksums")
    check_parser.add_argument("image_file", help="Path to input .ffpfs image")
    check_source_group = check_parser.add_mutually_exclusive_group()
    check_source_group.add_argument("--source-dir", help="Optional source folder for hierarchy and payload comparison")
    check_source_group.add_argument(
        "--source-file",
        help="Optional source file for single-file image comparison",
    )
    check_parser.add_argument(
        "--expect-crc32",
        help="Expected cumulative data CRC32 (hex), fails if different",
    )
    check_parser.add_argument(
        "--expect-manifest-sha256",
        help="Expected manifest SHA256 (64 hex chars), fails if different",
    )
    check_parser.add_argument("--ekpfs-key", help="Optional 64-hex EKPFS key for encrypted images")
    check_parser.add_argument("--new-crypt", action="store_true", help="Use alternate newCrypt EKPFS derivation")
    check_parser.set_defaults(func=cli_mkpfs_check_run)

    inspect_parser = sub.add_parser("inspect", help="Inspect image metadata and integrity summary")
    inspect_parser.add_argument("image_file", help="Path to input .ffpfs image")
    inspect_parser.add_argument(
        "--format",
        choices=["text", "json"],
        default="text",
        help="Output format for inspection report",
    )
    inspect_parser.add_argument("--ekpfs-key", help="Optional 64-hex EKPFS key for encrypted images")
    inspect_parser.add_argument("--new-crypt", action="store_true", help="Use alternate newCrypt EKPFS derivation")
    inspect_parser.set_defaults(func=cli_mkpfs_inspect_run)

    ls_parser = sub.add_parser("tree", help="Print image tree representation")
    ls_parser.add_argument("image_file", help="Path to input .ffpfs image")
    ls_parser.add_argument("--ekpfs-key", help="Optional 64-hex EKPFS key for encrypted images")
    ls_parser.add_argument("--new-crypt", action="store_true", help="Use alternate newCrypt EKPFS derivation")
    ls_parser.set_defaults(func=cli_mkpfs_ls_run)

    extract_parser = sub.add_parser("unpack", help="Extract files from image to destination directory")
    extract_parser.add_argument("image_file", help="Path to input .ffpfs image")
    extract_parser.add_argument("output_dir", help="Destination directory for extraction")
    extract_parser.add_argument("--overwrite", action="store_true", help="Overwrite existing output path")
    extract_parser.add_argument("--ekpfs-key", help="Optional 64-hex EKPFS key for encrypted images")
    extract_parser.add_argument("--new-crypt", action="store_true", help="Use alternate newCrypt EKPFS derivation")
    extract_parser.set_defaults(func=cli_mkpfs_extract_run)

    return parser


def normalize_cli_argv_for_pack_compat(argv: list[str] | None = None) -> list[str] | None:
    """Normalize legacy pack argv layouts into the canonical subcommand shape.

    This keeps the current ``mkpfs pack folder|file ...`` interface and also
    accepts the older ``mkpfs pack <source> <image> ...`` form by inferring the
    missing pack mode from the source path.

    Args:
        argv: Optional CLI argument vector. When omitted, ``sys.argv[1:]`` is
            inspected and a rewritten list is returned only when needed.

    Returns:
        Rewritten argument list for legacy flat pack invocations, otherwise the
        original value.
    """
    effective_argv: list[str] = list(sys.argv[1:] if argv is None else argv)
    if len(effective_argv) < 3 or effective_argv[0] != "pack":
        return argv

    explicit_pack_mode: str = effective_argv[1]
    if explicit_pack_mode in {"folder", "file"} or explicit_pack_mode.startswith("-"):
        return argv

    source_path: Path = Path(explicit_pack_mode).expanduser()
    inferred_pack_mode: str = "file" if source_path.is_file() else "folder"
    normalized_argv: list[str] = ["pack", inferred_pack_mode, *effective_argv[1:]]
    return normalized_argv


def cli_mkpfs_main(argv: list[str] | None = None) -> int:
    parser: argparse.ArgumentParser = cli_mkpfs_main_parsers()
    normalized_argv: list[str] | None = normalize_cli_argv_for_pack_compat(argv)
    args = parser.parse_args(normalized_argv)
    return int(args.func(args))


def main(argv: list[str] | None = None) -> int:
    """Entry point used by the installed console script."""
    return cli_mkpfs_main(argv)


def cli_mkpfs_inspect_run(args: argparse.Namespace) -> int:
    """Inspect image metadata, warnings, and errors.

    Args:
        args: Parsed CLI arguments with `image_file` and optional `format`.

    Returns:
        Process exit code, 0 when inspection has no errors, else 1.
    """
    image: Path = Path(args.image_file).expanduser().resolve()
    inspection: PFSImageInspection = inspect_pfs_image(
        image=image,
        ekpfs=parse_ekpfs_key_hex(getattr(args, "ekpfs_key", None)),
    )

    if args.format == "json":
        payload: dict[str, object] = {
            "image": str(image),
            "has_header": inspection.header is not None,
            "version": inspection.header.version if inspection.header is not None else None,
            "block_size": inspection.header.block_size if inspection.header is not None else None,
            "warnings": inspection.warnings,
            "errors": inspection.errors,
        }
        print(json.dumps(payload, indent=2, sort_keys=True))
    else:
        info("=" * 70)
        info("PFS Image Inspection")
        info("=" * 70)
        info(f"Image:    {image}")
        if inspection.header is not None:
            ver_label: str = "PS5" if inspection.header.version == consts.PFS_VERSION_PS5 else "PS4"
            info(f"Version:  {inspection.header.version} ({ver_label})")
            info(f"Magic:    {describe_magic(magic=inspection.header.magic)}")
            info(f"Block:    {inspection.header.block_size}")
        info(f"Warnings: {len(inspection.warnings)}")
        info(f"Errors:   {len(inspection.errors)}")
        for warning_text in inspection.warnings:
            info(warning_text)
        for error_text in inspection.errors:
            info(error_text)

    return 1 if inspection.errors else 0
