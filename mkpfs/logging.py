"""Logging helpers for MkPFS CLI and UI.

This module provides a compact `log` function and convenience wrappers
(`info`, `warning`, `error`) used by the CLI. It intentionally avoids
configuring the global `logging` subsystem so callers can opt-in if needed.
"""

from __future__ import annotations

import logging
import os
import sys


def supports_utf8() -> bool:
    """Return True when terminal appears to support UTF-8 icons.

    Honor the `MKPFS_NO_UTF8` environment variable to force ASCII-only
    output (useful in CI and tests).
    """
    env_val: str | None = os.environ.get("MKPFS_NO_UTF8")
    if env_val:
        return False
    enc: str = getattr(sys.stdout, "encoding", "") or ""
    if not enc:
        return False
    return "UTF-8" in enc.upper()


def icon(name: str | None) -> str:
    """Map a semantic icon name to a UTF-8 glyph or an ASCII fallback."""
    utf8: dict[str, str] = {"info": "ℹ️", "ok": "✅", "warning": "⚠️", "error": "❌", "file": "📄"}
    ascii_map: dict[str, str] = {"info": "INFO", "ok": "OK", "warning": "WARN", "error": "ERROR", "file": "FILE"}
    name_key: str = name or ""
    return utf8.get(name_key, "") if supports_utf8() else ascii_map.get(name_key, "")


def log(message: str, level: int = logging.INFO, icon_name: str | None = None) -> None:
    """Print a message to stdout/stderr using the provided logging level.

    Args:
        message: The textual message to emit.
        level: One of logging.INFO, logging.WARNING, logging.ERROR, logging.DEBUG.
        icon_name: Optional semantic icon name to prefix the message.
    """
    prefix: str = (icon(icon_name) + " ") if icon_name else ""
    text: str = prefix + str(message)
    if level >= logging.ERROR:
        print(text, file=sys.stderr)
    else:
        print(text, file=sys.stdout)


def info(message: str, icon_name: str | None = None) -> None:
    """Convenience wrapper for informational messages."""
    log(message, level=logging.INFO, icon_name=icon_name)


def warning(message: str, icon_name: str | None = None) -> None:
    """Convenience wrapper for warnings."""
    log(message, level=logging.WARNING, icon_name=icon_name)


def error(message: str, icon_name: str | None = None) -> None:
    """Convenience wrapper for errors."""
    log(message, level=logging.ERROR, icon_name=icon_name)
