"""MKPFS CLI main() hook."""

from __future__ import annotations

from mkpfs.cli import cli_mkpfs_main


def main(argv: list[str] | None = None) -> int:
    """Entrypoint for ``python -m mkpfs``.

    Args:
        argv: Optional argument vector. When omitted, sys.argv is used by
            the argument parser.

    Returns:
        The integer exit code from the CLI handler.
    """
    return cli_mkpfs_main(argv)


# When executed as a script, run the main entrypoint.
if __name__ == "__main__":
    raise SystemExit(main())
