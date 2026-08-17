---
name: related-projects-index
description: >
  Compact index of upstream projects and reference sources relevant to PKG/PFS/exFAT research.
  Each entry gives an executive summary, upstream links, and a pointer to our internal
  reference file with deeper notes and citations. Always use this skill when you are performin a research 
  related to MkPFS, PFS, compression, kraken, PKGs, etc.
context: fork
---

# Related Projects — Executive Index

Use this skill whenever you need quick orientation on external projects (code, wikis, tools)
that inform PKG/PFS/exFAT behavior or mounting/format details. For deeper research, open the
linked internal reference file under `references/` in this skill folder, or go upstream.

## How to use

- Start here to find the right project/source fast.
- For details, open the linked `references/<slug>.md` file in this skill folder.
- For implementation specifics, fetch or read from the upstream links.

---

## ShadowMountPlus
- What: Auto-detection and mounting tool for images; stages metadata and registers titles.
- Relevance: Practical mount flows for UFS/PFS/exFAT, including LVD attach + PFS nmount flags.
- Gotchas: For PFS, validates mounted block size vs chosen sector size; requires proper image root layout.
- Upstream: https://github.com/drakmor/ShadowMountPlus
- Internal: references/shadowmountplus.md

## PS5 Game Compressor
- What: Standalone PS5 payload + web UI to compress, validate/repair, uncompress, and move SMP-mounted games.
- Relevance: Real-console PFSC builder with zlib windowed pipeline (64 KiB blocks) and `.vhash` per-block SHA‑256; validates MkPFS images under SMP with APR Emu support.
- Gotchas: Requires ShadowMountPlus and kstuff-lite; default nested exFAT recommended; nested PFS is experimental; destructive mode is risky and constrained.
- Upstream: https://github.com/juma-sayeh/PS5-Game-Compressor
- Internal: references/ps5-game-compressor.md

## PKGTool
- What: Practical `.pkg` parser/extractor with a partial repack path.
- Relevance: Field-tested read path; good for entry table shape and decompression logic.
- Gotchas: Writer leaves CRC unimplemented; repack is basename-oriented by default.
- Upstream: https://github.com/thesupersonic16/PKGTool
- Internal: references/pkgtool.md

## LibOrbisPkg
- What: Full PKG/PFS toolkit (library + tools + tests).
- Relevance: Canonical reference for PFS tree modeling, inode/dirent serialization, flat path table,
  signed outer image layout, and optional AES-XTS.
- Gotchas: PFSC asymmetry; reader handles compressed/direct, writer emits header + full-block map for nested `pfs_image.dat`.
- Upstream: https://github.com/maxton/LibOrbisPkg
- Internal: references/liborbispkg.md

## LibOrbisPkg Wiki
- What: Orientation wiki for the LibOrbisPkg ecosystem (PkgEditor, PkgTool, library notes).
- Relevance: Highest value page is the PKG crypto note (passcode-derived keys, EKPFS, PFS key derivation, ENTRY_KEYS/IMAGE_KEY roles).
- Upstream (wiki git): https://github.com/maxton/LibOrbisPkg.wiki.git
- Internal: references/liborbispkg-wiki.md

## kstuff-lite
- What: PS5 payload bundle with loader, kernel hooks, mount automation, and crypto helpers.
- Relevance: Practical mount automation for UFS/PFS/exFAT; loader falls back to raw folder path when mount fails.
- Gotchas: `KSTUFF_OBS=1` enables observability/snapshots; crypto focuses on FPKG/FSELF/debug NPDRM.
- Upstream: https://github.com/EchoStretch/kstuff-lite
- Internal: references/kstuff-lite.md

## PSDevWiki — PFS page
- What: Community-maintained PFS structure page (headers, inode/dirent, flat_path_table; unsigned baseline spec).
- Relevance: Field offsets and packing rules MkPFS must honor for mountability; clarifies mode bits (signed/64b/encrypted/case-insensitive) and block size ranges.
- Upstream: https://www.psdevwiki.com/ps4/PFS
- Internal: references/psdevwiki-pfs.md

