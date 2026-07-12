"""Batch Convert operation panel for the mkpfs GUI."""

from typing import Any

import customtkinter as ctk

from ..i18n import tr
from ..theme import _BORDER_BRIGHT
from ..widgets import NeonCheckbox, OptionRow, PathRow, SectionLabel
from .base import BasePanel


class BatchPanel(BasePanel):
    """Panel for converting multiple games at once into PFS images."""

    _title_key = "bt_title"
    _subtitle_key = "bt_subtitle"
    _panel_key = "batch"

    def __init__(self, parent: Any) -> None:
        """Initialise BatchPanel.

        Args:
            parent: Parent widget.
        """
        self._src: ctk.StringVar = ctk.StringVar()
        self._out: ctk.StringVar = ctk.StringVar()
        self._version: ctk.StringVar = ctk.StringVar(value="PS5")
        self._compress: ctk.BooleanVar = ctk.BooleanVar(value=True)
        self._overwrite: ctk.BooleanVar = ctk.BooleanVar(value=False)
        self._dry_run: ctk.BooleanVar = ctk.BooleanVar(value=False)
        super().__init__(parent)

    def _build_controls(self, card: "GlassCard") -> None:  # noqa: F821
        card.columnconfigure(0, weight=1)
        card.columnconfigure(1, weight=1)

        SectionLabel(card, tr("paths"), color=self._accent).grid(
            row=0, column=0, columnspan=2, sticky="w", padx=16, pady=(14, 6)
        )

        PathRow(
            card,
            label=tr("bt_src_label"),
            variable=self._src,
            placeholder=tr("bt_src_ph"),
            mode="folder",
        ).grid(row=1, column=0, columnspan=2, sticky="ew", padx=16, pady=(0, 10))

        PathRow(
            card,
            label=tr("bt_out_label"),
            variable=self._out,
            placeholder=tr("bt_out_ph"),
            mode="folder",
        ).grid(row=2, column=0, columnspan=2, sticky="ew", padx=16, pady=(0, 14))

        ctk.CTkFrame(card, height=1, fg_color=_BORDER_BRIGHT).grid(row=3, column=0, columnspan=2, sticky="ew", padx=16)

        SectionLabel(card, tr("options"), color=self._accent).grid(
            row=4, column=0, columnspan=2, sticky="w", padx=16, pady=(12, 6)
        )

        opt: ctk.CTkFrame = ctk.CTkFrame(card, fg_color="transparent")
        opt.grid(row=5, column=0, columnspan=2, sticky="ew", padx=16, pady=(0, 14))
        opt.columnconfigure((0, 1), weight=1)

        OptionRow(opt, tr("bt_version"), self._version, ["PS4", "PS5"], accent=self._accent).grid(
            row=0, column=0, sticky="ew", padx=(0, 12)
        )

        chk: ctk.CTkFrame = ctk.CTkFrame(opt, fg_color="transparent")
        chk.grid(row=0, column=1, sticky="nw", padx=(8, 0))

        for text, var in [
            (tr("bt_compress"), self._compress),
            (tr("bt_overwrite"), self._overwrite),
            (tr("bt_dry"), self._dry_run),
        ]:
            NeonCheckbox(chk, text=text, variable=var, accent=self._accent).pack(anchor="w", pady=3)

    def _run_command(self) -> None:
        src: str = self._src.get().strip()
        out: str = self._out.get().strip()

        if not src:
            self._emit(tr("bt_err_src"), "error")
            return
        if not out:
            self._emit(tr("bt_err_out"), "error")
            return

        args: list[str] = [
            "batch",
            src,
            out,
            "--version",
            self._version.get(),
        ]

        if not self._compress.get():
            args.append("--no-compress")
        if self._overwrite.get():
            args.append("--overwrite")
        if self._dry_run.get():
            args.append("--dry-run")

        self._run_mkpfs(args)
