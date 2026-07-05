"""Lightweight CLI discovery and global progress-event registry.

This module is intentionally small and import-safe: it avoids importing heavy
modules like mkpfs.cli or mkpfs.pfs at import time. It provides:

- get_cli_metadata(prefer_import=True)
- default_image_basename(pathlib.Path) -> str (wrapper around utils)
- normalize_output_path(...)
- ProgressEvent dataclass
- register_progress_handler(handler)
- _emit_progress_event_raw(...) internal helper called by Progress and pfs

The help-fallback uses subprocesses with per-call and global timeouts and
records failures instead of raising.
"""

from __future__ import annotations

import contextlib
import re
import shutil
import subprocess
import sys
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from . import utils

# Public optional import-time authoritative metadata. Consumers may set this
# to provide argparse-accurate structures when the package's CLI builds them.
# Kept as a module-level variable so "import mkpfs" stays cheap (None by default).
cli_metadata: dict | None = None

# Progress-event registry
_progress_handlers: list[Callable[[ProgressEvent], None]] = []
_progress_handlers_lock = threading.Lock()

# Default output naming


def default_output_name(command_path: str, source_path: str | Path | None = None) -> str:
    """Generate an argparse-friendly default output filename for a command.

    Derives a filename from the command path (e.g. ``"pack.folder"`` →
    ``"pack_folder"``, ``"pack.file"`` → ``"pack_file"``, ``"verify"`` →
    ``"verify"``).  When a source path is provided, the result is prefixed
    with a sanitised version of the source's stem or parent directory name
    (e.g. ``"my_game"`` + ``"pack.folder"`` → ``"my_game_pack_folder"``).

    Args:
        command_path: Dot-joined command path from argparse metadata, e.g.
            ``"pack.folder"``, ``"pack.file"``, ``"verify"``.
        source_path: Optional path to the primary input (source dir or file).
            When provided, its stem or directory name is used as a prefix.

    Returns:
        A filesystem-safe, underscore-joined basename (no extension).
    """
    # Convert command path to underscore form: "pack.folder" -> "pack_folder"
    underscored: str = command_path.replace(".", "_").replace("-", "_")

    if source_path is not None:
        src: Path = Path(source_path)
        source_basename: str = src.stem if src.suffix else src.name
        # Sanitise the source basename for use as a filename component
        safe_source: str = "".join(c if (c.isalnum() or c in "_-.") else "_" for c in source_basename).strip(".")
        if safe_source:
            return f"{safe_source}_{underscored}"

    return underscored


# Default timeouts for help subprocesses
_SUBPROCESS_TIMEOUT: float = 5.0
_GLOBAL_HELP_WALLCAP: float = 10.0


@dataclass(frozen=True)
class ProgressEvent:
    phase: str
    done: int
    total: int
    bytes_processed: int | None
    timestamp: float


def register_progress_handler(handler: Callable[[ProgressEvent], None]) -> Callable[[], None]:
    """Register a global progress handler.

    Returns an unregister callable that removes the handler when called.
    Registration is additive and non-breaking; errors in handlers are swallowed
    during event emission.
    """
    with _progress_handlers_lock:
        _progress_handlers.append(handler)

    def _unregister() -> None:
        with _progress_handlers_lock, contextlib.suppress(Exception):
            if handler in _progress_handlers:
                _progress_handlers.remove(handler)

    return _unregister


def _emit_progress_event(event: ProgressEvent) -> None:
    """Invoke all registered handlers with the provided ProgressEvent.

    Exceptions from handlers are swallowed to preserve non-breaking behavior.
    """
    with _progress_handlers_lock:
        handlers = list(_progress_handlers)
    for h in handlers:
        with contextlib.suppress(Exception):
            h(event)


