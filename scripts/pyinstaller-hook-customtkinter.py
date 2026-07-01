# PyInstaller hook for customtkinter
# Collect submodules and package data to ensure PyInstaller bundles the package correctly.
from PyInstaller.utils.hooks import collect_data_files, collect_submodules

hiddenimports = collect_submodules("customtkinter")

datas = collect_data_files("customtkinter")
