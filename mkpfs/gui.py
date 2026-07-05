"""Graphical user interface for mkpfs - futuristic neon glassmorphism design."""

from __future__ import annotations

import argparse
import builtins
import contextlib
import io
import queue
import threading
from dataclasses import dataclass, field
from pathlib import Path
from tkinter import filedialog
from typing import Any, Callable

import customtkinter as ctk
from PIL import Image, ImageTk

# ---------------------------------------------------------------------------
# Internationalisation
# ---------------------------------------------------------------------------

_TRANSLATIONS: dict[str, dict[str, str]] = {
    "en": {
        # App chrome
        "app_subtitle": "PlayStation File System",
        "lang_label": "Language",
        "operations": "OPERATIONS",
        "version_footer": "v{version}",
        # Nav labels
        "nav_pack_folder": "📦  Pack Folder",
        "nav_pack_file": "📄  Pack File",
        "nav_verify": "✅  Verify",
        "nav_inspect": "🔍  Inspect",
        "nav_tree": "🌲  Tree",
        "nav_unpack": "📂  Unpack",
        # Common
        "paths": "Paths",
        "options": "Options",
        "encryption": "Encryption",
        "output_log": "Output Log",
        "export_log": "Export Log",
        "run": "Run",
        "running": "Running…",
        "browse": "Browse",
        "ok": "✓ Completed successfully.",
        "err_process": "✗ Process exited with code {}.",
        "err_not_found": "✗ mkpfs not found. Is the virtual environment active?",
        "err_unexpected": "[ERROR] Unexpected: {}",
        # Pack Folder
        "pf_title": "Pack Folder",
        "pf_subtitle": "Build a PFS image from a source directory",
        "pf_src_label": "Source Folder",
        "pf_src_ph": "Select source folder…",
        "pf_out_label": "Output Image",
        "pf_out_ph": "Select output path…",
        "pf_version": "Version",
        "pf_compress": "PFSC Compression",
        "pf_signed": "Signed Image",
        "pf_verify": "Verify After Pack",
        "pf_dry": "Dry Run",
        "pf_temp": "Temp Folder (optional)",
        "pf_temp_ph": "Custom temp folder…",
        "pkf_temp": "Temp Folder (optional)",
        "pkf_temp_ph": "Custom temp folder…",
        "pf_err_src": "✗ Source folder is required.",
        "pf_err_out": "✗ Output image path is required.",
        # Pack File
        "pkf_title": "Pack File",
        "pkf_subtitle": "Wrap a single file into a PFSC compressed image",
        "pkf_src_label": "Source File",
        "pkf_src_ph": "Select source file…",
        "pkf_out_label": "Output Image",
        "pkf_out_ph": "Select output path…",
        "pkf_version": "Version",
        "pkf_compress": "PFSC Compression",
        "pkf_err": "✗ Source file and output path are required.",
        # Verify
        "v_title": "Verify",
        "v_subtitle": "Validate image structure, inodes, and payload checksums",
        "v_image_label": "PFS Image",
        "v_image_ph": "Select .ffpfs image…",
        "v_source_label": "Source Folder (optional — payload comparison)",
        "v_source_ph": "Optional source folder…",
        "v_hashes": "Expected Hashes (optional)",
        "v_crc32": "Expected CRC32 (hex)",
        "v_crc32_ph": "e.g. 7F528D1F",
        "v_sha256": "Expected SHA256 (64 hex)",
        "v_sha256_ph": "64 hex chars…",
        "v_ekpfs": "EKPFS Key (64 hex, optional)",
        "v_ekpfs_ph": "64 hex chars…",
        "v_newcrypt": "Use newCrypt EKPFS derivation",
        "v_err": "✗ Image path is required.",
        # Inspect
        "i_title": "Inspect",
        "i_subtitle": "View image metadata, version, block size, and warnings",
        "i_image_label": "PFS Image",
        "i_image_ph": "Select .ffpfs image…",
        "i_format": "Output Format",
        "i_ekpfs": "EKPFS Key (optional)",
        "i_ekpfs_ph": "64 hex chars…",
        "i_err": "✗ Image path is required.",
        # Tree
        "t_title": "Tree",
        "t_subtitle": "Browse the directory tree embedded in a PFS image",
        "t_image_label": "PFS Image",
        "t_image_ph": "Select .ffpfs image…",
        "t_ekpfs": "EKPFS Key (optional)",
        "t_ekpfs_ph": "64 hex chars…",
        "t_newcrypt": "Use newCrypt EKPFS derivation",
        "t_err": "✗ Image path is required.",
        # Unpack
        "u_title": "Unpack",
        "u_subtitle": "Extract all files from a PFS image to a destination folder",
        "u_image_label": "PFS Image",
        "u_image_ph": "Select .ffpfs image…",
        "u_out_label": "Output Folder",
        "u_out_ph": "Destination folder…",
        "u_overwrite": "Overwrite existing output folder",
        "u_ekpfs": "EKPFS Key (optional)",
        "u_ekpfs_ph": "64 hex chars…",
        "u_newcrypt": "Use newCrypt EKPFS derivation",
        "u_err": "✗ Image and output folder are both required.",
        "u_auto_subdir": "→ Output subfolder: {}",
    },
    "pt_BR": {
        "app_subtitle": "Sistema de Arquivos PlayStation",
        "lang_label": "Idioma",
        "operations": "OPERAÇÕES",
        "version_footer": "v{version}",
        "nav_pack_folder": "📦  Empacotar Pasta",
        "nav_pack_file": "📄  Empacotar Arquivo",
        "nav_verify": "✅  Verificar",
        "nav_inspect": "🔍  Inspecionar",
        "nav_tree": "🌲  Árvore",
        "nav_unpack": "📂  Desempacotar",
        "paths": "Caminhos",
        "options": "Opções",
        "encryption": "Criptografia",
        "output_log": "Log de Saída",
        "export_log": "Exportar Log",
        "run": "Executar",
        "running": "Executando…",
        "browse": "Procurar",
        "ok": "✓ Concluído com sucesso.",
        "err_process": "✗ Processo encerrado com código {}.",
        "err_not_found": "✗ mkpfs não encontrado. O ambiente virtual está ativo?",
        "err_unexpected": "[ERRO] Inesperado: {}",
        "pf_title": "Empacotar Pasta",
        "pf_subtitle": "Construir uma imagem PFS a partir de um diretório fonte",
        "pf_src_label": "Pasta Fonte",
        "pf_src_ph": "Selecione a pasta fonte…",
        "pf_out_label": "Imagem de Saída",
        "pf_out_ph": "Selecione o caminho de saída…",
        "pf_version": "Versão",
        "pf_compress": "Compressão PFSC",
        "pf_signed": "Imagem Assinada",
        "pf_verify": "Verificar Após Empacotar",
        "pf_dry": "Simulação (Dry Run)",
        "pf_temp": "Pasta Temporária (opcional)",
        "pf_temp_ph": "Pasta temp personalizada…",
        "pkf_temp": "Pasta Temporária (opcional)",
        "pkf_temp_ph": "Pasta temp personalizada…",
        "pf_err_src": "✗ A pasta fonte é obrigatória.",
        "pf_err_out": "✗ O caminho de saída é obrigatório.",
        "pkf_title": "Empacotar Arquivo",
        "pkf_subtitle": "Encapsular um único arquivo em uma imagem PFSC comprimida",
        "pkf_src_label": "Arquivo Fonte",
        "pkf_src_ph": "Selecione o arquivo fonte…",
        "pkf_out_label": "Imagem de Saída",
        "pkf_out_ph": "Selecione o caminho de saída…",
        "pkf_version": "Versão",
        "pkf_compress": "Compressão PFSC",
        "pkf_err": "✗ Arquivo fonte e caminho de saída são obrigatórios.",
        "v_title": "Verificar",
        "v_subtitle": "Validar estrutura da imagem, inodes e checksums",
        "v_image_label": "Imagem PFS",
        "v_image_ph": "Selecione a imagem .ffpfs…",
        "v_source_label": "Pasta Fonte (opcional — comparação de payload)",
        "v_source_ph": "Pasta fonte opcional…",
        "v_hashes": "Hashes Esperados (opcional)",
        "v_crc32": "CRC32 Esperado (hex)",
        "v_crc32_ph": "ex: 7F528D1F",
        "v_sha256": "SHA256 Esperado (64 hex)",
        "v_sha256_ph": "64 caracteres hex…",
        "v_ekpfs": "Chave EKPFS (64 hex, opcional)",
        "v_ekpfs_ph": "64 caracteres hex…",
        "v_newcrypt": "Usar derivação newCrypt EKPFS",
        "v_err": "✗ O caminho da imagem é obrigatório.",
        "i_title": "Inspecionar",
        "i_subtitle": "Ver metadados, versão, tamanho de bloco e avisos da imagem",
        "i_image_label": "Imagem PFS",
        "i_image_ph": "Selecione a imagem .ffpfs…",
        "i_format": "Formato de Saída",
        "i_ekpfs": "Chave EKPFS (opcional)",
        "i_ekpfs_ph": "64 caracteres hex…",
        "i_err": "✗ O caminho da imagem é obrigatório.",
        "t_title": "Árvore",
        "t_subtitle": "Navegar pela árvore de diretórios embutida na imagem PFS",
        "t_image_label": "Imagem PFS",
        "t_image_ph": "Selecione a imagem .ffpfs…",
        "t_ekpfs": "Chave EKPFS (opcional)",
        "t_ekpfs_ph": "64 caracteres hex…",
        "t_newcrypt": "Usar derivação newCrypt EKPFS",
        "t_err": "✗ O caminho da imagem é obrigatório.",
        "u_title": "Desempacotar",
        "u_subtitle": "Extrair todos os arquivos de uma imagem PFS para uma pasta",
        "u_image_label": "Imagem PFS",
        "u_image_ph": "Selecione a imagem .ffpfs…",
        "u_out_label": "Pasta de Destino",
        "u_out_ph": "Pasta de destino…",
        "u_overwrite": "Sobrescrever pasta de saída existente",
        "u_ekpfs": "Chave EKPFS (opcional)",
        "u_ekpfs_ph": "64 caracteres hex…",
        "u_newcrypt": "Usar derivação newCrypt EKPFS",
        "u_err": "✗ Imagem e pasta de destino são obrigatórios.",
        "u_auto_subdir": "→ Subpasta de saída: {}",
    },
    "es": {
        "app_subtitle": "Sistema de Archivos PlayStation",
        "lang_label": "Idioma",
        "operations": "OPERACIONES",
        "version_footer": "v{version}",
        "nav_pack_folder": "📦  Empaquetar Carpeta",
        "nav_pack_file": "📄  Empaquetar Archivo",
        "nav_verify": "✅  Verificar",
        "nav_inspect": "🔍  Inspeccionar",
        "nav_tree": "🌲  Árbol",
        "nav_unpack": "📂  Desempaquetar",
        "paths": "Rutas",
        "options": "Opciones",
        "encryption": "Cifrado",
        "output_log": "Registro de Salida",
        "export_log": "Exportar Registro",
        "run": "Ejecutar",
        "running": "Ejecutando…",
        "browse": "Buscar",
        "ok": "✓ Completado con éxito.",
        "err_process": "✗ El proceso terminó con código {}.",
        "err_not_found": "✗ mkpfs no encontrado. ¿El entorno virtual está activo?",
        "err_unexpected": "[ERROR] Inesperado: {}",
        "pf_title": "Empaquetar Carpeta",
        "pf_subtitle": "Construir una imagen PFS desde un directorio fuente",
        "pf_src_label": "Carpeta Fuente",
        "pf_src_ph": "Seleccionar carpeta fuente…",
        "pf_out_label": "Imagen de Salida",
        "pf_out_ph": "Seleccionar ruta de salida…",
        "pf_version": "Versión",
        "pf_compress": "Compresión PFSC",
        "pf_signed": "Imagen Firmada",
        "pf_verify": "Verificar Tras Empaquetar",
        "pf_dry": "Simulación (Dry Run)",
        "pf_temp": "Carpeta Temporal (opcional)",
        "pf_temp_ph": "Carpeta temp personalizada…",
        "pkf_temp": "Carpeta Temporal (opcional)",
        "pkf_temp_ph": "Carpeta temp personalizada…",
        "pf_err_src": "✗ La carpeta fuente es obligatoria.",
        "pf_err_out": "✗ La ruta de salida es obligatoria.",
        "pkf_title": "Empaquetar Archivo",
        "pkf_subtitle": "Envolver un solo archivo en una imagen PFSC comprimida",
        "pkf_src_label": "Archivo Fuente",
        "pkf_src_ph": "Seleccionar archivo fuente…",
        "pkf_out_label": "Imagen de Salida",
        "pkf_out_ph": "Seleccionar ruta de salida…",
        "pkf_version": "Versión",
        "pkf_compress": "Compresión PFSC",
        "pkf_err": "✗ El archivo fuente y la ruta de salida son obligatorios.",
        "v_title": "Verificar",
        "v_subtitle": "Validar estructura de imagen, inodes y checksums de payload",
        "v_image_label": "Imagen PFS",
        "v_image_ph": "Seleccionar imagen .ffpfs…",
        "v_source_label": "Carpeta Fuente (opcional — comparación de payload)",
        "v_source_ph": "Carpeta fuente opcional…",
        "v_hashes": "Hashes Esperados (opcional)",
        "v_crc32": "CRC32 Esperado (hex)",
        "v_crc32_ph": "ej: 7F528D1F",
        "v_sha256": "SHA256 Esperado (64 hex)",
        "v_sha256_ph": "64 caracteres hex…",
        "v_ekpfs": "Clave EKPFS (64 hex, opcional)",
        "v_ekpfs_ph": "64 caracteres hex…",
        "v_newcrypt": "Usar derivación newCrypt EKPFS",
        "v_err": "✗ La ruta de imagen es obligatoria.",
        "i_title": "Inspeccionar",
        "i_subtitle": "Ver metadatos, versión, tamaño de bloque y advertencias",
        "i_image_label": "Imagen PFS",
        "i_image_ph": "Seleccionar imagen .ffpfs…",
        "i_format": "Formato de Salida",
        "i_ekpfs": "Clave EKPFS (opcional)",
        "i_ekpfs_ph": "64 caracteres hex…",
        "i_err": "✗ La ruta de imagen es obligatoria.",
        "t_title": "Árbol",
        "t_subtitle": "Explorar el árbol de directorios embebido en una imagen PFS",
        "t_image_label": "Imagen PFS",
        "t_image_ph": "Seleccionar imagen .ffpfs…",
        "t_ekpfs": "Clave EKPFS (opcional)",
        "t_ekpfs_ph": "64 caracteres hex…",
        "t_newcrypt": "Usar derivación newCrypt EKPFS",
        "t_err": "✗ La ruta de imagen es obligatoria.",
        "u_title": "Desempaquetar",
        "u_subtitle": "Extraer todos los archivos de una imagen PFS a una carpeta",
        "u_image_label": "Imagen PFS",
        "u_image_ph": "Seleccionar imagen .ffpfs…",
        "u_out_label": "Carpeta de Destino",
        "u_out_ph": "Carpeta de destino…",
        "u_overwrite": "Sobrescribir carpeta de salida existente",
        "u_ekpfs": "Clave EKPFS (opcional)",
        "u_ekpfs_ph": "64 caracteres hex…",
        "u_newcrypt": "Usar derivación newCrypt EKPFS",
        "u_err": "✗ La imagen y la carpeta de destino son obligatorias.",
        "u_auto_subdir": "→ Subcarpeta de salida: {}",
    },
}

