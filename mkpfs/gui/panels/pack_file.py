"""Pack File operation panel for mkpfs GUI."""

from pathlib import Path
from typing import Any

import customtkinter as ctk

from ...utils import ui_sanitize_basename
from ..i18n import tr
from ..metadata_preview import MetadataPreview
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
        self._version: ctk.StringVar = ctk.StringVar(value="PS5")
        self._compress: ctk.BooleanVar = ctk.BooleanVar(value=True)
        self._temp_folder: ctk.StringVar = ctk.StringVar()
        self._metadata_preview: MetadataPreview | None = None
        super().__init__(parent)

        # Auto-populate output path from source file selection when empty.
        self._src.trace_add("write", self._on_src_changed)

    def _build_controls(self, card: GlassCard) -> None:
        card.columnconfigure(0, weight=1)
        card.columnconfigure(1, weight=1)

        self._metadata_preview = MetadataPreview(card, self._accent)
        self._metadata_preview.grid(row=0, column=0, columnspan=2, sticky="ew")
        self._metadata_preview.load(self._src.get().strip())

        ctk.CTkFrame(card, height=1, fg_color=_BORDER_BRIGHT).grid(
            row=1, column=0, columnspan=2, sticky="ew", padx=16
        )

        SectionLabel(card, tr("paths"), color=self._accent).grid(
            row=2, column=0, columnspan=2, sticky="w", padx=16, pady=(12, 6)
        )

        PathRow(
            card,
            tr("pkf_src_label"),
            self._src,
            mode="open",
            filetypes=[
                ("Game images", "*.exfat *.ffpkg *.ffpfs *.ffpfsc"),
                ("PFS image", "*.ffpfs *.ffpfsc"),
                ("exFAT image", "*.exfat"),
                ("FFPKG image", "*.ffpkg"),
                ("All files", "*.*"),
            ],
            placeholder=tr("pkf_src_ph"),
            browse_label=tr("browse"),
        ).grid(row=3, column=0, columnspan=2, sticky="ew", padx=16, pady=(0, 10))

        PathRow(
            card,
            tr("pkf_out_label"),
            self._out,
            mode="save",
            filetypes=[("PFS image", "*.ffpfsc"), ("All files", "*.*")],
            placeholder=tr("pkf_out_ph"),
            browse_label=tr("browse"),
        ).grid(row=4, column=0, columnspan=2, sticky="ew", padx=16, pady=(0, 14))

        ctk.CTkFrame(card, height=1, fg_color=_BORDER_BRIGHT).grid(row=5, column=0, columnspan=2, sticky="ew", padx=16)

        SectionLabel(card, tr("options"), color=self._accent).grid(
            row=6, column=0, columnspan=2, sticky="w", padx=16, pady=(12, 6)
        )

        opt: ctk.CTkFrame = ctk.CTkFrame(card, fg_color="transparent")
        opt.grid(row=7, column=0, columnspan=2, sticky="ew", padx=16, pady=(0, 14))
        opt.columnconfigure((0, 1), weight=1)

        OptionRow(opt, tr("pkf_version"), self._version, ["PS5", "PS4"], accent=self._accent).grid(
            row=0, column=0, sticky="ew", padx=(0, 8), pady=(0, 8)
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

    def _on_src_changed(self, *_args: Any) -> None:
        """Auto-populate sensible output filename when user selects a source file.

        Uses the source file stem, sanitized using ui_sanitize_basename, with
        the .ffpfsc extension. Only fills the output when the output field is
        currently empty.
        """
        src_path: str = self._src.get().strip()
        if self._metadata_preview is not None:
            self._metadata_preview.load(src_path)
        if self._out.get().strip():
            return
        if not src_path:
            return
        p: Path = Path(src_path)
        # Only when the source is a file
        if not p.is_file():
            return
        self._out.set(str(p.parent / (ui_sanitize_basename(p.stem) + ".ffpfsc")))

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
