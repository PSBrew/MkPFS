# PSDevWiki — PKG files (Reference)

Upstream: https://www.psdevwiki.com/ps4/PKG_files

Executive summary
- Orientation and structure notes for PS4 PKG containers: big‑endian header, entry tables, digest blocks, and embedded signed/encrypted PFS payloads.
- Captures header fields that expose PFS placement (offset/size/digests) and content flags; lists common entry IDs (Entry Keys, Image Key, Metadata, Entry Names) with encryption hints.
- Documents PFS-in-PKG crypto derivation at a practical level (EKPFS→HMAC→XTS keys) and packaging/delivery adjuncts (title patch XML, PlayGo chunk manifests).

Why it matters (MkPFS scope)
- PKG header fields (pfs_image_offset/size/digests) are vital when validating PKG shells that embed PFS images produced elsewhere.
- Entry tables and digest blocks inform verification strategies for outer PKG integrity vs inner PFS correctness (two concentric validation domains).
- The PFS crypto derivation (EKPFS, crypt seed, HMAC-SHA256 split into tweak/data) clarifies how signed/encrypted production images differ from development/unsigned flows MkPFS targets.

Key technical points
- Header basics (big‑endian; excerpted fields):
  - pkg_magic=0x7F434E54, pkg_type, pkg_file_count, pkg_entry_count, pkg_table_offset, pkg_body_offset/size.
  - PFS placement: pfs_image_count (0x404), pfs_image_flags (0x408), pfs_image_offset (0x410), pfs_image_size (0x418), mount_image_offset/size, pkg_size (0x430), pfs_signed_size (0x438), pfs_cache_size (0x43C), pfs_image_digest (0x440), pfs_signed_digest (0x460), split sizes.
- Entry table (Sc0) describes per‑file metadata. Common entry IDs:
  - 0x10 Entry Keys (RSA-2048 related), 0x20 Image Key (AES‑128‑CBC key/IV derived from dk3_), 0x80 General Digests, 0x100 Metadata, 0x200 Entry Names.
  - Common files: license.dat/info, nptitle.dat, npbind.dat, selfinfo.dat, imageinfo.dat, psreserved.dat, param.sfo, playgo-*, icon0/pic0/snd0, trophy trp.
- Table entry digests: first entry is a digest block containing SHA‑256 for each subsequent entry.
- PFS in PKG (production):
  - XTS-AES encrypted; derive keys by HMAC‑SHA256(seed_prefix||EKPFS) where HMAC key = PFS crypt seed at offset 0x370 in PFS; split 32‑byte result into tweak (first 16) and data (second 16) keys.
  - Nested image exposed at runtime differs (signed inode variant, signatures per direct/indirect block).
  - Inside signed/encrypted PFS is pfs_image.dat (PFSC container) that holds app assets.
- Delivery metadata
  - Title patch XML structure enumerates packages, cumulative/delta, system_ver (decimal), PlayGo manifest URL.
  - PlayGo JSON enumerates chunk splicing: originalFileSize, packageDigest, numberOfSplitFiles, per‑chunk url/fileOffset/fileSize/hash.

Notes / gotchas
- Page mixes confirmed fields with community notes; when implementing builders/parsers, prefer LibOrbisPkg source for canonical types and field widths.
- ContentFlags mapping is indicative and incomplete; treat unknowns cautiously.
- For MkPFS, these PKG fields are reference material — MkPFS does not emit PKG but can verify/interpret inner PFS outputs when wrapped.

Source index
- https://www.psdevwiki.com/ps4/PKG_files
- Content flags and header structure sections on the page
- PFS subsection describing XTS/HMAC derivation (seed and EKPFS)
- PlayGo manifest and Title patch XML sections