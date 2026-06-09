# Development Guidelines

This document contains critical information about working with this codebase.
Follow these guidelines precisely.

## Rules

1. Package Management
    - ONLY use uv, NEVER pip
    - Installation: `uv add package`
    - Upgrading: `uv add --dev package --upgrade-package package`
    - FORBIDDEN: `uv pip install`, `@latest` syntax

2. Code Quality
    - Type hints required for all code
    - Follow existing patterns exactly
    - Use Google style for docstring
    - Prefer explicit keyword arguments when calling functions or instantiating classes in Python; avoid relying on
      parameter ordering.
    - All functions must include pydocs (Google style) describing what the function does, its parameters, return value(
      s), and any raised exceptions.
    - Keep CLI wiring in `mkpfs/cli.py` (`build_cli`, `cmd_*`) and keep PFS format/build/inspection logic in
      `mkpfs/pfs.py`.
    - Reuse shared modules for cross-cutting concerns: constants in `mkpfs/consts.py`, progress and tree scan flow
      in `mkpfs/pbar.py`, and utility helpers in `mkpfs/utils.py`.
    - Current CLI command surface is `pack`, `verify`, `inspect`, `tree`, and `unpack`; keep docs aligned when
      changing this surface.

3. Testing Requirements
    - Framework: `uv run --frozen pytest`
    - run ./run-tests.sh for convenience
    - `./run-tests.sh` also runs `uv run ruff format .` and `uv run ruff check . --fix` before tests, so it can modify
      files.
    - Coverage: test edge cases and errors
    - New features require tests
    - Bug fixes require regression tests
    - Keep CLI smoke behavior covered in `tests/test_main.py`; update the help-text assertion when CLI
      description/output changes.
    - Release validation should build the package and run `twine check` before publish

4. Temporary Artifacts and Reports
    - Use `./tmp/` for scratch files, planning notes, generated HTML reports, and other transient outputs.
    - Keep `./tmp/` out of commits.
    - For detailed research or long-form answers, provide the normal text response and also save a companion HTML
      report under `./tmp/` with a clickable file path.

5. Git
    - Follow the Conventional Commits style on commit messages.
    - When creating or editing public commit messages, PR titles, PR descriptions, PR comments, labels, or tags,
      use the `pr-writing` skill.

6. Read-only legacy
    - The `./legacy` directory is read-only. The agent MUST NOT create, edit, move, or delete any file or folder under `./legacy`. Read-only access only.

## Code Formatting and Linting

1. Ruff
    - Format: `uv run --frozen ruff format .`
    - Check: `uv run --frozen ruff check .`
    - Fix: `uv run --frozen ruff check . --fix`
2. Pre-commit
    - Config: `.pre-commit-config.yaml`
    - Runs: on git commit
    - Tools: Ruff (Python)

3. Type annotations (project preference)
    - The project targets Python 3.11: prefer built-in generic types (list, dict, tuple, set) instead of
      typing.List/Dict/Tuple/Set.
    - Use the `X | None` union form instead of `Optional[X]` where appropriate.
    - Annotate all function and method signatures with types.
    - All local variables must have explicit type annotations at their definition site, even for simple literals.
      Examples: `count: int = 0`, `name: str = ""`.
    - Prefer built-in generic types and explicit variable annotations; avoid relying on implicit type inference for
      readability and static analysis.
    - Always reason if variables are nullable and select the appropriate type. Sometimes differentiating None from a 0
      or empty string is the key to good code.

## GitHub CLI Tips

When using `gh` command in terminal automation:

- **Disable pager to avoid interactive prompts**: Use `GH_PAGER=cat gh <command>` to prevent pager from opening and
  blocking terminal execution
- **Export logs to file**: `GH_PAGER=cat gh run view <run-id> > output.txt 2>&1` to capture full output without
  interactive delays
