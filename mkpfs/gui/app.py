from pathlib import Path
from typing import ClassVar

import customtkinter as ctk
from PIL import Image, ImageTk

from .i18n import _LANG_NAMES, set_locale, tr
from .panels import (
    BasePanel,
    ExfatPanel,
    InspectPanel,
    PackFilePanel,
    PackFolderPanel,
    TreePanel,
    UnpackPanel,
    VerifyPanel,
)
from .theme import (
    _BG_CARD,
    _BG_DEEP,
    _BG_INPUT,
    _BG_PANEL,
    _BORDER_BRIGHT,
    _FONT_LABEL,
    _NEON_AMBER,
    _NEON_BLUE,
    _NEON_CYAN,
    _NEON_GREEN,
    _NEON_ORANGE,
    _NEON_PINK,
    _NEON_PURPLE,
    _SIDEBAR_W,
    _TEXT_MUTED,
    _TEXT_PRIMARY,
)
from .widgets import NavButton

# ---------------------------------------------------------------------------
# Theme - neon palette
# ---------------------------------------------------------------------------

ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")


# ---------------------------------------------------------------------------
# Main application window
# ---------------------------------------------------------------------------


class MkPFSApp(ctk.CTk):
    """Main application window with neon sidebar and language selector."""

    _PAGES: ClassVar[list[tuple[str, str, type, str]]] = [
        ("nav_pack_folder", "nav_pack_folder", PackFolderPanel, _NEON_BLUE),
        ("nav_pack_exfat", "nav_pack_exfat", ExfatPanel, _NEON_ORANGE),
        ("nav_pack_file", "nav_pack_file", PackFilePanel, _NEON_CYAN),
        ("nav_verify", "nav_verify", VerifyPanel, _NEON_GREEN),
        ("nav_inspect", "nav_inspect", InspectPanel, _NEON_PURPLE),
        ("nav_tree", "nav_tree", TreePanel, _NEON_AMBER),
        ("nav_unpack", "nav_unpack", UnpackPanel, _NEON_PINK),
    ]

    def __init__(self) -> None:
        """Initialise and configure the application window."""
        super().__init__()
        self.title("MkPFS")
        self.geometry("1120x780")
        self.minsize(900, 620)
        self.configure(fg_color=_BG_DEEP)

        self._panels: dict[str, BasePanel] = {}
        self._nav_buttons: dict[str, NavButton] = {}
        self._active_key: str = ""

        self._set_window_icon()
        self._build_sidebar()
        self._build_content()
        self._select(self._PAGES[0][0])

    def _set_window_icon(self) -> None:
        """Load icon.png from assets/images/ and apply it to the window.

        Tries multiple candidate paths so the icon loads whether the app is
        launched from the repo root, the mkpfs package directory, or as an
        installed entry point.
        """
        candidates: list[Path] = [
            Path(__file__).parent.parent / "assets" / "images" / "icon.png",
            Path(__file__).parent / ".." / "assets" / "images" / "icon.png",
            Path.cwd() / "assets" / "images" / "icon.png",
        ]
        icon_path: Path | None = next((p.resolve() for p in candidates if p.exists()), None)
        if icon_path is None:
            return
        try:
            img: Image.Image = Image.open(icon_path).convert("RGBA").resize((32, 32), Image.LANCZOS)
            photo: ImageTk.PhotoImage = ImageTk.PhotoImage(img)
            self.wm_iconphoto(True, photo)
            # Keep a reference so the image is not garbage-collected by Python
            self._icon_ref: ImageTk.PhotoImage = photo
        except (OSError, ValueError, RuntimeError):
            # Icon setup is optional; ignore expected failures (file missing or unreadable).
            return

    def _build_sidebar(self) -> None:
        """Build the left navigation sidebar with language selector."""
        sidebar: ctk.CTkFrame = ctk.CTkFrame(
            self,
            width=_SIDEBAR_W,
            fg_color=_BG_PANEL,
            corner_radius=0,
            border_width=1,
            border_color=_BORDER_BRIGHT,
        )
        sidebar.pack(side="left", fill="y")
        sidebar.pack_propagate(False)

        brand: ctk.CTkFrame = ctk.CTkFrame(sidebar, fg_color="transparent", height=74)
        brand.pack(fill="x", padx=16, pady=(18, 4))
        brand.pack_propagate(False)
        ctk.CTkLabel(brand, text="MkPFS", font=("Segoe UI", 22, "bold"), text_color=_NEON_BLUE).pack(anchor="w")
        self._subtitle_label: ctk.CTkLabel = ctk.CTkLabel(
            brand,
            text=tr("app_subtitle"),
            font=("Segoe UI", 9),
            text_color=_TEXT_MUTED,
        )
        self._subtitle_label.pack(anchor="w")

        ctk.CTkFrame(sidebar, height=1, fg_color=_NEON_BLUE).pack(fill="x", padx=10, pady=(8, 14))

        self._ops_label: ctk.CTkLabel = ctk.CTkLabel(
            sidebar,
            text=tr("operations"),
            font=("Segoe UI", 9, "bold"),
            text_color=_TEXT_MUTED,
        )
        self._ops_label.pack(anchor="w", padx=16, pady=(0, 6))

        for key, label_key, _, accent in self._PAGES:
            btn: NavButton = NavButton(
                sidebar,
                text=tr(label_key),
                command=lambda k=key: self._select(k),
                accent=accent,
            )
            btn.pack(fill="x", padx=10, pady=2)
            self._nav_buttons[key] = btn

        ctk.CTkFrame(sidebar, height=1, fg_color=_BORDER_BRIGHT).pack(fill="x", padx=10, pady=(14, 8))

        lang_frame: ctk.CTkFrame = ctk.CTkFrame(sidebar, fg_color="transparent")
        lang_frame.pack(fill="x", padx=12, pady=(0, 6))
        self._lang_label_widget: ctk.CTkLabel = ctk.CTkLabel(
            lang_frame,
            text=tr("lang_label"),
            font=("Segoe UI", 9, "bold"),
            text_color=_TEXT_MUTED,
        )
        self._lang_label_widget.pack(anchor="w", pady=(0, 4))

        self._lang_var: ctk.StringVar = ctk.StringVar(value=_LANG_NAMES["en"])
        ctk.CTkOptionMenu(
            lang_frame,
            variable=self._lang_var,
            values=list(_LANG_NAMES.values()),
            fg_color=_BG_INPUT,
            button_color=_NEON_BLUE,
            button_hover_color=_NEON_BLUE,
            dropdown_fg_color=_BG_CARD,
            dropdown_hover_color=_BORDER_BRIGHT,
            corner_radius=8,
            font=_FONT_LABEL,
            text_color=_TEXT_PRIMARY,
            command=self._on_lang_change,
        ).pack(fill="x")

        self._ver_label: ctk.CTkLabel = ctk.CTkLabel(
            sidebar,
            text=tr("version_footer"),
            font=("Segoe UI", 9),
            text_color=_TEXT_MUTED,
        )
        self._ver_label.pack(side="bottom", pady=12)

    def _build_content(self) -> None:
        """Pre-instantiate all panels inside the content area."""
        self._content: ctk.CTkFrame = ctk.CTkFrame(self, fg_color="transparent")
        self._content.pack(side="left", fill="both", expand=True)
        for key, _, PanelClass, _ in self._PAGES:
            panel: BasePanel = PanelClass(self._content)
            self._panels[key] = panel

    def _select(self, key: str) -> None:
        """Switch the visible panel.

        Args:
            key: Navigation key matching one of the _PAGES entries.
        """
        if key == self._active_key:
            return
        if self._active_key and self._active_key in self._panels:
            self._panels[self._active_key].pack_forget()
            self._nav_buttons[self._active_key].set_active(False)
        self._active_key = key
        self._panels[key].pack(fill="both", expand=True)
        self._nav_buttons[key].set_active(True)

    def _on_lang_change(self, display_name: str) -> None:
        """Handle language selection from the dropdown.

        Args:
            display_name: Human-readable language name chosen by the user.
        """
        for locale, name in _LANG_NAMES.items():
            if name == display_name:
                set_locale(locale)
                break
        self._refresh_all_labels()

    def _refresh_all_labels(self) -> None:
        """Propagate the new locale to all sidebar widgets and panels."""
        self._subtitle_label.configure(text=tr("app_subtitle"))
        self._ops_label.configure(text=tr("operations"))
        self._lang_label_widget.configure(text=tr("lang_label"))
        self._ver_label.configure(text=tr("version_footer"))
        for key, label_key, _, _ in self._PAGES:
            self._nav_buttons[key].configure(text=tr(label_key))
        for panel in self._panels.values():
            panel.refresh_labels()


def main() -> None:
    """Launch the MkPFS graphical user interface."""
    app: MkPFSApp = MkPFSApp()
    app.mainloop()


if __name__ == "__main__":
    # freeze_support() is required when running as a PyInstaller --onefile
    # executable on Windows. Without it, each multiprocessing.Pool worker
    # spawned by pfs.py re-imports __main__, opening a new GUI window.
    import multiprocessing

    multiprocessing.freeze_support()
    main()
