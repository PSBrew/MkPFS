---
name: research-update-status
description: Rewrite STATUS-data.json from current workspace state and regenerate STATUS.html
when-to-invoke: After completing a subtask, phase, or significant investigation step
---

# Research: Update Status

Regenerate the machine-readable status dashboard.

## STATUS-data.json Field Reference

All fields in the canonical schema:

### `meta`
```json
{ "schema_version": "1.0", "generated": "<ISO-8601 timestamp>", "generator": "research-update-status" }
```

### `topic`
```json
{ "name": "<full name>", "slug": "<slug>", "one_liner": "<description>", "started": "<YYYY-MM-DD>", "last_updated": "<YYYY-MM-DD>" }
```

### `progress`
- `overall_pct`: integer 0-100, weighted average of phase completion
- `current_phase`: name of the active phase
- `phases[]`: each `{ "name", "status" (complete|in_progress|not_started), "pct" (0-100), "when" (date range string or null) }`

### `components[]`
Each component tracks a piece of the research domain:
```json
{ "name": "Header", "icon": "📄", "location": "knowledge_base/002-byte-layout.md", "pct": 100, "status": "complete" }
```
Status values: `complete`, `in_progress`, `blocked`, `not_started`

### `key_documents[]`
```json
{ "name": "Format Spec", "location": "key_findings/FORMAT_SPEC.md", "icon": "📐", "status": "active" }
```
Status values: `active`, `complete`, `draft`

### `blockers[]`
```json
{ "title": "<short>", "severity": "critical|high|medium", "detail": "<one sentence>", "link": "<path or null>", "since": "<YYYY-MM-DD>" }
```

### `breakthroughs[]`
```json
{ "title": "<short>", "when": "<YYYY-MM-DD>", "detail": "<one sentence>", "link": "<path or null>" }
```

### `next_steps[]`
```json
{ "priority": 1, "task": "<imperative verb + object>", "owner": "agent|user" }
```

### `stats`
Auto-computed by scanning the workspace:
```json
{ "scripts": 2, "knowledge_docs": 3, "reports": 1, "subtasks_open": 1, "subtasks_done": 1, "data_files": 0 }
```

### `quick_links[]`
```json
{ "icon": "📋", "label": "Goal", "href": "GOAL.md" }
```

### `recent_files[]`
Last 3-5 modified files:
```json
{ "icon": "📝", "name": "003-encryption.md", "href": "knowledge_base/003-encryption.md", "date": "2026-06-15" }
```

### `session_summary`
```json
{ "total_sessions": 5, "last_session": "2026-06-14", "total_hours": 8, "next_session_focus": "<what to do next>" }
```

## Steps

1. Scan the workspace to compute `stats`:
   - Count files in `scripts/`, `knowledge_base/`, `reports/`, `data/`
   - Count subtasks in `subtasks/` (open) and `subtasks/done/` (done)
2. Read ROADMAP.md, MEMORY.md, GOAL.md for context
3. Update `progress.overall_pct` as weighted average of phases
4. Update `components[]` by checking which KB docs exist and their content
5. Update `key_documents[]` by scanning key_findings/ and knowledge_base/
6. Update `blockers[]` from MEMORY.md dead ends and open questions
7. Update `breakthroughs[]` from MEMORY.md breakthroughs section
8. Update `next_steps[]` from ROADMAP.md top 4 tasks
9. Update `recent_files[]` with last 3-5 modified files (check timestamps)
10. Update `session_summary` — bump total_sessions, set last_session to today
11. Set `meta.generated` to current ISO-8601 timestamp
12. Write `STATUS-data.json`
13. Verify `STATUS.html` references the correct JSON path (relative `STATUS-data.json`)

## Validation

After writing, verify:
- [ ] All file paths in `key_documents`, `components`, `recent_files` point to existing files
- [ ] `progress.phases` percentages are consistent with `overall_pct`
- [ ] `stats` counts match actual file counts
- [ ] `blockers` all have `since` dates
