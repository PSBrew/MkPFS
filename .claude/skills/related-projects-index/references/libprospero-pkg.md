# LibProsperoPkg — Reference

Upstream: https://github.com/SvenGDK/LibProsperoPKG

Executive summary
- What: A C# (.NET 10) class library that builds and reads PS5 packages end-to-end: inner PFS image construction (plaintext inner PFS layout and PFSC wrappers), optional inner-image PFSC compression (Kraken v3 and zlib), AES-XTS outer PFS encryption, the `\x7FCNT` metadata container, RSA-3072 metadata signing, and final `\x7FFIH` debug-image finalization.
- Why relevant: Provides concrete, field-tested engineering for PS5 package assembly and the PFS/PKG structures that MkPFS targets. It documents and implements the EKPFS→XTS key schedule, per-block digest / ICV rules, PFSC container formats, and a production Kraken encoder/decoder that MkPFS can study for compatibility and reimplementation.
- Key technical points (short):
  - EKPFS derivation and key schedule: uses a hashed combination of index/content-id/passcode (SHA3-256 forms used for outer PFS), plus `new_crypt` HMAC path to select tweak/data keys consumed by AES-128-XTS.
  - Inner vs outer PFS: inner-image AES-XTS encrypts on 0x1000-byte sectors (PFSc inner-image sector unit), outer finalized-image AES-XTS uses 0x10000-byte sectors (image block units), and the library implements per-block SHA3-256 digests and an `icv` for the superblock.
  - Kraken PFSC v3: production Kraken encoder (level-7 forward-DP) and managed Kraken decoder (seeded first chunk, dual 128 KiB chunk support, Huffman arrays, `excess` framing support, per-chunk literal/command/offset/length streams). Encoder enforces newLZ rules (no match start in final 16 bytes of a chunk) and the "keep compressed" threshold (comp <= (uncomp * 15) >> 4; ~6.25% savings required).
- Gotchas / immediate constraints:
  - License: GPL-3.0-or-later. Code is usable as a study/reference, but direct reuse in non-GPL projects has legal implications — prefer reimplementation of algorithms or follow project licensing policy.
  - Console-gated pieces: retail finalization steps, sealed 448‑byte `rif` key blobs and retail image key sealing are console-side and not implementable off-console; library intentionally refuses to fabricate these.

Why it matters to MkPFS
- Concrete reference for EKPFS → AES-XTS key schedule and the distinction between inner/outer keying (useful for implementing compatible key derivation and XTS wrapping in MkPFS).
- Detailed Kraken PFSC implementation (encoder + decoder) explains per-chunk framing, Huffman-array usage, excess mode, and LZ parse choices; useful for producing compatible compressed inner images or validating third-party decoders.
- Structural examples for CNT/FIH wrapping and digest generation (which MkPFS must match in order to be accepted by console mount paths in debug mode): the library calculates the same set of digests used for `package-digest`, `imagedigs.dat` and the nested image `pfs_signed_digest`.
- Practical build & extract flows (ProsperoPackageBuilder, ProsperoPackageExtractor) show how a builder should stage inner-image creation, PFSC validation, AES-XTS outer wrapping, metadata signing, and finalization.

Key upstream files/pages (canonical links)
- README.md — https://github.com/SvenGDK/LibProsperoPKG/blob/main/README.md — repo overview, highlights, quick-start samples.
- docs/implementation-status.md — https://github.com/SvenGDK/LibProsperoPKG/blob/main/docs/implementation-status.md — exhaustive feature-by-feature implementation and known gaps (critical reading: inner/outer PFS sections, Kraken/NAPS notes, limitations: retail finalization).
- docs/ps5-pkg-format.md — https://github.com/SvenGDK/LibProsperoPKG/blob/main/docs/ps5-pkg-format.md — technical write-up of the PS5 package format used by the library.
- src/LibProsperoPkg/Util/Crypto.cs — https://github.com/SvenGDK/LibProsperoPKG/blob/main/src/LibProsperoPkg/Util/Crypto.cs — key derivation helpers (ComputeKeys), EKPFS → PFS key generation (PfsGenEncKey / PfsGenSignKey), RSA/AES helpers and SHA3/XTS primitives.
- src/LibProsperoPkg/PFS/ProsperoPfsBuilder.cs — https://github.com/SvenGDK/LibProsperoPKG/blob/main/src/LibProsperoPkg/PFS/ProsperoPfsBuilder.cs — outer-PFS generation (data-first structure, superblock, inode table, `\x7fFLT` flat path table).
- src/LibProsperoPkg/PFS/Compression/ProsperoCompressedPfsFileWriter.cs — https://github.com/SvenGDK/LibProsperoPKG/blob/main/src/LibProsperoPkg/PFS/Compression/ProsperoCompressedPfsFileWriter.cs — PFSC container writer logic and compress-vs-store rule.
- src/LibProsperoPkg/PFS/Compression/Oodle/KrakenDecoder.cs — https://github.com/SvenGDK/LibProsperoPKG/blob/main/src/LibProsperoPkg/PFS/Compression/Oodle/KrakenDecoder.cs — managed Kraken decoder with excess framing/Huffman/LZ unpack logic.

