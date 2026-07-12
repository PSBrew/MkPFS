# PyInstaller standard hook for customtkinter.
# NOTE: This hook file should be named `hook-customtkinter.py` (without any `pyinstaller-` prefix)
# so PyInstaller can discover it using its `hook-<package_name>.py` convention.
# Collect submodules and package data to ensure PyInstaller bundles the package correctly.
from PyInstaller.utils.hooks import collect_data_files, collect_submodules


def _customtkinter_submodule_filter(module_name):
    excluded_parts = (".tests", ".test", ".testing", ".examples", ".docs")
    return not (
        module_name.endswith(excluded_parts)
        or any(part in module_name for part in excluded_parts)
    )


hiddenimports = collect_submodules("customtkinter", filter=_customtkinter_submodule_filter)

datas = collect_data_files("customtkinter")
