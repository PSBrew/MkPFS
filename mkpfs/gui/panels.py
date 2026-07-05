"""mkpfs.gui.panels — re-export of panel classes from the shim module."""

from importlib import import_module as _import_module

_shim = _import_module("mkpfs.gui")

BasePanel = _shim.BasePanel
PackFolderPanel = _shim.PackFolderPanel
PackFilePanel = _shim.PackFilePanel
VerifyPanel = _shim.VerifyPanel
InspectPanel = _shim.InspectPanel
TreePanel = _shim.TreePanel
UnpackPanel = _shim.UnpackPanel

__all__ = [
    "BasePanel",
    "InspectPanel",
    "PackFilePanel",
    "PackFolderPanel",
    "TreePanel",
    "UnpackPanel",
    "VerifyPanel",
]
