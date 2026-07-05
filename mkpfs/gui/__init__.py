"""mkpfs.gui package — compatibility layer that defers to the top-level shim.

We must preserve the original import semantics where importing ``mkpfs.gui``
returns the shim module located at ``mkpfs/gui.py`` (so that callers relying
on Path(__file__) for asset resolution keep working). To achieve that while
also providing a directory containing the refactored source files for
packaging/tooling, this package initializer loads the shim from the module
file and then replaces the package entry in sys.modules with that module
object.  The shim module is given a __path__ pointing at this directory so
``mkpfs.gui.<submodule>`` imports (e.g. ``mkpfs.gui.__main__``) continue to
work and submodules can be imported from the package directory.
"""
# ruff: noqa

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

# Path to the original top-level shim module (mkpfs/gui.py)
_shim_path = Path(__file__).parent.parent / "gui.py"
if _shim_path.exists():
    # Load the shim as a real module object and install it as "mkpfs.gui" in
    # sys.modules so imports of "mkpfs.gui" resolve to the shim file while
    # keeping the package directory present on disk.
    spec = importlib.util.spec_from_file_location("mkpfs.gui", str(_shim_path))
    _shim = importlib.util.module_from_spec(spec)

    # Execute the shim in an isolated module object. This runs the shim's
    # import-time side effects (CustomTkinter setup, translation tables, etc.)
    # and makes its public API available to callers of the package import.
    if spec and spec.loader:
        spec.loader.exec_module(_shim)  # type: ignore[attr-defined]

    # Copy public attributes from the shim onto this package module object.
    _this_mod = sys.modules[__name__]
    for _k, _v in vars(_shim).items():
        # Preserve existing package-level attributes like __path__ but copy
        # most names so ``from mkpfs import gui`` yields the same API surface.
        if _k in ("__name__", "__package__", "__path__"):
            continue
        setattr(_this_mod, _k, _v)

    # Expose the shim path as this module's __file__ so tools that rely on
    # Path(__file__) resolve to the original shim location.
    _this_mod.__file__ = str(_shim_path)

    # Keep a reference to the shim module under a private name to aid
    # introspection/debugging.
    sys.modules.setdefault("mkpfs.gui._shim", _shim)

# Provide a dynamically-computed __all__ based on the shim's public names so
# static analysis tools don't complain about undefined exports.
try:
    __all__ = [n for n in vars(_shim) if not n.startswith("_")]
except Exception:
    __all__ = []
