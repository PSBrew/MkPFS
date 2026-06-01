from __future__ import annotations

import unittest

import mkpfs


class TestPackageMetadata(unittest.TestCase):
    """Tests for package-level metadata exposed by the root module."""

    def test_package_docstring_mentions_mkpfs_toolkit(self) -> None:
        """The package docstring should mention the MkPFS toolkit name."""
        doc: str | None = mkpfs.__doc__
        self.assertIsNotNone(doc)
        self.assertIn("MkPFS", doc)
