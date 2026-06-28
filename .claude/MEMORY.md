# Project Memory

This file is a curated, durable knowledge base for active development and testing in this repository.
Keep entries concise, source-backed, and oriented toward repeatable workflows.

## How To Use This Memory

- Read this file first for high-signal project context before deep investigation.
- Treat this as a navigation layer; use linked source files as the ground truth.
- Prefer adding compact bullets over long prose.
- When behavior changes, update the related section and keep references current.

## Core References

- [PyPI project guidelines](rules/pypi-project-guidelines.md) — packaging checklist, README guidance, and release-validation references.
- [Root agent rules](../AGENTS.md) — canonical coding, testing, and style expectations used by local agent workflows.
- [Claude agent mirror](../CLAUDE.md) — synchronized agent guidance used by local `.claude` workflows.
- Architecture map: keep CLI wiring in [`mkpfs/cli.py`](../mkpfs/cli.py), and keep PFS format/build/inspection logic in [`mkpfs/pfs.py`](../mkpfs/pfs.py).
- Shared modules: constants in [`mkpfs/consts.py`](../mkpfs/consts.py), progress/tree scan in [`mkpfs/pbar.py`](../mkpfs/pbar.py), helpers in [`mkpfs/utils.py`](../mkpfs/utils.py).
- Current CLI surface: `create`, `check` (`verify` alias), `ls`, `info`, `analyze` (`analyse` alias), and `extract`; keep docs and smoke tests aligned.
- CLI smoke test anchor: [`tests/test_main.py`](../tests/test_main.py) validates help output text and should be updated when CLI description text changes.
- Convenience validation script: [`run-tests.sh`](../run-tests.sh) runs `uv sync`, installs pre-commit hooks, runs Ruff format/check with `--fix`, then runs pytest.

## Related Projects Knowledge Base

Moved to skill: [.claude/skills/related-projects-index/SKILL.md](../.claude/skills/related-projects-index/SKILL.md)

- Use the skill for executive summaries and authoritative upstream links.
- For deep dives, open the internal reference files under `related-projects/*.md`.
- This memory no longer carries per-project details to avoid duplication and drift.

## Update Standard

- Keep each entry factual, short, and tied to concrete source links.
- Prefer stable paths over temporary artifacts.
- Do not store scratch notes here; use tmp for transient work.
