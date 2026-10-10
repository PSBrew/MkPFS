"""Logging helpers for MkPFS CLI and UI.

This module provides a compact `log` function and convenience wrappers
(`info`, `warning`, `error`) used by the CLI. It intentionally avoids
configuring the global `logging` subsystem so callers can opt-in if needed.
"""

from __future__ import annotations

import logging
import os
import sys

# Icon maps kept at module scope so fallback logic can force ASCII without
# consulting `supports_utf8()` again during error handling.
UTF8_ICON_MAP: dict[str, str] = {
    "info": "ℹ️",
    "ok": "✅",
    "warning": "⚠️",
    "error": "❌",
    "file": "📄",
    "success": "🎉",
}
ASCII_ICON_MAP: dict[str, str] = {
    "info": "INFO",
    "ok": "OK",
    "warning": "WARN",
    "error": "ERROR",
    "file": "FILE",
    "success": "SUCCESS",
}


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
    name_key: str = name or ""
    return UTF8_ICON_MAP.get(name_key, "") if supports_utf8() else ASCII_ICON_MAP.get(name_key, "")


def log(message: str, level: int = logging.INFO, icon_name: str | None = None) -> None:
    """Print a message to stdout/stderr using the provided logging level.

    Args:
        message: The textual message to emit.
        level: One of logging.INFO, logging.WARNING, logging.ERROR, logging.DEBUG.
        icon_name: Optional semantic icon name to prefix the message.
    """
    prefix: str = (icon(icon_name) + " ") if icon_name else ""
    text: str = prefix + str(message)
    # Colorize output when terminal appears to support colors and the user has not
    # disabled colors via MKPFS_NO_COLOR. Keep logic simple and fall back to plain
    # output when unsure.
    no_color_env: str | None = os.environ.get("MKPFS_NO_COLOR")
    use_color: bool = False
    try:
        use_color = bool(
            (getattr(sys.stderr, "isatty", lambda: False)() or getattr(sys.stdout, "isatty", lambda: False)())
            and not no_color_env
        )
    except Exception:
        use_color = False

    color_code: str = ""
    reset_code: str = ""
    if use_color:
        reset_code = "\x1b[0m"
        if level >= logging.ERROR:
            color_code = "\x1b[31m"  # red
        elif level >= logging.WARNING:
            color_code = "\x1b[38;5;208m"  # orange (256-color)
        else:
            color_code = ""

    colored_text: str = f"{color_code}{text}{reset_code}" if color_code else text
    stream = sys.stderr if level >= logging.ERROR else sys.stdout
    try:
        print(colored_text, file=stream)
    except UnicodeEncodeError:
        # Fall back to ASCII-only icon + ASCII-safe message when the stream codec
        # (e.g. cp1252 on Windows pipes) cannot encode the original text.
        ascii_prefix: str = (ASCII_ICON_MAP.get(icon_name or "", "") + " ") if icon_name else ""
        ascii_message: str = str(message).encode("ascii", "replace").decode()
        print(ascii_prefix + ascii_message, file=stream)


def info(message: str, icon_name: str | None = None) -> None:
    """Convenience wrapper for informational messages."""
    log(message, level=logging.INFO, icon_name=icon_name)


def warning(message: str, icon_name: str | None = None) -> None:
    """Convenience wrapper for warnings."""
    log(message, level=logging.WARNING, icon_name=icon_name)


def error(message: str, icon_name: str | None = None) -> None:
    """Convenience wrapper for errors."""
    log(message, level=logging.ERROR, icon_name=icon_name)
