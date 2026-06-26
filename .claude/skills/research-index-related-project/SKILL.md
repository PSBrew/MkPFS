---
name: research-index-related-project
description: Register an external GitHub repo via the global related-projects/ convention
when-to-invoke: When a related external project is discovered during research
---

# Research: Index Related Project

Register an external project using the global `related-projects/` convention.

## Prompt Template

```
Found a related project: <repo URL>

What is the relationship to our research?
- [ ] Reference: provides format documentation or specs
- [ ] Tool: provides a usable tool for parsing/building
- [ ] Inspiration: architecture or approach we can learn from
- [ ] Dependency: we depend on this for our work

One-line description: ____
```

## Steps

1. Get the GitHub repo URL from the user or from a discovery during research
2. Use the existing `related-project-add` skill to index it into `related-projects/`
3. After indexing, create a reference entry in `research/<topic>/references/`:
   ```markdown
   # <Project Name>

   **Repo:** <GitHub URL>
   **Relationship:** reference | tool | inspiration | dependency
   **Indexed:** <YYYY-MM-DD>

   <One-line description>

   → Full index: [related-projects/<name>/](../../../related-projects/<name>/)
   ```
4. Link from `references/README.md`:
   ```markdown
   - [**<Name>**](<name>.md) — <one-line description> (<relationship>)
   ```
5. Update INDEX.md references section
6. If the project provides format docs, consider creating a `knowledge_base/` entry summarizing what we learned from it
