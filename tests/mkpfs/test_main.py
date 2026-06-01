from __future__ import annotations

import runpy
import unittest
from contextlib import redirect_stdout
from io import StringIO
from unittest.mock import patch

import mkpfs.cli as cli


class TestMainModule(unittest.TestCase):
    """Tests for the package ``__main__`` entrypoint module."""

    def test_main_help_exits_successfully_and_prints_description(self) -> None:
        """Calling ``main(['-h'])`` should exit cleanly and print CLI help text."""
        buffer: StringIO = StringIO()
        with self.assertRaises(SystemExit) as excinfo, redirect_stdout(buffer):
            cli.cli_mkpfs_main(["-h"])

        self.assertEqual(excinfo.exception.code, 0)
        self.assertIn("CLI for pack folder/file, verify, inspect, tree, and unpack PFS operations", buffer.getvalue())

    def test_module_execution_exits_with_the_stubbed_cli_code(self) -> None:
        """Executing ``mkpfs.__main__`` should raise ``SystemExit`` with the CLI return code."""
        with patch.object(cli, "cli_mkpfs_main", return_value=0), self.assertRaises(SystemExit) as excinfo:
            runpy.run_module("mkpfs.__main__", run_name="__main__")

        self.assertEqual(excinfo.exception.code, 0)

    def test_console_script_main_symbol_routes_to_canonical_handler(self) -> None:
        """The installed console-script entrypoint should delegate to the canonical CLI handler."""
        with patch.object(cli, "cli_mkpfs_main", return_value=17):
            self.assertEqual(cli.main(["-h"]), 17)
