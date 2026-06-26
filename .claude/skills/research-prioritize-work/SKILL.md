---
name: research-prioritize-work
description: Rank candidate next actions by impact, feasibility, and unblock-value
when-to-invoke: When multiple research directions are possible and a priority decision is needed
---

# Research: Prioritize Work

Rank candidate next actions and update the roadmap.

## Prompt Template

```
Evaluating <N> candidate tasks for priority...

| # | Task | Impact | Feasibility | Unblock | Score | Rank |
|---|------|--------|-------------|---------|-------|------|
| 1 | <task> | <1-5> | <1-5> | <1-5> | <sum> | #<n> |

Recommended order:
1. <highest score task> (P0)
2. <next task> (P1)
...

Update ROADMAP.md with this ordering?
```

## Scoring Formula

```
score = (impact × 2) + feasibility + (unblock_value × 3)
```

Weights:
- **Impact** (×2): advancing GOAL.md is the primary objective
- **Feasibility** (×1): we need the tools/knowledge to actually do it
- **Unblock value** (×3): unblocking downstream work has the highest leverage

## Axis Definitions

### Impact (1-5)
| Score | Meaning |
|-------|---------|
| 5 | Directly achieves a GOAL.md success criterion |
| 4 | Significantly advances toward GOAL.md |
| 3 | Useful progress, but not core to the goal |
| 2 | Incremental improvement |
| 1 | Marginal value |

### Feasibility (1-5)
| Score | Meaning |
|-------|---------|
| 5 | All tools/data/knowledge available, can do now |
| 4 | Mostly ready, minor gaps |
| 3 | Partially feasible, some unknowns |
| 2 | Significant gaps in tools or knowledge |
| 1 | Currently infeasible (blocked by external dependency) |

### Unblock Value (1-5)
| Score | Meaning |
|-------|---------|
| 5 | Unblocks 5+ downstream tasks |
| 4 | Unblocks 3-4 tasks |
| 3 | Unblocks 1-2 tasks |
| 2 | Unblocks related but non-critical work |
| 1 | No downstream dependencies |

## Steps

1. List candidate tasks from:
   - User input (if provided)
   - ROADMAP.md open tasks
   - subtasks/INDEX.md open items
   - MEMORY.md open questions
2. Score each task on the three axes
3. Calculate composite score
4. Sort by score descending
5. Present ranked table to user for confirmation
6. On confirmation, update `ROADMAP.md` with the agreed ordering
7. Update `STATUS-data.json` → `next_steps[]` with top 4 tasks
