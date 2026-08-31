"""Base panel class for the mkpfs GUI operation panels."""

import queue
import re
import subprocess
import sys
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
# Matches pbar.py progress lines: [##########----------] N% phase
_PROGRESS_RE: re.Pattern[str] = re.compile(r"^\[[#-]+\]\s*(\d+)%\s*(\S+)")


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
        self._failed: bool = False
        self._reset_after_id: str | None = None
        self._log_queue: queue.Queue[tuple[str, str]] = queue.Queue()
        self._accent: str = _PANEL_ACCENT.get(self._panel_key, _NEON_BLUE)
        self._last_phase: str = ""
        self._last_progress: tuple[int, int] = (0, 0)
        self._proc: subprocess.Popen | None = None

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
        self._progress.pack(fill="x", padx=24, pady=(14, 2))

        # Phase label shown between progress bar and log area
        self._phase_label: ctk.CTkLabel = ctk.CTkLabel(
            self,
            text="",
            font=_FONT_SMALL,
            text_color=_NEON_BLUE,
        )
        self._phase_label.pack(anchor="w", padx=26, pady=(0, 4))

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
        # Cancel any pending progress-bar reset from a previous completion
        if self._reset_after_id is not None:
            self.after_cancel(self._reset_after_id)
            self._reset_after_id = None
        self._failed = False
        self._last_phase = ""
        self._last_progress = (0, 0)
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
        # Drain log messages
        try:
            while True:
                tag, text = self._log_queue.get_nowait()
                if tag == "__progress__":
                    # Progress update from subprocess: format "pct\tphase"
                    parts: list[str] = text.split("\t", 1)
                    pct: int = int(parts[0]) if parts and parts[0] else 0
                    phase: str = parts[1] if len(parts) > 1 else ""
                    if self._progress.cget("mode") != "determinate":
                        self._progress.stop()
                        self._progress.configure(mode="determinate")
                        self._progress.set(0)
                    self._progress.set(max(0.0, min(1.0, pct / 100.0)))
                    if phase:
                        self._phase_label.configure(text=phase)
                    self._last_phase = phase
                    self._last_progress = (pct, 100)
                elif tag == "error":
                    self._failed = True
                    self._log.append(text, tag)
                elif tag == "__done__":
                    self._busy = False
                    self._run_btn.configure(state="normal", text=tr("run"))
                    if self._failed:
                        # On failure, reset immediately — no celebratory 100%
                        self._progress.stop()
                        self._progress.configure(mode="indeterminate")
                        self._progress.set(0)
                        self._phase_label.configure(text="")
                    else:
                        # Emit a final log line for the last completed phase
                        if self._last_phase:
                            prev_done, prev_total = self._last_progress
                            pct: int = int(prev_done / prev_total * 100) if prev_total > 0 else 100
                            self._log.append(f"✓ {self._last_phase}: {pct}%", "success")
                        # Freeze progress bar at 100% and show completion label briefly
                        self._progress.stop()
                        self._progress.configure(mode="determinate")
                        self._progress.set(1)
                        current_label = self._phase_label.cget("text")
                        if current_label:
                            self._phase_label.configure(text=f"✓ {current_label}")
                        else:
                            self._phase_label.configure(text="✓ " + tr("ok"))
                        # Reset progress bar after a delay so the final 100% state is visible

                        def _reset_progress() -> None:
                            try:
                                self._progress.stop()
                                self._progress.configure(mode="indeterminate")
                                self._progress.set(0)
                                self._phase_label.configure(text="")
                            except Exception:
                                pass  # Widget may be destroyed during shutdown

                        self._reset_after_id = self.after(3000, _reset_progress)
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
        r"""Run mkpfs as a child process and stream each output line to the log pane.

        The CLI runs in a separate process so the GUI's drawing thread is never
        blocked by long-running compression/multiprocessing work.  The spawned
        process handle is stored on ``self._proc`` so a future stop button can
        call ``terminate()``.

        Progress lines from ``pbar.py`` (``\r``-delimited ``[bar] N% phase``
        updates) are parsed and forwarded to the UI thread as ``__progress__``
        events so the determinate progress bar tracks real progress.  Other
        output lines are emitted to the log pane as usual.

        On Windows a console-window flash is suppressed via
        ``CREATE_NO_WINDOW``.  ``stdin`` is fed ``"y\n"`` so any
        ``Overwrite? [Y/n]`` prompt is auto-confirmed.

        Args:
            args: CLI argument list passed verbatim to the CLI entrypoint.
        """
        self._emit(f"$ mkpfs {' '.join(args)}", "muted")

        # Build the subprocess invocation.  In a frozen PyInstaller binary
        # ``sys.executable`` is the binary itself and ``--gui-subprocess`` lands
        # in ``sys.argv``; in dev mode ``sys.executable`` is the interpreter and
        # we route through ``-m mkpfs.gui`` to hit ``__main__.py``.
        if getattr(sys, "frozen", False):
            cmd: list[str] = [sys.executable, "--gui-subprocess", *args]
        else:
            cmd = [sys.executable, "-m", "mkpfs.gui", "--gui-subprocess", *args]

        # ``text=True`` enables universal newlines (``\r`` → ``\n``) so each
        # progress-bar tick becomes its own line.  ``encoding="utf-8"`` ensures
        # non-ASCII output decodes cleanly on all platforms.
        popen_kwargs: dict[str, Any] = {
            "stdout": subprocess.PIPE,
            "stderr": subprocess.STDOUT,
            "stdin": subprocess.PIPE,
            "text": True,
            "encoding": "utf-8",
            "errors": "replace",
        }
        if sys.platform == "win32":
            popen_kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW

        try:
            proc: subprocess.Popen = subprocess.Popen(cmd, **popen_kwargs)
        except OSError as exc:
            self._emit(f"\u2717 Failed to start mkpfs: {exc}", "error")
            return
        self._proc = proc

        # Auto-confirm any "Overwrite? [Y/n]" prompt from the CLI by piping
        # "y\n" to the child's stdin, then close it so the child sees EOF.
        if proc.stdin is not None:
            try:
                proc.stdin.write("y\n")
                proc.stdin.close()
            except (BrokenPipeError, OSError):
                pass

        # Stream child stdout/stderr line by line.  ``text=True`` universal
        # newlines split ``\r``-delimited progress ticks into individual lines;
        # we parse each as a progress update or emit it to the log pane.
        assert proc.stdout is not None
        try:
            line: str
            for line in proc.stdout:
                stripped: str = line.rstrip()
                if not stripped:
                    continue
                # Check if this is a pbar progress line: [####--] N% phase
                m: re.Match[str] | None = _PROGRESS_RE.match(stripped)
                if m:
                    pct: int = int(m.group(1))
                    phase: str = m.group(2)
                    self._log_queue.put(("__progress__", f"{pct}\t{phase}"))
                    continue
                # Not a progress line — classify and emit to the log pane.
                lower: str = stripped.lower()
                tag: str = ""
                if lower.startswith(("\u2713", "done:", "complete:", "success:")):
                    tag = "success"
                elif lower.startswith("error ") or "\u274c" in stripped:
                    tag = "error"
                elif lower.startswith("warn ") or "\u26a0" in stripped:
                    tag = "warning"
                self._emit(stripped, tag)
        finally:
            proc.wait()
            self._proc = None

        exit_code: int = int(proc.returncode or 0)
        self._emit("", "")
        if exit_code == 0:
            self._emit(tr("ok"), "success")
        else:
            self._emit(tr("err_process").format(exit_code), "error")
