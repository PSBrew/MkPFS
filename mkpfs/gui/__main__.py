"""Entry point for the PyInstaller-frozen MkPFS GUI application and ``python -m mkpfs.gui``.

PyInstaller targets this file directly (not ``__init__.py``) because ``__init__.py``
uses relative imports that fail in a frozen context where the file is executed as
``__main__`` with no ``__package__`` set.
"""

from __future__ import annotations

import multiprocessing
import sys

# Important on Windows: ensure multiprocessing-spawned children are handled
# before we decide which entrypoint to take.
multiprocessing.freeze_support()

# Lightweight router:
# - Normal launch → start the GUI (imports heavy GUI stack only on this path)
# - Special marker ``--gui-subprocess`` → run the CLI inside this same frozen
#   binary so the GUI can spawn a child process, stream its stdout/stderr, and
#   retain a handle for cancellation.  The marker is checked *after*
#   ``freeze_support()`` so multiprocessing-spawned children never take this
#   branch.
if "--gui-subprocess" in sys.argv:
    idx: int = sys.argv.index("--gui-subprocess")
    cli_args: list[str] = sys.argv[idx + 1 :]
    from mkpfs.cli import cli_mkpfs_main

    raise SystemExit(int(cli_mkpfs_main(cli_args)))

from mkpfs.gui.app import main  # ruff: ignore[module-import-not-at-top-of-file]

if __name__ == "__main__":
    main()
