---
name: Temporary workspace usage
description: Guidance for using ./tmp for scratch files, planning, and generated artifacts
type: reference
---

Use `./tmp/` for transient work only: planning notes, scratch files, ad hoc exports, generated reports, and other temporary artifacts.
Keep one-off filenames descriptive enough to find later, but never rely on anything in `./tmp/` as permanent project state.
Do not commit files from `./tmp/`.
If a task needs a temporary helper script or intermediate output, put it under `./tmp/` and delete it when the work is done.
Create a subfolder for each task/topic like `./tmp/<task-name>/`.
