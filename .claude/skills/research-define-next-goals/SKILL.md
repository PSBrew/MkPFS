---
name: research-define-next-goals
description: Regenerate ROADMAP.md by re-prioritizing based on current blockers and progress
when-to-invoke: After completing a phase or when priorities have shifted
---

# Research: Define Next Goals

Re-prioritize the research roadmap.

## ROADMAP.md Format

```markdown
# Roadmap: <Topic Name>

Last updated: <YYYY-MM-DD>

## Priority Legend
- **P0** — unblocks everything, do first
- **P1** — high impact, advances GOAL.md significantly
- **P2** — useful but not blocking other work
- **P3** — nice to have, low urgency

## Tasks

### P0: <task title>
- **Owner:** agent | user
- **Blocked by:** — | <task or blocker>
- **Status:** open | in_progress | done
- **Notes:** <context>

### P1: <task title>
...
```

## Evaluation Criteria

For each open task, assess:

| Factor | Question | Impact on Priority |
|--------|----------|-------------------|
| Blocker resolved | Has a blocker been lifted since last roadmap? | Promote to P0 |
| New blocker | Has a new blocker appeared? | Mark dependent tasks, keep priority |
| GOAL alignment | Does this still advance GOAL.md? | Remove if no longer relevant |
| Dependency chain | How many tasks does this unblock? | Higher unblock value = higher priority |
| Feasibility | Do we have the tools/knowledge now? | Increase priority if yes |

## Priority Scoring

Use this formula for numeric ranking when multiple tasks compete:

```
score = (impact × 2) + feasibility + (unblock_value × 3)
```

- **impact** (1-5): how much does this advance GOAL.md?
- **feasibility** (1-5): do we have the tools/data/knowledge?
- **unblock_value** (1-5): how many downstream tasks does this unblock?

## Steps

1. Read current `ROADMAP.md`, `MEMORY.md`, `STATUS-data.json`, and `GOAL.md`
2. List all open tasks from ROADMAP.md
3. Evaluate each task using the criteria above
4. Score each task numerically
5. Add any new tasks discovered during the latest phase
6. Remove tasks no longer relevant to GOAL.md
7. Re-sort by score descending, group into P0/P1/P2/P3
8. Present ranked list to user for confirmation
9. Write updated `ROADMAP.md`
10. Update `STATUS-data.json`:
    - `progress.current_phase` if changed
    - `next_steps[]` with top 4 tasks from the new roadmap
    - `topic.last_updated` to today
