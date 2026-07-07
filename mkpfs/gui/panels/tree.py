"""Tree operation panel for mkpfs GUI."""

from typing import Any

import customtkinter as ctk

from ..i18n import tr
from ..theme import _BG_INPUT, _BORDER_BRIGHT, _FONT_LABEL, _FONT_MONO, _TEXT_PRIMARY, _TEXT_SECONDARY
from ..widgets import GlassCard, NeonCheckbox, PathRow, SectionLabel
from .base import BasePanel


class TreePanel(BasePanel):
    """Panel for printing the PFS filesystem tree."""

    _title_key = "t_title"
    _subtitle_key = "t_subtitle"
    _panel_key = "tree"

    def __init__(self, parent: Any) -> None:
        """Initialise TreePanel.

        Args:
            parent: Parent widget.
        """
        self._image: ctk.StringVar = ctk.StringVar()
        self._ekpfs: ctk.StringVar = ctk.StringVar()
        self._new_crypt: ctk.BooleanVar = ctk.BooleanVar(value=False)
        super().__init__(parent)

    def _build_controls(self, card: GlassCard) -> None:
        card.columnconfigure(0, weight=1)
        card.columnconfigure(1, weight=1)

        SectionLabel(card, tr("paths"), color=self._accent).grid(
            row=0, column=0, columnspan=2, sticky="w", padx=16, pady=(14, 6)
        )
        PathRow(
            card,
            tr("t_image_label"),
            self._image,
            mode="open",
            filetypes=[("PFS image", "*.ffpfs *.ffpfsc"), ("All files", "*.*")],
            placeholder=tr("t_image_ph"),
            browse_label=tr("browse"),
        ).grid(row=1, column=0, columnspan=2, sticky="ew", padx=16, pady=(0, 14))

        ctk.CTkFrame(card, height=1, fg_color=_BORDER_BRIGHT).grid(row=2, column=0, columnspan=2, sticky="ew", padx=16)
        SectionLabel(card, tr("encryption"), color=self._accent).grid(
            row=3, column=0, columnspan=2, sticky="w", padx=16, pady=(12, 6)
        )

        enc: ctk.CTkFrame = ctk.CTkFrame(card, fg_color="transparent")
        enc.grid(row=4, column=0, columnspan=2, sticky="ew", padx=16, pady=(0, 14))
        ctk.CTkLabel(enc, text=tr("t_ekpfs"), font=_FONT_LABEL, text_color=_TEXT_SECONDARY).pack(
            anchor="w", pady=(0, 3)
        )
        ctk.CTkEntry(
            enc,
            textvariable=self._ekpfs,
            placeholder_text=tr("t_ekpfs_ph"),
            fg_color=_BG_INPUT,
            border_color=_BORDER_BRIGHT,
            corner_radius=8,
            font=_FONT_MONO,
            text_color=_TEXT_PRIMARY,
        ).pack(fill="x", pady=(0, 6))
        NeonCheckbox(enc, text=tr("t_newcrypt"), variable=self._new_crypt, accent=self._accent).pack(anchor="w")

    def _run_command(self) -> None:
        image: str = self._image.get().strip()
        if not image:
            self._emit(tr("t_err"), "error")
            return
        args: list[str] = ["tree", image]
        if ekpfs := self._ekpfs.get().strip():
            args += ["--ekpfs-key", ekpfs]
        if self._new_crypt.get():
            args.append("--new-crypt")
        self._run_mkpfs(args)