_LANG_NAMES: dict[str, str] = {
    "en": "English",
    "pt_BR": "Português (BR)",
    "es": "Español",
}

# Active locale — updated by the language selector
_current_locale: str = "en"


def tr(key: str) -> str:
    """Return the translated string for the given key in the active locale.

    Args:
        key: Translation dictionary key.

    Returns:
        Translated string, falling back to English when the key is missing.
    """
    from mkpfs import __version__

    lang: dict[str, str] = _TRANSLATIONS.get(_current_locale, _TRANSLATIONS["en"])
    value: str = lang.get(key, _TRANSLATIONS["en"].get(key, key))
    return value.replace("{version}", __version__)


# ---------------------------------------------------------------------------
# Theme - neon palette
# ---------------------------------------------------------------------------

ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")

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


# ---------------------------------------------------------------------------
# Utility helpers
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
        else:
            _browse_save(self._var, self._filetypes)


class LogPane(ctk.CTkFrame):
    """Scrollable monospace log output pane."""

    def __init__(self, parent: Any, **kwargs: Any) -> None:
        """Initialise a LogPane.

        Args:
            parent: Parent widget.
            **kwargs: Extra keyword arguments forwarded to CTkFrame.
        """
        # No explicit height — pack(expand=True) distribution handles sizing.
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

        self._text._textbox.tag_config("error", foreground=_ERROR)
        self._text._textbox.tag_config("warning", foreground=_WARNING)
        self._text._textbox.tag_config("success", foreground=_SUCCESS)
        self._text._textbox.tag_config("muted", foreground=_TEXT_MUTED)

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
        if tag:
            self._text._textbox.insert("end", text + "\n", tag)
        else:
            self._text.insert("end", text + "\n")
        self._text.configure(state="disabled")
        self._text.see("end")

    def get_text(self) -> str:
        """Return the full text content of the log pane."""
        return self._text._textbox.get("1.0", "end-1c")


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
            hover_color=color,
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
# Argparse option metadata extraction
# ---------------------------------------------------------------------------

# Key for 'pack folder' and 'pack file' subcommands.  The root parser uses
# 'command' and 'pack_command' to mirror argparse's nested subparser dests.
_PACK_SUBKEY: dict[str, str] = {
    "pack folder": "pack.folder",
    "pack file": "pack.file",
    "pack exfat": "pack.exfat",
}


@dataclass
class ArgOption:
    """Normalised representation of a single CLI argument for the form builder."""

    dest: str
    """Argparse dest (e.g. 'source_dir', 'no_compress')."""
    flags: list[str] = field(default_factory=list)
    """CLI flag strings (e.g. ['--source-dir'], ['--compress','--no-compress'])."""
    flag_str: str = ""
    """Primary flag for argv construction (e.g. '--no-compress', '--version')."""
    help: str = ""
    """Help text from argparse."""
    required: bool = False
    """Whether this argument is required."""
    kind: str = "text"
    """Widget hint: 'text', 'bool', 'choice', 'path-folder', 'path-open',
    'path-save', 'append'."""
    default: Any = None
    """Default value (str, bool, int, or None)."""
    choices: list[str] | None = None
    """Allowed values for choice/enum arguments."""
    group: str = ""
    """Logical section label for grouping related controls (e.g. 'paths', 'options')."""
    positional: bool = False
    """True for positional arguments that appear first."""
    negate_flag: str = ""
    """For store_true flags: the flag that disables (e.g. '--no-compress' when
    default is True). Used to present a checkbox that defaults to on."""
    int_type: bool = False
    """True for int-typed arguments; entry validates as numeric."""


# Accent palette per top-level subcommand (static map + dynamic fallback).
_DYNAMIC_ACCENTS: dict[str, str] = {
    "pack": _NEON_BLUE,
    "verify": _NEON_GREEN,
    "inspect": _NEON_PURPLE,
    "tree": _NEON_AMBER,
    "unpack": _NEON_PINK,
}

# Fallback accent colour when a subcommand isn't in the map.
_DEFAULT_DYNAMIC_ACCENT: str = _NEON_BLUE


# Expanded accent palette for nested pack subcommands.
_DYNAMIC_ACCENTS_PACK: dict[str, str] = {
    "pack.folder": _NEON_BLUE,
    "pack.file": _NEON_CYAN,
    "pack.exfat": _NEON_BLUE,
}


def _accent_for_cmd_path(cmd_path: str) -> str:
    """Resolve the neon accent for a (possibly nested) command path.

    Args:
        cmd_path: Dot-joined command path, e.g. ``"pack.folder"`` or ``"tree"``.

    Returns:
        Hex colour string.
    """
    if cmd_path in _DYNAMIC_ACCENTS_PACK:
        return _DYNAMIC_ACCENTS_PACK[cmd_path]
    top: str = cmd_path.split(".")[0]
    return _DYNAMIC_ACCENTS.get(top, _DEFAULT_DYNAMIC_ACCENT)


def _get_argparse_metadata() -> dict[str, list[ArgOption]]:
    """Introspect the live argparse parsers and return structured metadata.

    Calls ``cli_mkpfs_main_parsers()``, walks the subparser hierarchy, and
    extracts every argument's dest, flags, default, type, and required flag.
    The result is a dict mapping a dot-joined command path
    (e.g. ``"pack.folder"``) to an ordered list of ``ArgOption`` objects.

    Returns:
        Mapping from command path to ordered argument list.  Empty dict when
        the ``mkpfs.cli`` module cannot be imported.
    """
    try:
        from mkpfs.cli import cli_mkpfs_main_parsers
    except ImportError:
        return {}

    root: Any = cli_mkpfs_main_parsers()
    result: dict[str, list[ArgOption]] = {}

    # Walk subparsers.  argparse's internal _subparsers._group_actions[0]
    # contains each subparser action, each with .choices mapping name->parser.
    if not hasattr(root, "_subparsers"):
        return {}
    top_group: Any = getattr(root._subparsers, "_group_actions", [None])[0]
    if top_group is None:
        return {}

    for name, parser in top_group.choices.items():
        _walk_parser(parser, [name], result)
    return result


