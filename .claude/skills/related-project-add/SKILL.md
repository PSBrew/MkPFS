---
name: related-project-add
description: >
  Add a new related project or reference source to the Related Projects index. Investigate the upstream repo/website,
  write an executive-summary reference file under references/, and update the index SKILL.md with a concise entry.
context: fork
---

# Add a related project to the index

Use when the user asks to add a new external project or reference page (GitHub repo, wiki page, website)
into our Related Projects index.

## Goal

- Create a high-signal reference file under `.claude/skills/related-projects-index/references/` with upstream links only.
- Append a matching executive-summary entry to `.claude/skills/related-projects-index/SKILL.md`.

## Inputs

- Upstream URL (GitHub repo, wiki page, PSDevWiki page, technical blog, etc.)
- Optional: short display name override (defaults to repo or site name)
- Optional: category hint (tooling, wiki, kernel/payload, filesystem format, crypto)

## Workflow

1. **Identify and scope the target.** Determine if it's a GitHub repo, GitHub wiki, standalone site/page, or multi-page domain. Pick a slug = lowercase kebab-case (letters, digits, hyphens), usually from repo or page title (e.g., `liborbispkg`, `psdevwiki-pfs`).

2. **Investigate upstream and extract facts.**
   - GitHub repos: read README, top-level structure, key source files/dirs; optionally clone into a temp folder to investigate source. Identify important modules, commands, tests/templates that prove behavior.
   - Websites/wikis: read the specific page(s); capture strongest claims, structure/format insights, how it applies to our work.
   - Tools: `web_fetch` on the URL; optionally `web_search` to find the canonical page if the URL looks non-canonical.

3. **Draft the executive summary (3–6 bullets):** what it is (1 line), why it's relevant to PKG/PFS/exFAT/mounting/crypto, 1–3 key technical points, optional gotchas/limits.

4. **Write the reference file** at `.claude/skills/related-projects-index/references/<slug>.md`:

   ```md
   # <Display Name> — Reference

   Upstream: <canonical URL>

   Executive summary
   - <bullet 1>
   - <bullet 2>

   Why it matters
   - <how this helps MkPFS or related tooling>

   Key upstream files/pages
   - <path or page title> — <why it matters>

   Notes / gotchas
   - <constraints, partial coverage, edge cases>

   Source index
   - <one or more stable links>
   ```

   Link upstream only (no local mirror paths). Cite exact files/paths where possible (`blob/main`, wiki permalinks, named sections). Keep compact but complete enough for quick research.

5. **Update the index SKILL** at `.claude/skills/related-projects-index/SKILL.md`. Insert a new section following the existing style, placed near similar items (tools near tools, wikis near wikis; if unclear, append at the end):

   ```md
   ## <Display Name>
   - What: <one-line description>
   - Relevance: <why it matters to PKG/PFS/exFAT/mounting>
   - Gotchas: <optional short caveat>
   - Upstream: <canonical URL>
   - Internal: references/<slug>.md
   ```

6. **Validate.** All links open and are upstream (no `related-projects/*` references). Reference file exists with the structure above. Index SKILL.md updated with correct `Internal: references/<slug>.md` path.

7. **Commit/PR hygiene** (if requested): use the `pr-and-commit-writing` skill for public text.

## Naming and grouping

- Slug: lowercase kebab-case, derived from repo/page (e.g., `shadowmountplus`, `pkgtool`, `liborbispkg`, `psdevwiki-pfs`).
- Multi-page domains (e.g., PSDevWiki): create one reference file per high-value page (`psdevwiki-pfs.md`, `psdevwiki-pkg-files.md`) and add separate index entries, mirroring how we handle PSDevWiki and ShadPKG.

## Guardrails

- Never edit README.md or public docs when using this skill; only modify files under `.claude/skills/related-projects-index/*`.
- No local mirrors. Keep long quotes minimal; link upstream for details.
- Don't modify non-skill areas of the repo unless explicitly asked.
- Prefer canonical upstream URLs (original repo/site); avoid forks unless canonicalized in the README.
