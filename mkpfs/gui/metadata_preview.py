"""Reusable game metadata preview for GUI panels."""

from __future__ import annotations

import io
import threading
from pathlib import Path
from typing import Any

import customtkinter as ctk
from PIL import Image

from ..game_metadata import GameMetadata, read_game_metadata
from .i18n import tr
from .theme import _BG_INPUT, _BORDER_BRIGHT, _FONT_LABEL, _FONT_SMALL, _FONT_UI, _TEXT_MUTED, _TEXT_PRIMARY
from .widgets import SectionLabel


class MetadataPreview(ctk.CTkFrame):
    """Compact cover and metadata preview shared by import panels."""

    def __init__(self, parent: Any, accent: str) -> None:
        super().__init__(parent, fg_color="transparent")
        self._accent = accent
        self._metadata_after_id: str | None = None
        self._metadata_token = 0
        self._cover_image: ctk.CTkImage | None = None
        self._cover_label: ctk.CTkLabel | None = None
        self._title = ctk.StringVar(value="-")
        self._values: dict[str, ctk.StringVar] = {
            "title_id": ctk.StringVar(value="-"),
            "content_id": ctk.StringVar(value="-"),
            "size": ctk.StringVar(value="-"),
            "version": ctk.StringVar(value="-"),
            "region": ctk.StringVar(value="-"),
            "apr_emu": ctk.StringVar(value="-"),
        }
        self._build()

    def _build(self) -> None:
        self.columnconfigure(0, weight=1)

        SectionLabel(self, tr("meta_import"), color=self._accent).grid(
            row=0, column=0, sticky="w", padx=16, pady=(14, 6)
        )

        body = ctk.CTkFrame(self, fg_color="transparent")
        body.grid(row=1, column=0, sticky="ew", padx=16, pady=(0, 12))
        body.columnconfigure(1, weight=1)

        cover_box = ctk.CTkFrame(
            body,
            width=116,
            height=132,
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

        details = ctk.CTkFrame(body, fg_color="transparent")
        details.grid(row=0, column=1, sticky="nsew")
        details.columnconfigure((0, 1), weight=1, uniform="metadata")

        ctk.CTkLabel(
            details,
            textvariable=self._title,
            font=("Segoe UI", 15, "bold"),
            text_color=_TEXT_PRIMARY,
            anchor="w",
            wraplength=760,
            justify="left",
        ).grid(row=0, column=0, columnspan=2, sticky="ew", pady=(0, 6))

        self._field(details, 1, 0, tr("pkf_meta_title_id"), self._values["title_id"])
        self._field(details, 1, 1, tr("pkf_meta_size"), self._values["size"])
        self._field(details, 2, 0, tr("pkf_meta_content_id"), self._values["content_id"], columnspan=2)
        self._field(details, 3, 0, tr("pkf_meta_version"), self._values["version"])
        self._field(details, 3, 1, tr("pkf_meta_region"), self._values["region"])
        self._field(details, 4, 0, tr("pkf_meta_apr_emu"), self._values["apr_emu"])

    def _field(
        self,
        parent: ctk.CTkFrame,
        row: int,
        column: int,
        label: str,
        variable: ctk.StringVar,
        columnspan: int = 1,
    ) -> None:
        field = ctk.CTkFrame(parent, fg_color="transparent")
        field.grid(row=row, column=column, columnspan=columnspan, sticky="ew", padx=(0, 14), pady=2)
        field.columnconfigure(1, weight=1)
        ctk.CTkLabel(
            field,
            text=f"{label}:",
            font=_FONT_LABEL,
            text_color=_TEXT_MUTED,
            anchor="w",
        ).grid(row=0, column=0, sticky="w", padx=(0, 8))
        ctk.CTkLabel(
            field,
            textvariable=variable,
            font=_FONT_UI,
            text_color=_TEXT_PRIMARY,
            anchor="w",
            justify="left",
            wraplength=680 if columnspan > 1 else 260,
        ).grid(row=0, column=1, sticky="ew")

    def load(self, src_path: str) -> None:
        """Debounce metadata extraction for a selected file or folder."""
        if self._metadata_after_id is not None:
            self.after_cancel(self._metadata_after_id)
            self._metadata_after_id = None
        if not src_path.strip():
            self.reset()
            return
        self._title.set(Path(src_path).name or "-")
        self._metadata_after_id = self.after(250, lambda path=src_path: self._load(path))

    def reset(self) -> None:
        """Return the preview to its empty state."""
        self._metadata_token += 1
        self._title.set("-")
        for value in self._values.values():
            value.set("-")
        self._set_cover(None)

    def _load(self, src_path: str) -> None:
        self._metadata_after_id = None
        self._metadata_token += 1
        token = self._metadata_token
        path = Path(src_path)
        if not path.exists():
            self.reset()
            return

        def worker() -> None:
            metadata = read_game_metadata(path)
            self.after(0, lambda: self._apply_metadata(token, metadata))

        threading.Thread(target=worker, daemon=True).start()

    def _apply_metadata(self, token: int, metadata: GameMetadata) -> None:
        if token != self._metadata_token:
            return
        self._title.set(metadata.game_title or metadata.file_name or "-")
        self._values["title_id"].set(metadata.title_id or "-")
        self._values["content_id"].set(metadata.content_id or "-")
        self._values["size"].set(metadata.size_display)
        self._values["version"].set(metadata.version or "-")
        self._values["region"].set(metadata.region or "-")
        self._values["apr_emu"].set(tr("pkf_meta_apr_yes") if metadata.has_apr_emu else tr("pkf_meta_apr_no"))
        self._set_cover(metadata.icon_bytes)

    def _set_cover(self, icon_bytes: bytes | None) -> None:
        if self._cover_label is None:
            return
        if not icon_bytes:
            self._cover_image = None
            self._cover_label.configure(image=None, text=tr("pkf_cover_empty"))
            return
        try:
            image = Image.open(io.BytesIO(icon_bytes)).convert("RGBA")
            image.thumbnail((100, 116), Image.LANCZOS)
            self._cover_image = ctk.CTkImage(light_image=image, dark_image=image, size=image.size)
            self._cover_label.configure(image=self._cover_image, text="")
        except (OSError, ValueError):
            self._cover_image = None
            self._cover_label.configure(image=None, text=tr("pkf_cover_empty"))
