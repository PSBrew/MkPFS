# Worktree map (2 levels)

Quick navigation map for agents. Two levels deep with short descriptions.

- README.md — project overview, install/usage, command reference
- CLAUDE.md — development rules and workflows (AGENTS.md symlink points here)
- .claude/
  - MEMORY.md — unique pointers and links to rules/skills
  - rules/ — coding/writing rules and usage guides (this file lives here)
  - skills/
    - related-projects-index/ — executive index of external sources; references/*.md with deep notes
    - related-project-add/ — skill to add/index a new related project entry
    - pr-and-commit-writing/ — commit/PR message writer skill
    - running-unit-tests/ — quick local test runner guidance
    - html-report-builder/ — build HTML test/report artifacts
- mkpfs/
  - __main__.py — entry point (python -m mkpfs)
  - cli.py — CLI wiring (build_cli, cmd_*)
  - pfs.py — core PFS build/verify/inspect logic
  - exfat.py, exfat_writer.py — exFAT reader/writer
  - ampr.py — APR Emu index and helpers
  - pbar.py — progress bar, scan/tree utilities
  - utils.py — shared helpers
  - consts.py — constants used across modules
  - _exfat_upcase.py — exFAT upcase table (generated/static data)
  - logging.py — logging setup/utilities
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
