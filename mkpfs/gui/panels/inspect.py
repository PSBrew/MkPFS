"""Inspect operation panel for mkpfs GUI."""

from typing import Any

import customtkinter as ctk

from ..i18n import tr
from ..theme import _BG_INPUT, _BORDER_BRIGHT, _FONT_LABEL, _FONT_MONO, _TEXT_PRIMARY, _TEXT_SECONDARY
from ..widgets import GlassCard, OptionRow, PathRow, SectionLabel
from .base import BasePanel


class InspectPanel(BasePanel):
    """Panel for inspecting PFS image metadata."""

    _title_key = "i_title"
    _subtitle_key = "i_subtitle"
    _panel_key = "inspect"

    def __init__(self, parent: Any) -> None:
        """Initialise InspectPanel.

        Args:
            parent: Parent widget.
        """
        self._image: ctk.StringVar = ctk.StringVar()
        self._fmt: ctk.StringVar = ctk.StringVar(value="text")
        self._ekpfs: ctk.StringVar = ctk.StringVar()
        super().__init__(parent)

    def _build_controls(self, card: GlassCard) -> None:
        card.columnconfigure(0, weight=1)
        card.columnconfigure(1, weight=1)

        SectionLabel(card, tr("paths"), color=self._accent).grid(
            row=0, column=0, columnspan=2, sticky="w", padx=16, pady=(14, 6)
        )
        PathRow(
            card,
            tr("i_image_label"),
            self._image,
            mode="open",
            filetypes=[("PFS image", "*.ffpfs *.ffpfsc"), ("All files", "*.*")],
            placeholder=tr("i_image_ph"),
            browse_label=tr("browse"),
        ).grid(row=1, column=0, columnspan=2, sticky="ew", padx=16, pady=(0, 14))

        ctk.CTkFrame(card, height=1, fg_color=_BORDER_BRIGHT).grid(row=2, column=0, columnspan=2, sticky="ew", padx=16)
        SectionLabel(card, tr("options"), color=self._accent).grid(
            row=3, column=0, columnspan=2, sticky="w", padx=16, pady=(12, 6)
        )

        opt: ctk.CTkFrame = ctk.CTkFrame(card, fg_color="transparent")
        opt.grid(row=4, column=0, columnspan=2, sticky="ew", padx=16, pady=(0, 14))
        opt.columnconfigure((0, 1), weight=1)

        OptionRow(opt, tr("i_format"), self._fmt, ["text", "json"], accent=self._accent).grid(
            row=0, column=0, sticky="ew", padx=(0, 12)
        )

        ekpfs_col: ctk.CTkFrame = ctk.CTkFrame(opt, fg_color="transparent")
        ekpfs_col.grid(row=0, column=1, sticky="ew")
        ctk.CTkLabel(ekpfs_col, text=tr("i_ekpfs"), font=_FONT_LABEL, text_color=_TEXT_SECONDARY).pack(
            anchor="w", pady=(0, 3)
        )
        ctk.CTkEntry(
            ekpfs_col,
            textvariable=self._ekpfs,
            placeholder_text=tr("i_ekpfs_ph"),
            fg_color=_BG_INPUT,
            border_color=_BORDER_BRIGHT,
            corner_radius=8,
            font=_FONT_MONO,
            text_color=_TEXT_PRIMARY,
        ).pack(fill="x")

    def _run_command(self) -> None:
        image: str = self._image.get().strip()
        if not image:
            self._emit(tr("i_err"), "error")
            return
        args: list[str] = ["inspect", image, "--format", self._fmt.get()]
        if ekpfs := self._ekpfs.get().strip():
            args += ["--ekpfs-key", ekpfs]
        self._run_mkpfs(args)
