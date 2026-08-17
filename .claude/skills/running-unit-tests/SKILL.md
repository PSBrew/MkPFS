---
name: running-unit-tests
description: >
  Run formatting, linting, and tests; then iteratively fix failures until the branch is green.
  Use after implementing a feature or fixing a bug to get the branch ready to push.
  Triggers: "tests", "run tests", "lint", "format", "CI red", "fix failing tests".
context: fork
---

# Running and Fixing Tests

Run `./run-tests.sh` at the end of each feature, bug fix, or refactor to ensure the branch is ready to push.
It activates `.venv`, runs `uv sync`, installs pre-commit hooks, formats with `ruff format`,
auto-fixes with `ruff check --fix`, then runs `uv run --frozen pytest`.

## Workflow

1. **Inspect what changed.** `git status --short`, `git diff --stat`, `git diff`.
2. **Run the validation flow.**
   - Preferred: `./run-tests.sh` (full flow above).
   - Tests only: `uv run --frozen pytest`.
   - Pre-commit explicitly: `uv run --frozen pre-commit run --all-files`.
3. **Loop until clean.**
   - Group failures by root cause.
   - Apply minimal, readable fixes; keep behavior stable unless tests show it's incorrect.
   - Add or update focused tests for each bug fix.
   - Re-run `./run-tests.sh` (or `uv run --frozen pytest` for quicker cycles) after each batch.
4. **Final readiness check.** Confirm `./run-tests.sh` passes cleanly. Optionally re-run pre-commit.
   Summarize what was fixed and list any remaining risks before push.

## Setup notes

- First-time setup: if `.venv/` doesn't exist, run `uv sync` once, or run `./run-tests.sh`.
- Different virtualenv: set `SKIP_VENV=1` and ensure `python3` resolves to the desired environment.
- Faster loops: `uv run --frozen pytest -k <pattern> -q` to target tests, then finish with full `./run-tests.sh`.