def _walk_parser(
    parser: Any,
    path: list[str],
    result: dict[str, list[ArgOption]],
) -> None:
    """Recursively walk an argparse parser extracting argument metadata."""
    cmd_key: str = ".".join(path)

    # Collect actions by dest.  Multiple actions for the same dest happen
    # with toggle pairs (store_true + store_false on same dest) and mutually
    # exclusive groups with separate flag actions.
    actions_by_dest: dict[str, list[Any]] = {}
    for action in parser._actions:
        if action.dest in ("help", "command", "pack_command"):
            continue
        if isinstance(action, argparse._SubParsersAction):
            continue
        actions_by_dest.setdefault(action.dest, []).append(action)

    # Now convert each dest group to an ArgOption.
    options: list[ArgOption] = []

    for dest, actions in actions_by_dest.items():
        # Gather all flags across all actions for this dest.
        all_flags: list[str] = []
        for a in actions:
            all_flags.extend(a.option_strings)

        # Use the first action as representative.
        primary: Any = actions[0]
        cls_name: str = primary.__class__.__name__
        is_pos: bool = not bool(primary.option_strings)

        opt: ArgOption = ArgOption(
            dest=dest,
            flags=list(all_flags),
            help=getattr(primary, "help", "") or "",
            positional=is_pos,
        )

        if is_pos:
            opt.required = True
            dl: str = dest.lower()
            if "source" in dl or ("dir" in dl and "output" not in dl):
                opt.kind = "path-folder"
                opt.group = "paths"
            elif "image" in dl or ("file" in dl and "output" not in dl):
                opt.kind = "path-open"
                opt.group = "paths"
            elif "output" in dl or "out" in dl:
                opt.kind = "path-save"
                opt.group = "paths"
            else:
                opt.group = "paths"
            options.append(opt)
            continue

        # Optional argument.
        default_val: Any = getattr(primary, "default", None)

        # Detect store_true / store_false.
        if cls_name == "_StoreTrueAction" or cls_name == "_StoreFalseAction":
            # Check if there's a counterpart (toggle pair).
            has_store_true: bool = any(a.__class__.__name__ == "_StoreTrueAction" for a in actions)
            has_store_false: bool = any(a.__class__.__name__ == "_StoreFalseAction" for a in actions)

            if has_store_true and has_store_false:
                # Toggle pair: e.g. --adjust-output-file-extension /
                # --no-adjust-output-file-extension both share same dest.
                # The store_true action's default is the truth.
                store_true_act: Any = next(a for a in actions if a.__class__.__name__ == "_StoreTrueAction")
                opt.kind = "bool"
                opt.default = bool(store_true_act.default)
                opt.group = "options"
                # Primary flag is the store_true variant.
                opt.flag_str = store_true_act.option_strings[0] if store_true_act.option_strings else ""
            elif cls_name == "_StoreTrueAction":
                opt.kind = "bool"
                opt.default = bool(default_val) if default_val is not None else False
                opt.group = "options"
                opt.flag_str = primary.option_strings[0] if primary.option_strings else ""
            else:
                # Lone store_false — unusual but handle it.
                opt.kind = "bool"
                opt.default = bool(default_val) if default_val is not None else True
                opt.group = "options"
                opt.flag_str = primary.option_strings[0] if primary.option_strings else ""

        elif getattr(primary, "choices", None):
            opt.kind = "choice"
            opt.choices = list(primary.choices)
            opt.group = "options"
            if default_val is not None:
                opt.default = str(default_val)
            opt.flag_str = primary.option_strings[0] if primary.option_strings else ""

        elif isinstance(primary, argparse._AppendAction):
            opt.kind = "append"
            opt.group = "options"
            opt.default = []
            opt.flag_str = primary.option_strings[0] if primary.option_strings else ""

        else:
            # General store (text, int, path).
            opt.group = "options"
            if default_val is not None and default_val is not argparse.SUPPRESS:
                opt.default = str(default_val)
            opt.flag_str = primary.option_strings[0] if primary.option_strings else ""

            # Detect int type.
            if getattr(primary, "type", None) is int:
                opt.int_type = True
                opt.kind = "text"
            else:
                opt.kind = "text"

            # Path detection by name.
            dl = dest.lower()
            if "key" in dl or "ekpfs" in dl:
                opt.group = "encryption"
            elif "crc" in dl or "sha" in dl or "hash" in dl:
                opt.group = "hashes"
            elif (("folder" in dl or "temp" in dl) and opt.kind == "text") or ("source" in dl and "dir" in dl):
                opt.kind = "path-folder"
                opt.group = "paths"
            elif "source" in dl and "file" in dl:
                opt.kind = "path-open"
                opt.group = "paths"

        options.append(opt)

    # Sort: positionals first, then by dest.
    result[cmd_key] = sorted(options, key=lambda o: (not o.positional, o.dest))

    # Recurse into nested subparsers.
    if hasattr(parser, "_subparsers"):
        sub_group: Any = getattr(parser._subparsers, "_group_actions", [None])[0]
        if sub_group is not None:
            for sname, sparser in sub_group.choices.items():
                _walk_parser(sparser, [*path, sname], result)


# Lazy cached metadata so we only introspect argparse once.
_cache_argparse_meta: dict[str, list[ArgOption]] | None = None


def _ensure_argparse_meta() -> dict[str, list[ArgOption]]:
    """Return cached argparse metadata, building on first call."""
    global _cache_argparse_meta
    if _cache_argparse_meta is None:
        _cache_argparse_meta = _get_argparse_metadata()
    return _cache_argparse_meta


# ---------------------------------------------------------------------------
# CLI metadata discovery helpers
# ---------------------------------------------------------------------------


def _discover_cli_metadata() -> dict[str, list[ArgOption]]:
    """Discover CLI commands and options through the discovery chain.

    Priority order:
      1. ``mkpfs.discovery.get_cli_metadata(prefer_import=True)``
      2. Argparse introspection via ``_ensure_argparse_meta()``
      3. Subprocess help-text parsing fallback.

    Returns:
        Mapping from command path to ordered ``ArgOption`` list.  Empty dict
        when all discovery methods fail.
    """
    result: dict[str, list[ArgOption]] = {}

    # Tier 1: use the discovery module's get_cli_metadata (import or help fallback).
    try:
        from mkpfs.discovery import get_cli_metadata

        meta = get_cli_metadata(prefer_import=True)
        if meta.get("commands"):
            result = _convert_discovery_meta(meta)
            if result and any(result.values()):
                return result
    except Exception:
        pass

    # Tier 2: live argparse introspection.
    try:
        result = _ensure_argparse_meta()
        if result:
            return result
    except Exception:
        pass

    # Tier 3: subprocess help-text parsing (already attempted in tier 1 when
    # prefer_import failed; re-run without the import path if needed).
    with contextlib.suppress(Exception):
        result = _parse_help_text_metadata()

    return result


def _convert_discovery_meta(meta: dict) -> dict[str, list[ArgOption]]:
    """Convert discovery metadata into ArgOption lists.

    The ``get_cli_metadata()`` return value only provides command names +
    help text when coming from the help fallback.  When enriched opts are
    present we take them; otherwise we synthesise a minimal positional-
    only form for each command so the sidebar can still be built.
    """
    result: dict[str, list[ArgOption]] = {}
    commands: dict = meta.get("commands", {})
    for cmd_name, cmd_data in sorted(commands.items()):
        if isinstance(cmd_data, str):
            # Short help string only.
            result[cmd_name] = []
            continue
        if isinstance(cmd_data, dict):
            help_text: str | None = cmd_data.get("help")
            raw_opts: list | None = cmd_data.get("options")
            if raw_opts:
                opts = [ArgOption(**o) for o in raw_opts]
            elif help_text:
                opts = _parse_options_from_help(help_text, cmd_name)
            else:
                opts = []
            result[cmd_name] = opts

    return result


def _parse_options_from_help(help_text: str, cmd_name: str) -> list[ArgOption]:
    """Parse ArgOption list from argparse-generated --help output.

    This is a best-effort parser that extracts positional arguments,
    optional flags, choices, and help text from the standard argparse
    help format.
    """
    import re as _re

    options: list[ArgOption] = []
    lines: list[str] = help_text.splitlines()

    # Detect positional arguments block.
    in_positionals: bool = False
    in_options: bool = False

    for line in lines:
        stripped: str = line.strip()

        # Section headers.
        if _re.match(r"^positional arguments:\s*$", stripped, _re.IGNORECASE):
            in_positionals = True
            in_options = False
            continue
        if _re.match(r"^(optional arguments|options):\s*$", stripped, _re.IGNORECASE):
            in_positionals = False
            in_options = True
            continue

        if not (in_positionals or in_options):
            continue

        # Match "  NAME  help text" for positionals.
        m = _re.match(r"^\s{2,}([a-z][a-z0-9_-]+)\s{2,}(.*)$", stripped, _re.IGNORECASE)
        if m and in_positionals:
            opt = ArgOption(
                dest=m.group(1),
                help=m.group(2),
                positional=True,
                required=True,
            )
            dl: str = opt.dest.lower()
            if "source" in dl or ("dir" in dl and "output" not in dl):
                opt.kind = "path-folder"
                opt.group = "paths"
            elif "image" in dl or ("file" in dl and "output" not in dl):
                opt.kind = "path-open"
                opt.group = "paths"
            elif "output" in dl or "out" in dl:
                opt.kind = "path-save"
                opt.group = "paths"
            else:
                opt.kind = "text"
                opt.group = "paths"
            options.append(opt)
            continue

        # Match "  -f, --flag [VALUE]  help text" for optionals.
        # Also handle "  --flag [VALUE]  help" (single flag).
        m = _re.match(
            r"^\s{2,}(-[a-zA-Z0-9]\s*,\s*)?(--[a-z0-9][a-z0-9-]*)(\s+[A-Z][A-Z_]*)?\s{2,}(.*)$",
            stripped,
        )
        if m and in_options:
            flag_str: str = m.group(2)
            metavar: str | None = m.group(3)
            help_str: str = m.group(4) or ""
            dest: str = flag_str.lstrip("-").replace("-", "_")

            opt = ArgOption(
                dest=dest,
                flags=[flag_str],
                flag_str=flag_str,
                help=help_str,
                positional=False,
                group="options",
            )

            # Heuristic kind detection from flag/help.
            if metavar:
                metavar_upper: str = metavar.strip().upper()
                if metavar_upper in {"PATH", "DIR", "FILE", "FOLDER", "IMAGE"}:
                    if "out" in dest.lower() or "output" in help_str.lower():
                        opt.kind = "path-save"
                        opt.group = "paths"
                    elif "folder" in dest.lower() or "temp" in dest.lower() or "dir" in dest.lower():
                        opt.kind = "path-folder"
                        opt.group = "paths"
                    else:
                        opt.kind = "path-open"
                        opt.group = "paths"
            elif "flag" in help_str.lower() or "no-" in flag_str:
                opt.kind = "bool"
                opt.default = "no-" not in flag_str
            options.append(opt)

    return options


def _parse_help_text_metadata() -> dict[str, list[ArgOption]]:
    """Fallback discovery via subprocess help-text parsing.

    Runs ``mkpfs --help`` and each per-command ``mkpfs <cmd> --help``
    through a subprocess, extracting command names and help text.  The
    ArgOption lists are built by ``_parse_options_from_help``.
    """
    result: dict[str, list[ArgOption]] = {}
    try:
        from mkpfs.discovery import get_cli_metadata

        meta = get_cli_metadata(prefer_import=False)
        if meta.get("commands"):
            result = _convert_discovery_meta(meta)
    except Exception:
        pass
    return result


# ---------------------------------------------------------------------------
# Panel base class
# ---------------------------------------------------------------------------


