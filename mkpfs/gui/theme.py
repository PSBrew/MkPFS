"""mkpfs.gui.theme — re-export of theme constants from the shim."""

from importlib import import_module as _import_module

_shim = _import_module("mkpfs.gui")

# Theme constants (exported names expected by legacy imports)
_BG_DEEP = _shim._BG_DEEP
_BG_PANEL = _shim._BG_PANEL
_BG_CARD = _shim._BG_CARD
_BG_INPUT = _shim._BG_INPUT
_BORDER_BRIGHT = _shim._BORDER_BRIGHT

_TEXT_PRIMARY = _shim._TEXT_PRIMARY
_TEXT_SECONDARY = _shim._TEXT_SECONDARY
_TEXT_MUTED = _shim._TEXT_MUTED

_NEON_BLUE = _shim._NEON_BLUE
_NEON_CYAN = _shim._NEON_CYAN
_NEON_GREEN = _shim._NEON_GREEN
_NEON_PURPLE = _shim._NEON_PURPLE
_NEON_AMBER = _shim._NEON_AMBER
_NEON_PINK = _shim._NEON_PINK

_SUCCESS = _shim._SUCCESS
_ERROR = _shim._ERROR
_WARNING = _shim._WARNING

_SIDEBAR_W = _shim._SIDEBAR_W
_CORNER = _shim._CORNER
_FONT_MONO = _shim._FONT_MONO
_FONT_UI = _shim._FONT_UI
_FONT_LABEL = _shim._FONT_LABEL
_FONT_SMALL = _shim._FONT_SMALL

_PANEL_ACCENT = _shim._PANEL_ACCENT

__all__ = [
    "_BG_CARD",
    "_BG_DEEP",
    "_BG_INPUT",
    "_BG_PANEL",
    "_BORDER_BRIGHT",
    "_CORNER",
    "_ERROR",
    "_FONT_LABEL",
    "_FONT_MONO",
    "_FONT_SMALL",
    "_FONT_UI",
    "_NEON_AMBER",
    "_NEON_BLUE",
    "_NEON_CYAN",
    "_NEON_GREEN",
    "_NEON_PINK",
    "_NEON_PURPLE",
    "_PANEL_ACCENT",
    "_SIDEBAR_W",
    "_SUCCESS",
    "_TEXT_MUTED",
    "_TEXT_PRIMARY",
    "_TEXT_SECONDARY",
    "_WARNING",
]