- **Check workflow status**: `GH_PAGER=cat gh run view <run-id> --json conclusion,status` for structured status data
- Default: `gh` commands may open `less` pager, which opens the alternate terminal buffer and blocks async execution
- **GIT_PAGER** also opens alternate buffer — use `GIT_PAGER='' git <command>` to suppress for git commands
- **Prefer Python subprocess** for automation that requires capturing output reliably:
  `subprocess.run(['gh', ...], capture_output=True, text=True, env={**os.environ, 'GH_PAGER': 'cat'})`

## Writing style preference

When writing in natural language README, docs, comments, or wiki pages, avoid using the em dash (—). Prefer commas,
hyphens, 'title: subtitle' structure, or a semicolon to separate related ideas and maintain consistent punctuation
across project documentation in the same paragraph.

### `PFS` Capitalization Rule

- **Class / Symbol Names**: Use uppercase `PFS` (all three letters) when it appears inside class names, types, or other
  identifiers that use CamelCase or TitleCase. Examples: `PFSExtractionResult`, `PFSImageInfo`, `PFSOperationResult`.
- **Variables / Functions / snake_case**: Use lowercase `pfs` for variable names, function prefixes, and snake_case
  identifiers. Examples: `pfs_gen_sign_key`, `read_pfs_info`, `pfs_version`.
- **Never** use `Pfs` (mixed-case) — either `PFS` or `pfs` is correct depending on the context.

### Long-function block comments

- For functions that are long (roughly >30 lines) or that contain multiple logical phases, add a single-line comment
  above each major block explaining its purpose. Keep comments succinct and in present tense.
- These single-line comments are NOT a replacement for proper function docstrings; they should summarize the block
  intent (for example: `# Walk source tree and collect file metadata`).
- Prefer comments that clarify why a block exists or what it accomplishes, not restating what the code already shows.

## Additional coding preferences (user-provided)

The following items were requested by the project maintainer and should be considered part
of the repository coding norms. They clarify a few linting and architectural choices that
help keep the CLI layer predictable and easy to maintain.

- Place all imports at the top of the file, unless a local import is strictly necessary (document the reason when
  used). This helps static analysis and tools like ruff/pylint.
- Avoid catching broad exceptions (for example, `except Exception:`). Catch specific exception types and document why a
  catch-all is required if ever used.
- Use `from __future__ import annotations` only when necessary (for forward references or to delay evaluation of
  annotations). Do not add it by default to every module.
- Avoid duplicate code. When similar logic appears in multiple places, extract a small helper or canonical function so
  behavior is implemented in a single place.
- For primary CLI subcommands prefer a single, canonical function name (do not create multiple public aliases). Use
  clear hierarchical names such as `cli_mkpfs_create_run`, `cli_mkpfs_check_run`, `cli_mkpfs_ls_run`, etc.
  Backwards-compatibility aliases may be
  provided temporarily, but the main codebase should call and test the canonical names.
- Follow pylint/ruff style advice where practical: explicit imports, typed signatures, and minimal use of
  runtime-affecting globals.
- Do not mention you are an AI or attribute the text edits or anything to any AI tool like Claude or OpenClaude.
- Never include generator or AI attribution lines in public-facing project text such as commit messages, PR titles,
  PR bodies, PR comments, release notes, changelog entries, or similar artifacts.
- When using the `pr-writing` skill, do not stop at invoking it. You must make the final public text match the skill's structure and checklist before publishing or editing any commit, PR, comment, label, or tag.

## Agent / Tooling note

- When using automation helpers that apply patches (for example the internal `apply_patch` tool), always provide a
  short, clear `explanation` parameter describing the intent of the change. Omitting this required field causes the
  tool to fail with a "Missing explanation parameter" error. Including the `explanation` helps reviewers and tooling
  understand the purpose of edits.

---

Keep repository instructions here short and durable. Put detailed public-writing rules in the `pr-writing` skill and
use that skill whenever you need to create or edit commits, PRs, comments, labels, or tags.