class BasePanel(ctk.CTkFrame):
    """Abstract base for all operation panels.

    Subclasses implement _build_controls() and _run_command(). Each subclass
    also declares class-level _panel_key to look up its accent colour.
    """

    _title_key: str = ""
    _subtitle_key: str = ""
    _panel_key: str = ""

    def __init__(self, parent: Any) -> None:
        """Initialise BasePanel.

        Args:
            parent: Parent widget.
        """
        super().__init__(parent, fg_color="transparent")
        self._busy: bool = False
        self._log_queue: queue.Queue[tuple[str, str]] = queue.Queue()
        self._accent: str = _PANEL_ACCENT.get(self._panel_key, _NEON_BLUE)

        # Progress handler registration for progress mirroring.
        self._unregister_progress: Callable[[], None] | None = None
        self._try_register_progress_handler()

        # Header
        header: ctk.CTkFrame = ctk.CTkFrame(self, fg_color="transparent")
        header.pack(fill="x", padx=24, pady=(22, 0))

        self._title_label: ctk.CTkLabel = ctk.CTkLabel(
            header,
            text=tr(self._title_key),
            font=("Segoe UI", 20, "bold"),
            text_color=self._accent,
        )
        self._title_label.pack(anchor="w")

        self._subtitle_label: ctk.CTkLabel = ctk.CTkLabel(
            header,
            text=tr(self._subtitle_key),
            font=_FONT_SMALL,
            text_color=_TEXT_MUTED,
        )
        self._subtitle_label.pack(anchor="w", pady=(2, 0))

        # Neon divider bar
        ctk.CTkFrame(self, height=1, fg_color=self._accent).pack(fill="x", padx=24, pady=(12, 0))

        # Controls card with accent border
        self._card: GlassCard = GlassCard(self, accent=self._accent)
        self._card.pack(fill="x", padx=24, pady=14)
        self._build_controls(self._card)

        # Progress bar (neon colour matching panel)
        self._progress: ctk.CTkProgressBar = ctk.CTkProgressBar(
            self,
            mode="indeterminate",
            fg_color=_BG_INPUT,
            progress_color=self._accent,
            corner_radius=4,
            height=4,
        )
        self._progress.pack(fill="x", padx=24)
        self._progress.stop()
        self._progress.set(0)

        # Run button in panel's accent colour
        self._run_btn: NeonButton = NeonButton(
            self,
            text=tr("run"),
            command=self._on_run,
            color=self._accent,
        )
        self._run_btn.pack(padx=24, pady=(10, 0), anchor="e")

        # Log header row: label + export button side by side
        log_header: ctk.CTkFrame = ctk.CTkFrame(self, fg_color="transparent")
        log_header.pack(fill="x", padx=24, pady=(14, 4))
        self._log_section_label: SectionLabel = SectionLabel(log_header, tr("output_log"), color=self._accent)
        self._log_section_label.pack(side="left", anchor="w")
        self._export_btn: ctk.CTkButton = ctk.CTkButton(
            log_header,
            text=tr("export_log"),
            width=90,
            height=24,
            font=_FONT_SMALL,
            fg_color="transparent",
            border_width=1,
            border_color=self._accent,
            text_color=self._accent,
            hover_color=_BG_CARD,
            corner_radius=6,
            command=self._on_export_log,
        )
        self._export_btn.pack(side="right", anchor="e")
        self._log: LogPane = LogPane(self)
        self._log.pack(fill="both", expand=True, padx=24, pady=(0, 16))

        self.after(100, self._poll_log_queue)

    def refresh_labels(self) -> None:
        """Re-apply translated strings after a locale change.

        Updates the header labels and the run button, then destroys and
        recreates the controls card so every inner widget (PathRow labels,
        SectionLabels, checkboxes, OptionRows) reflects the new locale.
        """
        self._title_label.configure(text=tr(self._title_key))
        self._subtitle_label.configure(text=tr(self._subtitle_key))
        self._run_btn.set_label(tr("run"))
        self._log_section_label.configure(text=tr("output_log"))
        self._export_btn.configure(text=tr("export_log"))
        self._export_btn.configure(text=tr("export_log"))

        # Destroy and rebuild the controls card with the new locale strings.
        # pack(before=) keeps the card between the divider and the progress bar.
        self._card.destroy()
        self._card = GlassCard(self, accent=self._accent)
        self._card.pack(fill="x", padx=24, pady=14, before=self._progress)
        self._build_controls(self._card)

    def _build_controls(self, card: GlassCard) -> None:
        """Populate operation-specific controls inside the given card.

        Args:
            card: Card frame to populate.
        """

    def _run_command(self) -> None:
        """Execute the operation; runs inside a background thread."""
        raise NotImplementedError

    def _try_register_progress_handler(self) -> None:
        """Register a progress event handler for progress-bar mirroring.

        When ``mkpfs.discovery.register_progress_handler`` is importable,
        subscribes to progress events and updates this panel's progress bar
        to ``determinate`` mode with the fraction done/total. Stores the
        unregister callable so the subscription can be cleaned up on destroy.
        """
        with contextlib.suppress(Exception):
            from mkpfs.discovery import register_progress_handler

            def _on_progress(event: Any) -> None:
                """Mirror a ProgressEvent into this panel's progress bar."""
                with contextlib.suppress(Exception):
                    pct: float = event.done / max(event.total, 1)
                    self._progress.set(pct)
                    self.after(0, lambda: self._progress.configure(mode="determinate"))

            self._unregister_progress = register_progress_handler(_on_progress)

    def destroy(self) -> None:
        """Clean up progress handler subscription and destroy the widget."""
        if self._unregister_progress is not None:
            with contextlib.suppress(Exception):
                self._unregister_progress()
            self._unregister_progress = None
        super().destroy()

    def _on_run(self) -> None:
        """Clear log, reset progress, and launch the background worker thread."""
        if self._busy:
            return
        self._log.clear()
        self._busy = True
        self._run_btn.configure(state="disabled", text=tr("running"))
        # Reset progress bar to zero determinate before each new command.
        self._progress.stop()
        self._progress.configure(mode="determinate")
        self._progress.set(0)
        threading.Thread(target=self._worker, daemon=True).start()

    def _worker(self) -> None:
        """Wrap _run_command and signal completion back to the UI thread."""
        try:
            self._run_command()
        except Exception as exc:
            self._log_queue.put(("error", tr("err_unexpected").format(exc)))
        finally:
            self._log_queue.put(("__done__", ""))

    def _poll_log_queue(self) -> None:
        """Drain the log queue and update the UI; reschedules itself."""
        try:
            while True:
                tag, text = self._log_queue.get_nowait()
                if tag == "__done__":
                    self._busy = False
                    self._run_btn.configure(state="normal", text=tr("run"))
                    self._progress.stop()
                    self._progress.set(0)
                else:
                    self._log.append(text, tag)
        except queue.Empty:
            pass
        self.after(80, self._poll_log_queue)

    def _on_export_log(self) -> None:
        """Open a save dialog and write the current log content to a file."""
        import json as _json

        content: str = self._log.get_text().strip()
        if not content:
            return
        path: str | None = filedialog.asksaveasfilename(
            title="Export Log",
            defaultextension=".txt",
            filetypes=[("Text file", "*.txt"), ("JSON file", "*.json"), ("All files", "*.*")],
        )
        if not path:
            return
        try:
            if path.endswith(".json"):
                lines: list[str] = content.splitlines()
                with open(path, "w", encoding="utf-8") as fh:
                    _json.dump({"log": lines}, fh, indent=2, ensure_ascii=False)
            else:
                with open(path, "w", encoding="utf-8") as fh:
                    fh.write(content + "\n")
        except OSError as exc:
            self._emit(f"Export failed: {exc}", "error")

    def _emit(self, text: str, tag: str = "") -> None:
        """Queue a log line for display on the UI thread.

        Args:
            text: Log text.
            tag: Colour tag.
        """
        self._log_queue.put((tag, text))

    def _run_mkpfs(self, args: list[str]) -> None:
        """Run mkpfs in-process and stream each output line to the log pane.

        Executes ``cli_mkpfs_main`` directly in the current Python interpreter
        (the same one running the GUI) so no venv discovery or subprocess
        spawning is required.  ``sys.stdout`` / ``sys.stderr`` are temporarily
        redirected to a line-streaming helper that emits each line to the log
        queue as it arrives.  ``builtins.input`` is patched to auto-confirm the
        overwrite prompt with "y" so the GUI never blocks waiting for stdin.

        Args:
            args: CLI argument list passed verbatim to ``cli_mkpfs_main``.
        """
        # Late import -- if mkpfs or its dependencies are missing the
        # ImportError is caught below and shown as a readable error message.
        try:
            from mkpfs.cli import cli_mkpfs_main
        except ImportError as exc:
            self._emit(f"✗ Cannot import mkpfs: {exc}", "error")
            self._emit("   Ensure cryptography is installed: pip install cryptography", "muted")
            return

        self._emit(f"$ mkpfs {' '.join(args)}", "muted")

        # Line-streaming writer that forwards each line to the log queue.
        emit: Any = self._emit

        class _Streamer(io.TextIOBase):
            def __init__(self, tag_fn: Any) -> None:
                self._tag_fn: Any = tag_fn
                self._buf: str = ""

            def write(self, s: str) -> int:
                self._buf += s
                while "\n" in self._buf:
                    line, self._buf = self._buf.split("\n", 1)
                    stripped: str = line.rstrip()
                    if not stripped:
                        continue
                    lower: str = stripped.lower()
                    tag: str = ""
                    if "error" in lower:
                        tag = "error"
                    elif "warning" in lower:
                        tag = "warning"
                    elif any(k in lower for k in ("done", "complete", "success", "\u2713")):
                        tag = "success"
                    self._tag_fn(stripped, tag)
                return len(s)

            def flush(self) -> None:
                pass

        streamer: _Streamer = _Streamer(emit)
        original_input: Any = builtins.input
        exit_code: int = 0
        try:
            # Auto-confirm any "Overwrite? [Y/n]" prompts from the CLI.
            builtins.input = lambda _prompt="": "y"
            with contextlib.redirect_stdout(streamer), contextlib.redirect_stderr(streamer):
                exit_code = int(cli_mkpfs_main(args))
        except SystemExit as exc:
            exit_code = int(exc.code) if exc.code is not None else 0
        except Exception as exc:
            self._emit(f"✗ Unexpected error: {exc}", "error")
            return
        finally:
            builtins.input = original_input

        self._emit("", "")
        if exit_code == 0:
            self._emit(tr("ok"), "success")
        else:
            self._emit(tr("err_process").format(exit_code), "error")


