---
name: research-clean-tmp
description: Remove scratch files older than N days from tmp/ with confirmation
when-to-invoke: When tmp/ has accumulated old scratch files that are no longer needed
---

# Research: Clean Tmp

Remove old ephemeral scratch files from `research/<topic>/tmp/`.

## Prompt Template

```
Scanning tmp/ for files older than <N> days...

Found <count> files totaling <size>:
| File | Size | Age | Last Modified |
|------|------|-----|---------------|
| <file> | <size> | <N days> | <date> |

Delete these files? [y/n/select]
```

## Steps

1. List all files in `research/<topic>/tmp/` with modification dates
   ```bash
   find research/<topic>/tmp/ -type f -mtime +N -exec ls -lh {} \;
   ```
2. Default threshold: 7 days (ask user to confirm or override)
3. Present table with: filename, size, age in days, last modified date
4. Ask for confirmation:
   - **y** — delete all listed files
   - **n** — cancel, keep everything
   - **select** — let user pick which to delete
5. Delete confirmed files
6. Report summary:
   ```
   Deleted <count> files, freed <size>.
   Remaining: <count> files in tmp/
   ```

## Safety Rules

- Never delete files modified in the last 24 hours
- Never delete files referenced in MEMORY.md or LOG.md
- Never delete files outside of `research/<topic>/tmp/`
- Always show the list before deleting
