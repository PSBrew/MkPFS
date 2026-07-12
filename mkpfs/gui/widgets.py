"""Reusable widget layer for the mkpfs GUI - neon glassmorphism widgets.

This module hosts the file-dialog helpers and the building-block widget
classes used by the operation panels. Labels are passed in as parameters so
this module does not depend on the i18n layer.
"""

from tkinter import filedialog
from typing import Any

import customtkinter as ctk

from .theme import (
    _BG_CARD,
    _BG_DEEP,
    _BG_INPUT,
    _BG_PANEL,
    _BORDER_BRIGHT,
    _CORNER,
    _FONT_LABEL,
    _FONT_MONO,
    _FONT_UI,
    _NEON_BLUE,
    _TEXT_MUTED,
    _TEXT_PRIMARY,
    _TEXT_SECONDARY,
)

# ---------------------------------------------------------------------------
# Utility helpers


def _dim_hex_color(color: str, factor: float = 0.85) -> str:
    """Return a darker shade for a ``#RRGGBB`` color.

    If parsing fails (for example a named color), return the original value.
    """
    if not isinstance(color, str) or not color.startswith("#") or len(color) != 7:
        return color
    try:
        r = int(color[1:3], 16)
        g = int(color[3:5], 16)
        b = int(color[5:7], 16)
    except ValueError:
        return color

    r = max(0, min(255, int(r * factor)))
    g = max(0, min(255, int(g * factor)))
    b = max(0, min(255, int(b * factor)))
    return f"#{r:02X}{g:02X}{b:02X}"


# ---------------------------------------------------------------------------


def _browse_folder(var: ctk.StringVar) -> None:
    """Open a folder chooser dialog and update a StringVar.

    Args:
        var: Variable to receive the selected directory path.
    """
    path: str = filedialog.askdirectory()
    if path:
        var.set(path)


def _browse_file(var: ctk.StringVar, filetypes: list[tuple[str, str]] | None = None) -> None:
    """Open a file chooser dialog and update a StringVar.

    Args:
        var: Variable to receive the selected file path.
        filetypes: Optional list of (label, pattern) filter tuples.
    """
    path: str = filedialog.askopenfilename(filetypes=filetypes or [("All files", "*.*")])
    if path:
        var.set(path)


def _browse_save(var: ctk.StringVar, filetypes: list[tuple[str, str]] | None = None) -> None:
    """Open a save-file dialog and update a StringVar.

    Args:
        var: Variable to receive the chosen save path.
        filetypes: Optional list of (label, pattern) filter tuples.
    """
    path: str = filedialog.asksaveasfilename(filetypes=filetypes or [("All files", "*.*")])
    if path:
        var.set(path)


# ---------------------------------------------------------------------------
# Reusable widgets
# ---------------------------------------------------------------------------


class GlassCard(ctk.CTkFrame):
    """A dark card frame with rounded corners and a neon-tinted border."""

    def __init__(self, parent: Any, accent: str = _BORDER_BRIGHT, **kwargs: Any) -> None:
        """Initialise a GlassCard frame.

        Args:
            parent: Parent widget.
            accent: Border colour (defaults to subtle bright border).
            **kwargs: Extra keyword arguments forwarded to CTkFrame.
        """
        super().__init__(
            parent,
            fg_color=_BG_CARD,
            corner_radius=_CORNER,
            border_width=1,
            border_color=accent,
            **kwargs,
        )


class SectionLabel(ctk.CTkLabel):
    """Small neon-coloured section header label."""

    def __init__(self, parent: Any, text: str, color: str = _NEON_BLUE, **kwargs: Any) -> None:
        """Initialise a SectionLabel.

        Args:
            parent: Parent widget.
            text: Label text (uppercased automatically).
            color: Neon accent colour for this label.
            **kwargs: Extra keyword arguments forwarded to CTkLabel.
        """
        super().__init__(
            parent,
            text=text.upper(),
            font=("Segoe UI", 9, "bold"),
            text_color=color,
            **kwargs,
        )


