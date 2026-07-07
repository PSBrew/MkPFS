"""Pack File operation panel for mkpfs GUI."""

from typing import Any

import customtkinter as ctk

from ..i18n import tr
from ..theme import _BORDER_BRIGHT
from ..widgets import GlassCard, NeonCheckbox, OptionRow, PathRow, SectionLabel
from .base import BasePanel


class PackFilePanel(BasePanel):
    """Panel for packing a single file into a PFS image."""

    _title_key = "pkf_title"
    _subtitle_key = "pkf_subtitle"
    _panel_key = "pack_file"

    def __init__(self, parent: Any) -> None:
        """Initialise PackFilePanel.

        Args:
            parent: Parent widget.
        """
        self._src: ctk.StringVar = ctk.StringVar()
        self._out: ctk.StringVar = ctk.StringVar()
        self._version: ctk.StringVar = ctk.StringVar(value="PS4")
        self._compress: ctk.BooleanVar = ctk.BooleanVar(value=True)
        self._temp_folder: ctk.StringVar = ctk.StringVar()
        super().__init__(parent)

    def _build_controls(self, card: GlassCard) -> None:
        card.columnconfigure(0, weight=1)
        card.columnconfigure(1, weight=1)

        SectionLabel(card, tr("paths"), color=self._accent).grid(
            row=0, column=0, columnspan=2, sticky="w", padx=16, pady=(14, 6)
        )

        PathRow(
            card,
            tr("pkf_src_label"),
            self._src,
            mode="open",
            placeholder=tr("pkf_src_ph"),
            browse_label=tr("browse"),
        ).grid(row=1, column=0, columnspan=2, sticky="ew", padx=16, pady=(0, 10))

        PathRow(
            card,
            tr("pkf_out_label"),
            self._out,
            mode="save",
            filetypes=[("PFS image", "*.ffpfsc"), ("All files", "*.*")],
            placeholder=tr("pkf_out_ph"),
            browse_label=tr("browse"),
        ).grid(row=2, column=0, columnspan=2, sticky="ew", padx=16, pady=(0, 14))

        ctk.CTkFrame(card, height=1, fg_color=_BORDER_BRIGHT).grid(row=3, column=0, columnspan=2, sticky="ew", padx=16)

        SectionLabel(card, tr("options"), color=self._accent).grid(
            row=4, column=0, columnspan=2, sticky="w", padx=16, pady=(12, 6)
        )

        opt: ctk.CTkFrame = ctk.CTkFrame(card, fg_color="transparent")
        opt.grid(row=5, column=0, columnspan=2, sticky="ew", padx=16, pady=(0, 14))
        opt.columnconfigure((0, 1), weight=1)

        OptionRow(opt, tr("pkf_version"), self._version, ["PS4", "PS5"], accent=self._accent).grid(
            row=0, column=0, sticky="ew", padx=(0, 12)
        )

        chk: ctk.CTkFrame = ctk.CTkFrame(opt, fg_color="transparent")
        chk.grid(row=0, column=1, sticky="nw", padx=(8, 0))

        NeonCheckbox(chk, text=tr("pkf_compress"), variable=self._compress, accent=self._accent).pack(
            anchor="w", pady=3
        )

        PathRow(
            opt,
            tr("pkf_temp"),
            self._temp_folder,
            mode="folder",
            placeholder=tr("pkf_temp_ph"),
            browse_label=tr("browse"),
        ).grid(row=1, column=0, columnspan=2, sticky="ew", pady=(10, 0))

    def _run_command(self) -> None:
        src: str = self._src.get().strip()
        out: str = self._out.get().strip()
        if not src or not out:
            self._emit(tr("pkf_err"), "error")
            return
        args: list[str] = ["pack", "file", src, out, "--version", self._version.get()]
        if not self._compress.get():
            args.append("--no-compress")
        if temp := self._temp_folder.get().strip():
            args += ["--temp-folder", temp]
        self._run_mkpfs(args)
