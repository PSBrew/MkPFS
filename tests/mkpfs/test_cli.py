from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
import unittest
from contextlib import ExitStack, redirect_stderr, redirect_stdout
from io import StringIO
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import mkpfs.cli as cli
from mkpfs import consts
from mkpfs.cli import cli_mkpfs_main
from mkpfs.pfs import (
    BuildError,
    BuildStats,
    ParsedDirent,
    PFSExtractionResult,
    PFSImageInfo,
    PFSImageInspection,
    parse_image_header,
)


class CliTestCase(unittest.TestCase):
    """Shared helpers for CLI-related unittest-style tests."""

    def make_temp_path(self) -> Path:
        """Create and register a temporary directory path for the current test."""
        temp_dir: tempfile.TemporaryDirectory[str] = tempfile.TemporaryDirectory()
        self.addCleanup(temp_dir.cleanup)
        return Path(temp_dir.name)

    def make_valid_source(self, root: Path) -> Path:
        """Create a minimal valid source tree for pack-related tests."""
        source_path: Path = root / "src"
        sce_sys_path: Path = source_path / "sce_sys"
        sce_sys_path.mkdir(parents=True)
        (sce_sys_path / "param.json").write_text(json.dumps({"titleId": "ABC123"}), encoding="utf-8")
        (source_path / "eboot.bin").write_text("x", encoding="utf-8")
        return source_path

    def make_build_stats(self, root: Path) -> BuildStats:
        """Create a small BuildStats object for summary and create-run tests."""
        stats: BuildStats = BuildStats(input_path=root / "src", output_path=root / "out.ffpfs")
        stats.total_files = 2
        stats.uncompressed_total_size = 1024
        stats.stored_total_size = 512
        stats.compression_enabled = True
        stats.compressed_files = 1
        stats.uncompressed_files = 1
        stats.all_compressed_total_size = 400
        stats.block_alignment_waste = 128
        stats.block_size = 65536
        stats.elapsed_seconds = 1.5
        return stats

    def make_create_args(self, *, source_path: Path, image_path: Path, dry_run: bool, verify: bool) -> SimpleNamespace:
        """Build a baseline namespace for pack command tests."""
        return SimpleNamespace(
            source_dir=str(source_path),
            image_file=str(image_path),
            temp_folder=None,
            adjust_output_file_extension=True,
            no_compress=False,
            threshold_gain=20,
            block_size="auto",
            version="PS4",
            inode_bits=32,
            case_sensitive=False,
            case_insensitive=True,
            cpu_count=0,
            compression_level=7,
            min_compress_size=0,
            max_compressed_ratio=None,
            signed=False,
            encrypted=False,
            ekpfs_key=None,
            require_game_files=False,
            verbose=False,
            dry_run=dry_run,
            verify=verify,
            verify_structure=True,
            skip_verification=False,
        )

    def make_pack_file_args(
        self, *, source_path: Path, image_path: Path, dry_run: bool, verify: bool
    ) -> SimpleNamespace:
        """Build a baseline namespace for pack-file command tests."""
        return SimpleNamespace(
            source_file=str(source_path),
            image_file=str(image_path),
            temp_folder=None,
            adjust_output_file_extension=True,
            no_compress=False,
            threshold_gain=20,
            block_size="auto",
            version="PS4",
            inode_bits=32,
            case_sensitive=False,
            case_insensitive=True,
            cpu_count=0,
            compression_level=7,
            min_compress_size=0,
            max_compressed_ratio=None,
            signed=False,
            encrypted=False,
            ekpfs_key=None,
            use_spool=False,
            rename_inner_image=True,
            verbose=False,
            dry_run=dry_run,
            verify=verify,
            verify_structure=True,
            skip_verification=False,
        )


