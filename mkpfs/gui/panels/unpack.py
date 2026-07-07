"""Unpack operation panel for mkpfs GUI."""

from pathlib import Path
from typing import Any

import customtkinter as ctk

from ..i18n import tr
from ..theme import _BG_INPUT, _BORDER_BRIGHT, _FONT_LABEL, _FONT_MONO, _TEXT_PRIMARY, _TEXT_SECONDARY
from ..widgets import GlassCard, NeonCheckbox, PathRow, SectionLabel
from .base import BasePanel


class UnpackPanel(BasePanel):
    """Panel for extracting a PFS image."""

    _title_key = "u_title"
    _subtitle_key = "u_subtitle"
    _panel_key = "unpack"

    def __init__(self, parent: Any) -> None:
        """Initialise UnpackPanel.

        Args:
            parent: Parent widget.
        """
        self._image: ctk.StringVar = ctk.StringVar()
        self._output: ctk.StringVar = ctk.StringVar()
        self._overwrite: ctk.BooleanVar = ctk.BooleanVar(value=False)
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
            tr("u_image_label"),
            self._image,
            mode="open",
            filetypes=[("PFS image", "*.ffpfs *.ffpfsc"), ("All files", "*.*")],
            placeholder=tr("u_image_ph"),
            browse_label=tr("browse"),
        ).grid(row=1, column=0, columnspan=2, sticky="ew", padx=16, pady=(0, 10))

        PathRow(
            card,
            tr("u_out_label"),
            self._output,
            mode="folder",
            placeholder=tr("u_out_ph"),
            browse_label=tr("browse"),
        ).grid(row=2, column=0, columnspan=2, sticky="ew", padx=16, pady=(0, 14))

        ctk.CTkFrame(card, height=1, fg_color=_BORDER_BRIGHT).grid(row=3, column=0, columnspan=2, sticky="ew", padx=16)
        SectionLabel(card, tr("options"), color=self._accent).grid(
            row=4, column=0, columnspan=2, sticky="w", padx=16, pady=(12, 6)
        )

        opt: ctk.CTkFrame = ctk.CTkFrame(card, fg_color="transparent")
        opt.grid(row=5, column=0, columnspan=2, sticky="ew", padx=16, pady=(0, 14))
        opt.columnconfigure((0, 1), weight=1)

        NeonCheckbox(opt, text=tr("u_overwrite"), variable=self._overwrite, accent=self._accent).grid(
            row=0, column=0, columnspan=2, sticky="w", pady=(0, 8)
        )

        enc_col: ctk.CTkFrame = ctk.CTkFrame(opt, fg_color="transparent")
        enc_col.grid(row=1, column=0, sticky="ew", padx=(0, 12))
        ctk.CTkLabel(enc_col, text=tr("u_ekpfs"), font=_FONT_LABEL, text_color=_TEXT_SECONDARY).pack(
            anchor="w", pady=(0, 3)
        )
        ctk.CTkEntry(
            enc_col,
            textvariable=self._ekpfs,
            placeholder_text=tr("u_ekpfs_ph"),
            fg_color=_BG_INPUT,
            border_color=_BORDER_BRIGHT,
            corner_radius=8,
            font=_FONT_MONO,
            text_color=_TEXT_PRIMARY,
        ).pack(fill="x")

        NeonCheckbox(opt, text=tr("u_newcrypt"), variable=self._new_crypt, accent=self._accent).grid(
            row=1, column=1, sticky="w", padx=(8, 0)
        )

    def _run_command(self) -> None:
        image: str = self._image.get().strip()
        output: str = self._output.get().strip()
        if not image or not output:
            self._emit(tr("u_err"), "error")
            return

        # When the chosen output path already exists as a directory and
        # overwrite is not requested, automatically create a subfolder named
        # after the image file so the extraction never collides with an
        # existing directory (e.g. Desktop -> Desktop/GRIS).
        actual_output: Path = Path(output)
        if actual_output.exists() and actual_output.is_dir() and not self._overwrite.get():
            actual_output = actual_output / Path(image).stem
            self._emit(tr("u_auto_subdir").format(actual_output), "muted")

        args: list[str] = ["unpack", image, str(actual_output)]
        if self._overwrite.get():
            args.append("--overwrite")
        if ekpfs := self._ekpfs.get().strip():
            args += ["--ekpfs-key", ekpfs]
        if self._new_crypt.get():
            args.append("--new-crypt")
        self._run_mkpfs(args)
