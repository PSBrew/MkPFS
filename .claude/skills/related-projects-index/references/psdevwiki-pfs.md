# PSDevWiki — PFS (Reference)

Upstream: https://www.psdevwiki.com/ps4/PFS

Executive summary
- Concise description of the PlayStation File System (PFS) layout: superblock (header), inode blocks, directory blocks, data blocks.
- Precisely documents on‑disk structs (header fields, 32‑bit inode variant di_d32, dirent encoding) and the flat_path_table hashing used for fast lookups.
- Notes encryption model (XTS‑AES‑128) and key derivation linkage to PKG (EKPFS + seed) while emphasizing that the page focuses on unsigned/unencrypted PFS.

Why it matters (MkPFS scope)
- Serves as a baseline spec for the unencrypted PFS writer/reader: field offsets, alignment, path hashing, and directory entry packing — all critical to produce images mountable by tools like ShadowMountPlus.
- Inode/dirent and fpt hashing rules map directly to MkPFS structures (header constants, block sizes, case insensitivity flag, superroot/uroot entries).

Key technical points
- Superblock (selected fields/semantics):
  - version: 1 (PS4), 2 (PS5)
  - magic: 20130315
  - mode (bits): 0=signed, 1=64‑bit inodes, 2=encrypted, 3=case‑insensitive
  - blocksz: power of two, typical 64 KiB for game data; min 4 KiB, max 32 MiB
  - ndinode/ndblock/ndinodeblock: counts for inodes/data/inode blocks
  - superroot_ino: inode index of the superroot (contains uroot and fpt)
- Inodes (di_d32 shown; packed in fixed blocks, no cross‑block entries):
  - mode: POSIX bits + file(0x8000)/dir(0x4000)
  - flags: compressed, readonly, internal
  - size/size_compressed; times[4]; uid/gid; blocks; db[12], ib[5]
- Dirents: 8‑byte aligned entries with ino, type (2=file, 3=dir, 4=., 5=..), namelen, entsize, name, padding.
- Root discovery: superroot → uroot; flat_path_table file sits above uroot and maps uppercase‑folded hashes to inodes.
- Flat path table hashing (case‑insensitive):
  - hash = Σ uppercase(c) + 31*hash; entries sorted ascending by 32‑bit hash.
- Encryption (production images): XTS‑AES‑128; keys derived from PKG EKPFS and PFS header crypt seed; encryption starts at second block.

Notes / gotchas
- The page models unsigned/unencrypted PFS; signed variants add per‑block signatures and may use 64‑bit inodes (mode bit 1).
- Case‑insensitive images set mode bit 3; path hashing also uses uppercase transform.
- Directory entry packing must honor 8‑byte alignment; over/under‑padding breaks kernel dir walks.

Source index
- https://www.psdevwiki.com/ps4/PFS
- Header/Superblock, Inodes, Dirents, Root finding, flat_path_table, Encryption sections