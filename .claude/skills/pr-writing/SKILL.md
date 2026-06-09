---
name: pr-writing
description: Create or edit public-facing commits, PR titles, PR descriptions, comments, labels, and tags with a user-first style.
context: fork
---

# PR Writing

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

1. Use Conventional Commits for the title.
   - Examples:
     - `fix: avoid broken inner filenames`
     - `feat: make single-file images safer`

2. Keep the title short and human-friendly.
   - Say what problem was solved, not internal implementation details.

3. In the body, keep it simple.
   - Include:
     - `Why:` the user-facing problem
     - `What:` the high-level change
     - `Test:` one short validation note

Example:

```text
🔧 fix: avoid broken inner filenames

Why: some consoles could not mount images when the inner filename had special characters.
What: sanitize the internal filename, prefer title IDs, and warn when names differ during verify.
Test: ran ./run-tests.sh and verified full pytest pass.
```

## PR title rules

1. Write one short sentence.
2. Explain the problem solved.
3. Prefer user language over code language.
4. Avoid deep implementation details.

Good examples:
- `Fix inner image names that break mounts`
- `Make single-file image names safer`
- `Avoid mount failures caused by special characters in inner image names`
- `Updated the documentation about XYZ`


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

## 💬 Notes for non-technical readers 
- Reassure the reader what changed and what did not change.
```

### Example PR description

```md
# Fix inner image names that break mounts ✅

## Why? 🤔
- Some consoles could not mount single-file images when the inner filename had special characters.

## What changed 🔧
- The inner filename is now cleaned automatically by default.
- PlayStation title IDs like `CUSA` and `PPSA` are preferred when found.
- A short warning is shown when the inner filename is renamed.
- Verification still works even when the external and internal file names differ.

## How to test 🧪
- Pack a single file with special characters and run `mkpfs verify --source-file`.

## Notes for non-technical readers 💬
- This improves compatibility.
- The file contents do not change, only the internal filename is adjusted.
```

### Writing guidance

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
- `bug`
- `fix`
- `feature`
- `docs`
- `maintenance`
- `dependencies`
- `security`
- `breaking`

### Other labels
- `skip-changelog` only when the PR should not appear in release notes
- Area or workflow labels are fine if the repo uses them, but the main release label should stay compatible with release drafter

### Mapping guidance
- User-visible fix: `bug` or `fix`
- New user-facing capability: `feature`
- Docs-only change: `docs`
- Cleanup, tooling, refactor, or maintenance work: `maintenance`
- Dependency update: `dependencies`
- Security fix: `security`
- Breaking change: `breaking`

Choose labels based on the user impact first, then the implementation details.

## GitHub CLI notes

When editing PRs with `gh`, prefer:
- `gh pr edit ...`
- `gh pr create ...`
- `gh pr edit <number> --add-label "type: bug"`

## Final checklist

Before publishing a commit message, PR body, or comment, check:
- Is the title short and user-friendly?
- Does the text explain the problem first?
- Is there a clear **Why?** section for PRs?
- Are there UTF-8 icons in the PR description?
- Is the language understandable to a non-technical reader?
- Did you assign sensible labels that match release drafter?
- Did you avoid mentioning any AI tools?
