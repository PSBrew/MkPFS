#!/usr/bin/env bash
set -euo pipefail

# Set SKIP_VENV=1 to skip activating the venv
if [ -z "${SKIP_VENV:-}" ] && [ -z "${VIRTUAL_ENV:-}" ] && [ -f ".venv/bin/activate" ]; then
  source ".venv/bin/activate" || { echo 'WARNING: Could not source .venv/bin/activate'; exit 1; }
fi

uv sync

# Install pre-commit hooks
git config --unset-all core.hooksPath || true
uv run pre-commit install --overwrite

# Run formatting and linting (automatically runs on commit)
uv run ruff format .

# Auto Fix
uv run ruff check . --fix

# Execute the tests
uv run --frozen pytest
