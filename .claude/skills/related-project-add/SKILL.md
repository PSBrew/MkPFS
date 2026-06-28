---
name: related-project-add
description: >
  Add a new related project or reference source to the Related Projects index. Investigate the upstream repo/website,
  write an executive-summary reference file under references/, and update the index SKILL.md with a concise entry.
context: fork
---

# Add a related project to the index

Use this skill when the user asks to add a new external project or reference page (GitHub repo, wiki page, website)
into our Related Projects index.

Goal
- Create a high-signal reference file under .claude/skills/related-projects-index/references/ with upstream links only.
- Append a matching executive-summary entry to .claude/skills/related-projects-index/SKILL.md.

Inputs you need
- Upstream URL (GitHub repo, GitHub wiki page, PSDevWiki page, technical blog, etc.)
- Optional: short display name override (defaults to repo or site name)
- Optional: category hint (tooling, wiki, kernel/payload, filesystem format, crypto)

Workflow (do this step-by-step)
1) Identify and scope the target
- Determine if it is: GitHub repository, GitHub wiki, standalone site/page, or multi-page domain.
- Decide a short name and a slug:
  - slug = lowercase kebab-case (letters, digits, hyphens), usually from repo or page title (e.g., liborbispkg, psdevwiki-pfs).

2) Investigate upstream and extract facts
- For GitHub repos:
  - Read README, top-level structure, and key source files/dirs.
  - Clone the repository into a temporary folder and investigate its source code. 
  - Identify important modules, commands, and any tests or templates that prove behavior.
- For websites/wikis:
  - Read the specific page(s); capture the strongest claims, structure/format insights, and how to use it with our work.
- Use tools:
  - web_fetch on the URL for readable content; follow repo links as needed.
  - Optionally web_search to find the canonical page if the provided URL looks non-canonical.

3) Draft the executive summary (3–6 bullets)
- What it is (1 line).
- Why it is relevant to PKG/PFS/exFAT/mounting/crypto/workflows.
- 1–3 key technical points or behaviors (format structure, mount options, key derivation, performance, constraints).
- Optional gotchas/limits.

4) Write the reference file
- Path: .claude/skills/related-projects-index/references/<slug>.md
- Structure template:

  ```md
  # <Display Name> — Reference

  Upstream: <canonical URL>

  Executive summary
  - <bullet 1>
  - <bullet 2>
  - <bullet 3>

  Why it matters
  - <how this helps MkPFS or related tooling>

  Key upstream files/pages
  - <path or page title> — <why it matters>
  - ...

  Notes / gotchas
  - <constraints, partial coverage, edge cases>

  Source index
  - <one or more stable links>
  ```

- Rules:
  - Link to upstream only (no local mirror paths).
  - Keep it compact but complete enough for quick research.
  - Cite exact files/paths where possible (blob/main, wiki page permalinks, named sections).

5) Update the index SKILL with a new entry
- File: .claude/skills/related-projects-index/SKILL.md
- Insert a new section following the existing style, for example:

  ```md
  ## <Display Name>
  - What it is: <one-line description>
  - Relevance: <why it matters to PKG/PFS/exFAT/mounting>
  - Gotchas: <optional short caveat>
  - Upstream: <canonical URL>
  - Internal reference: references/<slug>.md
  ```

- Place the new entry near similar items (e.g., tools with tools, wikis with wikis). If unclear, add at the end of the list.

6) Validate
- All links open and are upstream (no related-projects/* references).
- Reference file exists and has the structure above.
- Index SKILL.md was updated with the correct Internal reference path (references/<slug>.md).

7) Commit/PR hygiene (if requested)
- If the user asks to commit, use the pr-and-commit-writing skill for public text.

Naming conventions and grouping
- Slug: lowercase kebab-case, derived from repo/page (e.g., shadowmountplus, pkgtool, liborbispkg, psdevwiki-pfs).
- Multi-page domains (e.g., PSDevWiki): create one reference file per high-value page (psdevwiki-pfs.md, psdevwiki-pkg-files.md) and add separate index entries, mirroring how we handle PSDevWiki and ShadPKG.

Safety and repo hygiene
- Do not create or reference local mirrors.
- Keep long quotes minimal; link upstream for details.
- Do not modify non-skill areas of the repo unless explicitly asked.

Common pitfalls and guardrails
- Never edit README.md or public docs when using this skill; only modify files under .claude/skills/related-projects-index/*
- Prefer canonical upstream URLs (original repo/site), avoid forks unless canonicalized in the README
- Validate that references/<slug>.md follows the template and links upstream only
- Place the new index entry near similar tools (e.g., after ShadowMountPlus for mounting/compression utilities)

Minimal example usage
- Input: https://github.com/example/repo
- Output files:
  - .claude/skills/related-projects-index/references/example-repo.md (new)
  - .claude/skills/related-projects-index/SKILL.md (appended index entry)

Checklist before finishing
- [ ] Upstream link(s) verified
- [ ] Concise executive summary written (3–6 bullets)
- [ ] Clear “why it matters” mapped to MkPFS/PKG/PFS/exFAT scope
- [ ] Key files/pages cited with stable paths
- [ ] Gotchas/limits captured (if any)
- [ ] Index SKILL updated with Internal reference path
- [ ] No references to deleted related-projects/*