## PSDevWiki — PKG files page
- What: Orientation + structure notes for PKG outer container and embedded PFS (header, entries, digests, PFS offsets/digests, delivery metadata).
- Relevance: Exposes where/what to validate when a PKG wraps a PFS from MkPFS; captures EKPFS→XTS key derivation narrative for production images.
- Upstream: https://www.psdevwiki.com/ps4/PKG_files
- Internal: references/psdevwiki-pkg-files.md

## ShadPKG — HOWWORKS
- What: Deep implementation walkthrough from PKG decryption to PFS/PFSC handling.
- Upstream: https://github.com/seregonwar/ShadPKG/blob/main/docs/HOWWORKS.md
- Internal: references/shadpkg-howworks.md

## Wololo — flatz FPKG writeup
- What: Authoritative deep-dive on FSELF/FPKG enablement (kernel hooks, toolchain key swap, ShellCore patches, kernel crypto shims).
- Relevance: Defines EKPFS vs EEKPFS and PFS final key derivation; clarifies why unsigned/PFSC developer flows exist versus retail.
- Upstream: https://wololo.net/ps4-fpkg-writeup-by-flatz/
- Internal: references/wololo-fpkg-flatz.md

## goodle
- What: Thin Go cgo wrapper for OodleLZ decompression; drop-in replacement for the `gooz` package.
- Relevance: Validates Oodle per-block decompression paths used in adjacent tooling; cross-check outputs independent of Python.
- Gotchas: Requires proprietary Oodle shared library (`oo2core_N_win64.dll`/`liboo2core.so/.dylib`).
- Upstream: https://github.com/oriath-net/goodle
- Internal: references/goodle.md

## TLOU PSARC Tool
- What: Windows GUI utility to read/extract and partially reimport Naughty Dog `.psarc` archives (big-endian headers, MD5 name table, per-block Oodle/zlib).
- Relevance: Demonstrates block size tables, MD5-based name resolution, and Oodle/zlib per-block decompression used in adjacent game assets.
- Gotchas: Windows-only, GUI-only; import path writes uncompressed, injects author signature, does not update the name table.
- Upstream: https://github.com/amrshaheen61/TLOU_PSARC_Tool
- Internal: references/tlou-psarc-tool.md

## PKG Passcode Finder
- What: VB.NET WPF app that randomly brute-forces 31-char alphanumeric passcodes for PS5 PKG extraction by invoking `prospero-pub-cmd.exe`.
- Relevance: Confirms passcode length/charset and SDK-driven extraction flow; context for why open tooling matters.
- Gotchas: Astronomical keyspace (62^31) makes naive random brute force impractical; Windows-only GUI; requires proprietary SDK tool.
- Upstream: https://github.com/bobg-github/PS5PKGPasscodeFinder
- Internal: references/pkg-passcode-finder.md

## Oodle/Kraken Decompression Tools
- What: Collection of open decoders and shims for Oodle codecs (Kraken/Mermaid/Selkie/Leviathan), including a Rust decompressor and Go Oodle wrapper.
- Relevance: Enables verifying Oodle-compressed block behavior across ecosystems that feed into or out of PFS.
- Gotchas: Official Oodle libraries are proprietary; prebuilt .so/.dll distribution may have licensing constraints.
- Upstream: https://github.com/lvlvllvlvllvlvl/oozextract
- Internal: references/oodle-kraken-tools.md

## LibProsperoPkg
- What: .NET 10 library for building & reading PS5 packages: inner/outer PFS, PFSC (Kraken/Zlib), AES-XTS encryption, RSA-3072 metadata signing, and debug/image finalization.
- Relevance: Source of engineering details for EKPFS key schedule, inner-vs-outer PFS boundaries, Kraken PFSC implementation & heuristics, digest/icv computation, and packaging workflows that MkPFS should either match or reimplement.
- Gotchas: GPL-3.0-or-later license; retail finalization and sealed `rif` key blobs are console-gated and not producible off-console. Use code as reference and prefer reimplementation for non-GPL integration.
- Upstream: https://github.com/SvenGDK/LibProsperoPKG
- Internal: references/libprospero-pkg.md

---

## Notes

- Internal reference files live under `references/*.md` in this skill and contain detailed notes and citations.
- If an upstream link moves, update it here and in the corresponding internal reference.
