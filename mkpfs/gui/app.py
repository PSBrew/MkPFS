"""mkpfs.gui.app — thin façade pointing at the original shim module.

This module exists to host a refactored implementation in the future. For
now it re-exports the public application entry points from the shim file so
both import styles work (import mkpfs.gui and import mkpfs.gui.app).
"""

from importlib import import_module as _import_module

_shim = _import_module("mkpfs.gui")

MkPFSApp = _shim.MkPFSApp
main = _shim.main

__all__ = ["MkPFSApp", "main"]