class PathRow(ctk.CTkFrame):
    """A labelled path input row with a Browse button."""

    def __init__(
        self,
        parent: Any,
        label: str,
        variable: ctk.StringVar,
        mode: str = "folder",
        filetypes: list[tuple[str, str]] | None = None,
        placeholder: str = "",
        browse_label: str = "Browse",
    ) -> None:
        """Initialise a PathRow.

        Args:
            parent: Parent widget.
            label: Field label text.
            variable: StringVar bound to the entry.
            mode: One of 'folder', 'open', or 'save'.
            filetypes: File type filters for 'open' / 'save' dialogs.
            placeholder: Placeholder text for the entry.
            browse_label: Button label (supports i18n).
        """
        super().__init__(parent, fg_color="transparent")
        self._var: ctk.StringVar = variable
        self._mode: str = mode
        self._filetypes: list[tuple[str, str]] | None = filetypes

        ctk.CTkLabel(self, text=label, font=_FONT_LABEL, text_color=_TEXT_SECONDARY).pack(anchor="w", pady=(0, 3))

        row: ctk.CTkFrame = ctk.CTkFrame(self, fg_color="transparent")
        row.pack(fill="x")
        row.columnconfigure(0, weight=1)

        ctk.CTkEntry(
            row,
            textvariable=variable,
            placeholder_text=placeholder,
            fg_color=_BG_INPUT,
            border_color=_BORDER_BRIGHT,
            corner_radius=8,
            font=_FONT_UI,
            text_color=_TEXT_PRIMARY,
        ).grid(row=0, column=0, sticky="ew", padx=(0, 8))

        ctk.CTkButton(
            row,
            text=browse_label,
            width=86,
            corner_radius=8,
            fg_color=_BG_PANEL,
            hover_color=_BORDER_BRIGHT,
            border_width=1,
            border_color=_BORDER_BRIGHT,
            font=_FONT_LABEL,
            text_color=_TEXT_SECONDARY,
            command=self._browse,
        ).grid(row=0, column=1)

    def _browse(self) -> None:
        """Open the appropriate dialog based on the mode setting."""
        if self._mode == "folder":
            _browse_folder(self._var)
        elif self._mode == "open":
            _browse_file(self._var, self._filetypes)
        elif self._mode == "save":
            _browse_save(self._var, self._filetypes)
        else:
            raise ValueError(f"Unsupported PathRow mode: {self._mode!r}")


class LogPane(ctk.CTkFrame):
    """Scrollable monospace log output pane."""

    def __init__(self, parent: Any, **kwargs: Any) -> None:
        """Initialise a LogPane.

        Args:
            parent: Parent widget.
            **kwargs: Extra keyword arguments forwarded to CTkFrame.
        """
        kwargs.setdefault("height", 240)
        super().__init__(
            parent,
            fg_color=_BG_INPUT,
            corner_radius=10,
            border_width=1,
            border_color=_BORDER_BRIGHT,
            **kwargs,
        )
        self._text: ctk.CTkTextbox = ctk.CTkTextbox(
            self,
            font=_FONT_MONO,
            fg_color="transparent",
            text_color=_TEXT_PRIMARY,
            wrap="none",
            state="disabled",
        )
        self._text.pack(fill="both", expand=True, padx=6, pady=6)

    def clear(self) -> None:
        """Remove all content from the log pane."""
        self._text.configure(state="normal")
        self._text.delete("0.0", "end")
        self._text.configure(state="disabled")

    def append(self, text: str, tag: str = "") -> None:
        """Append a line of text to the log.

        Args:
            text: Text to append.
            tag: Colour tag ('error', 'warning', 'success', 'muted').
        """
        self._text.configure(state="normal")
        self._text.insert("end", text + "\n")
        self._text.configure(state="disabled")
        self._text.see("end")

    def get_text(self) -> str:
        """Return the full text content of the log pane."""
        return self._text.get("1.0", "end-1c")


