"""Graphical user interface for mkpfs - futuristic neon glassmorphism design."""

import builtins
import contextlib
import io
import queue
import threading
from pathlib import Path
from tkinter import filedialog
from typing import Any, ClassVar

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
_BORDER = "#152035"
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
        kwargs.setdefault("height", 240)
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

    def _on_run(self) -> None:
        """Clear log and launch the background worker thread."""
        if self._busy:
            return
        self._log.clear()
        self._busy = True
        self._run_btn.configure(state="disabled", text=tr("running"))
        self._progress.start()
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
    """Main application window with neon sidebar and language selector."""

    _PAGES: ClassVar[list[tuple[str, str, type, str]]] = [
        ("nav_pack_folder", "nav_pack_folder", PackFolderPanel, _NEON_BLUE),
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
        except Exception:
            pass

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
        global _current_locale
        for locale, name in _LANG_NAMES.items():
            if name == display_name:
                _current_locale = locale
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
