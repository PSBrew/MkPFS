"""Pack Folder operation panel for mkpfs GUI."""

from pathlib import Path
from typing import Any

import customtkinter as ctk

from ...utils import ui_sanitize_basename
from ..i18n import tr
from ..theme import _BORDER_BRIGHT
from ..widgets import GlassCard, NeonCheckbox, PathRow, SectionLabel
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
        self._compress: ctk.BooleanVar = ctk.BooleanVar(value=True)
        self._signed: ctk.BooleanVar = ctk.BooleanVar(value=False)
        self._verify_after: ctk.BooleanVar = ctk.BooleanVar(value=False)
        self._dry_run: ctk.BooleanVar = ctk.BooleanVar(value=False)
        self._temp_folder: ctk.StringVar = ctk.StringVar()
        super().__init__(parent)
        # Auto-populate output filename from source when empty.
        self._src.trace_add("write", self._on_src_changed)

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

        chk_left: ctk.CTkFrame = ctk.CTkFrame(opt, fg_color="transparent")
        chk_left.grid(row=0, column=0, sticky="nw")

        chk_right: ctk.CTkFrame = ctk.CTkFrame(opt, fg_color="transparent")
        chk_right.grid(row=0, column=1, sticky="nw", padx=(8, 0))

        # Left column: Compression, Signed
        NeonCheckbox(chk_left, text=tr("pf_compress"), variable=self._compress, accent=self._accent).pack(
            anchor="w", pady=3
        )
        NeonCheckbox(chk_left, text=tr("pf_signed"), variable=self._signed, accent=self._accent).pack(
            anchor="w", pady=3
        )
        # Right column: Dry Run, Verify after pack
        NeonCheckbox(chk_right, text=tr("pf_dry"), variable=self._dry_run, accent=self._accent).pack(
            anchor="w", pady=3
        )
        NeonCheckbox(chk_right, text=tr("pf_verify"), variable=self._verify_after, accent=self._accent).pack(
            anchor="w", pady=3
        )

        # Temp folder (optional, spans both columns below checkboxes)
        PathRow(
            opt,
            tr("pf_temp"),
            self._temp_folder,
            mode="folder",
            placeholder=tr("pf_temp_ph"),
            browse_label=tr("browse"),
        ).grid(row=1, column=0, columnspan=2, sticky="ew", pady=(10, 0))

    def _on_src_changed(self, *_args: Any) -> None:
        """Auto-populate an output basename for pack-folder when the source is chosen.

        Applies ui_sanitize_basename to the source folder name, and uses the
        canonical .ffpfsc extension. Only triggers when the output field is
        currently empty and the source resolves to an existing directory.
        """
        if self._out.get().strip():
            return
        src_path: str = self._src.get().strip()
        if not src_path:
            return

        p: Path = Path(src_path)
        if not p.is_dir():
            return
        self._out.set(str(p.parent / (ui_sanitize_basename(p.name) + ".ffpfsc")))

    def _run_command(self) -> None:
        src: str = self._src.get().strip()
        out: str = self._out.get().strip()
        if not src:
            self._emit(tr("pf_err_src"), "error")
            return
        if not out:
            self._emit(tr("pf_err_out"), "error")
            return
        args: list[str] = ["pack", "folder", src, out]
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
