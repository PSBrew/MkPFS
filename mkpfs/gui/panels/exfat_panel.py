"""EXFAT image creation panel for the mkpfs GUI."""

from pathlib import Path
from typing import Any

import customtkinter as ctk

from ...utils import ui_sanitize_basename
from ..i18n import tr
from ..theme import _BORDER_BRIGHT
from ..widgets import GlassCard, NeonCheckbox, PathRow, SectionLabel
from .base import BasePanel


class ExfatPanel(BasePanel):
    """Panel for creating an EXFAT image from a source folder."""

    _title_key = "exf_title"
    _subtitle_key = "exf_subtitle"
    _panel_key = "pack_exfat"

    def __init__(self, parent: Any) -> None:
        """Initialise ExfatPanel.

        Args:
            parent: Parent widget.
        """
        self._src: ctk.StringVar = ctk.StringVar()
        self._out: ctk.StringVar = ctk.StringVar()
        self._overwrite: ctk.BooleanVar = ctk.BooleanVar(value=False)
        super().__init__(parent)
        # Auto-populate output path from source folder selection.
        # Only fills when output is currently empty so manually-typed
        # paths are never overwritten.
        self._src.trace_add("write", self._on_src_changed)

    def _on_src_changed(self, *_args: Any) -> None:
        """Auto-populate output path when the user selects a source folder.

        Computes the output as ``<source_dir>/<source_name>.exfat`` in the
        same parent directory. Only fires when the output field is empty so a
        manually-typed path is preserved.
        """
        if self._out.get().strip():
            return
        src_path: str = self._src.get().strip()
        if not src_path:
            return
        p: Path = Path(src_path)
        # Only auto-populate when source resolves to an existing directory,
        # avoiding clobber on partial/in-progress paths during typing.
        if not p.is_dir():
            return
        self._out.set(str(p.parent / (ui_sanitize_basename(p.name) + ".exfat")))

    def _build_controls(self, card: GlassCard) -> None:
        """Build the panel controls."""
        card.columnconfigure(0, weight=1)
        card.columnconfigure(1, weight=1)

        SectionLabel(card, tr("paths"), color=self._accent).grid(
            row=0, column=0, columnspan=2, sticky="w", padx=16, pady=(14, 6)
        )

        PathRow(
            card,
            tr("exf_src_label"),
            self._src,
            mode="folder",
            placeholder=tr("exf_src_ph"),
            browse_label=tr("browse"),
        ).grid(row=1, column=0, columnspan=2, sticky="ew", padx=16, pady=(0, 10))

        PathRow(
            card,
            tr("exf_out_label"),
            self._out,
            mode="save",
            filetypes=[("EXFAT image", "*.exfat")],
            placeholder=tr("exf_out_ph"),
            browse_label=tr("browse"),
        ).grid(row=2, column=0, columnspan=2, sticky="ew", padx=16, pady=(0, 14))

        ctk.CTkFrame(card, height=1, fg_color=_BORDER_BRIGHT).grid(row=3, column=0, columnspan=2, sticky="ew", padx=16)

        SectionLabel(card, tr("options"), color=self._accent).grid(
            row=4, column=0, columnspan=2, sticky="w", padx=16, pady=(12, 6)
        )

        opt: ctk.CTkFrame = ctk.CTkFrame(card, fg_color="transparent")
        opt.grid(row=5, column=0, columnspan=2, sticky="ew", padx=16, pady=(0, 14))
        opt.columnconfigure(0, weight=1)
        NeonCheckbox(opt, text=tr("exf_overwrite"), variable=self._overwrite, accent=self._accent).pack(
            anchor="w", pady=3
        )

    def _run_command(self) -> None:
        """Build and run the mkpfs pack exfat command."""
        src: str = self._src.get().strip()
        if not src:
            self._emit(tr("exf_err_src"), "error")
            return

        args: list[str] = ["pack", "exfat", src]

        # Output path (auto-populated or manually entered)
        out_path: str = self._out.get().strip()
        if out_path:
            args.append(out_path)

        # Overwrite flag
        if self._overwrite.get():
            args.append("--overwrite")

        self._run_mkpfs(args)
