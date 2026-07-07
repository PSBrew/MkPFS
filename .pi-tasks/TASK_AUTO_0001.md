---
id: TASK_AUTO_0001
state: completed
phase: done
created_at: 2026-07-05T19:34:39.490Z
updated_at: 2026-07-07T00:24:27.891Z
title: I've recently implemented a GUI in this project, and you task is to fist refactor the mkpfs/gui.py mmoving it into small files, logically groupts and easy to understanding inside the mkpfs/gui module (folder). Your goal is to keep the code simple and easy to understand.
---

## feature prompt

I've recently implemented a GUI in this project, and you task is to fist refactor the mkpfs/gui.py mmoving it into small files, logically groupts and easy to understanding inside the mkpfs/gui module (folder). Your goal is to keep the code simple and easy to understand.

## clarifications

Q1: Should each operation panel (Pack Folder, Pack File, Verify, Inspect, Tree, Unpack) become its own file under gui/panels/, or be grouped into fewer files by operation family? This sets the directory layout every other task depends on and decides whether the breakdown yields ~6 panel tasks versus ~2-3 grouped ones.
A1: one file per panel under gui/panels/ (e.g. pack_folder.py, unpack.py), since the request emphasises "small files" and each panel is already self-contained behind BasePanel.
Q2: Should the shared, non-panel infrastructure (theme constants, i18n/tr(), reusable widgets, BasePanel, NavButton) be split into per-concern files, or consolidated into a single gui/core.py? This decides how many "foundation" tasks must land before any panel can be moved, and fixes the import contract (from ..theme import ..., from ..widgets import ...) that every gui/panels/<op>.py file will use, so it gates the ordering and scope of all six panel tasks plus the final app.py task.
A2: split by concern — gui/theme.py (palette + fonts + _PANEL_ACCENT), gui/i18n.py (translations + tr() + locale state), gui/widgets.py (GlassCard/SectionLabel/PathRow/LogPane/NeonButton/OptionRow/NeonCheckbox/NavButton + browse helpers), gui/panels/base.py (BasePanel), gui/app.py (MkPFSApp), with gui/__init__.py re-exporting main to keep the mkpfs-gui entry point working

## tasks

- [x] TASK_0001  Scaffold the `mkpfs/gui/` package and extract `gui/theme.py` + `gui/i18n.py` — move `gui.py` into `gui/__init__.py`, then peel palette/fonts/`_PANEL_ACCENT` into `theme.py` and translations/`tr()`/locale state into `i18n.py`, keeping `mkpfs-gui` working | decisions (explicit user choices — these OVERRIDE the spec doc wherever they conflict; follow them exactly): split shared infrastructure by concern — gui/theme.py holds palette+fonts+_PANEL_ACCENT, gui/i18n.py holds translations+tr()+locale state, gui/__init__.py re-exports main to keep the mkpfs-gui entry point working
- [x] TASK_0002  Extract `gui/widgets.py` — move GlassCard, SectionLabel, PathRow, LogPane, NeonButton, OptionRow, NeonCheckbox, NavButton and the `_browse_*` helpers out of `gui/__init__.py` | decisions (explicit user choices — these OVERRIDE the spec doc wherever they conflict; follow them exactly): split by concern — gui/widgets.py holds GlassCard/SectionLabel/PathRow/LogPane/NeonButton/OptionRow/NeonCheckbox/NavButton + browse helpers
- [x] TASK_0003  Extract `gui/panels/base.py` — create the `gui/panels/` package and move `BasePanel` out of `gui/__init__.py` | decisions (explicit user choices — these OVERRIDE the spec doc wherever they conflict; follow them exactly): split by concern — gui/panels/base.py holds BasePanel
- [x] TASK_0004  Move the Pack Folder panel into `gui/panels/pack_folder.py` | decisions (explicit user choices — these OVERRIDE the spec doc wherever they conflict; follow them exactly): one file per panel under gui/panels/ (e.g. pack_folder.py, unpack.py)
- [x] TASK_0005  Move the Pack File panel into `gui/panels/pack_file.py` | decisions (explicit user choices — these OVERRIDE the spec doc wherever they conflict; follow them exactly): one file per panel under gui/panels/ (e.g. pack_folder.py, unpack.py)
- [x] TASK_0006  Move the Verify panel into `gui/panels/verify.py` | decisions (explicit user choices — these OVERRIDE the spec doc wherever they conflict; follow them exactly): one file per panel under gui/panels/ (e.g. pack_folder.py, unpack.py)
- [x] TASK_0007  Move the Inspect panel into `gui/panels/inspect.py` | decisions (explicit user choices — these OVERRIDE the spec doc wherever they conflict; follow them exactly): one file per panel under gui/panels/ (e.g. pack_folder.py, unpack.py)
- [x] TASK_0008  Move the Tree panel into `gui/panels/tree.py` | decisions (explicit user choices — these OVERRIDE the spec doc wherever they conflict; follow them exactly): one file per panel under gui/panels/ (e.g. pack_folder.py, unpack.py)
- [x] TASK_0009  Move the Unpack panel into `gui/panels/unpack.py` | decisions (explicit user choices — these OVERRIDE the spec doc wherever they conflict; follow them exactly): one file per panel under gui/panels/ (e.g. pack_folder.py, unpack.py)
- [x] TASK_0010  Extract `gui/app.py` and finalise `gui/__init__.py` — move `MkPFSApp` and `main()` into `app.py`, reduce `__init__.py` to re-export `main` | decisions (explicit user choices — these OVERRIDE the spec doc wherever they conflict; follow them exactly): split by concern — gui/app.py holds MkPFSApp, gui/__init__.py re-exports main to keep the mkpfs-gui entry point working

