---
name: research-session-end
description: End a research session cleanly with a log entry, status snapshot, and resume brief
when-to-invoke: When wrapping up a research session
---

# Research: Session End

End the current research session cleanly.

## Prompt Template

```
Wrapping up session <N>. Let me capture what we accomplished...

## Session Summary
- **Phase:** <current phase>
- **Duration:** ~<hours>h
- **Key accomplishments:**
  - <item 1>
  - <item 2>

## Files Created/Modified
- <file 1>
- <file 2>

Saving status snapshot and log entry...
```

## LOG.md Entry Format

Append at the TOP of LOG.md (newest first):

```markdown
---

## Session <N> — <YYYY-MM-DD>

**Phase:** <phase name>
**Focus:** <what we worked on>

### Accomplished
- <accomplishment 1>
- <accomplishment 2>

### Discovered
- <discovery 1>

### Remaining
- <remaining task 1>
- <remaining task 2>

### Files Changed
- Created: `path/to/file`
- Modified: `path/to/file`

**Next session focus:** <what to do next>
```

## Steps

1. Summarize what was accomplished this session
2. Prepend a LOG.md entry (newest first) using the format above
3. Update `STATUS-data.json`:
   - Increment `session_summary.total_sessions`
   - Set `session_summary.last_session` to today
   - Add estimated hours to `session_summary.total_hours`
   - Set `session_summary.next_session_focus` to next priority
   - Update `topic.last_updated` to today
   - Update component progress percentages
   - Update `next_steps[]` from current ROADMAP.md priorities
   - Update `recent_files[]` with files changed this session
4. Update `MEMORY.md`:
   - Move answered questions from Open Questions to Dead Ends or Critical Facts
   - Add any new critical facts discovered this session
5. Update `ROADMAP.md` if priorities changed
6. Write a brief "resume prompt" note at the top of LOG.md for next session
7. Regenerate INDEX.md

## Resume Prompt

At the very top of LOG.md, above the newest session entry, write:

```markdown
<!-- RESUME: Session <N+1> starts here. Focus: <next_session_focus>. Top priority: <P0 task>. -->
```

This serves as a quick-start hint for `research-continue`.
