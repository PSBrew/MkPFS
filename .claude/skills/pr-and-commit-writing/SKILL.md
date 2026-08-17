---
name: pr-and-commit-writing
description: >
  Write commit messages, PR titles/descriptions, and GitHub comments with a user-first style; apply
  release-drafter-compatible labels; produce release-note-ready PR titles.
context: fork
---

# Writing PRs, commit messages, and GitHub comments

Use whenever you need to: create/edit a PR, write a public commit message, write/edit a GitHub comment,
or assign labels/tags to a PR.

## Goal

Write public-facing GitHub content for non-technical readers first. Keep everything short, friendly,
scannable, and focused on the user problem solved.

## Commit message rules

1. Short, natural-language title (≤50 chars). Emoji optional.
2. Focus on the user-facing problem solved; avoid deep implementation details.
3. Blank line between title and body.
4. Optional body: concise (wrap ~72 cols), user-visible problem + high-level change.

Example:

```text
Avoid broken inner filenames by removing special characters

Some consoles could not mount images when inner filenames had special characters.
This change sanitizes the internal filename, prefers title IDs, and warns when names are changed.
Verification still works even when external and internal names differ.
```

## PR title rules

1. One short sentence (≤72 chars), plain language, user-facing.
2. Describe the problem solved or user impact; avoid implementation details.
3. No Conventional Commit prefixes (no `feat:`, `fix:`, etc.). No emoji.
4. Titles should paste directly into release notes.

Good examples:
- `Fix inner image names that break mounts`
- `Make single-file image names safer`
- `Update the documentation about the verify command`

## PR description rules

Use UTF-8 icons and Markdown.

```md
# Fix inner image names that break mounts

## 🤔 Why?
- Explain the user-visible problem in plain language.

## 🔧 What changed
- 3-5 short bullets. Focus on behavior, not internal code structure.

## 🧪 How to test
- One short command or simple manual flow.
- Link related issues (e.g., Closes #123).

## 💬 Notes for non-technical readers
- Reassure the reader what changed and what did not change.
```

### Writing guidance

- Use emoji lightly for scanning: ✅ 🔧 🧪 🤔 💬 ⚠️ 📦.
- Bullets over dense prose. Speak like you're updating a non-technical maintainer.
- Always state the original problem clearly in **Why?**.
- If contents are unchanged and only metadata/filenames changed, say so explicitly.
- Never mention AI tools or attribute text to any AI tool.
- Clean up PII, local paths, or internal-only details.

## Labels and tags

Use labels that fit `.github/release-drafter-config.yml`. Pick one primary:

- `feature` — new user-facing capability
- `bug` — user-visible fix
- `maintenance` — cleanup, tooling, refactor
- `documentation` — docs-only change
- `dependencies` — dependency update
- `security` — security fix
- `breaking` — breaking change

Other: `skip-changelog` only when the PR should not appear in release notes.
Choose based on user impact first, then implementation details.

## GitHub CLI notes

- `gh pr edit ...` / `gh pr create ...`
- `GH_PAGER=cat gh pr edit <number> --add-label "bug"`

## Final checklist

- [ ] PR title release-note ready (plain sentence, ≤72 chars, no CC prefixes, no emoji)
- [ ] Text explains the problem first; clear **Why?** section for PRs
- [ ] UTF-8 icons used lightly; language understandable to non-technical readers
- [ ] Correct label applied; `skip-changelog` if needed
- [ ] Related issues linked (e.g., Closes #123)
- [ ] No AI attribution; no PII/local paths
- [ ] After editing with `gh`, re-read the published PR to confirm it matches this skill
