---
name: research-update-goal
description: Edit GOAL.md when scope has shifted, keep README.md in sync
when-to-invoke: When research scope changes significantly
---

# Research: Update Goal

Update the research goal and keep dependent files in sync.

## GOAL.md Format

```markdown
# Goal: <Topic Name>

**Last updated:** <YYYY-MM-DD>

## Objective
<One paragraph: what are we trying to achieve?>

## In Scope
- <item 1>
- <item 2>

## Out of Scope
- <item 1> (explain why)

## Success Criteria
- [ ] <measurable criterion 1>
- [ ] <measurable criterion 2>

## Non-Goals
- <explicit thing we are NOT trying to do>

## Constraints
- <constraint 1>
- <constraint 2>
```

## Prompt Template

```
The research scope has changed. What shifted?

Current objective: <from GOAL.md>

Options:
1. Expand scope (add new investigation areas)
2. Narrow scope (remove areas no longer relevant)
3. Pivot (change the fundamental objective)
4. Refine (same objective, clarify success criteria)

What's the change?
```

## Steps

1. Read current `GOAL.md` and `README.md`
2. Identify what changed (user input or from session context)
3. Edit `GOAL.md`:
   - Update objective statement if scope changed
   - Adjust in-scope / out-of-scope lists
   - Update success criteria if needed
   - Add/remove non-goals
4. Edit `README.md` summary paragraph if it references the old goal
5. Update `ROADMAP.md`:
   - Remove tasks no longer relevant to the new goal
   - Add tasks for newly in-scope areas
   - Re-prioritize using `research-prioritize-work` scoring
6. Update `STATUS-data.json`:
   - `topic.one_liner` if it changed
   - `progress.phases` if a phase was added/removed
   - `topic.last_updated` to today
7. Append a LOG.md entry noting the scope change:
   ```markdown
   ### Scope Change (<YYYY-MM-DD>)
   **What changed:** <description>
   **Why:** <reason>
   **Impact:** <what tasks are affected>
   ```
