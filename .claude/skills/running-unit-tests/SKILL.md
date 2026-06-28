---
name: running-unit-tests
description: Run project checks/tests and iteratively fix failures until the branch is green. Use this skill when you finish to implement a feature or fix a bug and want to get the branch ready to push.
context: fork
---

# Running and Fixing Tests

Always run `./run-tests.sh` at the end of each feature, bug fix, or refactor to ensure the branch is ready to push. 
This script runs all pre-commit hooks and the full test suite, and it will fail if any issues are found.

These are the steps to follow when you run into test failures:

1. Inspect what changed.
   - Run `git status --short` to see modified files.
   - Review diffs with `git diff --stat` and `git diff` to understand the scope of changes.

2. Run the project test/validation flow.
   - Preferred: run `./run-tests.sh`.
     - Ensures the virtualenv is active.
     - Runs `uv sync` to keep dependencies in sync.
     - Installs pre-commit hooks (`uv run pre-commit install --overwrite`).
     - Formats code with `uv run ruff format .`.
     - Runs linting and auto-fixes with `uv run ruff check . --fix`.
     - Runs the full test suite with `uv run --frozen pytest`.
   - Optional: run pre-commit checks explicitly with `uv run --frozen pre-commit run --all-files` if you want to see hook results directly.
   - Lightweight option (tests only): `uv run --frozen pytest`.

3. Loop until clean.
   - Group related failures by root cause (e.g., one bug vs. multiple independent issues).
   - Apply minimal, readable fixes that keep behavior stable unless tests show the behavior is incorrect.
   - Add or update focused tests for each bug fix.
   - Re-run `./run-tests.sh` (or `uv run --frozen pytest` for a quicker cycle) after each batch of fixes.

4. Final readiness check.
   - Confirm `./run-tests.sh` completes successfully with no failures.
   - Optionally re-run `uv run --frozen pre-commit run --all-files` to catch any hook-specific issues.
   - Summarize what was fixed and list any remaining risks or follow-ups before push.

