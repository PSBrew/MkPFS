---
name: writing-style
description: Quick writing guide for README and short Markdown docs
type: project
---

# Writing Style (quick guide)

Keep docs practical, concise, and easy to scan. Prefer bullets over long prose.

## Tone
- Active voice, present tense. Short paragraphs, short sentences.
- Factual, no hype. Explain what it does and how to use it.

## Structure (README defaults)
1) Overview (why it exists, one paragraph)
2) Main features (short bullets)
3) Installation
4) Command overview (one‑line per subcommand + one example)
5) Related projects (curated, short)
6) Contributing + Thanks + Sponsor (brief pointers)

## Examples
- Show one example per command; avoid exhaustive flag lists in README.
- Use fenced code blocks with language hints for CLI/code.

## Formatting
- Use Markdown only; avoid inline HTML except when necessary.
- Reasonable line length (~100 cols for prose).
- Use code font for file names, commands, and flags.

## Consistency
- Align README claims with pyproject.toml (name, version, Python, license, URLs).
- Link to CONTRIBUTING.md instead of duplicating policy.
- Don’t commit ./tmp/.

## Skills to use for public text and reports
- Commits/PRs: load .claude/skills/pr-and-commit-writing/SKILL.md when generating commit messages or PR titles/descriptions (public text must follow that skill’s rules).
- HTML reporting: load .claude/skills/html-report-builder/SKILL.md when producing HTML summaries/reports (keeps format consistent and saved under ./tmp/).

That’s it — keep it simple and useful.
