---
name: research-continue
description: Resume a paused research topic by loading context and presenting a session brief
when-to-invoke: When resuming work on an existing research topic
---

# Research: Continue

Resume a paused research topic with full context loading.

## Prompt Template

```
Resuming research on <topic>. Let me load context...
```

## Context Loading Order (mandatory)

Read these files in order. Each file builds on the previous:

1. **`MEMORY.md`** — critical facts, dead ends, open questions (survival knowledge)
2. **`LOG.md`** — what happened last session (pick newest entry only)
3. **`ROADMAP.md`** — current task priorities and blockers
4. **`STATUS-data.json`** — machine-readable progress snapshot
5. **`subtasks/INDEX.md`** — open subtask list
6. **`GOAL.md`** — refresh on what "done" means

## Session Brief Format

Present this brief to the user:

```markdown
## Session Brief: <topic name>

**Phase:** <current_phase> (<overall_pct>% complete)
**Last session:** <date from LOG.md>

### Top 3 Priorities
1. <P0 task from ROADMAP.md>
2. <P1 task from ROADMAP.md>
3. <P2 task from ROADMAP.md>

### Active Blockers
- <blocker from STATUS-data.json or MEMORY.md>

### First Action
<Propose the highest-priority open subtask or ROADMAP item>

Ready to continue? What should we focus on?
```

## Steps

1. Identify the topic (from current directory or user input)
2. Read files in the mandatory order above
3. Present the session brief
4. Propose the first action based on ROADMAP priorities
5. Wait for user confirmation before diving in

## Session Numbering

Check `STATUS-data.json` → `session_summary.total_sessions` to determine the new session number. Increment by 1 for this session.
