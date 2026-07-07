"""Verify operation panel for mkpfs GUI."""

from typing import Any

import customtkinter as ctk

from ..i18n import tr
from ..theme import _BG_INPUT, _BORDER_BRIGHT, _FONT_LABEL, _FONT_MONO, _FONT_UI, _TEXT_PRIMARY, _TEXT_SECONDARY
from ..widgets import GlassCard, NeonCheckbox, PathRow, SectionLabel
from .base import BasePanel


class VerifyPanel(BasePanel):
    """Panel for verifying a PFS image."""

    _title_key = "v_title"
    _subtitle_key = "v_subtitle"
    _panel_key = "verify"

    def __init__(self, parent: Any) -> None:
        """Initialise VerifyPanel.

        Args:
            parent: Parent widget.
        """
        self._image: ctk.StringVar = ctk.StringVar()
        self._source: ctk.StringVar = ctk.StringVar()
        self._crc32: ctk.StringVar = ctk.StringVar()
        self._sha256: ctk.StringVar = ctk.StringVar()
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
            tr("v_image_label"),
            self._image,
            mode="open",
            filetypes=[("PFS image", "*.ffpfs *.ffpfsc"), ("All files", "*.*")],
            placeholder=tr("v_image_ph"),
            browse_label=tr("browse"),
        ).grid(row=1, column=0, columnspan=2, sticky="ew", padx=16, pady=(0, 10))

        PathRow(
            card,
            tr("v_source_label"),
            self._source,
            mode="folder",
            placeholder=tr("v_source_ph"),
            browse_label=tr("browse"),
        ).grid(row=2, column=0, columnspan=2, sticky="ew", padx=16, pady=(0, 14))

        ctk.CTkFrame(card, height=1, fg_color=_BORDER_BRIGHT).grid(row=3, column=0, columnspan=2, sticky="ew", padx=16)
        SectionLabel(card, tr("v_hashes"), color=self._accent).grid(
            row=4, column=0, columnspan=2, sticky="w", padx=16, pady=(12, 6)
        )

        for col, (lkey, var, phkey) in enumerate(
            [
                ("v_crc32", self._crc32, "v_crc32_ph"),
                ("v_sha256", self._sha256, "v_sha256_ph"),
            ]
        ):
            hf: ctk.CTkFrame = ctk.CTkFrame(card, fg_color="transparent")
            hf.grid(row=5, column=col, sticky="ew", padx=(16 if col == 0 else 6, 6 if col == 0 else 16), pady=(0, 14))
            ctk.CTkLabel(hf, text=tr(lkey), font=_FONT_LABEL, text_color=_TEXT_SECONDARY).pack(anchor="w", pady=(0, 3))
            ctk.CTkEntry(
                hf,
                textvariable=var,
                placeholder_text=tr(phkey),
                fg_color=_BG_INPUT,
                border_color=_BORDER_BRIGHT,
                corner_radius=8,
                font=_FONT_UI,
                text_color=_TEXT_PRIMARY,
            ).pack(fill="x")

        ctk.CTkFrame(card, height=1, fg_color=_BORDER_BRIGHT).grid(row=6, column=0, columnspan=2, sticky="ew", padx=16)
        SectionLabel(card, tr("encryption"), color=self._accent).grid(
            row=7, column=0, columnspan=2, sticky="w", padx=16, pady=(12, 6)
        )

        enc: ctk.CTkFrame = ctk.CTkFrame(card, fg_color="transparent")
        enc.grid(row=8, column=0, columnspan=2, sticky="ew", padx=16, pady=(0, 14))
        ctk.CTkLabel(enc, text=tr("v_ekpfs"), font=_FONT_LABEL, text_color=_TEXT_SECONDARY).pack(
            anchor="w", pady=(0, 3)
        )
        ctk.CTkEntry(
            enc,
            textvariable=self._ekpfs,
            placeholder_text=tr("v_ekpfs_ph"),
            fg_color=_BG_INPUT,
            border_color=_BORDER_BRIGHT,
            corner_radius=8,
            font=_FONT_MONO,
            text_color=_TEXT_PRIMARY,
        ).pack(fill="x", pady=(0, 6))
        NeonCheckbox(enc, text=tr("v_newcrypt"), variable=self._new_crypt, accent=self._accent).pack(anchor="w")

    def _run_command(self) -> None:
        image: str = self._image.get().strip()
        if not image:
            self._emit(tr("v_err"), "error")
            return
        args: list[str] = ["verify", image]
        if source := self._source.get().strip():
            args += ["--source-dir", source]
        if crc := self._crc32.get().strip():
            args += ["--expect-crc32", crc]
        if sha := self._sha256.get().strip():
            args += ["--expect-manifest-sha256", sha]
        if ekpfs := self._ekpfs.get().strip():
            args += ["--ekpfs-key", ekpfs]
        if self._new_crypt.get():
            args.append("--new-crypt")
        self._run_mkpfs(args)
