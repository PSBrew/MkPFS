"""Batch queue preview widgets for the GUI."""

from __future__ import annotations

import io
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import customtkinter as ctk
from PIL import Image

from ..batch import BatchItem, discover_batch_items
from ..game_metadata import GameMetadata, read_game_metadata
from .i18n import tr
from .theme import (
    _BG_CARD,
    _BG_INPUT,
    _BORDER_BRIGHT,
    _FONT_LABEL,
    _FONT_SMALL,
    _FONT_UI,
    _NEON_PINK,
    _TEXT_MUTED,
    _TEXT_PRIMARY,
    _TEXT_SECONDARY,
)
from .widgets import SectionLabel


@dataclass
class BatchPreviewItem:
    """One discovered batch item and its parsed metadata."""

    item: BatchItem
    metadata: GameMetadata


class BatchQueuePreview(ctk.CTkFrame):
    """Scrollable Spectrum-style preview of all discovered batch items."""

    def __init__(self, parent: Any, accent: str) -> None:
        super().__init__(parent, fg_color="transparent")
        self._accent = accent
        self._token = 0
        self._summary = ctk.StringVar(value=tr("bt_preview_empty"))
        self._rows: list[BatchItemRow] = []
        self._build()

    def _build(self) -> None:
        self.columnconfigure(0, weight=1)

        header = ctk.CTkFrame(self, fg_color="transparent")
        header.grid(row=0, column=0, sticky="ew", padx=16, pady=(14, 6))
        header.columnconfigure(1, weight=1)
        SectionLabel(header, tr("bt_queue"), color=self._accent).grid(row=0, column=0, sticky="w")
        ctk.CTkLabel(
            header,
            textvariable=self._summary,
            font=_FONT_SMALL,
            text_color=_TEXT_MUTED,
            anchor="e",
        ).grid(row=0, column=1, sticky="e")

        self._list = ctk.CTkScrollableFrame(
            self,
            height=280,
            fg_color=_BG_INPUT,
            corner_radius=8,
            border_width=1,
            border_color=_BORDER_BRIGHT,
            scrollbar_button_color=_BORDER_BRIGHT,
            scrollbar_button_hover_color=self._accent,
        )
        self._list.grid(row=1, column=0, sticky="ew", padx=16, pady=(0, 12))
        self._list.columnconfigure(0, weight=1)

        self._empty = ctk.CTkLabel(
            self._list,
            text=tr("bt_preview_empty"),
            font=_FONT_UI,
            text_color=_TEXT_MUTED,
        )
        self._empty.grid(row=0, column=0, sticky="ew", padx=12, pady=22)

    def load(self, src_path: str) -> None:
        """Scan a batch folder and show every packable item."""
        self._token += 1
        token = self._token
        path = Path(src_path.strip()) if src_path.strip() else None
        self._clear_rows()
        if path is None:
            self._summary.set(tr("bt_preview_empty"))
            self._empty.configure(text=tr("bt_preview_empty"))
            self._empty.grid(row=0, column=0, sticky="ew", padx=12, pady=22)
            return
        if not path.is_dir():
            self._summary.set(tr("bt_preview_invalid"))
            self._empty.configure(text=tr("bt_preview_invalid"))
            self._empty.grid(row=0, column=0, sticky="ew", padx=12, pady=22)
            return

        self._summary.set(tr("bt_preview_scanning"))
        self._empty.configure(text=tr("bt_preview_scanning"))
        self._empty.grid(row=0, column=0, sticky="ew", padx=12, pady=22)

        def worker() -> None:
            try:
                items = discover_batch_items(path)
                previews = [BatchPreviewItem(item=item, metadata=read_game_metadata(item.source)) for item in items]
                error = ""
            except Exception as exc:
                previews = []
                error = str(exc)
            self.after(0, lambda: self._apply(token, previews, error))

        threading.Thread(target=worker, daemon=True).start()

    def _clear_rows(self) -> None:
        for row in self._rows:
            row.destroy()
        self._rows.clear()

    def _apply(self, token: int, previews: list[BatchPreviewItem], error: str) -> None:
        if token != self._token:
            return
        self._clear_rows()
        if error:
            self._summary.set(tr("bt_preview_error").format(error))
            self._empty.configure(text=tr("bt_preview_error").format(error))
            self._empty.grid(row=0, column=0, sticky="ew", padx=12, pady=22)
            return
        if not previews:
            self._summary.set(tr("bt_preview_none"))
            self._empty.configure(text=tr("bt_preview_none"))
            self._empty.grid(row=0, column=0, sticky="ew", padx=12, pady=22)
            return

        self._empty.grid_forget()
        folders = sum(1 for preview in previews if preview.item.kind == "folder")
        files = len(previews) - folders
        self._summary.set(tr("bt_preview_count").format(len(previews), folders, files))
        for row_index, preview in enumerate(previews):
            row = BatchItemRow(self._list, preview, self._accent)
            row.grid(row=row_index, column=0, sticky="ew", padx=6, pady=(6 if row_index == 0 else 0, 6))
            self._rows.append(row)


