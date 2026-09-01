"""Pack File operation panel for mkpfs GUI."""

import io
import threading
from pathlib import Path
from typing import Any

import customtkinter as ctk
from PIL import Image

from ...game_metadata import GameMetadata, read_game_metadata
from ...utils import ui_sanitize_basename
from ..i18n import tr
from ..theme import _BG_INPUT, _BORDER_BRIGHT, _FONT_LABEL, _FONT_SMALL, _FONT_UI, _TEXT_MUTED, _TEXT_PRIMARY
from ..widgets import GlassCard, NeonCheckbox, PathRow, SectionLabel
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
        self._compress: ctk.BooleanVar = ctk.BooleanVar(value=True)
        self._temp_folder: ctk.StringVar = ctk.StringVar()
        self._meta_title: ctk.StringVar = ctk.StringVar(value="-")
        self._meta_status: ctk.StringVar = ctk.StringVar(value=tr("pkf_meta_waiting"))
        self._meta_values: dict[str, ctk.StringVar] = {
            "title_id": ctk.StringVar(value="-"),
            "content_id": ctk.StringVar(value="-"),
            "size": ctk.StringVar(value="-"),
            "version": ctk.StringVar(value="-"),
            "region": ctk.StringVar(value="-"),
            "apr_emu": ctk.StringVar(value="-"),
        }
        self._metadata_after_id: str | None = None
        self._metadata_token: int = 0
        self._cover_image: ctk.CTkImage | None = None
        self._cover_label: ctk.CTkLabel | None = None
        super().__init__(parent)

        # Auto-populate output path from source file selection when empty.
        self._src.trace_add("write", self._on_src_changed)

    def _build_controls(self, card: GlassCard) -> None:
        card.columnconfigure(0, weight=1)
        card.columnconfigure(1, weight=1)

        SectionLabel(card, tr("pkf_import"), color=self._accent).grid(
            row=0, column=0, columnspan=2, sticky="w", padx=16, pady=(14, 6)
        )

        preview: ctk.CTkFrame = ctk.CTkFrame(card, fg_color="transparent")
        preview.grid(row=1, column=0, columnspan=2, sticky="ew", padx=16, pady=(0, 14))
        preview.columnconfigure(1, weight=1)

        cover_box: ctk.CTkFrame = ctk.CTkFrame(
            preview,
            width=124,
            height=148,
            fg_color=_BG_INPUT,
            corner_radius=8,
            border_width=1,
            border_color=_BORDER_BRIGHT,
        )
        cover_box.grid(row=0, column=0, sticky="nw", padx=(0, 14))
        cover_box.grid_propagate(False)
        self._cover_label = ctk.CTkLabel(
            cover_box,
            text=tr("pkf_cover_empty"),
            font=_FONT_SMALL,
            text_color=_TEXT_MUTED,
        )
        self._cover_label.pack(fill="both", expand=True, padx=8, pady=8)

        meta: ctk.CTkFrame = ctk.CTkFrame(preview, fg_color="transparent")
        meta.grid(row=0, column=1, sticky="nsew")
        meta.columnconfigure(1, weight=1)
        ctk.CTkLabel(
            meta,
            textvariable=self._meta_title,
            font=("Segoe UI", 16, "bold"),
            text_color=_TEXT_PRIMARY,
            anchor="w",
        ).grid(row=0, column=0, columnspan=4, sticky="ew", pady=(0, 6))

        self._metadata_field(meta, 1, 0, tr("pkf_meta_title_id"), self._meta_values["title_id"])
        self._metadata_field(meta, 1, 2, tr("pkf_meta_size"), self._meta_values["size"])
        self._metadata_field(meta, 2, 0, tr("pkf_meta_content_id"), self._meta_values["content_id"])
        self._metadata_field(meta, 3, 0, tr("pkf_meta_version"), self._meta_values["version"])
        self._metadata_field(meta, 3, 2, tr("pkf_meta_region"), self._meta_values["region"])
        self._metadata_field(meta, 4, 0, tr("pkf_meta_apr_emu"), self._meta_values["apr_emu"])

        ctk.CTkLabel(
            meta,
            textvariable=self._meta_status,
            font=_FONT_SMALL,
            text_color=_TEXT_MUTED,
            anchor="w",
        ).grid(row=5, column=0, columnspan=4, sticky="ew", pady=(8, 0))

        ctk.CTkFrame(card, height=1, fg_color=_BORDER_BRIGHT).grid(
            row=2, column=0, columnspan=2, sticky="ew", padx=16
        )

        SectionLabel(card, tr("paths"), color=self._accent).grid(
            row=3, column=0, columnspan=2, sticky="w", padx=16, pady=(12, 6)
        )

        PathRow(
            card,
            tr("pkf_src_label"),
            self._src,
            mode="open",
            filetypes=[
                ("Game packages", "*.pkg *.exfat *.ffpkg *.ffpfs *.ffpfsc"),
                ("PFS image", "*.ffpfs *.ffpfsc"),
                ("exFAT image", "*.exfat"),
                ("FFPKG image", "*.ffpkg"),
                ("PKG package", "*.pkg"),
                ("All files", "*.*"),
            ],
            placeholder=tr("pkf_src_ph"),
            browse_label=tr("browse"),
        ).grid(row=4, column=0, columnspan=2, sticky="ew", padx=16, pady=(0, 10))

        PathRow(
            card,
            tr("pkf_out_label"),
            self._out,
            mode="save",
            filetypes=[("PFS image", "*.ffpfsc"), ("All files", "*.*")],
            placeholder=tr("pkf_out_ph"),
            browse_label=tr("browse"),
        ).grid(row=5, column=0, columnspan=2, sticky="ew", padx=16, pady=(0, 14))

        ctk.CTkFrame(card, height=1, fg_color=_BORDER_BRIGHT).grid(row=6, column=0, columnspan=2, sticky="ew", padx=16)

        SectionLabel(card, tr("options"), color=self._accent).grid(
            row=7, column=0, columnspan=2, sticky="w", padx=16, pady=(12, 6)
        )

        opt: ctk.CTkFrame = ctk.CTkFrame(card, fg_color="transparent")
        opt.grid(row=8, column=0, columnspan=2, sticky="ew", padx=16, pady=(0, 14))
        opt.columnconfigure((0, 1), weight=1)

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

    def _metadata_field(
        self,
        parent: ctk.CTkFrame,
        row: int,
        column: int,
        label: str,
        variable: ctk.StringVar,
    ) -> None:
        """Place one compact metadata label/value pair."""
        label_widget = ctk.CTkLabel(parent, text=label, font=_FONT_LABEL, text_color=_TEXT_MUTED, anchor="w")
        label_widget.grid(row=row, column=column, sticky="w", padx=(0, 8), pady=3)
        value = ctk.CTkLabel(
            parent,
            textvariable=variable,
            font=_FONT_UI,
            text_color=_TEXT_PRIMARY,
            anchor="w",
            wraplength=430 if column == 0 else 150,
        )
        value.grid(row=row, column=column + 1, sticky="ew", padx=(0, 16), pady=3)

    def _on_src_changed(self, *_args: Any) -> None:
        """Auto-populate sensible output filename when user selects a source file.

        Uses the source file stem, sanitized using ui_sanitize_basename, with
        the .ffpfsc extension. Only fills the output when the output field is
        currently empty.
        """
        src_path: str = self._src.get().strip()
        self._schedule_metadata_load(src_path)
        if self._out.get().strip():
            return
        if not src_path:
            return
        p: Path = Path(src_path)
        # Only when the source is a file
        if not p.is_file():
            return
        self._out.set(str(p.parent / (ui_sanitize_basename(p.stem) + ".ffpfsc")))

    def _schedule_metadata_load(self, src_path: str) -> None:
        """Debounce metadata extraction for the selected source file."""
        if self._metadata_after_id is not None:
            self.after_cancel(self._metadata_after_id)
            self._metadata_after_id = None
        if not src_path:
            self._reset_metadata(tr("pkf_meta_waiting"))
            return
        self._metadata_after_id = self.after(250, lambda path=src_path: self._load_metadata(path))

    def _load_metadata(self, src_path: str) -> None:
        """Read metadata off the UI thread and apply it when finished."""
        self._metadata_after_id = None
        self._metadata_token += 1
        token = self._metadata_token
        path = Path(src_path)
        if not path.is_file():
            self._reset_metadata(tr("pkf_meta_waiting"))
            return
        self._meta_status.set(tr("pkf_meta_loading"))

        def worker() -> None:
            metadata = read_game_metadata(path)
            self.after(0, lambda: self._apply_metadata(token, metadata))

        threading.Thread(target=worker, daemon=True).start()

    def _apply_metadata(self, token: int, metadata: GameMetadata) -> None:
        """Apply metadata to widgets if it belongs to the current selection."""
        if token != self._metadata_token:
            return
        title = metadata.game_title or metadata.file_name or "-"
        self._meta_title.set(title)
        self._meta_values["title_id"].set(metadata.title_id or "-")
        self._meta_values["content_id"].set(metadata.content_id or "-")
        self._meta_values["size"].set(metadata.size_display)
        self._meta_values["version"].set(metadata.version or "-")
        self._meta_values["region"].set(metadata.region or "-")
        self._meta_values["apr_emu"].set(tr("pkf_meta_apr_yes") if metadata.has_apr_emu else tr("pkf_meta_apr_no"))
        if metadata.error:
            self._meta_status.set(tr("pkf_meta_partial").format(metadata.package_type or "-", metadata.error))
        else:
            self._meta_status.set(tr("pkf_meta_ready").format(metadata.package_type or "-"))
        self._set_cover(metadata.icon_bytes)

    def _reset_metadata(self, status: str) -> None:
        """Return the metadata preview to its empty state."""
        self._metadata_token += 1
        self._meta_title.set("-")
        for value in self._meta_values.values():
            value.set("-")
        self._meta_status.set(status)
        self._set_cover(None)

    def _set_cover(self, icon_bytes: bytes | None) -> None:
        """Render the selected file cover or the empty placeholder."""
        if self._cover_label is None:
            return
        if not icon_bytes:
            self._cover_image = None
            self._cover_label.configure(image=None, text=tr("pkf_cover_empty"))
            return
        try:
            image = Image.open(io.BytesIO(icon_bytes)).convert("RGBA")
            image.thumbnail((108, 132), Image.LANCZOS)
            self._cover_image = ctk.CTkImage(light_image=image, dark_image=image, size=image.size)
            self._cover_label.configure(image=self._cover_image, text="")
        except (OSError, ValueError):
            self._cover_image = None
            self._cover_label.configure(image=None, text=tr("pkf_cover_empty"))

    def _run_command(self) -> None:
        src: str = self._src.get().strip()
        out: str = self._out.get().strip()
        if not src or not out:
            self._emit(tr("pkf_err"), "error")
            return
        args: list[str] = ["pack", "file", src, out]
        if not self._compress.get():
            args.append("--no-compress")
        if temp := self._temp_folder.get().strip():
            args += ["--temp-folder", temp]
        self._run_mkpfs(args)
