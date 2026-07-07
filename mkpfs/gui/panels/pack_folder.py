"""Pack Folder operation panel for mkpfs GUI."""

from typing import Any

import customtkinter as ctk

from ..i18n import tr
from ..theme import _BORDER_BRIGHT
from ..widgets import GlassCard, NeonCheckbox, OptionRow, PathRow, SectionLabel
from .base import BasePanel


class PackFolderPanel(BasePanel):
    """Panel for packing a folder into a PFS image."""

    _title_key = "pf_title"
    _subtitle_key = "pf_subtitle"
    _panel_key = "pack_folder"

    def __init__(self, parent: Any) -> None:
        """Initialise PackFolderPanel.

        Args:
            parent: Parent widget.
        """
        self._src: ctk.StringVar = ctk.StringVar()
        self._out: ctk.StringVar = ctk.StringVar()
        self._version: ctk.StringVar = ctk.StringVar(value="PS4")
        self._compress: ctk.BooleanVar = ctk.BooleanVar(value=True)
        self._signed: ctk.BooleanVar = ctk.BooleanVar(value=False)
        self._verify_after: ctk.BooleanVar = ctk.BooleanVar(value=False)
        self._dry_run: ctk.BooleanVar = ctk.BooleanVar(value=False)
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
            tr("pf_src_label"),
            self._src,
            mode="folder",
            placeholder=tr("pf_src_ph"),
            browse_label=tr("browse"),
        ).grid(row=1, column=0, columnspan=2, sticky="ew", padx=16, pady=(0, 10))

        PathRow(
            card,
            tr("pf_out_label"),
            self._out,
            mode="save",
            filetypes=[("PFS image", "*.ffpfs *.ffpfsc"), ("All files", "*.*")],
            placeholder=tr("pf_out_ph"),
            browse_label=tr("browse"),
        ).grid(row=2, column=0, columnspan=2, sticky="ew", padx=16, pady=(0, 14))

        ctk.CTkFrame(card, height=1, fg_color=_BORDER_BRIGHT).grid(row=3, column=0, columnspan=2, sticky="ew", padx=16)

        SectionLabel(card, tr("options"), color=self._accent).grid(
            row=4, column=0, columnspan=2, sticky="w", padx=16, pady=(12, 6)
        )

        opt: ctk.CTkFrame = ctk.CTkFrame(card, fg_color="transparent")
        opt.grid(row=5, column=0, columnspan=2, sticky="ew", padx=16, pady=(0, 14))
        opt.columnconfigure((0, 1), weight=1)

        OptionRow(opt, tr("pf_version"), self._version, ["PS4", "PS5"], accent=self._accent).grid(
            row=0, column=0, sticky="ew", padx=(0, 12)
        )

        chk: ctk.CTkFrame = ctk.CTkFrame(opt, fg_color="transparent")
        chk.grid(row=0, column=1, sticky="nw", padx=(8, 0))

        for text, var in [
            (tr("pf_compress"), self._compress),
            (tr("pf_signed"), self._signed),
            (tr("pf_verify"), self._verify_after),
            (tr("pf_dry"), self._dry_run),
        ]:
            NeonCheckbox(chk, text=text, variable=var, accent=self._accent).pack(anchor="w", pady=3)

        # Temp folder (optional, spans both columns below checkboxes)
        PathRow(
            opt,
            tr("pf_temp"),
            self._temp_folder,
            mode="folder",
            placeholder=tr("pf_temp_ph"),
            browse_label=tr("browse"),
        ).grid(row=1, column=0, columnspan=2, sticky="ew", pady=(10, 0))

    def _run_command(self) -> None:
        src: str = self._src.get().strip()
        out: str = self._out.get().strip()
        if not src:
            self._emit(tr("pf_err_src"), "error")
            return
        if not out:
            self._emit(tr("pf_err_out"), "error")
            return
        args: list[str] = ["pack", "folder", src, out, "--version", self._version.get()]
        if not self._compress.get():
            args.append("--no-compress")
        if self._signed.get():
            args.append("--signed")
        if self._verify_after.get():
            args.append("--verify")
        if self._dry_run.get():
            args.append("--dry-run")
        if temp := self._temp_folder.get().strip():
            args += ["--temp-folder", temp]
        self._run_mkpfs(args)
