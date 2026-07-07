"""Base panel class for the mkpfs GUI operation panels."""

import builtins
import contextlib
import io
import queue
import threading
from tkinter import filedialog
from typing import Any

import customtkinter as ctk

from ..i18n import tr
from ..theme import (
    _BG_CARD,
    _BG_INPUT,
    _FONT_SMALL,
    _NEON_BLUE,
    _PANEL_ACCENT,
    _TEXT_MUTED,
)
from ..widgets import GlassCard, LogPane, NeonButton, SectionLabel

# ---------------------------------------------------------------------------
# Panel base class
# ---------------------------------------------------------------------------


class BasePanel(ctk.CTkFrame):
    """Abstract base for all operation panels.

    Subclasses implement _build_controls() and _run_command(). Each subclass
    also declares class-level _panel_key to look up its accent colour.
    """

    _title_key: str = ""
    _subtitle_key: str = ""
    _panel_key: str = ""

    def __init__(self, parent: Any) -> None:
        """Initialise BasePanel.

        Args:
            parent: Parent widget.
        """
        super().__init__(parent, fg_color="transparent")
        self._busy: bool = False
        self._log_queue: queue.Queue[tuple[str, str]] = queue.Queue()
        self._accent: str = _PANEL_ACCENT.get(self._panel_key, _NEON_BLUE)

        # Header
        header: ctk.CTkFrame = ctk.CTkFrame(self, fg_color="transparent")
        header.pack(fill="x", padx=24, pady=(22, 0))

        self._title_label: ctk.CTkLabel = ctk.CTkLabel(
            header,
            text=tr(self._title_key),
            font=("Segoe UI", 20, "bold"),
            text_color=self._accent,
        )
        self._title_label.pack(anchor="w")

        self._subtitle_label: ctk.CTkLabel = ctk.CTkLabel(
            header,
            text=tr(self._subtitle_key),
            font=_FONT_SMALL,
            text_color=_TEXT_MUTED,
        )
        self._subtitle_label.pack(anchor="w", pady=(2, 0))

        # Neon divider bar
        ctk.CTkFrame(self, height=1, fg_color=self._accent).pack(fill="x", padx=24, pady=(12, 0))

        # Controls card with accent border
        self._card: GlassCard = GlassCard(self, accent=self._accent)
        self._card.pack(fill="x", padx=24, pady=14)
        self._build_controls(self._card)

        # Progress bar (neon colour matching panel)
        self._progress: ctk.CTkProgressBar = ctk.CTkProgressBar(
            self,
            mode="indeterminate",
            fg_color=_BG_INPUT,
            progress_color=self._accent,
            corner_radius=4,
            height=4,
        )
        self._progress.pack(fill="x", padx=24)
        self._progress.stop()
        self._progress.set(0)

        # Run button in panel's accent colour
        self._run_btn: NeonButton = NeonButton(
            self,
            text=tr("run"),
            command=self._on_run,
            color=self._accent,
        )
        self._run_btn.pack(padx=24, pady=(10, 0), anchor="e")

        # Log header row: label + export button side by side
        log_header: ctk.CTkFrame = ctk.CTkFrame(self, fg_color="transparent")
        log_header.pack(fill="x", padx=24, pady=(14, 4))
        self._log_section_label: SectionLabel = SectionLabel(log_header, tr("output_log"), color=self._accent)
        self._log_section_label.pack(side="left", anchor="w")
        self._export_btn: ctk.CTkButton = ctk.CTkButton(
            log_header,
            text=tr("export_log"),
            width=90,
            height=24,
            font=_FONT_SMALL,
            fg_color="transparent",
            border_width=1,
            border_color=self._accent,
            text_color=self._accent,
            hover_color=_BG_CARD,
            corner_radius=6,
            command=self._on_export_log,
        )
        self._export_btn.pack(side="right", anchor="e")
        self._log: LogPane = LogPane(self)
        self._log.pack(fill="both", expand=True, padx=24, pady=(0, 16))

        self.after(100, self._poll_log_queue)

    def refresh_labels(self) -> None:
        """Re-apply translated strings after a locale change.

        Updates the header labels and the run button, then destroys and
        recreates the controls card so every inner widget (PathRow labels,
        SectionLabels, checkboxes, OptionRows) reflects the new locale.
        """
        self._title_label.configure(text=tr(self._title_key))
        self._subtitle_label.configure(text=tr(self._subtitle_key))
        self._run_btn.set_label(tr("run"))
        self._log_section_label.configure(text=tr("output_log"))
        self._export_btn.configure(text=tr("export_log"))

        # Destroy and rebuild the controls card with the new locale strings.
        # pack(before=) keeps the card between the divider and the progress bar.
        self._card.destroy()
        self._card = GlassCard(self, accent=self._accent)
        self._card.pack(fill="x", padx=24, pady=14, before=self._progress)
        self._build_controls(self._card)

    def _build_controls(self, card: GlassCard) -> None:
        """Populate operation-specific controls inside the given card.

        Args:
            card: Card frame to populate.
        """

    def _run_command(self) -> None:
        """Execute the operation; runs inside a background thread."""
        raise NotImplementedError

    def _on_run(self) -> None:
        """Clear log and launch the background worker thread."""
        if self._busy:
            return
        self._log.clear()
        self._busy = True
        self._run_btn.configure(state="disabled", text=tr("running"))
        self._progress.start()
        threading.Thread(target=self._worker, daemon=True).start()

    def _worker(self) -> None:
        """Wrap _run_command and signal completion back to the UI thread."""
        try:
            self._run_command()
        except Exception as exc:
            self._log_queue.put(("error", tr("err_unexpected").format(exc)))
        finally:
            self._log_queue.put(("__done__", ""))

    def _poll_log_queue(self) -> None:
        """Drain the log queue and update the UI; reschedules itself."""
        try:
            while True:
                tag, text = self._log_queue.get_nowait()
                if tag == "__done__":
                    self._busy = False
                    self._run_btn.configure(state="normal", text=tr("run"))
                    self._progress.stop()
                    self._progress.set(0)
                else:
                    self._log.append(text, tag)
        except queue.Empty:
            pass
        self.after(80, self._poll_log_queue)

    def _on_export_log(self) -> None:
        """Open a save dialog and write the current log content to a file."""
        import json as _json

        content: str = self._log.get_text().strip()
        if not content:
            return
        path: str | None = filedialog.asksaveasfilename(
            title="Export Log",
            defaultextension=".txt",
            filetypes=[("Text file", "*.txt"), ("JSON file", "*.json"), ("All files", "*.*")],
        )
        if not path:
            return
        try:
            if path.endswith(".json"):
                lines: list[str] = content.splitlines()
                with open(path, "w", encoding="utf-8") as fh:
                    _json.dump({"log": lines}, fh, indent=2, ensure_ascii=False)
            else:
                with open(path, "w", encoding="utf-8") as fh:
                    fh.write(content + "\n")
        except OSError as exc:
            self._emit(f"Export failed: {exc}", "error")

    def _emit(self, text: str, tag: str = "") -> None:
        """Queue a log line for display on the UI thread.

        Args:
            text: Log text.
            tag: Colour tag.
        """
        self._log_queue.put((tag, text))

    def _run_mkpfs(self, args: list[str]) -> None:
        """Run mkpfs in-process and stream each output line to the log pane.

        Executes ``cli_mkpfs_main`` directly in the current Python interpreter
        (the same one running the GUI) so no venv discovery or subprocess
        spawning is required.  ``sys.stdout`` / ``sys.stderr`` are temporarily
        redirected to a line-streaming helper that emits each line to the log
        queue as it arrives.  ``builtins.input`` is patched to auto-confirm the
        overwrite prompt with "y" so the GUI never blocks waiting for stdin.

        Args:
            args: CLI argument list passed verbatim to ``cli_mkpfs_main``.
        """
        # Late import -- if mkpfs or its dependencies are missing the
        # ImportError is caught below and shown as a readable error message.
        try:
            from mkpfs.cli import cli_mkpfs_main
        except ImportError as exc:
            self._emit(f"✗ Cannot import mkpfs: {exc}", "error")
            self._emit("   Ensure cryptography is installed: uv sync", "muted")
            return

        self._emit(f"$ mkpfs {' '.join(args)}", "muted")

        # Line-streaming writer that forwards each line to the log queue.
        emit: Any = self._emit

        class _Streamer(io.TextIOBase):
            def __init__(self, tag_fn: Any) -> None:
                self._tag_fn: Any = tag_fn
                self._buf: str = ""

            def write(self, s: str) -> int:
                self._buf += s
                while "\n" in self._buf:
                    line, self._buf = self._buf.split("\n", 1)
                    stripped: str = line.rstrip()
                    if not stripped:
                        continue
                    lower: str = stripped.lower()
                    tag: str = ""
                    if "error" in lower:
                        tag = "error"
                    elif "warning" in lower:
                        tag = "warning"
                    elif any(k in lower for k in ("done", "complete", "success", "\u2713")):
                        tag = "success"
                    self._tag_fn(stripped, tag)
                return len(s)

            def flush(self) -> None:
                pass

        streamer: _Streamer = _Streamer(emit)
        original_input: Any = builtins.input
        exit_code: int = 0
        try:
            # Auto-confirm any "Overwrite? [Y/n]" prompts from the CLI.
            builtins.input = lambda _prompt="": "y"
            with contextlib.redirect_stdout(streamer), contextlib.redirect_stderr(streamer):
                exit_code = int(cli_mkpfs_main(args))
        except SystemExit as exc:
            exit_code = int(exc.code) if exc.code is not None else 0
        except Exception as exc:
            self._emit(f"✗ Unexpected error: {exc}", "error")
            return
        finally:
            builtins.input = original_input

        self._emit("", "")
        if exit_code == 0:
            self._emit(tr("ok"), "success")
        else:
            self._emit(tr("err_process").format(exit_code), "error")
