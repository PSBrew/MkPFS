# Development Guidelines

## Quick Start

```bash
uv sync --group dev
uv run mkpfs --help
```

## Rules

1. **Package Management**: Use `uv` only (never pip). Install: `uv add pkg`. Upgrade: `uv add --dev pkg --upgrade-package pkg`. Sync deps: `uv sync --group dev`.
2. **Code Quality**: Type hints required. Google-style docstrings. Prefer explicit keyword args. All variables need explicit type annotations (`count: int = 0`). Target Python 3.11 (use `list`, `dict`, `X | None`).
3. **CLI Structure**: Keep CLI wiring in `mkpfs/cli.py` (`build_cli`, `cmd_*`). Keep PFS logic in `mkpfs/pfs.py`. Shared modules: `consts.py` (constants), `pbar.py` (progress/scan), `utils.py` (helpers). Canonical CLI surface: `pack`, `verify`, `inspect`, `tree`, `unpack`.
4. **Testing**: `./run-tests.sh` (runs ruff format + check + pytest). Or: `uv run --frozen pytest`. New features need tests; bug fixes need regression tests. CLI smoke tests in `tests/test_main.py`.
5. **Git**: Always use the `pr-and-commit-writing` skill for commit messages and PRs. Commit titles short natural-language (≤50 chars); PR titles are release-note-ready sentences (≤72 chars) without Conventional Commit prefixes.
6. **Formatting**: `uv run --frozen ruff format .` / `uv run --frozen ruff check . --fix`.
7. **Imports**: Top of file (local imports only when necessary, document why). Catch specific exceptions only.
8. **Naming**: `PFS` in CamelCase symbols, `pfs` in snake_case. Never `Pfs`.
9. **Comments**: Block comments for major phases in long functions (~30+ lines). Present tense, explain why not what.
10. **CLI naming**: One canonical function per subcommand (e.g., `cli_mkpfs_pack_run`). No multiple public aliases.
11. **No AI attribution**: Never mention AI tools in public text (commits, PRs, release notes, etc.).
12. **Subagent cost**: Prefer focused, scoped subagent prompts with minimal context. Avoid passing full conversation history. Use targeted prompts with specific file paths and constraints.
13. **`tmp/` scratch**: Use `./tmp/` for ephemeral files (create `./tmp/<task-name>/` subfolders per task). Never commit files from `./tmp/`.

## Writing Style

Keep README/docs practical, concise, scannable. Prefer bullets over long prose.
- Active voice, present tense. Short paragraphs, short sentences. Factual, no hype.
- One example per command; avoid exhaustive flag lists in README. Fenced code blocks with language hints.
- Markdown only (avoid inline HTML). Line length ~100 cols for prose. Code font for filenames, commands, flags.
- Align README claims with pyproject.toml (name, version, Python, license, URLs).
- Link to CONTRIBUTING.md instead of duplicating policy.

## PyPI Packaging

- Use `pyproject.toml` as the primary source of packaging metadata. Keep core metadata explicit: name, version, supported Python, runtime deps, license, README, keywords, classifiers, project URLs.
- Build and publish both source distributions and wheels. Validate with `uv build` and `uv run --frozen twine check dist/*` before publishing.
- Package name: `mkpfs`; CLI entrypoint defined in pyproject.
- Keep README command reference aligned with CLI surface: `pack`, `verify`, `inspect`, `tree`, `unpack`.
- Keep README at repo root, renderer-safe for PyPI.

## Worktree Map (2 levels)

Quick navigation map for agents. Two levels deep with short descriptions.

- README.md — project overview, install/usage, command reference
- CLAUDE.md — development rules and workflows
- .claude/
  - skills/ — skills (see pointers below)
- mkpfs/
  - __main__.py — entry point (`python -m mkpfs`)
  - cli.py — CLI wiring (`build_cli`, `cmd_*`)
  - pfs.py — core PFS build/verify/inspect logic
  - exfat.py, exfat_writer.py — exFAT reader/writer
  - ampr.py — APR Emu index and helpers
  - pbar.py — progress bar, scan/tree utilities
  - utils.py — shared helpers
  - consts.py — constants used across modules
  - _exfat_upcase.py — exFAT upcase table (generated/static data)
  - logging.py — logging setup/utilities
  - gui/ — GUI package (app, panels, theme, widgets, i18n)
- tests/
  - integration.sh — CLI smoke harness
  - mkpfs/ — pytest suite: test_cli.py, test_pfs.py, test_exfat*.py, test_utils.py, etc.
- .github/
  - workflows/ — CI, stale, release-drafter, auto-assign, gitleaks
  - labels.yml, release-drafter-config.yml, FUNDING.yml, ISSUE_TEMPLATE/
- assets/ — project assets (images/docs)
- run-tests.sh — convenience script: ruff format+check, pytest
- pyproject.toml — project metadata, tooling config
- uv.lock — dependency lockfile

## GitHub CLI Tips

- `GH_PAGER=cat gh <command>` to avoid interactive pager
- `GIT_PAGER='' git <command>` for git commands in automation

## Token efficiency

Respond like a smart caveman. Cut filler, keep technical substance.
- Drop articles (a, an, the), filler (just, really, basically, actually).
- Drop pleasantries (sure, certainly, happy to). No hedging. Fragments fine.
- Technical terms stay exact. Code blocks unchanged.
- Pattern: [thing] [action] [reason]. [next step].

## Skills Pointers

- Related projects index: .claude/skills/related-projects-index/SKILL.md (curated external sources; see references/*.md)
- Commits/PRs: .claude/skills/pr-and-commit-writing/SKILL.md (use when generating public commit/PR text)
- HTML reporting: .claude/skills/html-report-builder/SKILL.md (use for producing self-contained HTML reports under ./tmp/)
