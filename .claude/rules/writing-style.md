---
name: writing-style
description: Project conventions for README, wiki, and Markdown formatting (icons, badges, colors, tone, and file layout)
type: project
---

# Writing Style Guide

Purpose: capture the visual and prose style we use across README.md and short wiki-style markdown files so contributors produce consistent, high-quality docs.

Keep this file short and actionable. If you change visual assets or global colors, update this rule.

## High-level tone and voice
- Practical, concise, and slightly technical: assume the reader knows basic tooling but keep onboarding friendly.
- Write in active voice, present tense. Prefer short paragraphs and bullet lists.
- Avoid marketing hyperbole, be factual about capabilities and workflows.
- Do not foreground lifecycle labels such as alpha or beta in user-facing docs unless explicitly requested.

## Visual identity
- Primary brand color: blue. Example palette (use these hex colors in images and banners):
  - Primary: #2563EB (blue)
  - Accent: #3B82F6 (light blue)
  - Surface / panels: #EFF6FF / #DBEAFE (very pale blues)
  - Neutral dark: #0F172A / #0B1733 (text, dark backgrounds)
- Iconography: use UTF-8 emoji for section headings and quick-links. Keep icons consistent and semantically appropriate. Examples:
  - 📚 Documentation
  - 📦 Install
  - ⌨️ Command Overview
  - 🖥️ GUI
  - 💙 Thanks (contributors)
  - 🔗 Related projects
  - 💖 Sponsor
- Badges: prefer shields.io for badges. Style: `style=for-the-badge` for the top cluster. Include: status, PyPI (version), license, Python version. Use flat-square for a second-row group when needed.

## Hero / title block
- Center the hero block. Include in order:
  1. Project icon image (assets/images/icon.png) — rounded with subtle shadow and light border. Example inline style: `style="border-radius:30px; box-shadow:0 10px 30px rgba(37,99,235,0.18); border:4px solid rgba(14,165,233,0.08);"`.
  2. H1: `ProjectName: ShortTagline` (e.g., `MkPFS: Make PSF`). Keep the H1 short.
  3. One-line product sentence (H3 or short paragraph) that expands the acronym and lists the three delivery surfaces when relevant (CLI, library, GUI).
   4. Top badge cluster (status, PyPI, license, python).
  5. Quick-links row (emoji-prefixed links separated by middot ·). Order:
      - 📦 Install · ⌨️ Commands · 💙 Thanks · 🔗 Related projects
     - then a blank line
     - then the sponsor entry on its own line: `💖 Sponsor` (linked badge)

## Images and screenshots
- Store project visuals under `assets/images/` (not `tmp/` and not scattered). Use descriptive names: `hero-banner.svg`, `screenshot-create.svg`, `screenshot-check.svg`, `screenshot-gui.svg`.
- PNG icons ok for favicon/logo; larger illustrations should be SVG when possible.
- Image styling in README: reference images by path only (no base64). Use alt text. Avoid calling them "placeholders" in public docs; instead caption them (e.g., "Screenshot: Create workflow").

## Section structure and headings
- Use emoji-prefixed headings for main sections. Keep consistent H2/H3 hierarchy.
- Typical README section order:
  1. Why / Overview
  2. Main Features (short bullets)
  3. Installation
  4. Command Overview (subcommands listed with short purpose; do not enumerate all flags)
  5. GUI (if present)
  6. Sponsorship (prominent, near top/hero or before contributors)
  7. Special thanks and Contributors (short list)
  8. Related projects (single curated list of external links)
   9. Contributing (short callout linking to CONTRIBUTING.md)

## Command blocks and examples
- Show subcommand usage at the top-level only. For each subcommand, include a one-line summary and a single example invocation (no exhaustive param list in README). Example style:

```bash
mkpfs create --path ./input --output ./game.ffpfs
```

- Use the terminal icon (⌨️) for the Command Overview heading.

## Links and documentation references
- Prefer linking to in-repo guidance in `README.md` or `related-projects/`.
- Keep public links focused on the repository, release artifacts, and source material.

## Style of writing and micro-rules
- Keep sentences short (<= 24 words where practical).
- Use code font (`code`) for file names and command tokens.
- Use backtick code blocks for CLI examples; use fenced triple-backtick with language when showing code.
- Use bullets for feature lists and checklists.
- Keep sponsorship ask polite and specific (what support buys: tests, packaging, docs).
- When writing English prose for README, docs, comments, or wiki pages, avoid using the em dash (—). Prefer commas, hyphens, 'title: subtitle' structure, or a semicolon to separate related ideas in the same paragraph.
- Do NOT use placeholder language that signals unfinished work (remove lines like: "The screenshots below are polished placeholders…").

## Metadata alignment
- Ensure README top claims align with `pyproject.toml` (name, version, supported Python, license, project URLs).
- If README content changes project positioning significantly, update `pyproject.toml` accordingly.

## Contribution & CI notes
- Include a short contributing pointer linking to `CONTRIBUTING.md`.
- Example common-checks snippet should reference our tooling:

```bash
uv sync --group dev
uv run --frozen pytest
uv run --frozen ruff check .
uv run --frozen ruff format .
```

- Do not commit files from `./tmp/`.

## File-level formatting rules
- Keep line-length reasonable (wrap at ~100 columns for prose in README).
- Use Markdown (CommonMark) only — avoid HTML unless necessary for image styling (small inline style for hero icon allowed as above).

## Enforcement and verification
- Before merging README or major docs changes run:
  - `uv run --frozen ruff check .`
  - `uv run --frozen pytest`

## Examples and snippets
- Hero icon HTML: use a rounded image with subtle shadow and small border (see top of README for exact style example).
- Quick links format: Emoji + text links separated by middot `·`. Put Sponsor on its own line after a blank line.

---

Keep this guideline lightweight — update it when the visual direction changes or when new global assets (icons, banners) are added.
