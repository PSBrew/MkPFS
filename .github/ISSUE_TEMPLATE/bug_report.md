---
name: Bug report
about: Report a problem with clear versions and command output
title: "[BUG] "
labels: bug
assignees: "RenanGBarreto"

---

## 🐞 What happened?

Briefly describe the problem.

## 📦 Versions (required)

- MkPFS version (`mkpfs -V`):
- Python version (`python --version`):
- PS5 FW Version:
- Target image format/strategy you attempted (check all that apply):
    - [ ] `.exfat->.ffpfsc`
    - [ ] `.ffpkg->.ffpfsc`
    - [ ] `raw-folder->.ffpfs`  _(direct / single-pass)_
    - [ ] `raw-folder->.dat->.ffpfsc`  `(wrapped / double-pass)`
    - [ ] Other (please specify):
- Did you use a UI to convert or the command line?
    - [ ] UI (please specify which)
    - [ ] Command line

## 💻 Command input (required)

Paste the exact command(s) you ran:

```bash
# example
mkpfs pack --input ./game --output ./game.pfs
```

## 📤 Command output

Paste the full stdout/stderr output:
_(make sure to hide any personal information or paths)_

```text
# paste output here
```

## 📎 Extra context

Add logs, sample files, or screenshots if helpful.