# ---------------------------------------------------------------------------
# Operation panels
# ---------------------------------------------------------------------------


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
        self._version: ctk.StringVar = ctk.StringVar(value="PS4")
        self._compress: ctk.BooleanVar = ctk.BooleanVar(value=True)
        self._signed: ctk.BooleanVar = ctk.BooleanVar(value=False)
        self._verify_after: ctk.BooleanVar = ctk.BooleanVar(value=False)
        self._dry_run: ctk.BooleanVar = ctk.BooleanVar(value=False)
        self._temp_folder: ctk.StringVar = ctk.StringVar()
        # Output-prefill tracking: remembers the last autofilled output path so
        # user manual edits are not overwritten on subsequent source changes.
        self._last_autofilled_output: str = ""
        self._src.trace_add("write", lambda *_: self._prefill_output())
        super().__init__(parent)

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

        OptionRow(opt, tr("pf_version"), self._version, ["PS4", "PS5"], accent=self._accent).grid(
            row=0, column=0, sticky="ew", padx=(0, 12)
        )

        chk: ctk.CTkFrame = ctk.CTkFrame(opt, fg_color="transparent")
        chk.grid(row=0, column=1, sticky="nw", padx=(8, 0))

        for text, var in [
            (tr("pf_compress"), self._compress),
            (tr("pf_signed"), self._signed),
            (tr("pf_verify"), self._verify_after),
            (tr("pf_dry"), self._dry_run),
        ]:
            NeonCheckbox(chk, text=text, variable=var, accent=self._accent).pack(anchor="w", pady=3)

        # Temp folder (optional, spans both columns below checkboxes)
        PathRow(
            opt,
            tr("pf_temp"),
            self._temp_folder,
            mode="folder",
            placeholder=tr("pf_temp_ph"),
            browse_label=tr("browse"),
        ).grid(row=1, column=0, columnspan=2, sticky="ew", pady=(10, 0))

    def _prefill_output(self) -> None:
        """Autofill the output path from the source path.

        Generates a default output filename from the command path
        (``"pack.folder"``) and the source folder value. Only autofills
        when the output field is empty or still contains the last
        autofilled value (user has not manually edited it).
        """
        import pathlib

        src_val: str = self._src.get().strip()
        if not src_val:
            return
        src_path: pathlib.Path = pathlib.Path(src_val)

        fallback_basename: str = src_path.name if src_path.is_dir() else src_path.stem
        fallback_basename = (
            "".join(c if (c.isalnum() or c in "_-.") else "_" for c in fallback_basename).strip(".") or "image"
        )

        default_out: str = ""
        try:
            from mkpfs.discovery import default_output_name
            from mkpfs.discovery import normalize_output_path as norm_fn

            basename: str = default_output_name("pack.folder", src_path)
            parent_dir: pathlib.Path = src_path.parent if src_path.is_absolute() else pathlib.Path()
            suggested_str: str = str(parent_dir / f"{basename}.ffpfsc")
            result_path, _changed = norm_fn(suggested_str, ".ffpfsc")
            default_out = str(result_path)
        except Exception:
            parent_dir = src_path.parent if src_path.is_absolute() else pathlib.Path()
            default_out = str(parent_dir / f"{fallback_basename}.ffpfsc")

        current: str = self._out.get().strip()
        if not current or current == self._last_autofilled_output:
            self._out.set(default_out)
            self._last_autofilled_output = default_out

    def _run_command(self) -> None:
        src: str = self._src.get().strip()
        out: str = self._out.get().strip()
        if not src:
            self._emit(tr("pf_err_src"), "error")
            return
        if not out:
            self._emit(tr("pf_err_out"), "error")
            return
        args: list[str] = ["pack", "folder", src, out, "--version", self._version.get()]
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
        self._version: ctk.StringVar = ctk.StringVar(value="PS4")
        self._compress: ctk.BooleanVar = ctk.BooleanVar(value=True)
        self._temp_folder: ctk.StringVar = ctk.StringVar()
        # Output-prefill tracking: remembers the last autofilled output path so
        # user manual edits are not overwritten on subsequent source changes.
        self._last_autofilled_output: str = ""
        self._src.trace_add("write", lambda *_: self._prefill_output())
        super().__init__(parent)

    def _build_controls(self, card: GlassCard) -> None:
        card.columnconfigure(0, weight=1)
        card.columnconfigure(1, weight=1)

        SectionLabel(card, tr("paths"), color=self._accent).grid(
            row=0, column=0, columnspan=2, sticky="w", padx=16, pady=(14, 6)
        )

        PathRow(
            card,
            tr("pkf_src_label"),
            self._src,
            mode="open",
            placeholder=tr("pkf_src_ph"),
            browse_label=tr("browse"),
        ).grid(row=1, column=0, columnspan=2, sticky="ew", padx=16, pady=(0, 10))

        PathRow(
            card,
            tr("pkf_out_label"),
            self._out,
            mode="save",
            filetypes=[("PFS image", "*.ffpfsc"), ("All files", "*.*")],
            placeholder=tr("pkf_out_ph"),
            browse_label=tr("browse"),
        ).grid(row=2, column=0, columnspan=2, sticky="ew", padx=16, pady=(0, 14))

        ctk.CTkFrame(card, height=1, fg_color=_BORDER_BRIGHT).grid(row=3, column=0, columnspan=2, sticky="ew", padx=16)

        SectionLabel(card, tr("options"), color=self._accent).grid(
            row=4, column=0, columnspan=2, sticky="w", padx=16, pady=(12, 6)
        )

        opt: ctk.CTkFrame = ctk.CTkFrame(card, fg_color="transparent")
        opt.grid(row=5, column=0, columnspan=2, sticky="ew", padx=16, pady=(0, 14))
        opt.columnconfigure((0, 1), weight=1)

        OptionRow(opt, tr("pkf_version"), self._version, ["PS4", "PS5"], accent=self._accent).grid(
            row=0, column=0, sticky="ew", padx=(0, 12)
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

    def _prefill_output(self) -> None:
        """Autofill the output path from the source path.

        Generates a default output filename from the command path
        (``"pack.file"``) and the source file value. Only autofills when
        the output field is empty or still contains the last autofilled
        value (user has not manually edited it).
        """
        import pathlib

        src_val: str = self._src.get().strip()
        if not src_val:
            return
        src_path: pathlib.Path = pathlib.Path(src_val)

        fallback_basename: str = src_path.stem or src_path.name
        fallback_basename = (
            "".join(c if (c.isalnum() or c in "_-.") else "_" for c in fallback_basename).strip(".") or "image"
        )

        default_out: str = ""
        try:
            from mkpfs.discovery import default_output_name
            from mkpfs.discovery import normalize_output_path as norm_fn

            basename: str = default_output_name("pack.file", src_path)
            parent_dir: pathlib.Path = src_path.parent if src_path.is_absolute() else pathlib.Path()
            suggested_str: str = str(parent_dir / f"{basename}.ffpfsc")
            result_path, _changed = norm_fn(suggested_str, ".ffpfsc")
            default_out = str(result_path)
        except Exception:
            parent_dir = src_path.parent if src_path.is_absolute() else pathlib.Path()
            default_out = str(parent_dir / f"{fallback_basename}.ffpfsc")

        current: str = self._out.get().strip()
        if not current or current == self._last_autofilled_output:
            self._out.set(default_out)
            self._last_autofilled_output = default_out

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


# ---------------------------------------------------------------------------
# Verify panel
# ---------------------------------------------------------------------------


class VerifyPanel(BasePanel):
    """Panel for verifying a PFS image."""

    _title_key = "v_title"
    _subtitle_key = "v_subtitle"
    _panel_key = "verify"

    def __init__(self, parent: Any) -> None:
        """Initialise VerifyPanel.

        Args:
            parent: Parent widget.
        """
        self._image: ctk.StringVar = ctk.StringVar()
        self._source: ctk.StringVar = ctk.StringVar()
        self._crc32: ctk.StringVar = ctk.StringVar()
        self._sha256: ctk.StringVar = ctk.StringVar()
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
            tr("v_image_label"),
            self._image,
            mode="open",
            filetypes=[("PFS image", "*.ffpfs *.ffpfsc"), ("All files", "*.*")],
            placeholder=tr("v_image_ph"),
            browse_label=tr("browse"),
        ).grid(row=1, column=0, columnspan=2, sticky="ew", padx=16, pady=(0, 10))

        PathRow(
            card,
            tr("v_source_label"),
            self._source,
            mode="folder",
            placeholder=tr("v_source_ph"),
            browse_label=tr("browse"),
        ).grid(row=2, column=0, columnspan=2, sticky="ew", padx=16, pady=(0, 14))

        ctk.CTkFrame(card, height=1, fg_color=_BORDER_BRIGHT).grid(row=3, column=0, columnspan=2, sticky="ew", padx=16)
        SectionLabel(card, tr("v_hashes"), color=self._accent).grid(
            row=4, column=0, columnspan=2, sticky="w", padx=16, pady=(12, 6)
        )

        for col, (lkey, var, phkey) in enumerate(
            [
                ("v_crc32", self._crc32, "v_crc32_ph"),
                ("v_sha256", self._sha256, "v_sha256_ph"),
            ]
        ):
            hf: ctk.CTkFrame = ctk.CTkFrame(card, fg_color="transparent")
            hf.grid(row=5, column=col, sticky="ew", padx=(16 if col == 0 else 6, 6 if col == 0 else 16), pady=(0, 14))
            ctk.CTkLabel(hf, text=tr(lkey), font=_FONT_LABEL, text_color=_TEXT_SECONDARY).pack(anchor="w", pady=(0, 3))
            ctk.CTkEntry(
                hf,
                textvariable=var,
                placeholder_text=tr(phkey),
                fg_color=_BG_INPUT,
                border_color=_BORDER_BRIGHT,
                corner_radius=8,
                font=_FONT_UI,
                text_color=_TEXT_PRIMARY,
            ).pack(fill="x")

        ctk.CTkFrame(card, height=1, fg_color=_BORDER_BRIGHT).grid(row=6, column=0, columnspan=2, sticky="ew", padx=16)
        SectionLabel(card, tr("encryption"), color=self._accent).grid(
            row=7, column=0, columnspan=2, sticky="w", padx=16, pady=(12, 6)
        )

        enc: ctk.CTkFrame = ctk.CTkFrame(card, fg_color="transparent")
        enc.grid(row=8, column=0, columnspan=2, sticky="ew", padx=16, pady=(0, 14))
        ctk.CTkLabel(enc, text=tr("v_ekpfs"), font=_FONT_LABEL, text_color=_TEXT_SECONDARY).pack(
            anchor="w", pady=(0, 3)
        )
        ctk.CTkEntry(
            enc,
            textvariable=self._ekpfs,
            placeholder_text=tr("v_ekpfs_ph"),
            fg_color=_BG_INPUT,
            border_color=_BORDER_BRIGHT,
            corner_radius=8,
            font=_FONT_MONO,
            text_color=_TEXT_PRIMARY,
        ).pack(fill="x", pady=(0, 6))
        NeonCheckbox(enc, text=tr("v_newcrypt"), variable=self._new_crypt, accent=self._accent).pack(anchor="w")

    def _run_command(self) -> None:
        image: str = self._image.get().strip()
        if not image:
            self._emit(tr("v_err"), "error")
            return
        args: list[str] = ["verify", image]
        if source := self._source.get().strip():
            args += ["--source-dir", source]
        if crc := self._crc32.get().strip():
            args += ["--expect-crc32", crc]
        if sha := self._sha256.get().strip():
            args += ["--expect-manifest-sha256", sha]
        if ekpfs := self._ekpfs.get().strip():
            args += ["--ekpfs-key", ekpfs]
        if self._new_crypt.get():
            args.append("--new-crypt")
        self._run_mkpfs(args)


