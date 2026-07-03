---
id: TASK_AUTO_0001
state: in_progress
phase: done
created_at: 2026-07-01T14:06:42.651Z
updated_at: 2026-07-03T10:16:04.546Z
title: I've recently implemented a simple GUI to allow some users to run the mkpfs commands without having to use the command line directly.
---

## feature prompt

I've recently implemented a simple GUI to allow some users to run the mkpfs commands without having to use the command line directly.                                              

The problem is that the GUI is outdated: it does not use the latest commands and it is missing many options for each subcommand.                                                   

I want you to refactor the GUI so it reflects all the subcommands we have, and add an "Advanced settings" area that displays settings based on the parameters available for each   
subcommand.

Some subcommands (for example, pack folder) have different modes (e.g. --raw (folder -> FFPFS) and the mode that wraps Fodler -> exFAT -> FFPFSC). These should be presented as primary options.
                                                                                                                                                                            
Each main command should be selectable from the left-side navigation (pack file, pack folder, tree, verify, exfat, etc.).
                                                                                                                                                                            
Also, the gui module is currently too complex and implemented as a single file. Instead of using gui.py, create a GUI package (a module folder) and split the code into 3–6 modules that group related parts logically. The goal is to make the GUI easy to maintain and simple to update when new commands or options are added.

One small subtask: show the correct mkpfs version in the footer (it currently appears to be hardcoded to 1.0.0). Also, when an input file is selected, if the output field in the  
same form is empty, default the output path to the same folder as the input and prefill a sensible output filename and extension based on the selected operation.

Another subtask: update the GUI so it captures and displays CLI progress bars. The GUI should present the progress both in the shell output area and as a native GUI progress bar  
with a status label that mirrors the shell progress (percentage and phase text).

Finally, the window must be resizable and maximizable, and the layout should adapt to different screen sizes. You may enforce a reasonable minimum size, but users must be able to 
maximize the window.

In the end, I want a polished, OS-independent UI that supports all mkpfs commands and options, is easy to use, and looks professional.

## clarifications

Q1: Should the refactor keep the existing CustomTkinter/tkinter UI stack, or should we migrate the GUI to a different toolkit (e.g., PySide6/PyQt) before splitting work? This choice changes dependencies, packaging, available widgets (native vs themed), how progress bars and subprocess output are integrated, and therefore which implementation tasks and modules are needed first.
A1: keep CustomTkinter/tkinter to minimize scope, preserve current behavior and packaging, and focus tasks on modularization, command/option mapping, progress parsing, and responsive layout.
Q2: Should the GUI discover available subcommands/options at runtime (by importing the mkpfs package or parsing mkpfs --help) so the UI is generated dynamically, or should it be driven from a static declarative schema file in the repo that must be updated when commands change? This choice determines whether we need runtime introspection and help-parsing/proc-handling tasks (and fallbacks) versus tasks to design, validate, and maintain a single authoritative UI schema.
A2: discover commands/options dynamically by first importing the mkpfs package to read its command/option metadata and fall back to parsing mkpfs --help if import metadata isn't available, so the GUI stays in sync automatically.
Q3: May this refactor add a small shared GUI-support API inside mkpfs itself for command metadata, default output naming, and progress events, or must the new GUI stay a pure consumer of the existing CLI/help text without changing core modules? This most changes the split because it decides whether we first land reusable core adapters/hooks or instead build brittle GUI-side parsers around argparse help and terminal output.
A3: allow a small shared API in mkpfs (reusing the existing argparse builders and pbar.Progress) so the GUI package stays thin and future command changes only need core updates in one place

## tasks

- [x] TASK_0001  Add shared mkpfs metadata and progress hooks | decisions (explicit user choices — these OVERRIDE the spec doc wherever they conflict; follow them exactly): allow a small shared API in mkpfs itself for command metadata, default output naming, and progress events; discover commands/options dynamically by first importing the mkpfs package and fall back to parsing mkpfs --help if import metadata isn't available
- [x] TASK_0002  Split the GUI into a package with focused modules | decisions (explicit user choices — these OVERRIDE the spec doc wherever they conflict; follow them exactly): keep CustomTkinter/tkinter to minimize scope, preserve current behavior and packaging, and focus on modularization
- [x] TASK_0003  Build dynamic command navigation and option forms | decisions (explicit user choices — these OVERRIDE the spec doc wherever they conflict; follow them exactly): discover commands/options dynamically by first importing the mkpfs package and fall back to parsing mkpfs --help if import metadata isn't available; allow a small shared API in mkpfs itself for command metadata, default output naming, and progress events; keep CustomTkinter/tkinter to minimize scope
- [x] TASK_0004  Implement default output naming, footer versioning, and progress mirroring | decisions (explicit user choices — these OVERRIDE the spec doc wherever they conflict; follow them exactly): allow a small shared API in mkpfs itself for command metadata, default output naming, and progress events
- [x] TASK_0005  Make the window responsive, resizable, and maximizable | decisions (explicit user choices — these OVERRIDE the spec doc wherever they conflict; follow them exactly): keep CustomTkinter/tkinter to minimize scope, preserve current behavior and packaging

