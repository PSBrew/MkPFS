"""mkpfs.gui.i18n — re-export of internationalisation helpers from the shim."""

from importlib import import_module as _import_module

_shim = _import_module("mkpfs.gui")

_TRANSLATIONS = _shim._TRANSLATIONS
_LANG_NAMES = _shim._LANG_NAMES
_current_locale = _shim._current_locale
tr = _shim.tr

__all__ = ["_LANG_NAMES", "_TRANSLATIONS", "_current_locale", "tr"]