# ---------------------------------------------------------------------------
# Inspect panel
# ---------------------------------------------------------------------------


class InspectPanel(BasePanel):
    """Panel for inspecting PFS image metadata."""

    _title_key = "i_title"
    _subtitle_key = "i_subtitle"
    _panel_key = "inspect"

    def __init__(self, parent: Any) -> None:
        """Initialise InspectPanel.

        Args:
            parent: Parent widget.
        """
        self._image: ctk.StringVar = ctk.StringVar()
        self._fmt: ctk.StringVar = ctk.StringVar(value="text")
        self._ekpfs: ctk.StringVar = ctk.StringVar()
        super().__init__(parent)

    def _build_controls(self, card: GlassCard) -> None:
        card.columnconfigure(0, weight=1)
        card.columnconfigure(1, weight=1)

        SectionLabel(card, tr("paths"), color=self._accent).grid(
            row=0, column=0, columnspan=2, sticky="w", padx=16, pady=(14, 6)
        )
        PathRow(
            card,
            tr("i_image_label"),
            self._image,
            mode="open",
            filetypes=[("PFS image", "*.ffpfs *.ffpfsc"), ("All files", "*.*")],
            placeholder=tr("i_image_ph"),
            browse_label=tr("browse"),
        ).grid(row=1, column=0, columnspan=2, sticky="ew", padx=16, pady=(0, 14))

        ctk.CTkFrame(card, height=1, fg_color=_BORDER_BRIGHT).grid(row=2, column=0, columnspan=2, sticky="ew", padx=16)
        SectionLabel(card, tr("options"), color=self._accent).grid(
            row=3, column=0, columnspan=2, sticky="w", padx=16, pady=(12, 6)
        )

        opt: ctk.CTkFrame = ctk.CTkFrame(card, fg_color="transparent")
        opt.grid(row=4, column=0, columnspan=2, sticky="ew", padx=16, pady=(0, 14))
        opt.columnconfigure((0, 1), weight=1)

        OptionRow(opt, tr("i_format"), self._fmt, ["text", "json"], accent=self._accent).grid(
            row=0, column=0, sticky="ew", padx=(0, 12)
        )

        ekpfs_col: ctk.CTkFrame = ctk.CTkFrame(opt, fg_color="transparent")
        ekpfs_col.grid(row=0, column=1, sticky="ew")
        ctk.CTkLabel(ekpfs_col, text=tr("i_ekpfs"), font=_FONT_LABEL, text_color=_TEXT_SECONDARY).pack(
            anchor="w", pady=(0, 3)
        )
        ctk.CTkEntry(
            ekpfs_col,
            textvariable=self._ekpfs,
            placeholder_text=tr("i_ekpfs_ph"),
            fg_color=_BG_INPUT,
            border_color=_BORDER_BRIGHT,
            corner_radius=8,
            font=_FONT_MONO,
            text_color=_TEXT_PRIMARY,
        ).pack(fill="x")

    def _run_command(self) -> None:
        image: str = self._image.get().strip()
        if not image:
            self._emit(tr("i_err"), "error")
            return
        args: list[str] = ["inspect", image, "--format", self._fmt.get()]
        if ekpfs := self._ekpfs.get().strip():
            args += ["--ekpfs-key", ekpfs]
        self._run_mkpfs(args)


# ---------------------------------------------------------------------------
# Tree panel
# ---------------------------------------------------------------------------


class TreePanel(BasePanel):
    """Panel for printing the PFS filesystem tree."""

    _title_key = "t_title"
    _subtitle_key = "t_subtitle"
    _panel_key = "tree"

    def __init__(self, parent: Any) -> None:
        """Initialise TreePanel.

        Args:
            parent: Parent widget.
        """
        self._image: ctk.StringVar = ctk.StringVar()
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
            tr("t_image_label"),
            self._image,
            mode="open",
            filetypes=[("PFS image", "*.ffpfs *.ffpfsc"), ("All files", "*.*")],
            placeholder=tr("t_image_ph"),
            browse_label=tr("browse"),
        ).grid(row=1, column=0, columnspan=2, sticky="ew", padx=16, pady=(0, 14))

        ctk.CTkFrame(card, height=1, fg_color=_BORDER_BRIGHT).grid(row=2, column=0, columnspan=2, sticky="ew", padx=16)
        SectionLabel(card, tr("encryption"), color=self._accent).grid(
            row=3, column=0, columnspan=2, sticky="w", padx=16, pady=(12, 6)
        )

        enc: ctk.CTkFrame = ctk.CTkFrame(card, fg_color="transparent")
        enc.grid(row=4, column=0, columnspan=2, sticky="ew", padx=16, pady=(0, 14))
        ctk.CTkLabel(enc, text=tr("t_ekpfs"), font=_FONT_LABEL, text_color=_TEXT_SECONDARY).pack(
            anchor="w", pady=(0, 3)
        )
        ctk.CTkEntry(
            enc,
            textvariable=self._ekpfs,
            placeholder_text=tr("t_ekpfs_ph"),
            fg_color=_BG_INPUT,
            border_color=_BORDER_BRIGHT,
            corner_radius=8,
            font=_FONT_MONO,
            text_color=_TEXT_PRIMARY,
        ).pack(fill="x", pady=(0, 6))
        NeonCheckbox(enc, text=tr("t_newcrypt"), variable=self._new_crypt, accent=self._accent).pack(anchor="w")

    def _run_command(self) -> None:
        image: str = self._image.get().strip()
        if not image:
            self._emit(tr("t_err"), "error")
            return
        args: list[str] = ["tree", image]
        if ekpfs := self._ekpfs.get().strip():
            args += ["--ekpfs-key", ekpfs]
        if self._new_crypt.get():
            args.append("--new-crypt")
        self._run_mkpfs(args)


# ---------------------------------------------------------------------------
# Unpack panel
# ---------------------------------------------------------------------------


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


# ---------------------------------------------------------------------------
# Dynamic panel -- builds controls from argparse metadata
# ---------------------------------------------------------------------------

# Heuristic filetype filters for path fields.
_PFS_IMAGE_FILETYPES: list[tuple[str, str]] = [("PFS image", "*.ffpfs *.ffpfsc"), ("All files", "*.*")]
_PFSC_FILETYPES: list[tuple[str, str]] = [("PFS image", "*.ffpfsc"), ("All files", "*.*")]
_FFPFS_FILETYPES: list[tuple[str, str]] = [("PFS image", "*.ffpfs"), ("All files", "*.*")]


def _filetypes_for_option(opt: ArgOption) -> list[tuple[str, str]] | None:
    """Return a sensible filetype filter for a path option based on its dest name."""
    dl: str = opt.dest.lower()
    if ("image" in dl or ("file" in dl and opt.positional)) and opt.kind == "path-open":
        return _PFS_IMAGE_FILETYPES
    if opt.kind == "path-save" and ("image" in dl or "out" in dl) and ("pfs" in dl or "image" in dl):
        return _PFS_IMAGE_FILETYPES
    return None


def _path_mode_for_option(opt: ArgOption) -> str:
    """Return 'folder', 'open', or 'save' based on dest name heuristics."""
    if opt.kind == "path-folder":
        return "folder"
    if opt.kind == "path-save":
        return "save"
    return "open"


def _human_label(dest: str) -> str:
    """Derive a human-readable label from an argparse dest name.

    Args:
        dest: e.g. 'source_dir', 'ekpfs_key', 'no_compress'.

    Returns:
        Title-case space-separated label.
    """
    # Drop the 'no_' prefix for display.
    name: str = dest.removeprefix("no_")
    # Replace underscores with spaces and title-case.
    return " ".join(w.capitalize() for w in name.split("_"))


def _placeholder_for_option(opt: ArgOption) -> str:
    """Return a placeholder string for an option's entry field."""
    dl: str = opt.dest.lower()
    if "crc" in dl:
        return "e.g. 7F528D1F"
    if "sha" in dl:
        return "64 hex chars…"
    if "ekpfs" in dl:
        return "64 hex chars…"
    if opt.kind in ("path-folder", "path-open", "path-save"):
        return f"Select {opt.dest.replace('_', ' ')}…"
    if opt.choices:
        return ""
    return ""


class _RepeatableRow(ctk.CTkFrame):
    """A row in a repeatable (append-action) argument list: entry + remove button."""

    def __init__(
        self,
        parent: Any,
        remove_cb: Callable[[_RepeatableRow], None],
        accent: str = _NEON_BLUE,
    ) -> None:
        super().__init__(parent, fg_color="transparent")
        self._remove_cb: Callable[[_RepeatableRow], None] = remove_cb
        self._var: ctk.StringVar = ctk.StringVar()

        self.columnconfigure(0, weight=1)
        ctk.CTkEntry(
            self,
            textvariable=self._var,
            fg_color=_BG_INPUT,
            border_color=_BORDER_BRIGHT,
            corner_radius=8,
            font=_FONT_UI,
            text_color=_TEXT_PRIMARY,
        ).grid(row=0, column=0, sticky="ew", padx=(0, 6))

        ctk.CTkButton(
            self,
            text="-",
            width=32,
            height=32,
            corner_radius=8,
            fg_color=_BG_PANEL,
            hover_color=_ERROR,
            border_width=1,
            border_color=_BORDER_BRIGHT,
            font=_FONT_LABEL,
            text_color=_TEXT_SECONDARY,
            command=self._on_remove,
        ).grid(row=0, column=1)

    def _on_remove(self) -> None:
        self._remove_cb(self)

    @property
    def value(self) -> str:
        return self._var.get().strip()


