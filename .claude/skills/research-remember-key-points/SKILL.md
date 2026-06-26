---
name: research-remember-key-points
description: Append discovered facts, dead ends, and decisions to MEMORY.md
when-to-invoke: After a significant finding or discovery during research
---

# Research: Remember Key Points

Append findings to the cross-session memory file.

## Entry Format

Each entry in MEMORY.md uses this structure:

```markdown
### <Short title> (<date>)
<Concise description of the finding, decision, or dead end>

**Evidence:** <file path, script output, or data reference>
**Impact:** <what this means for the research direction>
```

## Categories

### Critical Facts
Confirmed format details, field layouts, verified structures.
```markdown
### Header field at +0x1C is flags bitmask (2026-06-12)
Bit 0 = compressed, bit 1 = encrypted, bit 2 = signed.
**Evidence:** scripts/0002_header_parse.py output across 5 samples
**Impact:** Can now filter encrypted vs plaintext blocks
```

### Breakthroughs
Successful approaches, unexpected discoveries, key insights.
```markdown
### Allocation table type byte confirmed as compression algo (2026-06-10)
Type=1 is LZ4, type=2 is Zstd. Verified by decompressing blocks.
**Evidence:** outputs/sample_output.json, block entropy analysis
**Impact:** Can now decompress all non-encrypted blocks
```

### Dead Ends
Approaches tried that failed (always include WHY they failed).
```markdown
### AES-XTS key bruteforce infeasible (2026-06-14)
Tried all common key derivation functions. Keys are hardware-fused.
**Evidence:** entropy analysis shows no pattern in key material
**Impact:** Cannot read encrypted content without devkit or key leak
```

### Open Questions
Unresolved questions for future sessions.
```markdown
### What encoding does the directory tree use?
Block 2 appears to be an inode table but field layout is unknown.
**Next step:** Compare inode_count from footer with entries in block 2
```

### Decisions
Choices made with rationale.
```markdown
### Using absolute offsets for block addressing (2026-06-10)
The allocation table stores absolute byte offsets, not block indices.
**Rationale:** Footer root_inode field matches an absolute offset in block 1
```

## Steps

1. Read `MEMORY.md`
2. Determine category for each new item
3. Format entry using the template above
4. Append under the appropriate section header with date
5. Remove from **Open Questions** if the new finding answers a previous question
6. Write updated `MEMORY.md`
7. If this is a breakthrough, also update `STATUS-data.json` → `breakthroughs` array:
   ```json
   { "title": "<short title>", "when": "<YYYY-MM-DD>", "detail": "<one sentence>", "link": "<path to KB doc or null>" }
   ```

## Anti-patterns

- Don't duplicate what's already in knowledge_base docs (link instead)
- Don't record raw data (put in data/ or outputs/)
- Don't record temporary observations (use LOG.md)
- Don't leave open questions unanswered when you have the answer
