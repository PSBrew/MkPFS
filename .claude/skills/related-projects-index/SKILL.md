---
name: related-projects-index
description: >
  Compact index of upstream projects and reference sources relevant to PKG/PFS/exFAT research.
  Each entry gives an executive summary, upstream links, and a pointer to our internal
  reference file with deeper notes and citations.
context: fork
---

# Related Projects — Executive Index

Use this skill whenever you need quick orientation on external projects (code, wikis, tools)
that inform PKG/PFS/exFAT behavior or mounting/format details. For deeper research, open the
linked internal reference file or go to the upstream repository/wiki.

## How to use
- Start here to find the right project/source fast.
- If you need details, open the linked internal reference file under `references/` in this skill folder.
- When implementation specifics are required, fetch or read from the upstream links.

---

## ShadowMountPlus
- What it is: Auto-detection and mounting tool for images; stages metadata and registers titles.
- Relevance: Shows practical mount flows for UFS/PFS/exFAT, including LVD attach + PFS nmount flags.
- Gotchas: For PFS, validates mounted block size vs chosen sector size; requires proper image root layout.
- Upstream: https://github.com/drakmor/ShadowMountPlus
- Internal reference: references/shadowmountplus.md

## PS5 Game Compressor
- What it is: Standalone PS5 payload + web UI to compress, validate/repair, uncompress, and move ShadowMountPlus-mounted games.
- Relevance: Real-console PFSC builder with zlib windowed pipeline (64 KiB blocks) and .vhash per-block SHA‑256; validates MkPFS images under SMP with APR Emu support.
- Gotchas: Requires ShadowMountPlus and kstuff-lite; default nested exFAT recommended; nested PFS is experimental; destructive mode is risky and constrained.
- Upstream: https://github.com/juma-sayeh/PS5-Game-Compressor
- Internal reference: references/ps5-game-compressor.md

## PKGTool
- What it is: Practical `.pkg` parser/extractor with a partial repack path.
- Relevance: Field-tested read path; good for entry table shape and decompression logic.
- Gotchas: Writer leaves CRC unimplemented; repack is basename-oriented by default.
- Upstream: https://github.com/thesupersonic16/PKGTool
- Internal reference: references/pkgtool.md

## LibOrbisPkg
- What it is: Full PKG/PFS toolkit (library + tools + tests).
- Relevance: Canonical reference for PFS tree modeling, inode/dirent serialization, flat path table,
  signed outer image layout, and optional AES-XTS.
- Gotchas: PFSC asymmetry; reader handles compressed/direct, writer emits header + full-block map for nested `pfs_image.dat`.
- Upstream: https://github.com/maxton/LibOrbisPkg
- Internal reference: references/liborbispkg.md

## LibOrbisPkg Wiki
- What it is: Orientation wiki for the LibOrbisPkg ecosystem (PkgEditor, PkgTool, library notes).
- Relevance: Highest value page is the PKG crypto note (passcode-derived keys, EKPFS, PFS key derivation, ENTRY_KEYS/IMAGE_KEY roles).
- Upstream (wiki git): https://github.com/maxton/LibOrbisPkg.wiki.git
- Internal reference: references/liborbispkg-wiki.md

## kstuff-lite
- What it is: PS5 payload bundle with loader, kernel hooks, mount automation, and crypto helpers.
- Relevance: Shows practical mount automation for UFS/PFS/exFAT; loader falls back to raw folder path when mount fails.
- Gotchas: `KSTUFF_OBS=1` enables observability/snapshots; crypto focuses on FPKG/FSELF/debug NPDRM.
- Upstream: https://github.com/EchoStretch/kstuff-lite
- Internal reference: references/kstuff-lite.md

## PSDevWiki — PFS page
- What it is: Community-maintained PFS structure page (headers, inode/dirent, flat_path_table; unsigned baseline spec).
- Relevance: Field offsets and packing rules MkPFS must honor for mountability; clarifies mode bits (signed/64b/encrypted/case-insensitive) and block size ranges.
- Upstream: https://www.psdevwiki.com/ps4/PFS
- Internal reference: references/psdevwiki-pfs.md

## PSDevWiki — PKG files page
- What it is: Orientation + structure notes for PKG outer container and embedded PFS (header, entries, digests, PFS offsets/digests, delivery metadata).
- Relevance: Exposes where/what to validate when a PKG wraps a PFS from MkPFS; captures EKPFS→XTS key derivation narrative for production images.
- Upstream: https://www.psdevwiki.com/ps4/PKG_files
- Internal reference: references/psdevwiki-pkg-files.md

## ShadPKG — HOWWORKS
- What it is: Deep implementation walkthrough from PKG decryption to PFS/PFSC handling.
- Upstream: https://github.com/seregonwar/ShadPKG/blob/main/docs/HOWWORKS.md
- Internal reference: references/shadpkg-howworks.md

## Wololo — flatz FPKG writeup
- What it is: Authoritative deep-dive on FSELF/FPKG enablement (kernel hooks, toolchain key swap, ShellCore patches, kernel crypto shims).
- Relevance: Defines EKPFS vs EEKPFS and PFS final key derivation; clarifies why unsigned/PFSC developer flows exist versus retail.
- Upstream: https://wololo.net/ps4-fpkg-writeup-by-flatz/
- Internal reference: references/wololo-fpkg-flatz.md

---

## Notes
- Internal reference files live under `references/*.md` in this skill and contain the detailed notes and citations.
- If an upstream link moves, update it here and in the corresponding internal reference.