Notes / gotchas (expanded)
- Licensing: GPL-3.0-or-later (see LICENSE in repo root). The safest route for MkPFS is to reimplement algorithms (reference the repo in design notes) rather than copy-paste code. If a derived work is acceptable under GPL for some components, coordinate with legal/maintainers before merging.
- Console material: certain finalization artifacts (retail image keys, sealed 448‑byte `rif` key blobs) are impossible to generate off-console. The library detects and refuses retail-only operations; MkPFS must do the same and/or accept a supplied key for retail images.
- Kraken edge rules: encoder enforces a 16-byte match-start restriction near chunk ends; the decoder expects seeded first-chunk copy and supports two 128 KiB chunks per block. When reimplementing, include tests for: (a) chunk boundary cases (0x40000 boundary), (b) "excess" substream parsing and continuation bytes, (c) Huffman-array fallbacks.
- "KeepCompressed" threshold and heuristic: small compression wins are not retained — verify any reimplementation uses the same numeric threshold or document differences.
- PFSC container semantics: inner PFSC files are self-describing; the build validates compressed inner images with an in-process round-trip — adopt the same guard to avoid producing unreadable packages.

Source index (canonical links)
- https://github.com/SvenGDK/LibProsperoPKG/blob/main/README.md
- https://github.com/SvenGDK/LibProsperoPKG/blob/main/docs/implementation-status.md
- https://github.com/SvenGDK/LibProsperoPKG/blob/main/docs/ps5-pkg-format.md
- https://github.com/SvenGDK/LibProsperoPKG/blob/main/src/LibProsperoPkg/Util/Crypto.cs
- https://github.com/SvenGDK/LibProsperoPKG/blob/main/src/LibProsperoPkg/PFS/ProsperoPfsBuilder.cs
- https://github.com/SvenGDK/LibProsperoPKG/blob/main/src/LibProsperoPkg/PFS/Compression/ProsperoCompressedPfsFileWriter.cs
- https://github.com/SvenGDK/LibProsperoPKG/blob/main/src/LibProsperoPkg/PFS/Compression/Oodle/KrakenDecoder.cs

Suggested follow-up research / validation work for MkPFS
1. Re-derive EKPFS & key schedule: implement ComputeKeys(ContentId, Passcode, Index, useSha3=true) test harness and compare with a Prospero-built debug image (extract EKPFS fingerprint) — do this by building a sample debug image and extracting the EKPFS fingerprint (or use `ProsperoBuildResult.DebugLicense` outputs).
2. Build/round-trip test for Kraken: take a small prepared app tree, build a `nwonly` debug image with Kraken inner-image enabled, then run the library's `ProsperoCompressedPfsFile.Parse(...).Decompress()` path or use KrakenDecoder to verify produced blocks. Capture samples of compressed blocks (raw bytes) for MkPFS test vectors.
3. Reimplement (study-first) the Kraken decode/encode corner cases before using any GPL code directly; unit tests should include: single-chunk, multi-chunk, 0x40000 boundary, excess-substream length escapes, long-match splits, Huffman-array fallback, and the keep-compressed cutoff.
4. Verify AES-XTS parameters: confirm sector size differences (inner 0x1000 vs outer 0x10000) and that XTS sector numbering (image block vs file/data block) matches MkPFS expectations.

Practical note
- The library is a high-value engineering reference. For MkPFS: consult `docs/implementation-status.md` first (it summarizes intended behavior and gaps) and then read `Crypto.cs` and `KrakenDecoder.cs` for cryptographic and compression details. Keep the repo's GPL license in mind when deciding whether to re-use code or reimplement.

