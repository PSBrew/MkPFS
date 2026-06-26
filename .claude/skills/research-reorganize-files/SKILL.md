---
name: research-reorganize-files
description: Re-scan workspace, rebuild INDEX.md, detect number collisions, propose or execute merges
when-to-invoke: When the research folder has grown organically and needs cleanup
---

# Research: Reorganize Files

Scan and reorganize the research workspace.

## Prompt Template

```
Scanning research/<topic>/ for issues...

## Scan Results
- **Total files:** <count>
- **Script number collisions:** <count or "none">
- **KB number collisions:** <count or "none">
- **Misplaced files:** <count or "none">
- **Empty directories:** <count or "none">
- **Duplicate files:** <count or "none">
- **Stale INDEX.md entries:** <count or "none">

## Proposed Fixes
1. <fix description>
2. <fix description>

Apply these fixes? [y/n/select]
```

## Detection Rules

### Number Collisions
```bash
# Scripts: NNNN_*.py in scripts/
ls scripts/ | grep -E '^\d{4}_' | sort | uniq -d -w 4

# KB docs: NNN-*.md in knowledge_base/
ls knowledge_base/ | grep -E '^\d{3}-' | sort | uniq -d -w 3
```

Fix: rename the newer file to the next available number.

### Misplaced Files
Files outside expected subdirectories (data/, key_findings/, knowledge_base/, outputs/, reports/, scripts/, subtasks/, tmp/).

Fix: propose moving to the most appropriate subdirectory based on content.

### Empty Directories
```bash
find research/<topic>/ -type d -empty
```

Fix: remove unless it's a required directory (data/, tmp/, etc.).

### Duplicate Files
```bash
find research/<topic>/ -type f -exec md5 {} \; | sort | uniq -d
```

Fix: keep the one in the canonical location, note the duplicate for removal.

### Stale INDEX.md Entries
Compare files listed in INDEX.md against actual files on disk.

Fix: remove stale entries, add missing entries.

## Steps

1. Walk `research/<topic>/` and catalog every file
2. Run all detection rules above
3. Present scan results to user
4. Propose specific fixes for each issue found
5. Ask for confirmation (all, none, or selective)
6. Execute approved changes
7. Regenerate INDEX.md with `research-update-index` (or inline if not available)
8. Update `STATUS-data.json` → `stats` with corrected counts
