"""Batch Convert operation panel for the mkpfs GUI."""

from pathlib import Path
from typing import Any

import customtkinter as ctk

from ..batch_preview import BatchQueuePreview
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
        self._verify_after: ctk.BooleanVar = ctk.BooleanVar(value=False)
        self._queue_preview: BatchQueuePreview | None = None
        super().__init__(parent)
        self._src.trace_add("write", self._on_src_changed)

    def _build_controls(self, card: "GlassCard") -> None:  # ruff: ignore[undefined-name]
        card.columnconfigure(0, weight=1)
        card.columnconfigure(1, weight=1)

        self._queue_preview = BatchQueuePreview(card, self._accent)
        self._queue_preview.grid(row=0, column=0, columnspan=2, sticky="ew")
        self._queue_preview.load(self._src.get().strip())

        ctk.CTkFrame(card, height=1, fg_color=_BORDER_BRIGHT).grid(row=1, column=0, columnspan=2, sticky="ew", padx=16)

        SectionLabel(card, tr("paths"), color=self._accent).grid(
            row=2, column=0, columnspan=2, sticky="w", padx=16, pady=(12, 6)
        )

        PathRow(
            card,
            label=tr("bt_src_label"),
            variable=self._src,
            placeholder=tr("bt_src_ph"),
            mode="folder",
        ).grid(row=3, column=0, columnspan=2, sticky="ew", padx=16, pady=(0, 10))

        PathRow(
            card,
            label=tr("bt_out_label"),
            variable=self._out,
            placeholder=tr("bt_out_ph"),
            mode="folder",
        ).grid(row=4, column=0, columnspan=2, sticky="ew", padx=16, pady=(0, 14))

        ctk.CTkFrame(card, height=1, fg_color=_BORDER_BRIGHT).grid(row=5, column=0, columnspan=2, sticky="ew", padx=16)
        SectionLabel(card, tr("options"), color=self._accent).grid(
            row=6, column=0, columnspan=2, sticky="w", padx=16, pady=(12, 6)
        )

        opt: ctk.CTkFrame = ctk.CTkFrame(card, fg_color="transparent")
        opt.grid(row=7, column=0, columnspan=2, sticky="ew", padx=16, pady=(0, 14))
        opt.columnconfigure((0, 1, 2), weight=1)

        OptionRow(opt, tr("bt_version"), self._version, ["PS5", "PS4"], accent=self._accent).grid(
            row=0, column=0, sticky="ew", padx=(0, 8), pady=(0, 8)
        )

        chk_left: ctk.CTkFrame = ctk.CTkFrame(opt, fg_color="transparent")
        chk_left.grid(row=0, column=1, sticky="nw", padx=(8, 0))

        chk_right: ctk.CTkFrame = ctk.CTkFrame(opt, fg_color="transparent")
        chk_right.grid(row=0, column=2, sticky="nw", padx=(8, 0))

        # Left column: Compression, Overwrite
        NeonCheckbox(chk_left, text=tr("bt_compress"), variable=self._compress, accent=self._accent).pack(
            anchor="w", pady=3
        )
        NeonCheckbox(chk_left, text=tr("bt_overwrite"), variable=self._overwrite, accent=self._accent).pack(
            anchor="w", pady=3
        )

        # Right column: Dry Run, Verify after pack
        NeonCheckbox(chk_right, text=tr("bt_dry"), variable=self._dry_run, accent=self._accent).pack(
            anchor="w", pady=3
        )
        NeonCheckbox(chk_right, text=tr("pf_verify"), variable=self._verify_after, accent=self._accent).pack(
            anchor="w", pady=3
        )

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
        if self._verify_after.get():
            args.append("--verify")

        self._run_mkpfs(args)

    def _on_src_changed(self, *_args: Any) -> None:
        """Auto-populate the output folder to match the selected source directory.

        Only runs when the output field is currently empty and the source
        resolves to an existing directory to avoid interfering with manual
        typing.
        """
        src_path: str = self._src.get().strip()
        if self._queue_preview is not None:
            self._queue_preview.load(src_path)
        if self._out.get().strip():
            return
        if not src_path:
            return
        p: Path = Path(src_path)
        if not p.is_dir():
            return
        # Default output = same as source folder.
        self._out.set(src_path)