class TestCliSmokeIntegration(CliTestCase):
    """Smoke tests for the installed CLI entrypoints and help output."""

    def test_top_level_help_prints_the_project_description(self) -> None:
        """The top-level CLI help should exit successfully and print the main description."""
        buffer: StringIO = StringIO()
        with self.assertRaises(SystemExit) as excinfo, redirect_stdout(buffer):
            cli_mkpfs_main(["-h"])

        self.assertEqual(excinfo.exception.code, 0)
        self.assertIn(cli.get_output_title(), buffer.getvalue())
        self.assertIn("CLI for pack folder/file, verify, inspect, tree, and unpack PFS operations", buffer.getvalue())

    def test_top_level_version_flag_prints_version_and_exits_successfully(self) -> None:
        """The top-level CLI should print the package version for -V."""
        buffer: StringIO = StringIO()
        with redirect_stdout(buffer):
            exit_code: int = cli_mkpfs_main(["-V"])

        self.assertEqual(exit_code, 0)
        self.assertEqual(buffer.getvalue().strip(), cli.get_help_title())

    def test_verify_subcommand_help_lists_expected_options(self) -> None:
        """The verify subcommand help should list the image and source options."""
        result: subprocess.CompletedProcess[str] = subprocess.run(
            [sys.executable, "-m", "mkpfs", "verify", "--help"],
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0)
        self.assertIn(cli.get_help_title(), result.stdout)
        self.assertIn("image_file", result.stdout)
        self.assertIn("--source-dir", result.stdout)
        self.assertIn("--require-game-files", result.stdout)

    def test_pack_subcommand_help_lists_expected_positionals(self) -> None:
        """The pack folder and file help should list the expected positional arguments."""
        result: subprocess.CompletedProcess[str] = subprocess.run(
            [sys.executable, "-m", "mkpfs", "pack", "folder", "--help"],
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0)
        self.assertIn(cli.get_help_title(), result.stdout)
        self.assertIn("source_dir", result.stdout)
        self.assertIn("image_file", result.stdout)
        self.assertIn("--require-game-files", result.stdout)
        self.assertIn("--verify-structure", result.stdout)
        self.assertIn("--no-verify-structure", result.stdout)
        self.assertIn("--skip-verification", result.stdout)

        result = subprocess.run(
            [sys.executable, "-m", "mkpfs", "pack", "file", "--help"],
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0)
        self.assertIn(cli.get_help_title(), result.stdout)
        self.assertIn("source_file", result.stdout)
        self.assertIn("image_file", result.stdout)
        self.assertIn("--verify-structure", result.stdout)
        self.assertIn("--no-verify-structure", result.stdout)
        self.assertIn("--skip-verification", result.stdout)
        self.assertNotIn("--require-game-files", result.stdout)

    def test_pack_file_defaults_to_32_bit_inodes_and_verify_source_file_succeeds(self) -> None:
        """Single-file packing should keep 32-bit inode defaults and verify against the source file."""
        tmp_path: Path = self.make_temp_path()
        source_file: Path = tmp_path / "payload.bin"
        image_path: Path = tmp_path / "output.ffpfsc"
        source_file.write_bytes((b"A" * 200_000) + (b"B" * 150_000) + (b"C" * 50_000))

        pack_result: subprocess.CompletedProcess[str] = subprocess.run(
            [sys.executable, "-m", "mkpfs", "pack", "file", str(source_file), str(image_path)],
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(pack_result.returncode, 0, msg=pack_result.stdout + pack_result.stderr)
        self.assertTrue(image_path.exists())

        with image_path.open("rb") as image_handle:
            header = parse_image_header(image_handle)
        self.assertFalse(bool(header.mode & consts.PFS_MODE_64BIT_INODES))

        verify_result: subprocess.CompletedProcess[str] = subprocess.run(
            [sys.executable, "-m", "mkpfs", "verify", str(image_path), "--source-file", str(source_file)],
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(verify_result.returncode, 0, msg=verify_result.stdout + verify_result.stderr)
        self.assertIn("Errors:                0", verify_result.stdout)


class TestCliArgumentHelpers(CliTestCase):
    """Tests for the canonical pack parser helpers."""

    def test_main_parser_exposes_expected_subcommands(self) -> None:
        """The canonical CLI parser should register the expected subcommands."""
        parser: argparse.ArgumentParser = cli.cli_mkpfs_main_parsers()
        choices: dict[str, argparse.ArgumentParser] = next(
            action.choices for action in parser._actions if isinstance(action, argparse._SubParsersAction)
        )
        self.assertEqual(set(choices), {"pack", "verify", "inspect", "tree", "unpack"})

    def test_pack_parser_uses_default_compression_level_of_nine(self) -> None:
        """The pack parser should expose 9 as the default compression level."""
        parser: argparse.ArgumentParser = cli.cli_mkpfs_main_parsers()
        pack_parser: argparse.ArgumentParser = next(
            action.choices["pack"] for action in parser._actions if isinstance(action, argparse._SubParsersAction)
        )
        pack_choices: dict[str, argparse.ArgumentParser] = next(
            action.choices for action in pack_parser._actions if isinstance(action, argparse._SubParsersAction)
        )
        folder_parser: argparse.ArgumentParser = pack_choices["folder"]
        compression_action = next(
            action for action in folder_parser._actions if getattr(action, "dest", "") == "compression_level"
        )
        self.assertEqual(compression_action.default, 7)

    def test_pack_parser_uses_five_as_default_threshold_gain(self) -> None:
        """The pack parser should expose 5 as the default threshold gain."""
        parser: argparse.ArgumentParser = cli.cli_mkpfs_main_parsers()
        pack_parser: argparse.ArgumentParser = next(
            action.choices["pack"] for action in parser._actions if isinstance(action, argparse._SubParsersAction)
        )
        pack_choices: dict[str, argparse.ArgumentParser] = next(
            action.choices for action in pack_parser._actions if isinstance(action, argparse._SubParsersAction)
        )
        folder_parser: argparse.ArgumentParser = pack_choices["folder"]
        threshold_action: argparse.Action = next(
            action for action in folder_parser._actions if getattr(action, "dest", "") == "threshold_gain"
        )
        self.assertEqual(threshold_action.default, 5)

    def test_pack_parser_uses_thirty_two_as_default_inode_bits(self) -> None:
        """The pack parser should expose 32 as the default inode width."""
        parser: argparse.ArgumentParser = cli.cli_mkpfs_main_parsers()
        pack_parser: argparse.ArgumentParser = next(
            action.choices["pack"] for action in parser._actions if isinstance(action, argparse._SubParsersAction)
        )
        pack_choices: dict[str, argparse.ArgumentParser] = next(
            action.choices for action in pack_parser._actions if isinstance(action, argparse._SubParsersAction)
        )
        folder_parser: argparse.ArgumentParser = pack_choices["folder"]
        inode_bits_action: argparse.Action = next(
            action for action in folder_parser._actions if getattr(action, "dest", "") == "inode_bits"
        )
        self.assertEqual(inode_bits_action.default, 32)

    def test_pack_file_parser_uses_thirty_two_as_default_inode_bits(self) -> None:
        """The pack file parser should stay pinned to 32-bit inodes by default."""
        parser: argparse.ArgumentParser = cli.cli_mkpfs_main_parsers()
        parsed_args: argparse.Namespace = parser.parse_args(["pack", "file", "src.bin", "out.ffpfsc"])
        self.assertEqual(parsed_args.inode_bits, 32)

    def test_pack_parser_uses_ps4_as_default_version(self) -> None:
        """The pack parser should expose PS5 as the default pack profile version."""
        parser: argparse.ArgumentParser = cli.cli_mkpfs_main_parsers()
        pack_parser: argparse.ArgumentParser = next(
            action.choices["pack"] for action in parser._actions if isinstance(action, argparse._SubParsersAction)
        )
        pack_choices: dict[str, argparse.ArgumentParser] = next(
            action.choices for action in pack_parser._actions if isinstance(action, argparse._SubParsersAction)
        )
        folder_parser: argparse.ArgumentParser = pack_choices["folder"]
        version_action: argparse.Action = next(
            action for action in folder_parser._actions if getattr(action, "dest", "") == "version"
        )
        self.assertEqual(version_action.default, "PS5")

    def test_pack_parser_exposes_executable_compression_skip_flag(self) -> None:
        """The pack parser should default to skipping executable compression."""
        parser: argparse.ArgumentParser = cli.cli_mkpfs_main_parsers()
        pack_parser: argparse.ArgumentParser = next(
            action.choices["pack"] for action in parser._actions if isinstance(action, argparse._SubParsersAction)
        )
        pack_choices: dict[str, argparse.ArgumentParser] = next(
            action.choices for action in pack_parser._actions if isinstance(action, argparse._SubParsersAction)
        )
        folder_parser: argparse.ArgumentParser = pack_choices["folder"]
        skip_action: argparse.Action = next(
            action for action in folder_parser._actions if getattr(action, "dest", "") == "skip_executable_compression"
        )
        self.assertTrue(skip_action.default)
        self.assertIsNotNone(skip_action.help)
        self.assertIn("Skip compression", skip_action.help or "")

    def test_pack_parser_exposes_whole_file_compression_threshold(self) -> None:
        """The pack parser should expose the whole-file compression threshold."""
        parser: argparse.ArgumentParser = cli.cli_mkpfs_main_parsers()
        pack_parser: argparse.ArgumentParser = next(
            action.choices["pack"] for action in parser._actions if isinstance(action, argparse._SubParsersAction)
        )
        pack_choices: dict[str, argparse.ArgumentParser] = next(
            action.choices for action in pack_parser._actions if isinstance(action, argparse._SubParsersAction)
        )
        folder_parser: argparse.ArgumentParser = pack_choices["folder"]
        max_ratio_action: argparse.Action = next(
            action for action in folder_parser._actions if getattr(action, "dest", "") == "max_compressed_ratio"
        )
        min_size_action: argparse.Action = next(
            action for action in folder_parser._actions if getattr(action, "dest", "") == "min_compress_size"
        )
        self.assertEqual(max_ratio_action.default, 95)
        self.assertEqual(min_size_action.default, 0)

    def test_pack_parser_cpu_count_help_mentions_auto_and_user_normalization(self) -> None:
        """The pack parser should document auto and explicit worker normalization rules."""
        parser: argparse.ArgumentParser = cli.cli_mkpfs_main_parsers()
        pack_parser: argparse.ArgumentParser = next(
            action.choices["pack"] for action in parser._actions if isinstance(action, argparse._SubParsersAction)
        )
        pack_choices: dict[str, argparse.ArgumentParser] = next(
            action.choices for action in pack_parser._actions if isinstance(action, argparse._SubParsersAction)
        )
        folder_parser: argparse.ArgumentParser = pack_choices["folder"]
        cpu_action: argparse.Action = next(
            action for action in folder_parser._actions if getattr(action, "dest", "") == "cpu_count"
        )
        self.assertEqual(cpu_action.default, 0)
        self.assertIsNotNone(cpu_action.help)
        self.assertIn("min(8, max(1, cpu_count() - 1))", cpu_action.help or "")
        self.assertIn("max(1, user value)", cpu_action.help or "")

    def test_pack_parser_folder_variant_exposes_optional_game_file_requirement_flag(self) -> None:
        """The pack folder parser should expose the optional strict game-file flag."""
        parser: argparse.ArgumentParser = cli.cli_mkpfs_main_parsers()
        pack_parser: argparse.ArgumentParser = next(
            action.choices["pack"] for action in parser._actions if isinstance(action, argparse._SubParsersAction)
        )
        pack_choices: dict[str, argparse.ArgumentParser] = next(
            action.choices for action in pack_parser._actions if isinstance(action, argparse._SubParsersAction)
        )
        folder_parser: argparse.ArgumentParser = pack_choices["folder"]
        option_strings: list[str] = []
        for action in folder_parser._actions:
            if getattr(action, "dest", "") == "require_game_files":
                option_strings = action.option_strings
                break
        self.assertIn("--require-game-files", option_strings)

    def test_pack_parser_folder_variant_exposes_output_extension_adjustment_flags(self) -> None:
        """The pack folder parser should expose the extension adjustment toggle pair."""
        parser: argparse.ArgumentParser = cli.cli_mkpfs_main_parsers()
        pack_parser: argparse.ArgumentParser = next(
            action.choices["pack"] for action in parser._actions if isinstance(action, argparse._SubParsersAction)
        )
        pack_choices: dict[str, argparse.ArgumentParser] = next(
            action.choices for action in pack_parser._actions if isinstance(action, argparse._SubParsersAction)
        )
        folder_parser: argparse.ArgumentParser = pack_choices["folder"]
        option_strings: set[str] = set()
        for action in folder_parser._actions:
            if getattr(action, "dest", "") == "adjust_output_file_extension":
                option_strings.update(action.option_strings)
        self.assertIn("--adjust-output-file-extension", option_strings)
        self.assertIn("--no-adjust-output-file-extension", option_strings)

    def test_pack_parser_exposes_temp_folder_flag_for_both_pack_variants(self) -> None:
        """The pack folder and file parsers should expose the temp-folder option."""
        parser: argparse.ArgumentParser = cli.cli_mkpfs_main_parsers()
        pack_parser: argparse.ArgumentParser = next(
            action.choices["pack"] for action in parser._actions if isinstance(action, argparse._SubParsersAction)
        )
        pack_choices: dict[str, argparse.ArgumentParser] = next(
            action.choices for action in pack_parser._actions if isinstance(action, argparse._SubParsersAction)
        )
        for variant_name in ("folder", "file"):
            variant_parser: argparse.ArgumentParser = pack_choices[variant_name]
            self.assertTrue(any(getattr(action, "dest", "") == "temp_folder" for action in variant_parser._actions))

    def test_pack_parser_defaults_to_adjusting_output_extensions(self) -> None:
        """The pack parser should default to automatic extension adjustment."""
        parser: argparse.ArgumentParser = cli.cli_mkpfs_main_parsers()
        pack_parser: argparse.ArgumentParser = next(
            action.choices["pack"] for action in parser._actions if isinstance(action, argparse._SubParsersAction)
        )
        pack_choices: dict[str, argparse.ArgumentParser] = next(
            action.choices for action in pack_parser._actions if isinstance(action, argparse._SubParsersAction)
        )
        folder_parser: argparse.ArgumentParser = pack_choices["folder"]
        adjust_action = next(
            action
            for action in folder_parser._actions
            if getattr(action, "dest", "") == "adjust_output_file_extension"
        )
        self.assertTrue(adjust_action.default)

    def test_pack_parser_file_variant_omits_game_file_requirement_flag(self) -> None:
        """The pack file parser should not expose the strict game-file flag."""
        parser: argparse.ArgumentParser = cli.cli_mkpfs_main_parsers()
        pack_parser: argparse.ArgumentParser = next(
            action.choices["pack"] for action in parser._actions if isinstance(action, argparse._SubParsersAction)
        )
        pack_choices: dict[str, argparse.ArgumentParser] = next(
            action.choices for action in pack_parser._actions if isinstance(action, argparse._SubParsersAction)
        )
        file_parser: argparse.ArgumentParser = pack_choices["file"]
        self.assertFalse(any(getattr(action, "dest", "") == "require_game_files" for action in file_parser._actions))

    def test_verify_parser_exposes_optional_game_file_requirement_flag(self) -> None:
        """The verify parser should expose the optional game-file checklist flag."""
        parser: argparse.ArgumentParser = cli.cli_mkpfs_main_parsers()
        verify_parser: argparse.ArgumentParser = next(
            action.choices["verify"] for action in parser._actions if isinstance(action, argparse._SubParsersAction)
        )
        option_strings: list[str] = []
        for action in verify_parser._actions:
            if getattr(action, "dest", "") == "require_game_files":
                option_strings = action.option_strings
                break
        self.assertIn("--require-game-files", option_strings)

    def test_pack_parser_file_variant_exposes_output_extension_adjustment_flags(self) -> None:
        """The pack file parser should expose the extension adjustment toggle pair."""
        parser: argparse.ArgumentParser = cli.cli_mkpfs_main_parsers()
        pack_parser: argparse.ArgumentParser = next(
            action.choices["pack"] for action in parser._actions if isinstance(action, argparse._SubParsersAction)
        )
        pack_choices: dict[str, argparse.ArgumentParser] = next(
            action.choices for action in pack_parser._actions if isinstance(action, argparse._SubParsersAction)
        )
        file_parser: argparse.ArgumentParser = pack_choices["file"]
        option_strings: set[str] = set()
        for action in file_parser._actions:
            if getattr(action, "dest", "") == "adjust_output_file_extension":
                option_strings.update(action.option_strings)
        self.assertIn("--adjust-output-file-extension", option_strings)
        self.assertIn("--no-adjust-output-file-extension", option_strings)

    def test_pack_file_parser_exposes_inner_image_rename_toggle_pair(self) -> None:
        """The pack file parser should expose the inner-image rename toggle pair."""
        parser: argparse.ArgumentParser = cli.cli_mkpfs_main_parsers()
        pack_parser: argparse.ArgumentParser = next(
            action.choices["pack"] for action in parser._actions if isinstance(action, argparse._SubParsersAction)
        )
        pack_choices: dict[str, argparse.ArgumentParser] = next(
            action.choices for action in pack_parser._actions if isinstance(action, argparse._SubParsersAction)
        )
        file_parser: argparse.ArgumentParser = pack_choices["file"]
        option_strings: set[str] = set()
        rename_action: argparse.Action | None = None
        for action in file_parser._actions:
            if getattr(action, "dest", "") == "rename_inner_image":
                option_strings.update(action.option_strings)
                if rename_action is None:
                    rename_action = action
        self.assertIn("--rename-inner-image", option_strings)
        self.assertIn("--no-rename-inner-image", option_strings)
        self.assertIsNotNone(rename_action)
        self.assertTrue(rename_action.default)

    def test_pack_file_parser_parses_rename_inner_image_toggle_values(self) -> None:
        """The pack file parser should default rename-inner-image on and allow opt-out."""
        parser: argparse.ArgumentParser = cli.cli_mkpfs_main_parsers()
        default_args: argparse.Namespace = parser.parse_args(["pack", "file", "src.bin", "out.ffpfsc"])
        disabled_args: argparse.Namespace = parser.parse_args(
            ["pack", "file", "src.bin", "out.ffpfsc", "--no-rename-inner-image"]
        )
        enabled_args: argparse.Namespace = parser.parse_args(
            ["pack", "file", "src.bin", "out.ffpfsc", "--rename-inner-image"]
        )

        self.assertTrue(default_args.rename_inner_image)
        self.assertFalse(disabled_args.rename_inner_image)
        self.assertTrue(enabled_args.rename_inner_image)

    def test_pack_parser_defaults_to_structure_verification(self) -> None:
        """The pack parser should enable structure verification by default."""
        parser: argparse.ArgumentParser = cli.cli_mkpfs_main_parsers()
        parsed_args: argparse.Namespace = parser.parse_args(["pack", "folder", "src", "out.ffpfs"])
        self.assertFalse(parsed_args.verify)
        self.assertTrue(parsed_args.verify_structure)
        self.assertFalse(parsed_args.skip_verification)

    def test_pack_parser_parses_structure_verification_toggles(self) -> None:
        """The pack parser should expose structure verification opt-in and opt-out flags."""
        parser: argparse.ArgumentParser = cli.cli_mkpfs_main_parsers()
        disabled_args: argparse.Namespace = parser.parse_args(
            ["pack", "folder", "src", "out.ffpfs", "--no-verify-structure"]
        )
        enabled_args: argparse.Namespace = parser.parse_args(
            ["pack", "folder", "src", "out.ffpfs", "--verify-structure"]
        )
        self.assertFalse(disabled_args.verify_structure)
        self.assertTrue(enabled_args.verify_structure)

    def test_resolve_pack_verification_mode_prefers_full_verify(self) -> None:
        """Explicit full verification should override the default structure-only mode."""
        args: argparse.Namespace = argparse.Namespace(verify=True, verify_structure=True, skip_verification=False)
        self.assertEqual(cli._resolve_pack_verification_mode(args), cli.PackVerificationMode.FULL)

    def test_resolve_pack_verification_mode_rejects_skip_with_full_verify(self) -> None:
        """Skip verification should conflict with the full verify flag."""
        args: argparse.Namespace = argparse.Namespace(verify=True, verify_structure=False, skip_verification=True)
        with self.assertRaisesRegex(BuildError, "--verify and --skip-verification"):
            cli._resolve_pack_verification_mode(args)

    def test_resolve_pack_verification_mode_rejects_skip_with_structure_verify(self) -> None:
        """Skip verification should conflict with structure verification when enabled."""
        args: argparse.Namespace = argparse.Namespace(verify=False, verify_structure=True, skip_verification=True)
        with self.assertRaisesRegex(BuildError, "--verify-structure and --skip-verification"):
            cli._resolve_pack_verification_mode(args)

    def test_pack_parser_accepts_file_subcommand_with_output_positional(self) -> None:
        """The canonical pack file parser should keep source and output positional args."""
        parser: argparse.ArgumentParser = cli.cli_mkpfs_main_parsers()
        parsed_args: argparse.Namespace = parser.parse_args(["pack", "file", "src.bin", "out.ffpfsc"])
        self.assertEqual(parsed_args.command, "pack")
        self.assertEqual(parsed_args.pack_command, "file")
        self.assertEqual(parsed_args.source_file, "src.bin")
        self.assertEqual(parsed_args.image_file, "out.ffpfsc")

    def test_pack_argv_normalization_rewrites_legacy_flat_pack_commands(self) -> None:
        """Legacy flat pack commands should be rewritten to include the missing pack mode."""
        tmp_path: Path = self.make_temp_path()
        source_dir: Path = tmp_path / "folder-source"
        source_dir.mkdir()
        source_file: Path = tmp_path / "payload.bin"
        source_file.write_bytes(b"payload")

        dir_argv: list[str] | None = cli.normalize_cli_argv_for_pack_compat(
            ["pack", str(source_dir), "folder.ffpfs", "--dry-run"]
        )
        file_argv: list[str] | None = cli.normalize_cli_argv_for_pack_compat(
            ["pack", str(source_file), "file.ffpfsc", "--dry-run"]
        )

        self.assertIsNotNone(dir_argv)
        self.assertIsNotNone(file_argv)
        self.assertEqual(dir_argv[0:3], ["pack", "folder", str(source_dir)])
        self.assertEqual(file_argv[0:3], ["pack", "file", str(source_file)])


class TestCliPromptOverwrite(CliTestCase):
    """Tests for the interactive overwrite prompt helper."""

    def test_prompt_overwrite_returns_true_when_output_is_missing(self) -> None:
        """The overwrite prompt should allow creation when no output file exists yet."""
        output_path: Path = self.make_temp_path() / "missing.ffpfs"
        self.assertTrue(cli.prompt_overwrite(output_path=output_path))

    def test_prompt_overwrite_returns_false_for_explicit_no(self) -> None:
        """The overwrite prompt should stop when the user answers no."""
        tmp_path: Path = self.make_temp_path()
        output_path: Path = tmp_path / "out.ffpfs"
        output_path.write_text("x", encoding="utf-8")
        with patch("builtins.input", return_value="n"):
            self.assertFalse(cli.prompt_overwrite(output_path=output_path))

    def test_prompt_overwrite_removes_partial_temp_file_before_yes(self) -> None:
        """The overwrite prompt should remove old output and partial temp files."""
        tmp_path: Path = self.make_temp_path()
        output_path: Path = tmp_path / "out.ffpfs"
        partial_path: Path = Path(f"{output_path}.tmp")
        output_path.write_text("x", encoding="utf-8")
        partial_path.write_text("partial", encoding="utf-8")
        with patch("builtins.input", return_value="y"):
            self.assertTrue(cli.prompt_overwrite(output_path=output_path))
        self.assertFalse(output_path.exists())
        self.assertFalse(partial_path.exists())

    def test_prompt_overwrite_retries_invalid_input_and_ignores_unlink_errors(self) -> None:
        """The overwrite prompt should retry invalid input and continue when temp cleanup fails."""
        tmp_path: Path = self.make_temp_path()
        output_path: Path = tmp_path / "out.ffpfs"
        partial_path: Path = Path(f"{output_path}.tmp")
        output_path.write_text("x", encoding="utf-8")
        partial_path.write_text("partial", encoding="utf-8")
        with patch("builtins.input", side_effect=["maybe", "yes"]), patch.object(
            Path,
            "unlink",
            side_effect=OSError("unlink blocked"),
        ):
            self.assertTrue(cli.prompt_overwrite(output_path=output_path))

    def test_cleanup_pack_temp_artifacts_removes_output_tmp_and_stale_spool_files(self) -> None:
        """Temp cleanup should remove stale output tmp files and stale pfsc spool files."""
        tmp_path: Path = self.make_temp_path()
        output_path: Path = tmp_path / "out.ffpfs"
        output_tmp_path: Path = Path(f"{output_path}.tmp")
        output_tmp_path.write_text("partial", encoding="utf-8")

        temp_root: Path = tmp_path / "temp-root"
        temp_root.mkdir(parents=True, exist_ok=True)
        stale_spool_path: Path = temp_root / "mkpfs-stale.pfsc"
        fresh_spool_path: Path = temp_root / "mkpfs-fresh.pfsc"
        stale_spool_path.write_bytes(b"x")
        fresh_spool_path.write_bytes(b"y")
        os.utime(stale_spool_path, times=(100.0, 100.0))
        os.utime(fresh_spool_path, times=(990.0, 990.0))

        with patch.object(cli.tempfile, "gettempdir", return_value=str(temp_root)), patch.object(
            cli.time,
            "time",
            return_value=1000.0,
        ):
            cli.cleanup_pack_temp_artifacts(output_path=output_path, stale_age_seconds=300)

        self.assertFalse(output_tmp_path.exists())
        self.assertFalse(stale_spool_path.exists())
        self.assertTrue(fresh_spool_path.exists())


class TestCliOutputFormatting(CliTestCase):
    """Tests for text and JSON output emitted by CLI helper functions."""

    def test_print_build_parameters_writes_expected_header_lines(self) -> None:
        """Printing build parameters should emit the builder title and selected settings."""
        stdout_buffer: StringIO = StringIO()
        with patch.object(cli, "resolve_compression_worker_count", return_value=1), redirect_stdout(stdout_buffer):
            cli.print_build_parameters(
                source_path=Path("src"),
                output_path=Path("out.ffpfs"),
                temp_folder=Path("/tmp/mkpfs"),
                block_size=65536,
                pfs_version=0,
                inode_bits=32,
                case_insensitive=False,
                signed=False,
                encrypted=True,
                new_crypt=False,
                compress=True,
                threshold_gain=20,
                cpu_count=0,
                zlib_level=7,
                max_compressed_ratio=None,
                min_compress_size=0,
                dry_run=True,
                require_game_files=False,
            )
        output_text: str = stdout_buffer.getvalue()
        self.assertIn("PFS Image Builder - Parameters", output_text)
        self.assertIn("Header magic:      PFS (20130315)", output_text)
        self.assertIn("Compression Setup: PFSC (0x43534650)", output_text)
        self.assertIn("Temp folder:       /tmp/mkpfs", output_text)
        self.assertIn("CPU cores:         1 (auto, capped at 8)", output_text)
        self.assertIn("Zlib level:        7", output_text)

    def test_print_summary_reports_build_summary_and_disabled_compression(self) -> None:
        """Printing a summary should emit both the summary header and the disabled compression line."""
        tmp_path: Path = self.make_temp_path()
        stats: BuildStats = BuildStats(input_path=tmp_path / "src", output_path=tmp_path / "out.ffpfs")
        stats.compression_enabled = False
        stats.total_files = 0
        stdout_buffer: StringIO = StringIO()
        with redirect_stdout(stdout_buffer):
            cli.print_summary(stats=stats)
        output_text: str = stdout_buffer.getvalue()
        self.assertIn("Build Summary", output_text)
        self.assertIn("Compression:             disabled", output_text)

    def test_inspect_run_writes_json_payload_when_json_format_is_requested(self) -> None:
        """Inspecting with JSON output should print a serialized payload with header details."""
        inspection: PFSImageInspection = PFSImageInspection(image=Path("img.ffpfs"))
        inspection.header = SimpleNamespace(version=2, block_size=65536, magic=consts.PFS_MAGIC)
        inspection.warnings = ["warn"]
        inspection.errors = []
        stdout_buffer: StringIO = StringIO()
        with patch.object(cli, "inspect_pfs_image", return_value=inspection), redirect_stdout(stdout_buffer):
            exit_code: int = cli.cli_mkpfs_inspect_run(SimpleNamespace(image_file="img.ffpfs", format="json"))
        self.assertEqual(exit_code, 0)
        self.assertIn('"block_size": 65536', stdout_buffer.getvalue())
        self.assertIn('"warnings": [', stdout_buffer.getvalue())

    def test_inspect_run_writes_text_report_and_errors_when_text_format_is_requested(self) -> None:
        """Inspecting with text output should print a report and return a nonzero code for errors."""
        inspection: PFSImageInspection = PFSImageInspection(image=Path("img.ffpfs"))
        inspection.header = SimpleNamespace(version=0, block_size=65536, magic=consts.PFS_MAGIC)
        inspection.warnings = ["warn"]
        inspection.errors = ["err"]
        stdout_buffer: StringIO = StringIO()
        with patch.object(cli, "inspect_pfs_image", return_value=inspection), redirect_stdout(stdout_buffer):
            exit_code: int = cli.cli_mkpfs_inspect_run(SimpleNamespace(image_file="img.ffpfs", format="text"))
        self.assertEqual(exit_code, 1)
        output_text: str = stdout_buffer.getvalue()
        self.assertIn(cli.get_output_title(), output_text)
        self.assertIn("PFS Image Inspection", output_text)
        self.assertIn("Magic:    PFS (20130315)", output_text)
        self.assertIn("warn", output_text)
        self.assertIn("err", output_text)

    def test_tree_run_prints_version_header_before_tree_output(self) -> None:
        """Tree output should include the standard MkPFS banner before the rendered tree."""
        stdout_buffer: StringIO = StringIO()
        with patch.object(cli, "run_image_check", return_value=([], [], {}, 1)), patch.object(
            cli, "render_tree", return_value=["child"]
        ), redirect_stdout(stdout_buffer):
            exit_code: int = cli.cli_mkpfs_ls_run(
                SimpleNamespace(image_file="img.ffpfs", ekpfs_key=None, new_crypt=False)
            )

        self.assertEqual(exit_code, 0)
        output_text: str = stdout_buffer.getvalue()
        self.assertIn(cli.get_output_title(), output_text)
        self.assertIn("/", output_text)
        self.assertIn("child", output_text)

    def test_extract_run_prints_version_header_before_summary(self) -> None:
        """Extraction summary output should include the standard MkPFS banner."""
        extraction_result: PFSExtractionResult = PFSExtractionResult(
            image=Path("img.ffpfs"),
            output_path=Path("out"),
        )
        extraction_result.files_written = 3
        extraction_result.directories_created = 2
        extraction_result.bytes_written = 1234
        stdout_buffer: StringIO = StringIO()
        with patch.object(cli, "extract_pfs_image", return_value=extraction_result), redirect_stdout(stdout_buffer):
            exit_code: int = cli.cli_mkpfs_extract_run(
                SimpleNamespace(
                    image_file="img.ffpfs", output_dir="out", overwrite=True, ekpfs_key=None, new_crypt=False
                )
            )

        self.assertEqual(exit_code, 0)
        output_text: str = stdout_buffer.getvalue()
        self.assertIn(cli.get_output_title(), output_text)
        self.assertIn("Extraction complete:", output_text)


class TestCliCreateRun(CliTestCase):
    """Tests for pack command execution and validation branches."""

    def test_create_run_supports_dry_run_with_stubbed_build(self) -> None:
        """A dry-run create command should auto-select .ffpfsc for a plain folder tree."""
        tmp_path: Path = self.make_temp_path()
        args: SimpleNamespace = self.make_create_args(
            source_path=tmp_path,
            image_path=tmp_path / "out",
            dry_run=True,
            verify=False,
        )
        stdout_buffer: StringIO = StringIO()
        with patch.object(
            cli, "build_pfs", return_value=self.make_build_stats(tmp_path)
        ) as mocked_build, patch.object(
            cli,
            "prompt_overwrite",
            return_value=True,
        ), redirect_stdout(stdout_buffer):
            self.assertEqual(cli.cli_mkpfs_create_run(args), 0)
        self.assertEqual(mocked_build.call_args.kwargs["output_path"].suffix, ".ffpfsc")
        self.assertEqual(mocked_build.call_args.kwargs["min_compress_size"], 65536)
        self.assertEqual(mocked_build.call_args.kwargs["ekpfs"], b"\x00" * 32)
        self.assertFalse(mocked_build.call_args.kwargs["encrypted"])
        self.assertIn("The folder does not seem to contain any direct game information", stdout_buffer.getvalue())

    def test_create_run_adjusts_to_ffpfs_for_game_folders(self) -> None:
        """Pack should auto-select .ffpfs when game files are detected."""
        tmp_path: Path = self.make_temp_path()
        source_path: Path = self.make_valid_source(tmp_path)
        args: SimpleNamespace = self.make_create_args(
            source_path=source_path,
            image_path=tmp_path / "out.bin",
            dry_run=True,
            verify=False,
        )
        stdout_buffer: StringIO = StringIO()
        with patch.object(
            cli, "build_pfs", return_value=self.make_build_stats(tmp_path)
        ) as mocked_build, patch.object(
            cli,
            "prompt_overwrite",
            return_value=True,
        ), redirect_stdout(stdout_buffer):
            self.assertEqual(cli.cli_mkpfs_create_run(args), 0)
        self.assertEqual(mocked_build.call_args.kwargs["output_path"].suffix, ".ffpfs")
        self.assertIn("Raw game files detected inside the source folder", stdout_buffer.getvalue())

    def test_create_run_keeps_requested_extension_when_adjustment_is_disabled(self) -> None:
        """Pack should leave the requested output name untouched when adjustment is disabled."""
        tmp_path: Path = self.make_temp_path()
        source_path: Path = self.make_valid_source(tmp_path)
        args: SimpleNamespace = self.make_create_args(
            source_path=source_path,
            image_path=tmp_path / "custom-name.img",
            dry_run=True,
            verify=False,
        )
        args.adjust_output_file_extension = False
        stdout_buffer: StringIO = StringIO()
        with patch.object(
            cli, "build_pfs", return_value=self.make_build_stats(tmp_path)
        ) as mocked_build, patch.object(
            cli,
            "prompt_overwrite",
            return_value=True,
        ), redirect_stdout(stdout_buffer):
            self.assertEqual(cli.cli_mkpfs_create_run(args), 0)
        self.assertEqual(mocked_build.call_args.kwargs["output_path"].name, "custom-name.img")
        self.assertNotIn("adjusting output file extension", stdout_buffer.getvalue())

    def test_create_run_auto_fit_block_size_selects_small_blocks_for_small_files(self) -> None:
        """The auto-fit block-size mode should pick a smaller block size for small-file trees."""
        tmp_path: Path = self.make_temp_path()
        source_path: Path = self.make_valid_source(tmp_path)
        data_path: Path = source_path / "data"
        data_path.mkdir()
        for idx in range(32):
            (data_path / f"small_{idx:02d}.bin").write_bytes(b"x" * 100)
        args: SimpleNamespace = self.make_create_args(
            source_path=source_path,
            image_path=tmp_path / "out",
            dry_run=True,
            verify=False,
        )
        args.block_size = "auto-fit"
        stdout_buffer: StringIO = StringIO()

        with patch.object(
            cli, "build_pfs", return_value=self.make_build_stats(tmp_path)
        ) as mocked_build, patch.object(
            cli,
            "prompt_overwrite",
            return_value=True,
        ), redirect_stdout(stdout_buffer):
            self.assertEqual(cli.cli_mkpfs_create_run(args), 0)

        self.assertEqual(mocked_build.call_args.kwargs["block_size"], 4096)
        self.assertEqual(mocked_build.call_args.kwargs["min_compress_size"], 4096)
        self.assertIn("Auto-fit block size selected", stdout_buffer.getvalue())

    def test_create_run_requires_game_files_when_flag_is_enabled(self) -> None:
        """Pack should fail fast when strict game-file validation is enabled and files are missing."""
        tmp_path: Path = self.make_temp_path()
        source_path: Path = tmp_path / "src"
        source_path.mkdir()
        args: SimpleNamespace = self.make_create_args(
            source_path=source_path,
            image_path=tmp_path / "out",
            dry_run=True,
            verify=False,
        )
        args.require_game_files = True
        with patch.object(cli, "build_pfs", side_effect=AssertionError("build should not run")), self.assertRaises(
            BuildError
        ):
            cli.cli_mkpfs_create_run(args)

    def test_create_run_passes_new_crypt_flag_through_to_build(self) -> None:
        """Create run should forward the newCrypt compatibility flag into the builder."""
        tmp_path: Path = self.make_temp_path()
        args: SimpleNamespace = self.make_create_args(
            source_path=tmp_path,
            image_path=tmp_path / "out",
            dry_run=True,
            verify=False,
        )
        args.new_crypt = True
        with patch.object(
            cli, "build_pfs", return_value=self.make_build_stats(tmp_path)
        ) as mocked_build, patch.object(
            cli,
            "prompt_overwrite",
            return_value=True,
        ):
            self.assertEqual(cli.cli_mkpfs_create_run(args), 0)
        self.assertTrue(mocked_build.call_args.kwargs["new_crypt"])

    def test_create_run_forwards_custom_temp_folder_to_cleanup_and_build(self) -> None:
        """Create run should use the configured temp folder for cleanup and builder calls."""
        tmp_path: Path = self.make_temp_path()
        source_path: Path = self.make_valid_source(tmp_path)
        temp_folder: Path = tmp_path / "pack-temp"
        args: SimpleNamespace = self.make_create_args(
            source_path=source_path,
            image_path=tmp_path / "out",
            dry_run=False,
            verify=False,
        )
        args.temp_folder = str(temp_folder)
        args.verify_structure = False
        with patch.object(cli, "validate_input", return_value=("TITLE", [])), patch.object(
            cli,
            "prompt_overwrite",
            return_value=True,
        ), patch.object(cli, "build_pfs", return_value=self.make_build_stats(tmp_path)) as mocked_build, patch.object(
            cli,
            "cleanup_pack_temp_artifacts",
        ) as mocked_cleanup:
            self.assertEqual(cli.cli_mkpfs_create_run(args), 0)
        self.assertEqual(mocked_build.call_args.kwargs["temp_folder"], temp_folder.resolve())
        self.assertEqual(mocked_cleanup.call_args.kwargs["temp_folder"], temp_folder.resolve())

    def test_create_run_rejects_invalid_threshold_block_cpu_and_level_values(self) -> None:
        """Create run should raise BuildError for invalid threshold, block size, cpu count, and compression level."""
        tmp_path: Path = self.make_temp_path()
        source_path: Path = self.make_valid_source(tmp_path)
        with patch.object(cli, "validate_input", return_value=("TITLE", [])):
            base_args: dict[str, object] = self.make_create_args(
                source_path=source_path,
                image_path=tmp_path / "out.img",
                dry_run=True,
                verify=False,
            ).__dict__.copy()

            bad_threshold_dict: dict[str, object] = base_args.copy()
            bad_threshold_dict["threshold_gain"] = -1
            bad_threshold: SimpleNamespace = SimpleNamespace(**bad_threshold_dict)
            with self.assertRaises(BuildError):
                cli.cli_mkpfs_create_run(bad_threshold)

            bad_block_dict: dict[str, object] = base_args.copy()
            bad_block_dict["block_size"] = "bad"
            bad_block: SimpleNamespace = SimpleNamespace(**bad_block_dict)
            with self.assertRaises(BuildError):
                cli.cli_mkpfs_create_run(bad_block)

            bad_cpu_dict: dict[str, object] = base_args.copy()
            bad_cpu_dict["cpu_count"] = -1
            bad_cpu: SimpleNamespace = SimpleNamespace(**bad_cpu_dict)
            with self.assertRaises(BuildError):
                cli.cli_mkpfs_create_run(bad_cpu)

            bad_level_dict: dict[str, object] = base_args.copy()
            bad_level_dict["compression_level"] = 10
            bad_level: SimpleNamespace = SimpleNamespace(**bad_level_dict)
            with self.assertRaises(BuildError):
                cli.cli_mkpfs_create_run(bad_level)

            bad_max_ratio_dict: dict[str, object] = base_args.copy()
            bad_max_ratio_dict["max_compressed_ratio"] = 101
            bad_max_ratio: SimpleNamespace = SimpleNamespace(**bad_max_ratio_dict)
            with self.assertRaises(BuildError):
                cli.cli_mkpfs_create_run(bad_max_ratio)

            bad_min_size_dict: dict[str, object] = base_args.copy()
            bad_min_size_dict["min_compress_size"] = -1
            bad_min_size: SimpleNamespace = SimpleNamespace(**bad_min_size_dict)
            with self.assertRaises(BuildError):
                cli.cli_mkpfs_create_run(bad_min_size)

            bad_key_dict: dict[str, object] = base_args.copy()
            bad_key_dict["encrypted"] = True
            bad_key_dict["ekpfs_key"] = "xyz"
            bad_key: SimpleNamespace = SimpleNamespace(**bad_key_dict)
            with self.assertRaises(BuildError):
                cli.cli_mkpfs_create_run(bad_key)

            key_without_encryption_dict: dict[str, object] = base_args.copy()
            key_without_encryption_dict["ekpfs_key"] = "ab" * 32
            key_without_encryption: SimpleNamespace = SimpleNamespace(**key_without_encryption_dict)
            with self.assertRaises(BuildError):
                cli.cli_mkpfs_create_run(key_without_encryption)

    def test_create_run_returns_zero_when_user_cancels_overwrite(self) -> None:
        """Create run should stop cleanly when overwrite confirmation is denied."""
        tmp_path: Path = self.make_temp_path()
        source_path: Path = self.make_valid_source(tmp_path)
        args: SimpleNamespace = self.make_create_args(
            source_path=source_path,
            image_path=tmp_path / "out.ffpfs",
            dry_run=False,
            verify=False,
        )
        with patch.object(cli, "validate_input", return_value=("TITLE", [])), patch.object(
            cli,
            "cleanup_pack_temp_artifacts",
        ) as mocked_cleanup, patch.object(cli, "prompt_overwrite", return_value=False), patch.object(
            cli,
            "build_pfs",
            side_effect=AssertionError("build should not run"),
        ):
            self.assertEqual(cli.cli_mkpfs_create_run(args), 0)
        mocked_cleanup.assert_called_once()

    def test_create_run_returns_error_when_destination_disk_is_too_small(self) -> None:
        """Create run should fail early when destination free space is below raw source size."""
        tmp_path: Path = self.make_temp_path()
        source_path: Path = self.make_valid_source(tmp_path)
        args: SimpleNamespace = self.make_create_args(
            source_path=source_path,
            image_path=tmp_path / "out.ffpfs",
            dry_run=False,
            verify=False,
        )
        stderr_buffer: StringIO = StringIO()
        with patch.object(cli, "validate_input", return_value=("TITLE", [])), patch.object(
            cli,
            "cleanup_pack_temp_artifacts",
            side_effect=AssertionError("cleanup should not run"),
        ), patch.object(
            cli,
            "prompt_overwrite",
            side_effect=AssertionError("prompt should not run"),
        ), patch.object(
            cli,
            "build_pfs",
            side_effect=AssertionError("build should not run"),
        ), patch.object(
            cli.shutil,
            "disk_usage",
            return_value=SimpleNamespace(total=10, used=9, free=1),
        ), redirect_stderr(stderr_buffer):
            self.assertEqual(cli.cli_mkpfs_create_run(args), 1)
        self.assertIn(
            "ERROR: The destination file is on a disk that does not have enough space", stderr_buffer.getvalue()
        )
        self.assertIn("Operation cancelled.", stderr_buffer.getvalue())

    def test_pack_file_run_returns_error_when_destination_disk_is_too_small(self) -> None:
        """Pack file should fail early when destination free space is below raw source size."""
        tmp_path: Path = self.make_temp_path()
        source_file: Path = tmp_path / "single.bin"
        source_file.write_bytes(b"payload")
        args: SimpleNamespace = self.make_pack_file_args(
            source_path=source_file,
            image_path=tmp_path / "out.ffpfsc",
            dry_run=False,
            verify=False,
        )
        stderr_buffer: StringIO = StringIO()
        with patch.object(cli, "validate_input", return_value=(None, [])), patch.object(
            cli,
            "cleanup_pack_temp_artifacts",
            side_effect=AssertionError("cleanup should not run"),
        ), patch.object(
            cli,
            "prompt_overwrite",
            side_effect=AssertionError("prompt should not run"),
        ), patch.object(
            cli,
            "build_pfs",
            side_effect=AssertionError("build should not run"),
        ), patch.object(
            cli.shutil,
            "disk_usage",
            return_value=SimpleNamespace(total=10, used=9, free=1),
        ), redirect_stderr(stderr_buffer):
            self.assertEqual(cli.cli_mkpfs_pack_file_run(args), 1)
        self.assertIn(
            "ERROR: The destination file is on a disk that does not have enough space", stderr_buffer.getvalue()
        )
        self.assertIn("Operation cancelled.", stderr_buffer.getvalue())

    def test_create_run_returns_error_when_temp_disk_is_too_small(self) -> None:
        """Create run should fail early when PFSC temp free space is below raw source size."""
        tmp_path: Path = self.make_temp_path()
        source_path: Path = self.make_valid_source(tmp_path)
        args: SimpleNamespace = self.make_create_args(
            source_path=source_path,
            image_path=tmp_path / "out.ffpfs",
            dry_run=False,
            verify=False,
        )
        stderr_buffer: StringIO = StringIO()
        with patch.object(cli, "validate_input", return_value=("TITLE", [])), patch.object(
            cli,
            "cleanup_pack_temp_artifacts",
            side_effect=AssertionError("cleanup should not run"),
        ), patch.object(
            cli,
            "prompt_overwrite",
            side_effect=AssertionError("prompt should not run"),
        ), patch.object(
            cli,
            "build_pfs",
            side_effect=AssertionError("build should not run"),
        ), patch.object(
            cli.shutil,
            "disk_usage",
            side_effect=[
                SimpleNamespace(total=100, used=1, free=100),
                SimpleNamespace(total=10, used=9, free=1),
            ],
        ), redirect_stderr(stderr_buffer):
            self.assertEqual(cli.cli_mkpfs_create_run(args), 1)
        self.assertIn("ERROR: The temp folder does not have enough free space", stderr_buffer.getvalue())
        self.assertIn("Use --temp-folder", stderr_buffer.getvalue())
        self.assertIn("Operation cancelled.", stderr_buffer.getvalue())

    def test_create_run_defaults_to_structure_verification(self) -> None:
        """Create run should perform structure verification by default after a real pack."""
        tmp_path: Path = self.make_temp_path()
        source_path: Path = self.make_valid_source(tmp_path)
        output_path: Path = tmp_path / "out.ffpfs"
        args: SimpleNamespace = self.make_create_args(
            source_path=source_path,
            image_path=output_path,
            dry_run=False,
            verify=False,
        )

        with patch.object(cli, "validate_input", return_value=("TITLE", [])), patch.object(
            cli,
            "prompt_overwrite",
            return_value=True,
        ), patch.object(
            cli, "build_pfs", return_value=BuildStats(input_path=source_path, output_path=output_path)
        ), patch.object(cli, "run_image_check", return_value=([], [], {}, -1)) as mocked_check:
            self.assertEqual(cli.cli_mkpfs_create_run(args), 0)

        self.assertFalse(mocked_check.call_args.kwargs["verify_payloads"])
        self.assertFalse(mocked_check.call_args.kwargs["compare_source_contents"])
        self.assertEqual(mocked_check.call_args.kwargs["report_title"], "PFS Structure Verify Report")

    def test_create_run_skip_verification_disables_post_pack_check(self) -> None:
        """Create run should skip post-pack verification when explicitly requested."""
        tmp_path: Path = self.make_temp_path()
        source_path: Path = self.make_valid_source(tmp_path)
        output_path: Path = tmp_path / "out.ffpfs"
        args: SimpleNamespace = self.make_create_args(
            source_path=source_path,
            image_path=output_path,
            dry_run=False,
            verify=False,
        )
        args.verify_structure = False
        args.skip_verification = True

        with patch.object(cli, "validate_input", return_value=("TITLE", [])), patch.object(
            cli,
            "prompt_overwrite",
            return_value=True,
        ), patch.object(
            cli, "build_pfs", return_value=BuildStats(input_path=source_path, output_path=output_path)
        ), patch.object(
            cli,
            "run_image_check",
            side_effect=AssertionError("verify should not run"),
        ):
            self.assertEqual(cli.cli_mkpfs_create_run(args), 0)

    def test_create_run_dry_run_skips_default_structure_verification(self) -> None:
        """Create run dry-runs should not perform default structure verification."""
        tmp_path: Path = self.make_temp_path()
        source_path: Path = self.make_valid_source(tmp_path)
        output_path: Path = tmp_path / "out.ffpfs"
        args: SimpleNamespace = self.make_create_args(
            source_path=source_path,
            image_path=output_path,
            dry_run=True,
            verify=False,
        )

        with patch.object(cli, "validate_input", return_value=("TITLE", [])), patch.object(
            cli,
            "build_pfs",
            return_value=BuildStats(input_path=source_path, output_path=output_path),
        ), patch.object(
            cli,
            "run_image_check",
            side_effect=AssertionError("verify should not run"),
        ):
            self.assertEqual(cli.cli_mkpfs_create_run(args), 0)

    def test_create_run_verify_enables_full_post_pack_verification(self) -> None:
        """Create run should upgrade to full verification when --verify is enabled."""
        tmp_path: Path = self.make_temp_path()
        source_path: Path = self.make_valid_source(tmp_path)
        output_path: Path = tmp_path / "out.ffpfs"
        args: SimpleNamespace = self.make_create_args(
            source_path=source_path,
            image_path=output_path,
            dry_run=False,
            verify=True,
        )
        stdout_buffer: StringIO = StringIO()

        with patch.object(cli, "validate_input", return_value=("TITLE", [])), patch.object(
            cli,
            "prompt_overwrite",
            return_value=True,
        ), patch.object(
            cli, "build_pfs", return_value=BuildStats(input_path=source_path, output_path=output_path)
        ), patch.object(cli, "run_image_check", return_value=([], [], {}, -1)), redirect_stdout(stdout_buffer):
            self.assertEqual(cli.cli_mkpfs_create_run(args), 0)

    def test_create_run_runs_post_verify_and_returns_error_when_check_fails(self) -> None:
        """Create run should perform post-verify and return a failure code when verification reports errors."""
        tmp_path: Path = self.make_temp_path()
        source_path: Path = self.make_valid_source(tmp_path)
        output_path: Path = tmp_path / "out.ffpfs"
        args: SimpleNamespace = self.make_create_args(
            source_path=source_path,
            image_path=output_path,
            dry_run=False,
            verify=True,
        )
        with patch.object(cli, "validate_input", return_value=("TITLE", [])), patch.object(
            cli,
            "prompt_overwrite",
            return_value=True,
        ), patch.object(
            cli, "build_pfs", return_value=BuildStats(input_path=source_path, output_path=output_path)
        ), patch.object(
            cli,
            "run_image_check",
            return_value=(["error"], ["warning"], {}, -1),
        ):
            self.assertEqual(cli.cli_mkpfs_create_run(args), 1)

    def test_create_run_supports_signed_64_bit_inode_dry_run(self) -> None:
        """Create run should accept the signed 64-bit inode combination during a real dry run."""
        tmp_path: Path = self.make_temp_path()
        source_path: Path = self.make_valid_source(tmp_path)
        output_path: Path = tmp_path / "out.ffpfs"
        args: SimpleNamespace = self.make_create_args(
            source_path=source_path,
            image_path=output_path,
            dry_run=True,
            verify=False,
        )
        args.inode_bits = 64
        args.signed = True
        with patch.object(cli, "validate_input", return_value=("TITLE", [])):
            self.assertEqual(cli.cli_mkpfs_create_run(args), 0)

    def test_create_run_passes_encryption_settings_to_build(self) -> None:
        """Create run should pass parsed encryption settings into the builder."""
        tmp_path: Path = self.make_temp_path()
        source_path: Path = self.make_valid_source(tmp_path)
        output_path: Path = tmp_path / "out.ffpfs"
        args: SimpleNamespace = self.make_create_args(
            source_path=source_path,
            image_path=output_path,
            dry_run=True,
            verify=False,
        )
        args.encrypted = True
        args.ekpfs_key = "12" * 32
        with patch.object(cli, "validate_input", return_value=("TITLE", [])), patch.object(
            cli,
            "build_pfs",
            return_value=BuildStats(input_path=source_path, output_path=output_path),
        ) as mocked_build:
            self.assertEqual(cli.cli_mkpfs_create_run(args), 0)
        self.assertTrue(mocked_build.call_args.kwargs["encrypted"])
        self.assertEqual(mocked_build.call_args.kwargs["ekpfs"], bytes.fromhex("12" * 32))

    def test_pack_file_run_prefers_streaming_by_default_when_supported(self) -> None:
        """Pack file should use the streaming builder by default for supported options."""
        tmp_path: Path = self.make_temp_path()
        source_file: Path = tmp_path / "sample.bin"
        source_file.write_bytes(b"payload")
        output_path: Path = tmp_path / "out.ffpfs"
        args: SimpleNamespace = self.make_pack_file_args(
            source_path=source_file,
            image_path=output_path,
            dry_run=True,
            verify=False,
        )
        with patch.object(cli, "_run_stream_pack_file", return_value=0) as mocked_stream, patch.object(
            cli,
            "_run_pack_build",
            side_effect=AssertionError("legacy fallback should not run"),
        ):
            self.assertEqual(cli.cli_mkpfs_pack_file_run(args), 0)

        mocked_stream.assert_called_once_with(args=args, source_file=source_file.resolve())

    def test_pack_file_run_uses_legacy_fallback_for_signed_images(self) -> None:
        """Single-file packing should fall back to the legacy builder for signed images."""
        tmp_path: Path = self.make_temp_path()
        source_file: Path = tmp_path / "sample.bin"
        source_file.write_bytes(b"payload")
        args: SimpleNamespace = self.make_pack_file_args(
            source_path=source_file,
            image_path=tmp_path / "out",
            dry_run=True,
            verify=False,
        )
        args.signed = True

        with patch.object(
            cli, "_run_stream_pack_file", side_effect=AssertionError("streaming should not run")
        ), patch.object(
            cli,
            "_run_pack_build",
            return_value=0,
        ) as mocked_pack:
            self.assertEqual(cli.cli_mkpfs_pack_file_run(args), 0)

        mocked_pack.assert_called_once()
        self.assertFalse(mocked_pack.call_args.kwargs["require_game_files"])

    def test_pack_file_run_uses_custom_temp_folder_for_legacy_staging_and_build(self) -> None:
        """Legacy fallback should stage the source file inside the configured temp folder."""
        tmp_path: Path = self.make_temp_path()
        source_file: Path = tmp_path / "sample.bin"
        source_file.write_bytes(b"payload")
        temp_folder: Path = tmp_path / "custom-pack-temp"
        args: SimpleNamespace = self.make_pack_file_args(
            source_path=source_file,
            image_path=tmp_path / "out",
            dry_run=True,
            verify=False,
        )
        args.signed = True
        args.temp_folder = str(temp_folder)

        def fake_run_pack_build(**kwargs: object) -> int:
            staged_root_value: object = kwargs["build_source_root"]
            self.assertIsInstance(staged_root_value, Path)
            staged_root: Path = staged_root_value
            staged_file: Path = staged_root / source_file.name
            self.assertTrue(staged_root.parent.samefile(temp_folder.resolve()))
            self.assertTrue(staged_file.is_file())
            self.assertTrue(staged_file.samefile(source_file))
            return 0

        with patch.object(
            cli, "_run_stream_pack_file", side_effect=AssertionError("streaming should not run")
        ), patch.object(
            cli,
            "_run_pack_build",
            side_effect=fake_run_pack_build,
        ):
            self.assertEqual(cli.cli_mkpfs_pack_file_run(args), 0)

    def test_pack_file_run_defaults_to_structure_verification(self) -> None:
        """Pack file should perform structure verification by default after a real pack."""
        tmp_path: Path = self.make_temp_path()
        source_file: Path = tmp_path / "sample.bin"
        source_file.write_bytes(b"payload")
        output_path: Path = tmp_path / "out.ffpfsc"
        args: SimpleNamespace = self.make_pack_file_args(
            source_path=source_file,
            image_path=output_path,
            dry_run=False,
            verify=False,
        )

        with patch.object(
            cli,
            "build_pfs_stream_single_file",
            return_value=BuildStats(input_path=source_file, output_path=output_path),
        ), patch.object(
            cli,
            "prompt_overwrite",
            return_value=True,
        ), patch.object(cli, "run_image_check", return_value=([], [], {}, -1)) as mocked_check:
            self.assertEqual(cli.cli_mkpfs_pack_file_run(args), 0)

        self.assertFalse(mocked_check.call_args.kwargs["verify_payloads"])
        self.assertFalse(mocked_check.call_args.kwargs["compare_source_contents"])
        self.assertEqual(mocked_check.call_args.kwargs["report_title"], "PFS Structure Verify Report")

    def test_pack_file_run_skip_verification_disables_post_pack_check(self) -> None:
        """Pack file should skip post-pack verification when explicitly requested."""
        tmp_path: Path = self.make_temp_path()
        source_file: Path = tmp_path / "sample.bin"
        source_file.write_bytes(b"payload")
        output_path: Path = tmp_path / "out.ffpfsc"
        args: SimpleNamespace = self.make_pack_file_args(
            source_path=source_file,
            image_path=output_path,
            dry_run=False,
            verify=False,
        )
        args.verify_structure = False
        args.skip_verification = True

        with patch.object(
            cli,
            "build_pfs_stream_single_file",
            return_value=BuildStats(input_path=source_file, output_path=output_path),
        ), patch.object(
            cli,
            "prompt_overwrite",
            return_value=True,
        ), patch.object(
            cli,
            "run_image_check",
            side_effect=AssertionError("verify should not run"),
        ):
            self.assertEqual(cli.cli_mkpfs_pack_file_run(args), 0)

    def test_pack_file_run_dry_run_skips_default_structure_verification(self) -> None:
        """Pack file dry-runs should not perform default structure verification."""
        tmp_path: Path = self.make_temp_path()
        source_file: Path = tmp_path / "sample.bin"
        source_file.write_bytes(b"payload")
        output_path: Path = tmp_path / "out.ffpfsc"
        args: SimpleNamespace = self.make_pack_file_args(
            source_path=source_file,
            image_path=output_path,
            dry_run=True,
            verify=False,
        )

        with patch.object(
            cli,
            "build_pfs_stream_single_file",
            return_value=BuildStats(input_path=source_file, output_path=output_path),
        ), patch.object(
            cli,
            "run_image_check",
            side_effect=AssertionError("verify should not run"),
        ):
            self.assertEqual(cli.cli_mkpfs_pack_file_run(args), 0)

    def test_pack_file_run_verify_enables_full_post_pack_verification(self) -> None:
        """Pack file should upgrade to full verification when --verify is enabled."""
        tmp_path: Path = self.make_temp_path()
        source_file: Path = tmp_path / "sample.bin"
        source_file.write_bytes(b"payload")
        output_path: Path = tmp_path / "out.ffpfsc"
        args: SimpleNamespace = self.make_pack_file_args(
            source_path=source_file,
            image_path=output_path,
            dry_run=False,
            verify=True,
        )
        stdout_buffer: StringIO = StringIO()

        with patch.object(
            cli,
            "build_pfs_stream_single_file",
            return_value=BuildStats(input_path=source_file, output_path=output_path),
        ), patch.object(
            cli,
            "prompt_overwrite",
            return_value=True,
        ), patch.object(cli, "run_image_check", return_value=([], [], {}, -1)) as mocked_check, redirect_stdout(
            stdout_buffer
        ):
            self.assertEqual(cli.cli_mkpfs_pack_file_run(args), 0)

        self.assertTrue(mocked_check.call_args.kwargs["verify_payloads"])
        self.assertTrue(mocked_check.call_args.kwargs["compare_source_contents"])
        self.assertEqual(mocked_check.call_args.kwargs["report_title"], "PFS Full Verify Report")
        self.assertFalse(mocked_check.call_args.kwargs["require_game_files"])
        self.assertIn("Running post-pack full verification...", stdout_buffer.getvalue())

    def test_pack_file_run_disables_game_file_checks_during_post_create_verify(self) -> None:
        """Pack file post-create verification should skip the optional game-file checklist."""
        tmp_path: Path = self.make_temp_path()
        source_file: Path = tmp_path / "sample.bin"
        source_file.write_bytes(b"payload")
        output_path: Path = tmp_path / "out.ffpfsc"
        args: SimpleNamespace = self.make_pack_file_args(
            source_path=source_file,
            image_path=output_path,
            dry_run=False,
            verify=True,
        )

        with patch.object(
            cli,
            "build_pfs_stream_single_file",
            return_value=BuildStats(input_path=source_file, output_path=output_path),
        ), patch.object(
            cli,
            "prompt_overwrite",
            return_value=True,
        ), patch.object(cli, "run_image_check", return_value=([], [], {}, -1)) as mocked_check:
            self.assertEqual(cli.cli_mkpfs_pack_file_run(args), 0)

        self.assertFalse(mocked_check.call_args.kwargs["require_game_files"])

        tmp_path: Path = self.make_temp_path()
        source_file: Path = tmp_path / "sample.bin"
        source_file.write_bytes(b"payload")

        with patch.object(cli.os, "link", side_effect=OSError("hard links unavailable")), patch.object(
            Path, "symlink_to", side_effect=OSError("symlinks unavailable")
        ), patch.object(
            cli.shutil, "copyfile", wraps=cli.shutil.copyfile
        ) as mocked_copy, cli._stage_single_file_source_root(
            source_file=source_file, temp_folder=tmp_path
        ) as staging_root:
            staged_file: Path = staging_root / source_file.name
            self.assertTrue(staged_file.is_file())
            self.assertEqual(staged_file.read_bytes(), source_file.read_bytes())
            mocked_copy.assert_called_once_with(source_file, staged_file)

    def test_stage_single_file_source_root_uses_resolved_name_when_provided(self) -> None:
        """Single-file staging should expose the requested internal file name."""
        tmp_path: Path = self.make_temp_path()
        source_file: Path = tmp_path / "My File (Demo)!!.ExFAT"
        source_file.write_bytes(b"payload")

        with cli._stage_single_file_source_root(
            source_file=source_file,
            temp_folder=tmp_path,
            staged_file_name="PPSA01325.exfat",
        ) as staging_root:
            staged_file: Path = staging_root / "PPSA01325.exfat"
            self.assertTrue(staged_file.is_file())
            self.assertEqual(staged_file.read_bytes(), source_file.read_bytes())

    def test_pack_file_run_warns_when_inner_file_name_is_renamed(self) -> None:
        """Pack file should warn when it renames the internal file name."""
        tmp_path: Path = self.make_temp_path()
        source_file: Path = tmp_path / "UP0700-CUSA03388_00-DARKSOULS3000000.ExFAT"
        source_file.write_bytes(b"payload")
        output_path: Path = tmp_path / "out.ffpfsc"
        args: SimpleNamespace = self.make_pack_file_args(
            source_path=source_file,
            image_path=output_path,
            dry_run=True,
            verify=False,
        )
        with patch.object(cli, "_run_stream_pack_file", return_value=0), patch.object(
            cli, "_stream_fallback_reason", return_value="signed images"
        ), patch.object(cli, "warning") as mocked_warning:
            self.assertEqual(cli.cli_mkpfs_pack_file_run(args), 0)

        warning_texts: list[str] = [str(call.args[0]) for call in mocked_warning.call_args_list]
        self.assertTrue(any("renamed to a safer file name" in text for text in warning_texts))

    def test_create_run_emits_red_warning_for_compressed_game_folder(self) -> None:
        """Pack folder should emit the red warning for direct game folders when compression is enabled."""
        tmp_path: Path = self.make_temp_path()
        source_path: Path = self.make_valid_source(tmp_path)
        output_path: Path = tmp_path / "out.ffpfs"
        args: SimpleNamespace = self.make_create_args(
            source_path=source_path,
            image_path=output_path,
            dry_run=True,
            verify=False,
        )
        combined: StringIO = StringIO()
        with patch.object(cli, "validate_input", return_value=("TITLE", [])), patch.object(
            cli,
            "build_pfs",
            return_value=BuildStats(input_path=source_path, output_path=output_path),
        ), redirect_stdout(combined), redirect_stderr(combined):
            self.assertEqual(cli.cli_mkpfs_create_run(args), 0)

        self.assertIn(cli._GAME_FOLDER_COMPRESS_WARNING_TEXT.splitlines()[0], combined.getvalue())

    def test_check_run_warns_when_source_file_name_differs_from_internal_name(self) -> None:
        """Verify should warn when a single-file source name differs from the internal name."""
        tmp_path: Path = self.make_temp_path()
        source_file: Path = tmp_path / "My Bad File!!.ExFAT"
        source_file.write_bytes(b"payload")
        seen_source: list[Path | None] = []

        def fake_run_image_check(
            image: Path,
            source: Path | None,
            print_tree: bool,
            expected_crc32: int | None = None,
            expected_manifest_sha256: str | None = None,
            emit_report: bool = True,
            require_game_files: bool = False,
            ekpfs: bytes | None = None,
            new_crypt: bool = False,
        ) -> tuple[list[str], list[str], dict[int, list[ParsedDirent]], int]:
            del (
                image,
                print_tree,
                expected_crc32,
                expected_manifest_sha256,
                emit_report,
                require_game_files,
                ekpfs,
                new_crypt,
            )
            seen_source.append(source)
            assert source is not None
            self.assertTrue((source / "My_Bad_File.exfat").is_file())
            return [], [], {}, -1

        args: SimpleNamespace = SimpleNamespace(
            image_file="img.ffpfs",
            source_dir=None,
            source_file=str(source_file),
            expect_crc32=None,
            expect_manifest_sha256=None,
            ekpfs_key=None,
            new_crypt=False,
            require_game_files=False,
        )
        with patch.object(cli, "run_image_check", side_effect=fake_run_image_check), patch.object(
            cli, "warning"
        ) as mocked_warning:
            self.assertEqual(cli.cli_mkpfs_check_run(args), 0)

        self.assertEqual(len(seen_source), 1)
        warning_texts: list[str] = [str(call.args[0]) for call in mocked_warning.call_args_list]
        self.assertTrue(any("does not match the internal file name" in text for text in warning_texts))

    def test_run_image_check_emits_red_warning_for_compressed_game_marker_images(self) -> None:
        """Verify should emit the red warning when a game-marker image contains any compressed file."""
        tmp_path: Path = self.make_temp_path()
        image_path: Path = tmp_path / "image.ffpfs"
        image_path.write_bytes(b"x")
        header: SimpleNamespace = SimpleNamespace(
            mode=consts.PFS_MODE_CASE_INSENSITIVE,
            version=consts.PFS_VERSION_PS5,
            magic=123,
            readonly=1,
            block_size=65536,
        )
        inodes: list[SimpleNamespace] = [
            SimpleNamespace(
                number=0,
                is_compressed=True,
                size=100,
                size_compressed=90,
                logical_size=100,
                stored_size=90,
            ),
            SimpleNamespace(
                number=1,
                is_compressed=False,
                size=50,
                size_compressed=50,
                logical_size=50,
                stored_size=50,
            ),
        ]
        combined: StringIO = StringIO()
        with ExitStack() as stack:
            stack.enter_context(patch.object(cli, "parse_image_header", return_value=header))
            stack.enter_context(patch.object(cli, "parse_image_inodes", return_value=inodes))
            stack.enter_context(patch.object(cli, "validate_inode_layout", return_value=None))
            stack.enter_context(patch.object(cli, "verify_signed_image_signatures", return_value=None))
            stack.enter_context(patch.object(cli, "parse_superroot_and_indexes", return_value=(0, {1: 2}, {}, {0})))
            stack.enter_context(
                patch.object(
                    cli,
                    "build_tree_from_uroot",
                    return_value=({"eboot.bin": 0, "other.bin": 1}, {"": 0}, {0: []}),
                )
            )
            stack.enter_context(patch.object(cli, "build_expected_fpt", return_value={1: []}))
            stack.enter_context(patch.object(cli, "validate_fpt_maps", return_value=None))
            stack.enter_context(patch.object(cli, "validate_ps5_checklist", return_value=None))
            stack.enter_context(patch.object(cli, "verify_file_payload_hashes", return_value=(2, 0x1234, "a" * 64)))
            stack.enter_context(redirect_stdout(combined))
            stack.enter_context(redirect_stderr(combined))
            errors, warnings, tree, uroot = cli.run_image_check(
                image=image_path,
                source=None,
                print_tree=False,
                emit_report=True,
            )
        self.assertEqual(errors, [])
        self.assertEqual(warnings, [])
        self.assertEqual(tree, {0: []})
        self.assertEqual(uroot, 0)
        self.assertIn(cli._GAME_FOLDER_COMPRESS_WARNING_TEXT.splitlines()[0], combined.getvalue())


class TestCliReadOnlyCommands(CliTestCase):
    """Tests for verify, inspect, tree, info, analyze, extract, and entrypoint wrappers."""

    def test_check_run_accepts_valid_expected_crc_and_manifest(self) -> None:
        """Verify should accept valid expected checksum arguments and return success when checks pass."""
        args: SimpleNamespace = SimpleNamespace(
            image_file="img.ffpfs",
            source_dir=None,
            source_file=None,
            expect_crc32="0x7F528D1F",
            expect_manifest_sha256="a" * 64,
        )
        with patch.object(cli, "run_image_check", return_value=([], [], {}, -1)):
            self.assertEqual(cli.cli_mkpfs_check_run(args), 0)

    def test_check_run_passes_require_game_files_to_image_check(self) -> None:
        """Verify should only enable the game-file checklist when explicitly requested."""
        args: SimpleNamespace = SimpleNamespace(
            image_file="img.ffpfs",
            source_dir=None,
            source_file=None,
            expect_crc32=None,
            expect_manifest_sha256=None,
            require_game_files=True,
            ekpfs_key=None,
            new_crypt=False,
        )
        with patch.object(cli, "run_image_check", return_value=([], [], {}, -1)) as mocked_run:
            self.assertEqual(cli.cli_mkpfs_check_run(args), 0)
        self.assertTrue(mocked_run.call_args.kwargs["require_game_files"])

    def test_check_run_supports_source_file_by_staging_single_file_tree(self) -> None:
        """Verify should stage a single source file as root content without copying bytes."""
        tmp_path: Path = self.make_temp_path()
        source_file: Path = tmp_path / "only.bin"
        source_file.write_bytes(b"payload")
        seen_source: list[Path | None] = []

        def fake_run_image_check(
            image: Path,
            source: Path | None,
            print_tree: bool,
            expected_crc32: int | None = None,
            expected_manifest_sha256: str | None = None,
            emit_report: bool = True,
            require_game_files: bool = False,
            ekpfs: bytes | None = None,
            new_crypt: bool = False,
        ) -> tuple[list[str], list[str], dict[int, list[ParsedDirent]], int]:
            del image, print_tree, expected_crc32, expected_manifest_sha256, emit_report, ekpfs, new_crypt
            self.assertFalse(require_game_files)
            seen_source.append(source)
            assert source is not None
            staged_file: Path = source / source_file.name
            self.assertTrue(staged_file.is_file())
            self.assertTrue(staged_file.samefile(source_file))
            return [], [], {}, -1

        args: SimpleNamespace = SimpleNamespace(
            image_file="img.ffpfs",
            source_dir=None,
            source_file=str(source_file),
            expect_crc32=None,
            expect_manifest_sha256=None,
            ekpfs_key=None,
            new_crypt=False,
        )
        with patch.object(cli, "run_image_check", side_effect=fake_run_image_check):
            self.assertEqual(cli.cli_mkpfs_check_run(args), 0)
        self.assertEqual(len(seen_source), 1)

    def test_check_run_rejects_source_dir_and_source_file_together(self) -> None:
        """Verify should reject combining source-dir and source-file in direct handler calls."""
        args: SimpleNamespace = SimpleNamespace(
            image_file="img.ffpfs",
            source_dir="src",
            source_file="file.bin",
            expect_crc32=None,
            expect_manifest_sha256=None,
            ekpfs_key=None,
            new_crypt=False,
        )
        self.assertEqual(cli.cli_mkpfs_check_run(args), 2)

    def test_check_parser_rejects_source_dir_and_source_file_together(self) -> None:
        """Verify parser should enforce source-dir/source-file mutual exclusion."""
        with self.assertRaises(SystemExit) as excinfo:
            cli.cli_mkpfs_main(
                [
                    "verify",
                    "img.ffpfs",
                    "--source-dir",
                    "src",
                    "--source-file",
                    "file.bin",
                ]
            )
        self.assertEqual(excinfo.exception.code, 2)

    def test_check_run_rejects_invalid_crc_and_manifest_values(self) -> None:
        """Verify should reject malformed CRC32 and manifest checksum arguments."""
        with patch.object(cli, "run_image_check", return_value=([], [], {}, -1)):
            self.assertEqual(
                cli.cli_mkpfs_check_run(
                    SimpleNamespace(
                        image_file="img",
                        source_dir=None,
                        source_file=None,
                        expect_crc32="0xZZ",
                        expect_manifest_sha256=None,
                    )
                ),
                2,
            )
            self.assertEqual(
                cli.cli_mkpfs_check_run(
                    SimpleNamespace(
                        image_file="img",
                        source_dir=None,
                        source_file=None,
                        expect_crc32="0x123456789",
                        expect_manifest_sha256=None,
                    )
                ),
                2,
            )
            self.assertEqual(
                cli.cli_mkpfs_check_run(
                    SimpleNamespace(
                        image_file="img",
                        source_dir=None,
                        source_file=None,
                        expect_crc32="-1",
                        expect_manifest_sha256=None,
                    )
                ),
                2,
            )
            self.assertEqual(
                cli.cli_mkpfs_check_run(
                    SimpleNamespace(
                        image_file="img",
                        source_dir=None,
                        source_file=None,
                        expect_crc32=None,
                        expect_manifest_sha256="abc",
                    )
                ),
                2,
            )

    def test_ls_run_returns_success_and_prints_tree_for_valid_images(self) -> None:
        """Tree listing should print a root marker and return success for a valid image."""
        stdout_buffer: StringIO = StringIO()
        dirents: dict[int, list[ParsedDirent]] = {0: [ParsedDirent(inode_number=1, type_code=1, name="file")]}
        with patch.object(cli, "run_image_check", return_value=([], [], dirents, 0)), redirect_stdout(stdout_buffer):
            self.assertEqual(cli.cli_mkpfs_ls_run(SimpleNamespace(image_file="img")), 0)
        self.assertIn("/", stdout_buffer.getvalue())

    def test_ls_run_returns_failure_for_invalid_images(self) -> None:
        """Tree listing should return a failure code when image validation reports errors."""
        with patch.object(cli, "run_image_check", return_value=(["bad"], [], {}, -1)):
            self.assertEqual(cli.cli_mkpfs_ls_run(SimpleNamespace(image_file="img")), 1)

    def test_info_run_returns_error_code_when_errors_are_present(self) -> None:
        """Info output should surface warnings and return a failure code when errors exist."""
        info_result: PFSImageInfo = PFSImageInfo(image=Path("img.ffpfs"))
        info_result.warnings = ["warn"]
        info_result.errors = ["err"]
        with patch.object(cli, "read_pfs_info", return_value=info_result):
            self.assertEqual(cli.cli_mkpfs_info_run(SimpleNamespace(image_file="img.ffpfs")), 1)

    def test_info_run_prints_header_details_when_header_is_available(self) -> None:
        """Info output should include header metadata when the image header exists."""
        info_result: PFSImageInfo = PFSImageInfo(image=Path("img.ffpfs"))
        info_result.header = SimpleNamespace(version=0, block_size=65536, magic=0xABCD)
        stdout_buffer: StringIO = StringIO()
        with patch.object(cli, "read_pfs_info", return_value=info_result), redirect_stdout(stdout_buffer):
            self.assertEqual(cli.cli_mkpfs_info_run(SimpleNamespace(image_file="img.ffpfs")), 0)
        output_text: str = stdout_buffer.getvalue()
        self.assertIn("PFS Image Info", output_text)
        self.assertIn("Header magic:0x000000000000ABCD", output_text)

    def test_analyze_run_handles_invalid_and_valid_checksum_inputs(self) -> None:
        """Analyze should reject bad checksum inputs and succeed for valid inputs with no errors."""
        self.assertEqual(
            cli.cli_mkpfs_analyze_run(
                SimpleNamespace(
                    image="img", source=None, expected_crc32="zz", expected_manifest_sha256=None, print_tree=False
                )
            ),
            2,
        )
        self.assertEqual(
            cli.cli_mkpfs_analyze_run(
                SimpleNamespace(
                    image="img",
                    source=None,
                    expected_crc32=None,
                    expected_manifest_sha256="deadbeef",
                    print_tree=False,
                )
            ),
            2,
        )

        inspection: PFSImageInspection = PFSImageInspection(image=Path("img"))
        inspection.header = SimpleNamespace(version=0, block_size=65536, magic=consts.PFS_MAGIC)
        inspection.warnings = []
        inspection.errors = []
        inspection.dirents_by_inode = {}
        inspection.uroot_inode = 0
        with patch.object(cli, "inspect_pfs_image", return_value=inspection):
            self.assertEqual(
                cli.cli_mkpfs_analyze_run(
                    SimpleNamespace(
                        image="img",
                        source=None,
                        expected_crc32="0x1A2B",
                        expected_manifest_sha256="a" * 64,
                        print_tree=False,
                    )
                ),
                0,
            )

    def test_analyze_run_can_print_tree_for_successful_inspection(self) -> None:
        """Analyze should print the tree when requested and the inspection includes tree data."""
        inspection: PFSImageInspection = PFSImageInspection(image=Path("img"))
        inspection.header = SimpleNamespace(version=0, block_size=65536, magic=consts.PFS_MAGIC)
        inspection.warnings = []
        inspection.errors = []
        inspection.dirents_by_inode = {0: [ParsedDirent(inode_number=1, type_code=1, name="file")]}
        inspection.uroot_inode = 0
        stdout_buffer: StringIO = StringIO()
        with patch.object(cli, "inspect_pfs_image", return_value=inspection), redirect_stdout(stdout_buffer):
            self.assertEqual(
                cli.cli_mkpfs_analyze_run(
                    SimpleNamespace(
                        image="img", source=None, expected_crc32=None, expected_manifest_sha256=None, print_tree=True
                    )
                ),
                0,
            )
        self.assertIn("/", stdout_buffer.getvalue())

    def test_extract_run_handles_existing_paths_success_warnings_and_errors(self) -> None:
        """Extract should reject existing outputs without overwrite and honor result warnings or errors."""
        tmp_path: Path = self.make_temp_path()
        existing_dir: Path = tmp_path / "outdir"
        existing_dir.mkdir()
        self.assertEqual(
            cli.cli_mkpfs_extract_run(
                SimpleNamespace(image_file="does-not-exist.img", output_dir=str(existing_dir), overwrite=False)
            ),
            2,
        )

        warning_result: PFSExtractionResult = PFSExtractionResult(image=Path("img"), output_path=tmp_path / "out")
        warning_result.warnings.append("warn")
        with patch.object(cli, "extract_pfs_image", return_value=warning_result):
            self.assertEqual(
                cli.cli_mkpfs_extract_run(
                    SimpleNamespace(image_file="img", output_dir=str(tmp_path / "out"), overwrite=True)
                ),
                0,
            )

        error_result: PFSExtractionResult = PFSExtractionResult(image=Path("img"), output_path=tmp_path / "bad")
        error_result.errors.append("failed")
        with patch.object(cli, "extract_pfs_image", return_value=error_result):
            self.assertEqual(
                cli.cli_mkpfs_extract_run(
                    SimpleNamespace(image_file="img", output_dir=str(tmp_path / "bad"), overwrite=True)
                ),
                1,
            )

    def test_main_and_compat_wrapper_dispatch_to_selected_handlers(self) -> None:
        """The canonical main function should dispatch to the selected subcommand handler."""
        parser: argparse.ArgumentParser = argparse.ArgumentParser()
        subparsers = parser.add_subparsers(dest="command", required=True)
        noop_parser = subparsers.add_parser("noop")

        def handler(_args: argparse.Namespace) -> int:
            return 123

        noop_parser.set_defaults(func=handler)
        with patch.object(cli, "cli_mkpfs_main_parsers", return_value=parser):
            self.assertEqual(cli.cli_mkpfs_main(["noop"]), 123)


class TestRunImageCheck(CliTestCase):
    """Tests for the image-check orchestration helper in the CLI module."""

    def test_run_image_check_returns_a_user_friendly_error_for_missing_files(self) -> None:
        """Checking a missing image should return a single descriptive error and no tree data."""
        errors: list[str]
        warnings: list[str]
        tree: dict[int, list[ParsedDirent]]
        uroot: int
        errors, warnings, tree, uroot = cli.run_image_check(
            image=Path("missing.ffpfs"),
            source=None,
            print_tree=False,
            emit_report=False,
        )
        self.assertEqual(len(errors), 1)
        self.assertEqual(warnings, [])
        self.assertEqual(tree, {})
        self.assertEqual(uroot, -1)

    def test_run_image_check_reports_tree_and_success_for_happy_path(self) -> None:
        """A happy-path image check should return the parsed tree and no validation issues."""
        tmp_path: Path = self.make_temp_path()
        image_path: Path = tmp_path / "image.ffpfs"
        image_path.write_bytes(b"x")
        header: SimpleNamespace = SimpleNamespace(mode=0, version=0, magic=123, readonly=1, block_size=65536)
        inodes: list[SimpleNamespace] = [
            SimpleNamespace(
                number=0,
                is_compressed=False,
                size=100,
                size_compressed=90,
                logical_size=100,
                stored_size=90,
            )
        ]
        with ExitStack() as stack:
            stack.enter_context(patch.object(cli, "parse_image_header", return_value=header))
            stack.enter_context(patch.object(cli, "parse_image_inodes", return_value=inodes))
            stack.enter_context(patch.object(cli, "validate_inode_layout", return_value=None))
            stack.enter_context(patch.object(cli, "verify_signed_image_signatures", return_value=None))
            stack.enter_context(patch.object(cli, "parse_superroot_and_indexes", return_value=(0, {1: 2}, {}, {0})))
            stack.enter_context(
                patch.object(cli, "build_tree_from_uroot", return_value=({"file.bin": 0}, {"": 0}, {0: []}))
            )
            stack.enter_context(patch.object(cli, "build_expected_fpt", return_value={1: []}))
            stack.enter_context(patch.object(cli, "validate_fpt_maps", return_value=None))
            stack.enter_context(patch.object(cli, "validate_ps5_checklist", return_value=None))
            stack.enter_context(patch.object(cli, "verify_file_payload_hashes", return_value=(1, 0x1234, "a" * 64)))
            stack.enter_context(patch.object(cli, "validate_source_paths", return_value=["file.bin"]))
            stack.enter_context(patch.object(cli, "validate_source_match", return_value=None))
            stack.enter_context(patch.object(cli, "render_tree", return_value=["|- file.bin"]))
            errors, warnings, tree, uroot = cli.run_image_check(
                image=image_path,
                source=tmp_path,
                print_tree=True,
                expected_crc32=0x1234,
                expected_manifest_sha256="a" * 64,
                emit_report=True,
            )
        self.assertEqual(errors, [])
        self.assertEqual(warnings, [])
        self.assertEqual(tree, {0: []})
        self.assertEqual(uroot, 0)

    def test_run_image_check_skips_game_file_checklist_by_default(self) -> None:
        """Image checks should not emit game-file warnings unless explicitly requested."""
        tmp_path: Path = self.make_temp_path()
        image_path: Path = tmp_path / "image.ffpfs"
        image_path.write_bytes(b"x")
        header: SimpleNamespace = SimpleNamespace(
            mode=consts.PFS_MODE_CASE_INSENSITIVE,
            version=consts.PFS_VERSION_PS5,
            magic=123,
            readonly=1,
            block_size=65536,
        )
        inodes: list[SimpleNamespace] = [
            SimpleNamespace(
                number=0,
                is_compressed=False,
                size=100,
                size_compressed=90,
                logical_size=100,
                stored_size=90,
            )
        ]
        with ExitStack() as stack:
            stack.enter_context(patch.object(cli, "parse_image_header", return_value=header))
            stack.enter_context(patch.object(cli, "parse_image_inodes", return_value=inodes))
            stack.enter_context(patch.object(cli, "validate_inode_layout", return_value=None))
            stack.enter_context(patch.object(cli, "verify_signed_image_signatures", return_value=None))
            stack.enter_context(patch.object(cli, "parse_superroot_and_indexes", return_value=(0, {1: 2}, {}, {0})))
            stack.enter_context(
                patch.object(cli, "build_tree_from_uroot", return_value=({"file.bin": 0}, {"": 0}, {0: []}))
            )
            stack.enter_context(patch.object(cli, "build_expected_fpt", return_value={1: []}))
            stack.enter_context(patch.object(cli, "validate_fpt_maps", return_value=None))
            mocked_checklist = stack.enter_context(patch.object(cli, "validate_ps5_checklist", return_value=None))
            stack.enter_context(patch.object(cli, "verify_file_payload_hashes", return_value=(1, 0x1234, "a" * 64)))
            errors, warnings, tree, uroot = cli.run_image_check(
                image=image_path,
                source=None,
                print_tree=False,
                emit_report=False,
            )
        self.assertEqual(errors, [])
        self.assertEqual(warnings, [])
        self.assertEqual(tree, {0: []})
        self.assertEqual(uroot, 0)
        mocked_checklist.assert_not_called()

    def test_run_image_check_runs_game_file_checklist_when_requested(self) -> None:
        """Image checks should run the game-file checklist when explicitly requested."""
        tmp_path: Path = self.make_temp_path()
        image_path: Path = tmp_path / "image.ffpfs"
        image_path.write_bytes(b"x")
        header: SimpleNamespace = SimpleNamespace(
            mode=consts.PFS_MODE_CASE_INSENSITIVE,
            version=consts.PFS_VERSION_PS5,
            magic=123,
            readonly=1,
            block_size=65536,
        )
        inodes: list[SimpleNamespace] = [
            SimpleNamespace(
                number=0,
                is_compressed=False,
                size=100,
                size_compressed=90,
                logical_size=100,
                stored_size=90,
            )
        ]
        with ExitStack() as stack:
            stack.enter_context(patch.object(cli, "parse_image_header", return_value=header))
            stack.enter_context(patch.object(cli, "parse_image_inodes", return_value=inodes))
            stack.enter_context(patch.object(cli, "validate_inode_layout", return_value=None))
            stack.enter_context(patch.object(cli, "verify_signed_image_signatures", return_value=None))
            stack.enter_context(patch.object(cli, "parse_superroot_and_indexes", return_value=(0, {1: 2}, {}, {0})))
            stack.enter_context(
                patch.object(cli, "build_tree_from_uroot", return_value=({"file.bin": 0}, {"": 0}, {0: []}))
            )
            stack.enter_context(patch.object(cli, "build_expected_fpt", return_value={1: []}))
            stack.enter_context(patch.object(cli, "validate_fpt_maps", return_value=None))
            mocked_checklist = stack.enter_context(patch.object(cli, "validate_ps5_checklist", return_value=None))
            stack.enter_context(patch.object(cli, "verify_file_payload_hashes", return_value=(1, 0x1234, "a" * 64)))
            errors, warnings, tree, uroot = cli.run_image_check(
                image=image_path,
                source=None,
                print_tree=False,
                emit_report=False,
                require_game_files=True,
            )
        self.assertEqual(errors, [])
        self.assertEqual(warnings, [])
        self.assertEqual(tree, {0: []})
        self.assertEqual(uroot, 0)
        mocked_checklist.assert_called_once()

    def test_run_image_check_path_only_mode_skips_content_reads(self) -> None:
        """Structure checks should compare file paths without hashing payload contents."""
        tmp_path: Path = self.make_temp_path()
        image_path: Path = tmp_path / "image.ffpfs"
        image_path.write_bytes(b"x")
        source_path: Path = tmp_path / "source"
        source_path.mkdir()
        header: SimpleNamespace = SimpleNamespace(mode=0, version=0, magic=123, readonly=1, block_size=65536)
        inodes: list[SimpleNamespace] = [
            SimpleNamespace(
                number=0,
                is_compressed=False,
                size=100,
                size_compressed=90,
                logical_size=100,
                stored_size=90,
            )
        ]
        with ExitStack() as stack:
            stack.enter_context(patch.object(cli, "parse_image_header", return_value=header))
            stack.enter_context(patch.object(cli, "parse_image_inodes", return_value=inodes))
            stack.enter_context(patch.object(cli, "validate_inode_layout", return_value=None))
            stack.enter_context(patch.object(cli, "verify_signed_image_signatures", return_value=None))
            stack.enter_context(patch.object(cli, "parse_superroot_and_indexes", return_value=(0, {1: 2}, {}, {0})))
            stack.enter_context(
                patch.object(cli, "build_tree_from_uroot", return_value=({"file.bin": 0}, {"": 0}, {0: []}))
            )
            stack.enter_context(patch.object(cli, "build_expected_fpt", return_value={1: []}))
            stack.enter_context(patch.object(cli, "validate_fpt_maps", return_value=None))
            mocked_paths = stack.enter_context(patch.object(cli, "validate_source_paths", return_value=["file.bin"]))
            mocked_match = stack.enter_context(patch.object(cli, "validate_source_match", return_value=None))
            mocked_hashes = stack.enter_context(
                patch.object(cli, "verify_file_payload_hashes", return_value=(1, 0x1234, "a" * 64))
            )
            errors, warnings, tree, uroot = cli.run_image_check(
                image=image_path,
                source=source_path,
                print_tree=False,
                emit_report=False,
                verify_payloads=False,
                compare_source_contents=False,
            )
        self.assertEqual(errors, [])
        self.assertEqual(warnings, [])
        self.assertEqual(tree, {0: []})
        self.assertEqual(uroot, 0)
        mocked_paths.assert_called_once_with(file_inodes={"file.bin": 0}, source=source_path, errors=[])
        mocked_match.assert_not_called()
        mocked_hashes.assert_not_called()

    def test_run_image_check_defaults_to_source_content_comparison(self) -> None:
        """Full checks should keep source content comparison enabled by default."""
        tmp_path: Path = self.make_temp_path()
        image_path: Path = tmp_path / "image.ffpfs"
        image_path.write_bytes(b"x")
        source_path: Path = tmp_path / "source"
        source_path.mkdir()
        header: SimpleNamespace = SimpleNamespace(mode=0, version=0, magic=123, readonly=1, block_size=65536)
        inodes: list[SimpleNamespace] = [
            SimpleNamespace(
                number=0,
                is_compressed=False,
                size=100,
                size_compressed=90,
                logical_size=100,
                stored_size=90,
            )
        ]
        with ExitStack() as stack:
            stack.enter_context(patch.object(cli, "parse_image_header", return_value=header))
            stack.enter_context(patch.object(cli, "parse_image_inodes", return_value=inodes))
            stack.enter_context(patch.object(cli, "validate_inode_layout", return_value=None))
            stack.enter_context(patch.object(cli, "verify_signed_image_signatures", return_value=None))
            stack.enter_context(patch.object(cli, "parse_superroot_and_indexes", return_value=(0, {1: 2}, {}, {0})))
            stack.enter_context(
                patch.object(cli, "build_tree_from_uroot", return_value=({"file.bin": 0}, {"": 0}, {0: []}))
            )
            stack.enter_context(patch.object(cli, "build_expected_fpt", return_value={1: []}))
            stack.enter_context(patch.object(cli, "validate_fpt_maps", return_value=None))
            stack.enter_context(patch.object(cli, "validate_source_paths", return_value=["file.bin"]))
            mocked_match = stack.enter_context(patch.object(cli, "validate_source_match", return_value=None))
            mocked_hashes = stack.enter_context(
                patch.object(cli, "verify_file_payload_hashes", return_value=(1, 0x1234, "a" * 64))
            )
            errors, warnings, tree, uroot = cli.run_image_check(
                image=image_path,
                source=source_path,
                print_tree=False,
                emit_report=False,
            )
        self.assertEqual(errors, [])
        self.assertEqual(warnings, [])
        self.assertEqual(tree, {0: []})
        self.assertEqual(uroot, 0)
        mocked_hashes.assert_called_once()
        mocked_match.assert_called_once()

    """Tests for the spool-free streaming flag on the file pack path."""

    def test_pack_file_stream_auto_block_size_defaults_min_compress_size_to_65536(self) -> None:
        """Streaming single-file mode should map min_compress_size=0 to the auto block-size value."""
        tmp_path: Path = self.make_temp_path()
        src: Path = tmp_path / "payload.bin"
        src.write_bytes(b"DATA" * 1000)
        out: Path = tmp_path / "payload.ffpfsc"
        args: SimpleNamespace = self.make_pack_file_args(source_path=src, image_path=out, dry_run=True, verify=False)
        args.block_size = "auto"
        with patch.object(
            cli,
            "build_pfs_stream_single_file",
            return_value=self.make_build_stats(tmp_path),
        ) as mocked_build:
            self.assertEqual(cli.cli_mkpfs_pack_file_run(args), 0)
        self.assertEqual(mocked_build.call_args.kwargs["block_size"], 65536)
        self.assertEqual(mocked_build.call_args.kwargs["min_compress_size"], 65536)

    def test_pack_file_auto_fit_fallback_defaults_min_compress_size_to_selected_block_size(self) -> None:
        """Fallback single-file mode should map min_compress_size=0 to the resolved auto-fit block size."""
        tmp_path: Path = self.make_temp_path()
        src: Path = tmp_path / "payload.bin"
        src.write_bytes(b"DATA" * 500)
        out: Path = tmp_path / "payload.ffpfsc"
        args: SimpleNamespace = self.make_pack_file_args(source_path=src, image_path=out, dry_run=True, verify=False)
        args.block_size = "auto-fit"
        with patch.object(cli, "build_pfs", return_value=self.make_build_stats(tmp_path)) as mocked_build:
            self.assertEqual(cli.cli_mkpfs_pack_file_run(args), 0)
        resolved_block_size: int = mocked_build.call_args.kwargs["block_size"]
        self.assertEqual(mocked_build.call_args.kwargs["min_compress_size"], resolved_block_size)

    def test_pack_file_streams_by_default_without_spool(self) -> None:
        """`pack file` streams by default and leaves no spool in the temp folder."""
        tmp_path: Path = self.make_temp_path()
        src: Path = tmp_path / "PPSA.exfat"
        src.write_bytes(b"DATA" * 20000 + b"\x00" * 60000)
        temp: Path = tmp_path / "temp"
        temp.mkdir()
        out: Path = tmp_path / "PPSA.ffpfsc"
        buffer: StringIO = StringIO()
        with patch.object(cli, "prompt_overwrite", return_value=True), redirect_stdout(buffer), redirect_stderr(
            StringIO()
        ):
            rc: int = cli_mkpfs_main(
                [
                    "pack",
                    "file",
                    str(src),
                    str(out),
                    "--version",
                    "PS5",
                    "--inode-bits",
                    "32",
                    "--temp-folder",
                    str(temp),
                    "--no-adjust-output-file-extension",
                ]
            )
        self.assertEqual(rc, 0)
        self.assertTrue(out.exists())
        self.assertEqual(list(temp.glob("mkpfs-*.pfsc")), [])

    def test_pack_file_use_spool_forces_legacy_builder(self) -> None:
        """`--use-spool` forces the legacy staged/spool builder even when streaming is supported."""
        tmp_path: Path = self.make_temp_path()
        src: Path = tmp_path / "x.exfat"
        src.write_bytes(b"x" * 1000)
        out: Path = tmp_path / "x.ffpfsc"
        args: SimpleNamespace = self.make_pack_file_args(source_path=src, image_path=out, dry_run=True, verify=False)
        args.use_spool = True
        with patch.object(
            cli, "_run_stream_pack_file", side_effect=AssertionError("streaming should not run")
        ), patch.object(
            cli,
            "_run_pack_build",
            return_value=0,
        ) as mocked_pack:
            self.assertEqual(cli.cli_mkpfs_pack_file_run(args), 0)
        mocked_pack.assert_called_once()

    def test_pack_file_falls_back_for_signed_with_notice(self) -> None:
        """`--signed` falls back to the legacy builder and prints a notice."""
        tmp_path: Path = self.make_temp_path()
        src: Path = tmp_path / "x.exfat"
        src.write_bytes(b"x" * 1000)
        out: Path = tmp_path / "x.ffpfsc"
        args: SimpleNamespace = self.make_pack_file_args(source_path=src, image_path=out, dry_run=True, verify=False)
        args.signed = True
        buffer: StringIO = StringIO()
        with patch.object(
            cli, "_run_stream_pack_file", side_effect=AssertionError("streaming should not run")
        ), patch.object(cli, "_run_pack_build", return_value=0) as mocked_pack, redirect_stdout(buffer):
            self.assertEqual(cli.cli_mkpfs_pack_file_run(args), 0)
        mocked_pack.assert_called_once()
        self.assertIn("signed images", buffer.getvalue())

    def test_pack_folder_does_not_accept_use_spool(self) -> None:
        """The --use-spool flag is only available on the file path, not the folder path."""
        parser: argparse.ArgumentParser = cli.cli_mkpfs_main_parsers()
        with self.assertRaises(SystemExit):
            parser.parse_args(["pack", "folder", "src", "out", "--use-spool"])

    def test_pack_file_streaming_with_verify_succeeds(self) -> None:
        """`pack file --verify` completes the post-create check without errors."""
        tmp_path: Path = self.make_temp_path()
        src: Path = tmp_path / "PPSA.exfat"
        src.write_bytes(b"GAMEDATA" * 20000 + b"\x00" * 200000)
        out: Path = tmp_path / "PPSA.ffpfsc"
        buffer: StringIO = StringIO()
        with patch.object(cli, "prompt_overwrite", return_value=True), redirect_stdout(buffer), redirect_stderr(
            StringIO()
        ):
            rc: int = cli_mkpfs_main(
                [
                    "pack",
                    "file",
                    str(src),
                    str(out),
                    "--version",
                    "PS5",
                    "--inode-bits",
                    "32",
                    "--verify",
                    "--temp-folder",
                    str(tmp_path / "temp"),
                    "--no-adjust-output-file-extension",
                ]
            )
        self.assertEqual(rc, 0)

    def test_pack_file_streaming_prints_parameters_and_progress(self) -> None:
        """The streaming path prints the parameters banner and a compression status line."""
        tmp_path: Path = self.make_temp_path()
        src: Path = tmp_path / "PPSA.exfat"
        src.write_bytes(b"GAMEDATA" * 20000 + b"\x00" * 200000)
        out: Path = tmp_path / "PPSA.ffpfsc"
        stdout_buffer: StringIO = StringIO()
        stderr_buffer: StringIO = StringIO()
        with patch.object(cli, "prompt_overwrite", return_value=True), redirect_stdout(stdout_buffer), redirect_stderr(
            stderr_buffer
        ):
            rc: int = cli_mkpfs_main(
                [
                    "pack",
                    "file",
                    str(src),
                    str(out),
                    "--version",
                    "PS5",
                    "--inode-bits",
                    "32",
                    "--temp-folder",
                    str(tmp_path / "temp"),
                    "--no-adjust-output-file-extension",
                ]
            )
        self.assertEqual(rc, 0)
        combined: str = stdout_buffer.getvalue() + stderr_buffer.getvalue()
        self.assertIn("PFS Image Builder - Parameters", combined)
        self.assertIn("Source path:", combined)
        self.assertIn("Compressing 1 file", combined)

    def test_pack_file_falls_back_for_inode_bits_64(self) -> None:
        """64-bit inode requests fall back to the legacy single-file builder."""
        tmp_path: Path = self.make_temp_path()
        src: Path = tmp_path / "x.exfat"
        src.write_bytes(b"x" * 1000)
        out: Path = tmp_path / "x.ffpfsc"
        args: SimpleNamespace = self.make_pack_file_args(source_path=src, image_path=out, dry_run=True, verify=False)
        args.inode_bits = 64
        with patch.object(
            cli, "_run_stream_pack_file", side_effect=AssertionError("streaming should not run")
        ), patch.object(
            cli,
            "_run_pack_build",
            return_value=0,
        ) as mocked_pack:
            self.assertEqual(cli.cli_mkpfs_pack_file_run(args), 0)
        mocked_pack.assert_called_once()

    def test_pack_file_falls_back_for_auto_fit_block_size(self) -> None:
        """Auto-fit block size requests fall back to the legacy single-file builder."""
        tmp_path: Path = self.make_temp_path()
        src: Path = tmp_path / "x.exfat"
        src.write_bytes(b"x" * 1000)
        out: Path = tmp_path / "x.ffpfsc"
        args: SimpleNamespace = self.make_pack_file_args(source_path=src, image_path=out, dry_run=True, verify=False)
        args.block_size = "auto-fit"
        with patch.object(
            cli, "_run_stream_pack_file", side_effect=AssertionError("streaming should not run")
        ), patch.object(
            cli,
            "_run_pack_build",
            return_value=0,
        ) as mocked_pack:
            self.assertEqual(cli.cli_mkpfs_pack_file_run(args), 0)
        mocked_pack.assert_called_once()

    def test_pack_file_streaming_dry_run_writes_nothing(self) -> None:
        """`pack file --dry-run` reports layout without writing an image."""
        tmp_path: Path = self.make_temp_path()
        src: Path = tmp_path / "PPSA.exfat"
        src.write_bytes(b"DATA" * 20000 + b"\x00" * 60000)
        out: Path = tmp_path / "PPSA.ffpfsc"
        buffer: StringIO = StringIO()
        with patch.object(cli, "prompt_overwrite", return_value=True), redirect_stdout(buffer), redirect_stderr(
            StringIO()
        ):
            rc: int = cli_mkpfs_main(
                ["pack", "file", str(src), str(out), "--dry-run", "--no-adjust-output-file-extension"]
            )
        self.assertEqual(rc, 0)
        self.assertFalse(out.exists())


class TestCliTreeStructureOnly(CliTestCase):
    """The tree command should render structure without decoding file payloads."""

    def test_tree_does_not_decode_file_payloads(self) -> None:
        """`mkpfs tree` builds the listing from metadata only, skipping payload hashing."""
        tmp_path: Path = self.make_temp_path()
        src: Path = tmp_path / "blob.exfat"
        src.write_bytes((b"GAMEDATA" * 4000) + b"\x00" * 200_000)
        out: Path = tmp_path / "blob.ffpfsc"
        cli.build_pfs_stream_single_file(
            source_file=src,
            output_path=out,
            block_size=65536,
            pfs_version=consts.PFS_VERSION_PS5,
            case_insensitive=True,
            zlib_level=9,
            threshold_gain=0,
            min_file_gain=0,
            min_compress_size=0,
            cpu_count=1,
            compress=True,
        )
        buffer: StringIO = StringIO()
        with patch.object(cli, "verify_file_payload_hashes") as mock_verify, redirect_stdout(buffer), redirect_stderr(
            StringIO()
        ):
            rc: int = cli_mkpfs_main(["tree", str(out)])
        self.assertEqual(rc, 0)
        mock_verify.assert_not_called()
        self.assertIn("blob.exfat", buffer.getvalue())
