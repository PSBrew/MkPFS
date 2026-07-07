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
5. **Git**: Always use the `pr-and-commit-writing` skill for commit messages and PRs. Follow its rules: commit messages use short natural-language titles (≤50 chars); PR titles are simple, release‑note‑ready sentences (≤72 chars) without Conventional Commit prefixes.
6. **Formatting**: `uv run --frozen ruff format .` / `uv run --frozen ruff check . --fix`.
7. **Imports**: Top of file (local imports only when necessary, document why). Catch specific exceptions only.
8. **Naming**: `PFS` in CamelCase symbols, `pfs` in snake_case. Never `Pfs`.
9. **Comments**: Block comments for major phases in long functions (~30+ lines). Present tense, explain why not what.
10. **CLI naming**: One canonical function per subcommand (e.g., `cli_mkpfs_pack_run`). No multiple public aliases.
11. **No AI attribution**: Never mention AI tools in public text (commits, PRs, release notes, etc.).
12. **Subagent cost**: Prefer focused, scoped subagent prompts with minimal context. Avoid passing full conversation history. Use targeted prompts with specific file paths and constraints.
13. **`tmp/` scratch**: Use `./tmp/` for ephemeral files. Never commit files from `./tmp/`.

## GitHub CLI Tips

- `GH_PAGER=cat gh <command>` to avoid interactive pager
- `GIT_PAGER='' git <command>` for git commands in automation

## Docs & Skills Pointers

- Worktree map: .agents/rules/worktree.md (2-level repository map for fast navigation)
- Writing style: .agents/rules/writing-style.md (quick guide for README/docs)
- Related projects index: .agents/skills/related-projects-index/SKILL.md (curated external sources; see references/*.md)
- Commits/PRs: .agents/skills/pr-and-commit-writing/SKILL.md (use when generating public commit/PR text)
- HTML reporting: .agents/skills/html-report-builder/SKILL.md (use for producing public commit/PR text)
- TEMP folder usage: .agents/rules/tmp-usage.md (use ./tmp/ for transient artifacts only)

## Token efficiency

Respond like smart caveman. Cut all filler, keep technical substance.
- Drop articles (a, an, the), filler (just, really, basically, actually).
- Drop pleasantries (sure, certainly, happy to).
- No hedging. Fragments fine. Short synonyms.
- Technical terms stay exact. Code blocks unchanged.
- Pattern: [thing] [action] [reason]. [next step].