class BatchItemRow(ctk.CTkFrame):
    """One row in the batch queue preview."""

    def __init__(self, parent: Any, preview: BatchPreviewItem, accent: str) -> None:
        super().__init__(
            parent,
            fg_color=_BG_CARD,
            corner_radius=8,
            border_width=1,
            border_color=_BORDER_BRIGHT,
        )
        self._preview = preview
        self._accent = accent
        self._cover_image: ctk.CTkImage | None = None
        self._build()

    def _build(self) -> None:
        metadata = self._preview.metadata
        self.columnconfigure(1, weight=1)

        cover = ctk.CTkFrame(
            self,
            width=70,
            height=84,
            fg_color=_BG_INPUT,
            corner_radius=8,
            border_width=1,
            border_color=_BORDER_BRIGHT,
        )
        cover.grid(row=0, column=0, sticky="nw", padx=10, pady=10)
        cover.grid_propagate(False)
        cover_label = ctk.CTkLabel(cover, text=tr("pkf_cover_empty"), font=_FONT_SMALL, text_color=_TEXT_MUTED)
        cover_label.pack(fill="both", expand=True, padx=5, pady=5)
        self._set_cover(cover_label, metadata.icon_bytes)

        body = ctk.CTkFrame(self, fg_color="transparent")
        body.grid(row=0, column=1, sticky="nsew", padx=(0, 10), pady=10)
        body.columnconfigure(0, weight=1)

        title = metadata.game_title or metadata.file_name or self._preview.item.name
        ctk.CTkLabel(
            body,
            text=title,
            font=("Segoe UI", 13, "bold"),
            text_color=_TEXT_PRIMARY,
            anchor="w",
            justify="left",
            wraplength=760,
        ).grid(row=0, column=0, sticky="ew")

        details = (
            f"{tr('pkf_meta_title_id')}: {metadata.title_id or '-'}"
            f"  |  {tr('pkf_meta_version')}: {metadata.version or '-'}"
            f"  |  {metadata.package_type or self._preview.item.kind.upper()}"
            f"  |  {tr('pkf_meta_size')}: {metadata.size_display}"
            f"  |  {tr('pkf_meta_region')}: {metadata.region or '-'}"
        )
        ctk.CTkLabel(
            body,
            text=details,
            font=_FONT_LABEL,
            text_color=self._accent,
            anchor="w",
            justify="left",
            wraplength=900,
        ).grid(row=1, column=0, sticky="ew", pady=(3, 0))

        ctk.CTkLabel(
            body,
            text=f"{tr('pkf_meta_content_id')}: {metadata.content_id or '-'}",
            font=_FONT_LABEL,
            text_color=_TEXT_SECONDARY,
            anchor="w",
            justify="left",
            wraplength=900,
        ).grid(row=2, column=0, sticky="ew", pady=(3, 0))

        footer = ctk.CTkFrame(body, fg_color="transparent")
        footer.grid(row=3, column=0, sticky="ew", pady=(7, 0))
        ctk.CTkLabel(
            footer,
            text=self._preview.item.kind.upper(),
            font=_FONT_SMALL,
            text_color=_TEXT_MUTED,
        ).pack(side="left")
        if metadata.has_apr_emu:
            ctk.CTkLabel(
                footer,
                text=f"  {tr('pkf_meta_apr_emu')}: {tr('pkf_meta_apr_yes')}",
                font=("Segoe UI", 10, "bold"),
                text_color=_NEON_PINK,
            ).pack(side="left", padx=(10, 0))

    def _set_cover(self, label: ctk.CTkLabel, icon_bytes: bytes | None) -> None:
        if not icon_bytes:
            return
        try:
            image = Image.open(io.BytesIO(icon_bytes)).convert("RGBA")
            image.thumbnail((60, 74), Image.LANCZOS)
            self._cover_image = ctk.CTkImage(light_image=image, dark_image=image, size=image.size)
            label.configure(image=self._cover_image, text="")
        except (OSError, ValueError):
            self._cover_image = None
