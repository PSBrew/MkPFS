---
name: pr-and-commit-writing
description: >
  Write commit messages, PR titles/descriptions, and GitHub comments with a user-first style; apply 
  release-drafter-compatible labels; produce release-note-ready PR titles.
context: fork
---

# Writing PRs, commit messages, and GitHub comments

Use this skill whenever you need to:
- create or edit a pull request
- write a public commit message
- write or edit a GitHub comment that other people will read
- assign labels or tags to a PR

## Goal

Write public-facing GitHub content for non-technical readers first.

Keep everything:
- short
- friendly
- easy to scan
- focused on the user problem that was solved

## Commit message rules

1. Use a short, natural-language title (≤50 chars). Emoji allowed but optional.
2. Focus on the user-facing problem solved; avoid deep implementation details.
3. Leave a blank line between the title and the body.
4. Optional body: keep concise (wrap ~72 cols) and include the user-visible problem and the high-level change.

Example:

```text
Avoid broken inner filenames by removing special characters

Some consoles could not mount images when inner filenames had special characters.
This change sanitizes the internal filename, prefers title IDs, and warns when names are changed.
Verification still works even when external and internal names differ.
```

## PR title rules

1. One short sentence (≤72 chars), plain language, user-facing.
2. Describe the problem solved or user impact; avoid deep implementation details.
3. No Conventional Commit prefixes (no `feat:`, `fix:`, etc.).
4. Titles should paste directly into release notes.

Good examples:
- `Fix inner image names that break mounts`
- `Make single-file image names safer`
- `Avoid mount failures caused by special characters in inner image names`
- `Update the documentation about the verify command`


## PR description rules

Use UTF-8 icons and Markdown.

Recommended structure:

```md
# Fix inner image names that break mounts

## 🤔 Why? 
- Explain the user-visible problem in plain language.

## 🔧 What changed
- 3-5 short bullets.
- Focus on behavior, not internal code structure.

## 🧪 How to test
- One short command or simple manual flow.
- Link related issues (e.g., Closes #123).

## 💬 Notes for non-technical readers 
- Reassure the reader what changed and what did not change.
```

### Example Pull Request description

```md
# Fix inner image names that break mounts

## 🤔 Why?
- Some consoles could not mount single-file images when the inner filename had special characters.

## 🔧 What changed
- The inner filename is now cleaned automatically by default.
- PlayStation title IDs like `CUSA` and `PPSA` are preferred when found.
- A short warning is shown when the inner filename is renamed.
- Verification still works even when the external and internal file names differ.

## 🧪 How to test
- Pack a single file with special characters and run `mkpfs verify --source-file`.

## 💬 Notes for non-technical readers
- This improves compatibility.
- The file contents do not change, only the internal filename is adjusted.
```

### General Writing guidance

- Use emoji lightly for scanning: ✅ 🔧 🧪 🤔 💬 ⚠️ 📦
- Keep paragraphs short.
- Use bullets over dense prose.
- Speak like you are updating a non-technical maintainer.
- Always mention the original problem clearly in the **Why?** section.
- If the change is user-visible, lead with the user impact.
- If the contents are unchanged and only metadata or filenames changed, say that explicitly.
- Do not mention you are an AI or attribute the text edits or anything to any AI tool like Claude or OpenClaude.
- Clean up any personal information or internal details like local file paths, usernames, or PII.

## Labels and tags

Use labels that fit the release drafter config in `.github/release-drafter-config.yml`.

### Type labels, pick one
- `type: feature`
- `type: bug`
- `type: maintenance`
- `type: docs`
- `type: dependencies`
- `type: security`
- `type: breaking`

### Other labels
- `skip-changelog` only when the PR should not appear in release notes
- Area or workflow labels are fine if the repo uses them, but the main release label should stay compatible with release drafter

### Mapping guidance
- User-visible fix: `type: bug`
- New user-facing capability: `type: feature`
- Docs-only change: `type: docs`
- Cleanup, tooling, refactor, or maintenance work: `type: maintenance`
- Dependency update: `type: dependencies`
- Security fix: `type: security`
- Breaking change: `type: breaking`

Choose labels based on the user impact first, then the implementation details.

## GitHub CLI notes

When editing PRs with `gh`, prefer:
- `gh pr edit ...`
- `gh pr create ...`
- `GH_PAGER=cat gh pr edit <number> --add-label "type: bug"`
- `GH_PAGER=cat gh pr edit <number> --add-label "skip-changelog"`

## Gotchas
- PR titles: plain sentence, no emoji, no Conventional Commit prefixes; release-note ready.
- Use `type:` labels so release drafter categorizes the PR correctly.
- Avoid PII, local paths, or internal-only details in public text.

## Final checklist

Before publishing a commit message, PR body, or comment, check:
- Is the PR title release-note ready (plain sentence, ≤72 chars, no CC prefixes, no emoji)?
- Does the text explain the problem first?
- Is there a clear **Why?** section for PRs?
- Are there UTF-8 icons in the PR description (lightly used)?
- Is the language understandable to a non-technical reader?
- Did you apply the correct `type:` label and `skip-changelog` if needed?
- Did you link related issues (e.g., Closes #123)?
- Did you avoid mentioning any AI tools?
- After editing with `gh`, did you re-read the final published PR title/body and confirm it still matches this skill instead of a generic Markdown template?
- If a repository instruction says to use this skill for PR text, did you follow the full structure here rather than only invoking the skill tool?
