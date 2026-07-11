PR #89 — GUI progress & Pack exFAT manual verification checklist

Branch: feat/gui-improvements-v2
Commit: 7791255 (latest pushed)
PR: https://github.com/PSBrew/MkPFS/pull/89

Goal

- Verify the GUI progress bar shows the real progress of CLI operations and that the log pane preserves readable progress output for later review, and confirm the new "Pack exFAT" panel is present and its output auto-populates.

Prerequisites

- Checkout branch: git fetch && git checkout feat/gui-improvements-v2
- Activate your development environment and install deps as your project normally requires.
- Prepare a sample source directory with several files so packing takes > a few seconds (so progress is visible).

How to launch the GUI

- Run: python -m mkpfs.gui.app
- Or: python -c "from mkpfs.gui.app import main; main()"

Manual checklist (do these steps)

1) Locate the panel
   - In the sidebar confirm the order: 
     • Pack Folder
     • Pack exFAT
     • Pack File
     ...
   - Select "Pack exFAT" (if you use another language, pick the localized label).

2) Source selection and auto-population
   - Click Browse and choose the prepared source folder.
   - Confirm the Output field auto-populates to: <parent_of_src>/<src_basename>.img
   - Confirm auto-population occurs only when the Output field was empty (typing a custom output should persist).

3) Run and observe progress
   - Click Run.
   - Expected visual behavior:
     - Progress bar moves from indeterminate → determinate on the first progress event.
     - Progress bar advances roughly in step with CLI progress (per-phase updates).
     - Phase label updates with the current phase name (e.g., "scan", "build", "write").

4) Log pane expectations
   - You should see compact per-phase completion lines such as:
       ✓ scan: 100%
       ✓ build: 100%
     and a final line like:
       ✓ Completed successfully.
   - The log should not be full of ephemeral overwritten fragments — only readable summaries and final messages.

5) Responsiveness
   - While the operation runs, the GUI should remain responsive (you can move the window, interact with other widgets). If it appears frozen or the OS reports the app as unresponsive, capture evidence.

Collect evidence on failure

- If anything fails collect:
  - Screenshots or a short screen recording showing the frozen UI / log behavior.
  - Terminal output if the GUI was started from a terminal (copy the output).
  - OS and Python version used for the test.

Follow-up actions

- If verification passes: reply here or add a PR comment with OS/time and “manual verification passed” so we can proceed to review/merge.
- If verification fails: attach the evidence and I will propose and implement a mitigation (options: serialize listener swap, ContextVar already used but we can switch to subprocess-mode execution to avoid in-process blocking).

Notes

- The branch contains the ContextVar-based listener wiring, per-phase log summaries, improved CR handling in logs, and the new Pack exFAT panel with auto-populate behavior.
- Tests were run locally: 418 passed, 1 skipped (full suite).

Thank you — please run these checks on a machine with a display and report back the results.