class NeonButton(ctk.CTkButton):
    """Primary action button with configurable neon colour."""

    def __init__(self, parent: Any, text: str, command: Any, color: str = _NEON_BLUE, **kwargs: Any) -> None:
        """Initialise a NeonButton.

        Args:
            parent: Parent widget.
            text: Button label.
            command: Click callback.
            color: Neon accent colour for this button.
            **kwargs: Extra keyword arguments forwarded to CTkButton.
        """
        # Derive a darker hover shade by slightly dimming the colour
        super().__init__(
            parent,
            text=text,
            command=command,
            fg_color=color,
            hover_color=_dim_hex_color(color),
            corner_radius=10,
            font=("Segoe UI", 13, "bold"),
            text_color=_BG_DEEP,
            height=40,
            **kwargs,
        )
        self._neon_color: str = color

    def set_label(self, text: str) -> None:
        """Update the button label text.

        Args:
            text: New label.
        """
        self.configure(text=text)


class OptionRow(ctk.CTkFrame):
    """A labelled option menu row."""

    def __init__(
        self,
        parent: Any,
        label: str,
        variable: ctk.StringVar,
        values: list[str],
        accent: str = _NEON_BLUE,
    ) -> None:
        """Initialise an OptionRow.

        Args:
            parent: Parent widget.
            label: Field label text.
            variable: StringVar bound to the option menu.
            values: Available option values.
            accent: Accent colour for the button.
        """
        super().__init__(parent, fg_color="transparent")
        ctk.CTkLabel(self, text=label, font=_FONT_LABEL, text_color=_TEXT_SECONDARY).pack(anchor="w", pady=(0, 3))
        ctk.CTkOptionMenu(
            self,
            variable=variable,
            values=values,
            fg_color=_BG_INPUT,
            button_color=accent,
            button_hover_color=accent,
            dropdown_fg_color=_BG_CARD,
            dropdown_hover_color=_BORDER_BRIGHT,
            corner_radius=8,
            font=_FONT_UI,
            text_color=_TEXT_PRIMARY,
        ).pack(fill="x")


class NeonCheckbox(ctk.CTkCheckBox):
    """Checkbox with a neon accent colour."""

    def __init__(
        self,
        parent: Any,
        text: str,
        variable: ctk.BooleanVar,
        accent: str = _NEON_BLUE,
        **kwargs: Any,
    ) -> None:
        """Initialise a NeonCheckbox.

        Args:
            parent: Parent widget.
            text: Label text beside the checkbox.
            variable: BooleanVar to bind.
            accent: Neon colour for the checkbox fill.
            **kwargs: Extra keyword arguments forwarded to CTkCheckBox.
        """
        super().__init__(
            parent,
            text=text,
            variable=variable,
            font=_FONT_LABEL,
            text_color=_TEXT_SECONDARY,
            fg_color=accent,
            hover_color=accent,
            border_color=_BORDER_BRIGHT,
            checkmark_color=_BG_DEEP,
            **kwargs,
        )


# ---------------------------------------------------------------------------
# Sidebar navigation button
# ---------------------------------------------------------------------------


class NavButton(ctk.CTkButton):
    """Sidebar navigation button with per-panel neon accent on active state."""

    def __init__(self, parent: Any, text: str, command: Any, accent: str = _NEON_BLUE, **kwargs: Any) -> None:
        """Initialise a NavButton.

        Args:
            parent: Parent widget.
            text: Button label.
            command: Click callback.
            accent: Neon colour shown when this button is active.
            **kwargs: Extra keyword arguments forwarded to CTkButton.
        """
        super().__init__(
            parent,
            text=text,
            command=command,
            anchor="w",
            fg_color="transparent",
            hover_color="#0D1828",
            text_color=_TEXT_MUTED,
            corner_radius=10,
            font=_FONT_UI,
            height=42,
            **kwargs,
        )
        self._accent: str = accent

    def set_active(self, active: bool) -> None:
        """Update visual state to reflect selection.

        Args:
            active: True to apply the neon active style, False for inactive.
        """
        if active:
            self.configure(
                fg_color=_BG_CARD,
                text_color=self._accent,
                border_width=1,
                border_color=self._accent,
            )
        else:
            self.configure(fg_color="transparent", text_color=_TEXT_MUTED, border_width=0)