class DynamicPanel(BasePanel):
    """A panel whose controls are built dynamically from argparse metadata.

    Constructed with a command path string (e.g. ``"pack.folder"``) and the
    ordered list of ``ArgOption`` objects for that command.
    """

    def __init__(self, parent: Any, cmd_path: str, options: list[ArgOption]) -> None:
        """Initialise a DynamicPanel.

        Args:
            parent: Parent widget.
            cmd_path: Dot-joined command path, e.g. ``"pack.folder"``.
            options: Ordered list of ArgOption describing CLI arguments.
        """
        self._cmd_path: str = cmd_path
        self._arg_options: list[ArgOption] = options
        self._panel_key = cmd_path
        self._accent_cfg: str = _accent_for_cmd_path(cmd_path)

        # Derive title/subtitle keys.
        self._title_key = f"dyn_{cmd_path.replace('.', '_')}_title"
        self._subtitle_key = f"dyn_{cmd_path.replace('.', '_')}_subtitle"

        # Add dynamic translations for this command.
        # We use the cmd path parts to build the label.
        cmd_parts: list[str] = cmd_path.split(".")
        display_title: str = " ".join(w.capitalize() for w in cmd_parts)

        # Try to get a help-based subtitle from the metadata.
        display_subtitle: str = ""
        for o in options:
            if o.help:
                display_subtitle = o.help
                break

        # Store the title/subtitle for all three locales.
        for locale_key in ("en", "pt_BR", "es"):
            _TRANSLATIONS.setdefault(locale_key, {})[self._title_key] = display_title
            _TRANSLATIONS[locale_key][self._subtitle_key] = display_subtitle or display_title

        # Set accent before BasePanel.__init__ runs.
        self._accent = self._accent_cfg

        # Field variables: dict[str, Any] mapping dest -> StringVar | BooleanVar | list[StringVar]
        self._fields: dict[str, Any] = {}
        # Repeatable list containers: dest -> list of _RepeatableRow
        self._repeatable_rows: dict[str, list[_RepeatableRow]] = {}

        # Output prefill support.
        self._source_positional_dests: list[str] = []
        self._output_positional_dests: list[str] = []
        # Track the last autofilled output value so we don't overwrite user edits.
        self._last_autofilled_output: str = ""

        super().__init__(parent)

    def _build_controls(self, card: GlassCard) -> None:
        """Build the form from ArgOption metadata."""
        card.columnconfigure(0, weight=1)
        card.columnconfigure(1, weight=1)

        # Separate positionals and optionals.
        positionals: list[ArgOption] = [o for o in self._arg_options if o.positional]
        optionals: list[ArgOption] = [o for o in self._arg_options if not o.positional]

        # Section labels by group: tracks which groups we've emitted.
        emitted_groups: dict[str, int] = {}
        row: int = 0

        def _section(group: str, r: int) -> int:
            if group not in emitted_groups:
                SectionLabel(card, tr(group), color=self._accent).grid(
                    row=r, column=0, columnspan=2, sticky="w", padx=16, pady=(14, 6)
                )
                emitted_groups[group] = r
                return r + 1
            return r

        # Track positional dests for output prefill.
        self._source_positional_dests = [
            o.dest for o in positionals if o.kind in ("path-folder", "path-open") and o.required
        ]
        self._output_positional_dests = [o.dest for o in positionals if o.kind == "path-save"]

        # Render positionals first.
        for opt in positionals:
            row = _section(opt.group, row)
            row = self._render_control(card, opt, row, span=True)

        # Add traces on required positional fields for continuous validation
        # and output prefill.
        for opt in positionals:
            if not opt.required:
                continue
            field: Any = self._fields.get(opt.dest)
            if isinstance(field, ctk.StringVar):
                field.trace_add("write", lambda *_: self._update_run_button_state())

        # Set up output prefill trace on source fields.
        for src_dest in self._source_positional_dests:
            src_var: Any = self._fields.get(src_dest)
            if isinstance(src_var, ctk.StringVar):
                src_var.trace_add("write", lambda *_: self._prefill_output())

        # Separator between positional and optional sections.
        if positionals and optionals:
            ctk.CTkFrame(card, height=1, fg_color=_BORDER_BRIGHT).grid(
                row=row, column=0, columnspan=2, sticky="ew", padx=16
            )
            row += 1

        # Render optionals, grouping by section.
        cur_group: str | None = None
        opt_frame: ctk.CTkFrame | None = None
        opt_row: int = 0

        for opt in optionals:
            if opt.group != cur_group or opt_frame is None:
                # Flush previous frame.
                if opt_frame is not None:
                    opt_frame.grid(row=row, column=0, columnspan=2, sticky="ew", padx=16, pady=(0, 14))
                    row += 1

                row = _section(opt.group, row)
                opt_frame = ctk.CTkFrame(card, fg_color="transparent")
                opt_frame.columnconfigure((0, 1), weight=1)
                opt_row = 0
                cur_group = opt.group

            opt_row = self._render_control(opt_frame, opt, opt_row, span=False)

        # Pack the last opt frame.
        if opt_frame is not None:
            opt_frame.grid(row=row, column=0, columnspan=2, sticky="ew", padx=16, pady=(0, 14))
            row += 1

        # Initial validation state.
        self._update_run_button_state()

    def _render_control(
        self,
        parent: Any,
        opt: ArgOption,
        row: int,
        span: bool = False,
    ) -> int:
        """Render a single control widget for the given option, returning next row."""
        col_span: int = 2 if span else 1
        col: int = 0

        if opt.kind == "bool":
            var: ctk.BooleanVar = ctk.BooleanVar(value=bool(opt.default))
            self._fields[opt.dest] = var
            label: str = _human_label(opt.dest)
            NeonCheckbox(
                parent,
                text=label,
                variable=var,
                accent=self._accent,
            ).grid(row=row, column=col, columnspan=col_span, sticky="w", padx=(0, 8), pady=3)
            return row + 1

        elif opt.kind == "choice":
            var = ctk.StringVar(value=str(opt.default) if opt.default else (opt.choices[0] if opt.choices else ""))
            self._fields[opt.dest] = var
            label = _human_label(opt.dest)
            str_choices: list[str] = [str(c) for c in opt.choices] if opt.choices else []
            OptionRow(
                parent,
                label=label,
                variable=var,
                values=str_choices,
                accent=self._accent,
            ).grid(row=row, column=col, columnspan=col_span, sticky="ew", padx=(0, 8), pady=(0, 8))
            return row + 1

        elif opt.kind in ("path-folder", "path-open", "path-save"):
            var = ctk.StringVar(value=str(opt.default) if opt.default else "")
            self._fields[opt.dest] = var
            mode: str = _path_mode_for_option(opt)
            ft: list[tuple[str, str]] | None = _filetypes_for_option(opt)
            label = _human_label(opt.dest)
            placeholder: str = _placeholder_for_option(opt)
            PathRow(
                parent,
                label=label,
                variable=var,
                mode=mode,
                filetypes=ft,
                placeholder=placeholder,
                browse_label=tr("browse"),
            ).grid(row=row, column=col, columnspan=col_span, sticky="ew", padx=(0, 8), pady=(0, 10))
            return row + 1

        elif opt.kind == "append":
            # Repeatable list: label + add button + list of entry rows.
            self._repeatable_rows.setdefault(opt.dest, [])
            self._fields[opt.dest] = []  # list of StringVar managed via rows

            label = _human_label(opt.dest)

            # Label row with add button.
            label_frame: ctk.CTkFrame = ctk.CTkFrame(parent, fg_color="transparent")
            label_frame.grid(row=row, column=col, columnspan=col_span, sticky="ew", padx=(0, 8), pady=(0, 3))
            row += 1
            ctk.CTkLabel(label_frame, text=label, font=_FONT_LABEL, text_color=_TEXT_SECONDARY).pack(
                side="left", anchor="w"
            )

            def _add_repeatable() -> None:
                rrow: _RepeatableRow = _RepeatableRow(
                    self._list_frame, self._on_remove_repeatable, accent=self._accent
                )
                self._repeatable_rows[opt.dest].append(rrow)
                rrow.pack(fill="x", pady=(0, 4))
                self._fields[opt.dest].append(rrow._var)

            ctk.CTkButton(
                label_frame,
                text="+",
                width=32,
                height=24,
                corner_radius=8,
                fg_color=_BG_PANEL,
                hover_color=self._accent,
                border_width=1,
                border_color=_BORDER_BRIGHT,
                font=_FONT_LABEL,
                text_color=_TEXT_SECONDARY,
                command=_add_repeatable,
            ).pack(side="right")

            # Container for repeatable rows.
            self._list_frame: ctk.CTkFrame = ctk.CTkFrame(parent, fg_color="transparent")
            self._list_frame.grid(row=row, column=col, columnspan=col_span, sticky="ew", padx=(0, 8), pady=(0, 8))
            return row + 1

        else:
            # Generic text/numeric entry.
            default_str: str = str(opt.default) if opt.default else ""
            var = ctk.StringVar(value=default_str)
            self._fields[opt.dest] = var
            label = _human_label(opt.dest)
            placeholder = _placeholder_for_option(opt)

            # Entry with label above.
            ef: ctk.CTkFrame = ctk.CTkFrame(parent, fg_color="transparent")
            ef.grid(row=row, column=col, columnspan=col_span, sticky="ew", padx=(0, 8), pady=(0, 8))
            ctk.CTkLabel(ef, text=label, font=_FONT_LABEL, text_color=_TEXT_SECONDARY).pack(anchor="w", pady=(0, 3))
            font_used: tuple[str, int] = (
                _FONT_MONO if ("key" in opt.dest.lower() or "ekpfs" in opt.dest.lower()) else _FONT_UI
            )
            ctk.CTkEntry(
                ef,
                textvariable=var,
                placeholder_text=placeholder,
                fg_color=_BG_INPUT,
                border_color=_BORDER_BRIGHT,
                corner_radius=8,
                font=font_used,
                text_color=_TEXT_PRIMARY,
            ).pack(fill="x")
            return row + 1

    def _on_remove_repeatable(self, row_widget: _RepeatableRow) -> None:
        """Remove a repeatable row from its container."""
        # Find which dest owns this row.
        for dest, rows in self._repeatable_rows.items():
            if row_widget in rows:
                rows.remove(row_widget)
                row_widget.destroy()
                # Also remove from fields list.
                if dest in self._fields:
                    self._fields[dest] = [v for v in self._fields[dest] if v is not row_widget._var]
                break

    def _validate_and_build_argv(self) -> list[str] | None:
        """Validate required fields and build the argv list.

        Returns:
            argv list ready for ``_run_mkpfs``, or None on validation failure.
        """
        argv: list[str] = []

        # Build the command path prefix.
        cmd_parts: list[str] = self._cmd_path.split(".")
        argv.extend(cmd_parts)

        # Collect positional values first.
        positionals: list[ArgOption] = [o for o in self._arg_options if o.positional]
        for opt in positionals:
            value: str = ""
            field: Any = self._fields.get(opt.dest)
            if field is not None:
                if isinstance(field, ctk.StringVar):
                    value = field.get().strip()
                elif isinstance(field, ctk.BooleanVar):
                    value = str(field.get())
            if opt.required and not value:
                self._emit(f"✗ {_human_label(opt.dest)} is required.", "error")
                return None
            if value:
                argv.append(value)

        # Collect optional values.
        optionals: list[ArgOption] = [o for o in self._arg_options if not o.positional]
        # sort by position in options list
        for opt in optionals:
            field = self._fields.get(opt.dest)

            if opt.kind == "bool":
                if isinstance(field, ctk.BooleanVar):
                    val: bool = field.get()
                    # Determine which flag to emit.
                    # For toggle pairs (store_true + store_false on same dest),
                    # the flag_str comes from the store_true variant.
                    # For store_true with default=True (i.e. negate_flag),
                    # the default is on, and the user unchecked → emit the negate flag.
                    flag: str = opt.flag_str
                    if not flag:
                        flag = f"--{opt.dest.replace('_', '-')}"

                    # Heuristic: if default is True and value is False, emit the negation.
                    # Check if there's a flag containing 'no-' for this dest.
                    no_flags: list[str] = [f for f in opt.flags if f.startswith("--no-")]

                    if opt.default is True and not val and no_flags:
                        argv.append(no_flags[0])
                    elif opt.default is False and val:
                        # Emit the regular flag (pick one that doesn't start with --no-).
                        yes_flags: list[str] = [f for f in opt.flags if not f.startswith("--no-")]
                        if yes_flags:
                            argv.append(yes_flags[0])
                        else:
                            argv.append(flag)
                    elif (opt.default is True and val) or (opt.default is False and not val):
                        # Default matches; no flag needed.
                        pass

            elif opt.kind == "choice":
                if isinstance(field, ctk.StringVar):
                    val = field.get().strip()
                    default_s: str = str(opt.default) if opt.default else ""
                    if val and val != default_s:
                        argv.append(opt.flag_str)
                        argv.append(val)

            elif opt.kind == "append":
                rows: list[_RepeatableRow] = self._repeatable_rows.get(opt.dest, [])
                for rrow in rows:
                    v: str = rrow.value
                    if v:
                        argv.append(opt.flag_str)
                        argv.append(v)

            else:
                # text, path-*.
                if isinstance(field, ctk.StringVar):
                    val = field.get().strip()
                    default_s = str(opt.default) if opt.default else ""
                    if val and val != default_s:
                        if opt.flag_str:
                            argv.append(opt.flag_str)
                        argv.append(val)

        return argv

    def _update_run_button_state(self) -> None:
        """Enable or disable the Run button based on required field state.

        All required positional StringVars must contain a non-empty value
        for the Run button to be enabled.  This is called on every write
        to a required-field variable via ``trace_add``.
        """
        if self._busy:
            return
        all_filled: bool = True
        for opt in self._arg_options:
            if not opt.required:
                continue
            field: Any = self._fields.get(opt.dest)
            if isinstance(field, ctk.StringVar) and not field.get().strip():
                all_filled = False
                break
        state: str = "normal" if all_filled else "disabled"
        with contextlib.suppress(Exception):
            self._run_btn.configure(state=state)

    def _prefill_output(self) -> None:
        """Prefill output path fields from source positional args.

        Generates a default output basename from the command path and the first
        source positional field's value by calling ``default_output_name`` from
        the discovery module.  Only autofills when the output field is empty or
        still contains the previous autofill (user has not manually edited it
        since the last autofill).

        The last autofilled value is tracked so command-option changes re-autofill
        when the user has not made manual edits.
        """
        import pathlib

        if not self._output_positional_dests or not self._source_positional_dests:
            return

        # Collect the first non-empty source path value.
        src_val: str = ""
        for sd in self._source_positional_dests:
            sv: Any = self._fields.get(sd)
            if isinstance(sv, ctk.StringVar):
                v: str = sv.get().strip()
                if v:
                    src_val = v
                    break

        if not src_val:
            return

        src_path: pathlib.Path = pathlib.Path(src_val)
        stem: str = src_path.stem if src_path.suffix else src_path.name

        # Use the shared default_output_name API.
        try:
            from mkpfs.discovery import default_output_name

            basename: str = default_output_name(self._cmd_path, src_path)
        except Exception:
            basename = stem or "image"

        # Derive the suggested output path (same directory as source).
        parent_dir: pathlib.Path = src_path.parent if src_path.is_absolute() else pathlib.Path()
        suggested: pathlib.Path = parent_dir / f"{basename}.ffpfsc"
        suggested_str: str = str(suggested)

        # Update output fields.
        for od in self._output_positional_dests:
            ov: Any = self._fields.get(od)
            if isinstance(ov, ctk.StringVar):
                current: str = ov.get().strip()
                # Autofill when empty, or when it still matches the last autofill
                # (meaning the user has not manually changed it).
                if not current or current == self._last_autofilled_output:
                    try:
                        from mkpfs.discovery import normalize_output_path

                        result_path, _changed = normalize_output_path(suggested_str, ".ffpfsc")
                        result_str: str = str(result_path)
                        ov.set(result_str)
                        self._last_autofilled_output = result_str
                    except Exception:
                        ov.set(suggested_str)
                        self._last_autofilled_output = suggested_str

    def _run_command(self) -> None:
        """Validate fields and invoke mkpfs in-process."""
        argv: list[str] | None = self._validate_and_build_argv()
        if argv is None:
            return
        self._run_mkpfs(argv)


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


