"""Entry point for the PyInstaller-frozen MkPFS GUI application and ``python -m mkpfs.gui``.

PyInstaller targets this file directly (not ``__init__.py``) because ``__init__.py``
uses relative imports that fail in a frozen context where the file is executed as
``__main__`` with no ``__package__`` set.
"""

from __future__ import annotations

import multiprocessing

multiprocessing.freeze_support()

from mkpfs.gui.app import main  # ruff: ignore[module-import-not-at-top-of-file]

if __name__ == "__main__":
    main()
