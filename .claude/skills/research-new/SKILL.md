---
name: research-new
description: Bootstrap a new research topic from the standard template
when-to-invoke: When the user wants to start a brand new research investigation
---

# Research: New Topic

Bootstrap a complete research workspace for a new topic.

## Prompt Template

When invoked, use this prompt to gather requirements:

```
I'll set up a new research workspace. A few questions:

1. **Topic slug** (lowercase, hyphens, e.g. `wgp-42`): ____
2. **Full topic name** (e.g. "Widget Protocol (WGP-42)"): ____
3. **One-liner** (what are we investigating?): ____
4. **Initial goal** (what does "done" look like?): ____
```

## Directory Structure

Create this tree under `research/<topic>/`:

```
research/<topic>/
  GOAL.md              # research goal, scope, success criteria
  INDEX.md             # flat file registry with one-line descriptions
  LOG.md               # session log, newest entries first
  MEMORY.md            # cross-session facts, dead ends, decisions
  README.md            # topic overview and quick links
  ROADMAP.md           # prioritized task list
  STATUS-data.json     # machine-readable progress dashboard data
  STATUS-data.schema.json  # JSON schema for STATUS-data.json
  STATUS.html          # beautiful dashboard that loads STATUS-data.json
  data/                # raw samples, firmware dumps, test images
  key_findings/        # canonical conclusions (specs, assessments)
  knowledge_base/      # numbered investigation documents (NNN-*.md)
  outputs/             # generated artifacts (JSON exports, parsed data)
  reports/             # phase reports (NNN_title.md + .html pairs)
  scripts/             # analysis scripts (NNNN_description.py)
  subtasks/            # active subtask specs (NNN_description.md + .html)
  subtasks/done/       # completed subtask archives
```

## STATUS-data.json Schema

Generate `STATUS-data.schema.json` first (from `research/STATUS-data.schema.json` template), then populate `STATUS-data.json` with this structure:

```json
{
  "meta": {
    "schema_version": "1.0",
    "generated": "<ISO-8601>",
    "generator": "research-new"
  },
  "topic": {
    "name": "<full topic name>",
    "slug": "<slug>",
    "one_liner": "<one-line description>",
    "started": "<YYYY-MM-DD>",
    "last_updated": "<YYYY-MM-DD>"
  },
  "progress": {
    "overall_pct": 0,
    "current_phase": "<phase name>",
    "phases": [
      { "name": "<Phase 1>", "status": "in_progress", "pct": 0, "when": "<date range or null>" }
    ]
  },
  "components": [],
  "key_documents": [],
  "blockers": [],
  "breakthroughs": [],
  "next_steps": [
    { "priority": 1, "task": "<first task>", "owner": "agent" }
  ],
  "stats": {
    "scripts": 0, "knowledge_docs": 0, "reports": 0,
    "subtasks_open": 0, "subtasks_done": 0, "data_files": 0
  },
  "quick_links": [],
  "recent_files": [],
  "session_summary": {
    "total_sessions": 0, "last_session": null,
    "total_hours": 0, "next_session_focus": null
  }
}
```

## Steps

1. Gather topic info from user (use prompt template above)
2. Create all directories listed above
3. Generate `STATUS-data.schema.json` from `research/STATUS-data.schema.json`
4. Generate `STATUS.html` from the dark-themed dashboard template (loads STATUS-data.json via fetch)
5. Populate each file using these content rules:
   - **GOAL.md**: Objective, in-scope, out-of-scope, success criteria, non-goals
   - **INDEX.md**: Two sections: "Files" (all files with one-line descriptions) and "External References" (empty initially)
   - **LOG.md**: First entry with date, session 1, initial setup done
   - **MEMORY.md**: Sections: Critical Facts, Breakthroughs, Dead Ends, Open Questions, Decisions (all empty initially)
   - **README.md**: Overview, quick links to GOAL/ROADMAP/LOG/INDEX, current status summary
   - **ROADMAP.md**: Numbered tasks with priority (P0-P3), owner, blocked-by fields
   - **STATUS-data.json**: Full structure matching schema, `overall_pct: 0`, phase 1 `in_progress`
6. Populate `data/README.md` with usage notes
7. Populate `references/README.md` with placeholder
8. Run `research-update-index` to generate the initial INDEX.md

## Validation Checklist

After creation, verify:
- [ ] All directories exist
- [ ] STATUS-data.json validates against STATUS-data.schema.json
- [ ] STATUS.html loads STATUS-data.json correctly (check via fetch path)
- [ ] GOAL.md has clear success criteria
- [ ] ROADMAP.md has at least one actionable task
- [ ] INDEX.md lists all created files