def _emit_progress_event_raw(
    *,
    phase: str,
    done: int,
    total: int,
    bytes_processed: int | None,
    timestamp: float,
) -> None:
    """Internal helper used by Progress and other producers to emit events.

    Kept as a simple function so callers do not need to import the ProgressEvent
    type directly at the callsite when avoiding circular imports.
    """
    try:
        ev = ProgressEvent(
            phase=phase,
            done=done,
            total=total,
            bytes_processed=bytes_processed,
            timestamp=timestamp,
        )
        _emit_progress_event(ev)
    except Exception:
        # Must be non-raising
        pass


# CLI discovery helpers


def default_image_basename(source_root: Path) -> str:
    """Wrapper around utils.default_image_basename to keep public API stable."""
    return utils.default_image_basename(source_root)


def normalize_output_path(path_arg: str, desired_suffix: str, adjust: bool = True) -> tuple[Path, bool]:
    """Wrapper around utils.normalize_output_path."""
    return utils.normalize_output_path(path_arg, desired_suffix, adjust)


def _run_help_command(cmd: list[str], timeout: float) -> tuple[str | None, str | None]:
    """Run a help subprocess, return (stdout, error) where error is set on failure."""
    try:
        result = subprocess.run(cmd, check=True, capture_output=True, text=True, timeout=timeout)
        return result.stdout, None
    except subprocess.CalledProcessError as exc:
        return None, f"subprocess failed: {exc}"
    except subprocess.TimeoutExpired:
        return None, "timeout"
    except (OSError, FileNotFoundError) as exc:
        return None, f"exec error: {exc}"


def _parse_top_level_commands(help_text: str) -> dict[str, str]:
    """Parse top-level subcommands and short help from a help text.

    Returns mapping command -> short_help. Conservative heuristic: lines that
    start with a token (no leading hyphen) and have at least two spaces then
    text are considered candidates.
    """
    commands: dict[str, str] = {}
    for line in help_text.splitlines():
        # Skip option lines
        if line.lstrip().startswith("-"):
            continue
        m = re.match(r"^\s{0,4}([a-z0-9_-]+)\s{2,}(.*)$", line, flags=re.IGNORECASE)
        if m:
            name = m.group(1).strip()
            short = m.group(2).strip()
            # ignore generic headers and usage markers
            if name.lower() in {"usage", "options", "positional"}:
                continue
            commands.setdefault(name, short)
    return commands


def get_cli_metadata(prefer_import: bool = True) -> dict:
    """Return CLI metadata for programmatic discovery.

    If prefer_import is True and a package import-time cli_metadata is
    present (mkpfs.cli_metadata), return it with ``source: 'import'``.
    Otherwise perform a safe, timeboxed help fallback that runs the package
    CLI with ``--help`` and per-subcommand ``--help``. Failures/timeouts are
    recorded and do not raise.
    """
    # First try import-time metadata when requested and available.
    if prefer_import:
        try:
            from . import cli_metadata as meta
        except Exception:
            meta = None
        if meta:
            return {"source": "import", "commands": meta}

    # Fallback: run help parsing
    start = time.time()
    metadata: dict[str, Any] = {"source": "help", "commands": {}, "errors": []}

    # Choose executable: prefer installed "mkpfs" if on PATH, else use python -m mkpfs
    exe = shutil.which("mkpfs")
    base_cmd = [exe] if exe else [sys.executable, "-m", "mkpfs"]

    stdout, err = _run_help_command([*base_cmd, "--help"], timeout=_SUBPROCESS_TIMEOUT)
    if stdout is None:
        metadata["errors"].append({"cmd": [*base_cmd, "--help"], "err": err})
        return metadata

    # Parse top-level commands
    top_commands = _parse_top_level_commands(stdout)
    for name, short in top_commands.items():
        if time.time() - start > _GLOBAL_HELP_WALLCAP:
            metadata["errors"].append({"stage": "wallcap_exceeded"})
            break
        out, perr = _run_help_command([*base_cmd, name, "--help"], timeout=_SUBPROCESS_TIMEOUT)
        metadata["commands"][name] = {
            "short_help": short,
            "help": out,
            "help_error": perr,
            # Help-parsed options could be added here by more advanced parsing.
            "options": None,
        }
    return metadata
