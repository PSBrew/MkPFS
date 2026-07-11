# 🤝 Contributing

Thanks for helping improve MkPFS.

This guide is for contributors working on the CLI, library, packaging, or the research material that supports the project.

## 🚀 Before you start

- Use `uv` for all Python dependency and environment work.
- Keep changes focused and easy to review.
- Run the relevant project checks before opening a pull request.
- Prefer updating existing files instead of creating duplicate docs.

## 🧰 Local setup

```bash
uv sync --group dev
uv run pre-commit install
```

## ✅ Common checks

```bash
uv run --frozen pytest
uv run --frozen ruff format .
uv run --frozen ruff check .
uv build
uv run --frozen twine check dist/*
```

## 🧪 What to update where

- `README.md` — public project overview, badges, screenshots, quick-start messaging, sponsorship links
- `CONTRIBUTING.md` — contributor workflow, local setup, checks, and pull request expectations
- `CLAUDE.md` — AI assistant/developer workflow instructions and project-specific coding guidance
- `docs/` — deeper documentation, design notes, and research/supporting material
- `tests/` (and related test files) — coverage for new features, bug fixes, and behavior changes

## 🔎 Pull request expectations

- Keep pull requests scoped to a clear goal.
- Include updated docs or screenshots when user-facing behavior changes.
- Preserve the current blue visual identity when editing README or docs graphics.
- Do not commit one-off temporary files from `./tmp/`.