# ---------------------------------------------------------------------------
# Main application window
# ---------------------------------------------------------------------------


class MkPFSApp(ctk.CTk):
    """Main application window with neon sidebar and language selector.

    At startup, attempts to discover commands via argparse introspection.
    If that succeeds, the sidebar is built dynamically and each command gets
    a ``DynamicPanel``.  Otherwise, the original hard-coded panels are used
    as a fallback.
    """

    _PAGES: list[tuple[str, str, type | None, str]] | None = None

    def __init__(self) -> None:
        """Initialise and configure the application window."""
        super().__init__()
        self.title("MkPFS")
        self.geometry("1200x800")
        self.minsize(800, 600)
        self.configure(fg_color=_BG_DEEP)

        class_pages: list[tuple[str, str, type | None, str]] | None = self._PAGES
        self._pages: list[tuple[str, str, type | None, str]] = list(
            class_pages
            if class_pages is not None
            else [
                ("nav_pack_folder", "nav_pack_folder", PackFolderPanel, _NEON_BLUE),
                ("nav_pack_file", "nav_pack_file", PackFilePanel, _NEON_CYAN),
                ("nav_verify", "nav_verify", VerifyPanel, _NEON_GREEN),
                ("nav_inspect", "nav_inspect", InspectPanel, _NEON_PURPLE),
                ("nav_tree", "nav_tree", TreePanel, _NEON_AMBER),
                ("nav_unpack", "nav_unpack", UnpackPanel, _NEON_PINK),
            ]
        )
        self._panels: dict[str, BasePanel] = {}
        self._nav_buttons: dict[str, NavButton] = {}
        self._active_key: str = ""
        self._dynamic: bool = False

        # Try dynamic discovery.
        self._try_dynamic_discovery()

        self._set_window_icon()

        # Main area: sidebar + content side-by-side, above the footer.
        self._main_area: ctk.CTkFrame = ctk.CTkFrame(self, fg_color="transparent")
        self._main_area.pack(fill="both", expand=True)

        self._build_sidebar()
        self._build_content()

        # Version footer bar (persistent across all window states).
        self._build_footer()

        # Select first entry.
        first_key: str = next(iter(self._nav_buttons))
        self._select(first_key)

    def _try_dynamic_discovery(self) -> None:
        """Attempt CLI command discovery through the full discovery chain.

        Calls ``_discover_cli_metadata()`` which tries (in order):
          1. ``mkpfs.discovery.get_cli_metadata(prefer_import=True)``
          2. Live argparse introspection
          3. Subprocess help-text parsing fallback

        On success, populates ``_PAGES`` from the discovered metadata.
        On failure, keeps the hard-coded fallback list.
        """
        try:
            meta: dict[str, list[ArgOption]] = _discover_cli_metadata()
        except Exception:
            return

        if not meta:
            return

        # Build dynamic pages list: (key, label_key, None, accent).
        # The PanelClass is None for dynamic; we create DynamicPanel in _build_content.
        dynamic_pages: list[tuple[str, str, type | None, str]] = []

        # Navigation label emoji map by top-level command.
        EMOJI: dict[str, str] = {
            "pack": "📦",
            "pack.folder": "📦",
            "pack.file": "📄",
            "pack.exfat": "📦",
            "verify": "✅",
            "inspect": "🔍",
            "tree": "🌲",
            "unpack": "📂",
        }

        # Build nav entries.  For top-level commands that have nested subcommands
        # (pack.*), we use the nested versions directly.
        seen: set[str] = set()
        for cmd_path in meta:
            if cmd_path in seen:
                continue
            seen.add(cmd_path)

            accent: str = _accent_for_cmd_path(cmd_path)
            display_name: str = " ".join(w.capitalize() for w in cmd_path.replace(".", " ").split())
            emoji: str = EMOJI.get(cmd_path, "")
            nav_label: str = f"{emoji}  {display_name}" if emoji else display_name

            # Translation key for nav.
            nav_key: str = f"dyn_nav_{cmd_path.replace('.', '_')}"
            # Store nav label for all locales.
            for lk in ("en", "pt_BR", "es"):
                _TRANSLATIONS.setdefault(lk, {})[nav_key] = nav_label

            dynamic_pages.append((nav_key, nav_key, None, accent))

        # Ensure we have at least the hard-coded set if nothing was discovered.
        if not dynamic_pages:
            return

        self._pages = list[tuple[str, str, type | None, str]](dynamic_pages)
        self._dynamic = True
        self._dynamic_meta: dict[str, list[ArgOption]] = meta

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
        except (OSError, ValueError, RuntimeError, Exception):
            # Icon setup is optional; ignore expected failures (file missing or unreadable).
            return

    def _build_footer(self) -> None:
        """Build the persistent version-footer bar at the bottom of the window.

        Displays ``mkpfs vX.Y.Z`` sourced from the mkpfs package version string
        via runtime introspection.  Visible in every window state (idle, running,
        error).
        """
        from mkpfs import __version__

        footer: ctk.CTkFrame = ctk.CTkFrame(
            self,
            fg_color=_BG_PANEL,
            corner_radius=0,
            height=26,
        )
        footer.pack(side="bottom", fill="x")
        footer.pack_propagate(False)

        ctk.CTkLabel(
            footer,
            text=f"mkpfs v{__version__}",
            font=("Segoe UI", 9),
            text_color=_TEXT_MUTED,
        ).pack(side="right", padx=(0, 14), pady=2)

    def _build_sidebar(self) -> None:
        """Build the left navigation sidebar with language selector."""
        sidebar: ctk.CTkFrame = ctk.CTkFrame(
            self._main_area,
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

        for key, label_key, _, accent in self._pages:
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

        # Version label removed from sidebar — now lives in the footer bar.

    def _build_content(self) -> None:
        """Pre-instantiate all panels inside the content area."""
        self._content: ctk.CTkFrame = ctk.CTkFrame(self._main_area, fg_color="transparent")
        self._content.pack(side="left", fill="both", expand=True)

        if self._dynamic:
            # Dynamic panels: build from metadata.
            for key, _, _, _ in self._pages:
                # Extract cmd_path from the nav_key (strip dyn_nav_ prefix).
                cmd_path: str = key.removeprefix("dyn_nav_").replace("_", ".")
                options: list[ArgOption] = self._dynamic_meta.get(cmd_path, [])
                panel: BasePanel = DynamicPanel(self._content, cmd_path, options)
                self._panels[key] = panel
        else:
            # Fallback: hard-coded panels (PanelClass is never None here).
            for key, _, PanelClass, _ in self._pages:
                if PanelClass is not None:
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
        global _current_locale
        for locale, name in _LANG_NAMES.items():
            if name == display_name:
                _current_locale = locale
                break
        self._refresh_all_labels()

    def _refresh_all_labels(self) -> None:
        """Propagate the new locale to all sidebar widgets and panels.

        The version footer is static and does not change with locale.
        """
        self._subtitle_label.configure(text=tr("app_subtitle"))
        self._ops_label.configure(text=tr("operations"))
        self._lang_label_widget.configure(text=tr("lang_label"))
        for key, label_key, _, _ in self._pages:
            if key in self._nav_buttons:
                self._nav_buttons[key].configure(text=tr(label_key))
        for panel in self._panels.values():
            panel.refresh_labels()


# ---------------------------------------------------------------------------
# Entry point


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


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
