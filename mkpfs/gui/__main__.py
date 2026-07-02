"""Entry point for mkpfs.gui when executed with `python -m mkpfs.gui`.

This module ensures multiprocessing.freeze_support() is called (required for
Windows/PyInstaller single-file builds) and then delegates to the GUI main()
function exposed by the original top-level shim module (mkpfs/gui.py).

The delegation tries a direct import of mkpfs.gui (which should resolve to the
original shim module). If that import fails or yields the package itself,
this file will fall back to loading the shim file from disk and executing it
as the module name "mkpfs.gui" so the expected top-level API is available.
"""

import importlib
import importlib.util
import multiprocessing
import sys
from pathlib import Path


def _load_shim_from_file() -> None:
    """Load the top-level shim file mkpfs/gui.py as module 'mkpfs.gui'."""
    shim_path = Path(__file__).parent.parent / "gui.py"
    spec = importlib.util.spec_from_file_location("mkpfs.gui", str(shim_path))
    module = importlib.util.module_from_spec(spec)
    sys.modules["mkpfs.gui"] = module
    assert spec and spec.loader
    spec.loader.exec_module(module)


if __name__ == "__main__":
    multiprocessing.freeze_support()
    try:
        # Try to import the public module name. In normal operation the shim
        # at mkpfs/gui.py will be importable as mkpfs.gui and provide main().
        mod = importlib.import_module("mkpfs.gui")
    except Exception:
        # Fallback: explicitly load the shim file by path so this -m entry
        # works even when package import semantics would otherwise shadow it.
        _load_shim_from_file()
        mod = importlib.import_module("mkpfs.gui")

    # Delegate to the GUI launcher
    try:
        main = mod.main
    except AttributeError:
        raise SystemExit("mkpfs.gui does not expose a main() function") from None
    main()
