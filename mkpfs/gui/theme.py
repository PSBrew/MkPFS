"""Neon glassmorphism theme constants for the mkpfs GUI."""

# Backgrounds — deep space
_BG_DEEP = "#05080F"
_BG_PANEL = "#0A0F1C"
_BG_CARD = "#0E1828"
_BG_INPUT = "#07101E"
_BORDER_BRIGHT = "#1E3A5F"

# Text
_TEXT_PRIMARY = "#E8F4FF"
_TEXT_SECONDARY = "#8BA8C4"
_TEXT_MUTED = "#344A62"

# Neon accents — each panel / element gets its own hue
_NEON_BLUE = "#00C8FF"  # primary brand, sidebar logo, Pack Folder
_NEON_CYAN = "#00FFD4"  # Pack File
_NEON_GREEN = "#39FF8A"  # Verify, success messages
_NEON_PURPLE = "#B560FF"  # Inspect
_NEON_AMBER = "#FFB800"  # Tree, warnings
_NEON_PINK = "#FF5CAA"  # Unpack

# Semantic
_SUCCESS = _NEON_GREEN
_ERROR = "#FF3B5C"
_WARNING = _NEON_AMBER

# UI constants
_SIDEBAR_W: int = 210
_CORNER: int = 14
_FONT_MONO = ("Consolas", 12)
_FONT_UI = ("Segoe UI", 13)
_FONT_LABEL = ("Segoe UI", 11)
_FONT_SMALL = ("Segoe UI", 10)


# ---------------------------------------------------------------------------
# Per-panel accent colours (used for headers + progress bars)
# ---------------------------------------------------------------------------

_PANEL_ACCENT: dict[str, str] = {
    "pack_folder": _NEON_BLUE,
    "pack_file": _NEON_CYAN,
    "verify": _NEON_GREEN,
    "inspect": _NEON_PURPLE,
    "tree": _NEON_AMBER,
    "unpack": _NEON_PINK,
}
