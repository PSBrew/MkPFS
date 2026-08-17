# LibOrbisPkg — PKG/PFS Implementation Reference

Upstream repository: https://github.com/maxton/LibOrbisPkg
Upstream wiki: https://github.com/maxton/LibOrbisPkg/wiki/PKG-Information

## Executive Summary

LibOrbisPkg is a broad PS4 packaging toolkit rather than a single-purpose PFS builder. It combines a reusable library, GUI and CLI tools, tests, and Binary Template reference files for PKG, PFS, PFSC, SFO, and related formats. For PFS work specifically, it contains a full filesystem tree model, inode/dirent serializers, block layout logic, signed outer-image generation, optional AES-XTS encryption, PFSC wrapping for nested `pfs_image.dat`, and read paths that reconstruct signed non-contiguous file layouts.

It also ties PFS creation to PKG metadata and key derivation instead of treating PFS as an isolated format. The PKG layer derives developer-controlled keys from Content ID and passcode, exposes fake-PKG EKPFS recovery, carries outer-PFS offsets and digests in the package header, and feeds those values into the PFS builder and reader flows.

## Table of Contents

1. Repository Surface
2. Relevant Modules and Artifacts
3. PFS Build Pipeline
4. PFS Read Pipeline
5. Binary Structures, Flags, and Layout Rules
6. Flat Path Table and Collision Handling
7. PFSC Wrapping Behavior
8. PKG Key Derivation and PFS Integration
9. Verified Corrections and Caveats
10. Practical Reuse Checklist
11. Priority Source Index

## Repository Surface

Top-level repo covers three layers:

1) Tools/apps: `PkgEditor/` (WinForms), `PkgTool/` (CLI), and `*.Core` variants
2) Library: `LibOrbisPkg/` for PKG, PFS, SFO, GP4, PlayGo, utilities, crypto
3) Validation aids: `LibOrbisPkgTests/`, Binary Templates (`PS4PKG.bt`, `PS4PFS.bt`, `PFSC.bt`, `SFO.bt`, `CollisionResolver.bt`)

Main solutions: `LibOrbisPkg.sln` and narrower `LibOrbisPkg.Core.sln`.

## Relevant Modules and Artifacts

PFS construction/reading:
- PFSBuilder.cs — build pipeline, layout, signing/encryption
  https://github.com/maxton/LibOrbisPkg/blob/master/LibOrbisPkg/PFS/PFSBuilder.cs
- PfsReader.cs — read pipeline, encrypted access, non-contiguous signed files
  https://github.com/maxton/LibOrbisPkg/blob/master/LibOrbisPkg/PFS/PfsReader.cs
- PfsStructs.cs — header, inode, dirent, flags/sizes
  https://github.com/maxton/LibOrbisPkg/blob/master/LibOrbisPkg/PFS/PfsStructs.cs
- PfsProperties.cs — presets/properties
  https://github.com/maxton/LibOrbisPkg/blob/master/LibOrbisPkg/PFS/PfsProperties.cs
- FSTree.cs — FS tree model and PFSC-wrapped pfs_image.dat creation
  https://github.com/maxton/LibOrbisPkg/blob/master/LibOrbisPkg/PFS/FSTree.cs
- FlatPathTable.cs — hashing and collision encoding
  https://github.com/maxton/LibOrbisPkg/blob/master/LibOrbisPkg/PFS/FlatPathTable.cs
- PFSCReader.cs, PFSCWriter.cs — nested-image wrapper
  https://github.com/maxton/LibOrbisPkg/blob/master/LibOrbisPkg/PFS/PFSCReader.cs
  https://github.com/maxton/LibOrbisPkg/blob/master/LibOrbisPkg/PFS/PFSCWriter.cs

Crypto and PKG linkage:
- Crypto.cs — derived keys, EKPFS, PFS HMAC/XTS keys
  https://github.com/maxton/LibOrbisPkg/blob/master/LibOrbisPkg/Util/Crypto.cs
- Pkg.cs, Entry.cs — PKG header linkage, EKPFS recovery, ENTRY_KEYS
  https://github.com/maxton/LibOrbisPkg/blob/master/LibOrbisPkg/PKG/Pkg.cs
  https://github.com/maxton/LibOrbisPkg/blob/master/LibOrbisPkg/PKG/Entry.cs

Operational entry points/tests:
- PkgTool/Program.cs — intended CLI workflows and integration sequence
  https://github.com/maxton/LibOrbisPkg/blob/master/PkgTool/Program.cs
- Tests validating encrypted-reader key requirements, PKG build/read
  https://github.com/maxton/LibOrbisPkg/tree/master/LibOrbisPkgTests

Binary Templates:
- PS4PFS.bt, PFSC.bt, PS4PKG.bt — auxiliary references
  https://github.com/maxton/LibOrbisPkg/tree/master/LibOrbisPkg

## PFS Build Pipeline

Setup phase (PfsBuilder.Setup): header init, collect dirs/files, filter `sce_sys` items mirrored as PKG entries, create superroot, build inodes, build flat path table (+ optional collision resolver), compute allocation.

Special root: superroot contains `flat_path_table`, optional `collision_resolver`, then `uroot` with content tree.

Write ordering: header → inode blocks → superroot dirents → flat_path_table → optional collision_resolver → rest of nodes.

Signed vs unsigned: different inode shapes and pointer graphs; signed images insert signature-bearing indirect blocks and special blocks (empty/non-encrypted) after the path table. Unsigned images allocate direct blocks linearly and may place collision resolver there.

Write targets: single-stream vs memory-mapped; the latter parallelizes data-block signing, then signs indirect/final blocks.

## PFS Read Pipeline

Header and inode selection: choose `DinodeS32` for signed (0x2C8) vs `DinodeD32` for unsigned (0xA8).

Encrypted reads: require EKPFS or explicit tweak/data keys. With EKPFS, derive XTS keys via `Crypto.PfsGenEncKey(ekpfs, seed, newCrypt)`; `newCrypt` toggled by PKG `pfs_flags`.

Directory loading: scan dir blocks into `PfsDirent`s; enforce `uroot`.

Non-contiguous files (signed): rebuild block indices from signature records; throw if unsigned image appears non-contiguous.

PFSC decompression: `PfsReader.File.Save(decompress=true)` wraps with PFSCReader when needed.

## Binary Structures, Flags, and Layout Rules

Header highlights: `Version=1`, `Magic=20130315`, default `BlockSize=0x10000`, mode combines signed/64-bit/encrypted/unknown flag; `InodeBlockSig` embedded; `UnknownIndex` (0x36C) only when a seed is present; fallback marker at 0x368 when no seed; reader always reads 16-byte Seed at 0x370.

Inodes: `DinodeD32=0xA8`, `DinodeS32=0x2C8`, `DinodeS64=0x310` (header sig region). Flags seen: `compressed=0x1`, `readonly=0x10`, `internal=0x20000`.

Dirents: inode, type, name length, entry size; padded to 8-byte alignment; builder may jump blocks if little room remains.

Defaults/constants: PFS block size `0x10000`; XTS sector `0x1000`, starts at sector `16`; signed record size `36`; initial `emptyBlock=0x4`.

## Flat Path Table and Collision Handling

Hash: uppercase path fold with `hash = char.ToUpper(c) + (31 * hash)`.

Encoding: directories ORed with `0x20000000`; collisions marked with `0x80000000` then replaced with `0x80000000 | offset` into synthetic resolver stream. Resolver entries are dirent-style with full-path names and `0x18` spacing per group. Always present `flat_path_table`; conditional `collision_resolver`.

## PFSC Wrapping Behavior

Writer: PFSCWriter frames header + full-block table and streams nested PFS bytes after header (no compression emitted).

Reader: supports direct-copy, zero-fill (sectorSize > blockSize), and deflate (sectorSize < blockSize with 2-byte prefix) sectors.

## PKG Key Derivation and PFS Integration

Derived keys (dk0..dk6): `ComputeKeys` SHA-256 over (index[BE] | padded content ID | passcode). `dk1` (EKPFS) feeds PFS keys; `dk2`/`dk3` used for other entries.

PFS keys: `PfsGenCryptoKey(ekpfs, seed, index)` uses HMAC-SHA256 with little-endian index in this implementation; `PfsGenEncKey` splits 32-byte digest into XTS tweak/data; `PfsGenSignKey` for signing; `newCrypt` changes the HMAC key to HMAC(ekpfs, seed) before derivation.

Fake PKG: `Pkg.GetEkpfs()` recovers EKPFS from fake-PKG records using known RSA sets, AES IV/key from `IMAGE_KEY` + `dk3`, and final RSA decrypt.

ENTRY_KEYS: stores seed digest, seven digests as `SHA256(dk) XOR dk`, and seven RSA-encrypted records; index 0 stores the passcode itself in RSA slot.

PKG→PFS flow: `pfs_buildinner` (unsigned inner) → `pfs_buildouter` (signed outer, optional encryption) → `pkg_build`. Extraction reverses this via EKPFS recovery and PFSC→PFS.

## Verified Corrections and Caveats

1) `PfsGenCryptoKey` index endianness differs from `ComputeKeys` (LE vs BE).
2) `newCrypt` path is real and toggled via PKG `pfs_flags` in some images.
3) `MakeOuterPFSProps()` uses zero seed in this repo (verification note, repo-specific).
4) PFSCWriter emits framing only; no adaptive compression.
5) PFSCReader supports compressed/zero-fill sectors.
6) Some `sce_sys` members are filtered from FS tree in favor of PKG entries.
7) Tests increase trust in behavior vs prose-only repos.

Unknowns/partials: additional inode flags; exact header fallback semantics at 0x368; real-world prevalence of `newCrypt`; availability of general PFSC writer elsewhere.

## Practical Reuse Checklist

- Two-stage model: inner unsigned PFS, then signed outer PFS containing PFSC-wrapped `pfs_image.dat`.
- Mirror superroot layout and FlatPathTable hashing/collision encoding.
- Preserve distinct inode layouts for signed vs unsigned.
- Maintain signed-image block-signature graph and ordering dependency.
- XTS: sector 0x1000, start 16; preserve empty-block behavior.
- Keep `ComputeKeys` vs `PfsGenCryptoKey` endianness distinct.
- Implement `newCrypt` when needed for flagged images.
- Treat PFSCWriter as framing-only unless adding compression deliberately.
- Use tests and BT files as verification aids.

## Priority Source Index

- PFSBuilder.cs — https://github.com/maxton/LibOrbisPkg/blob/master/LibOrbisPkg/PFS/PFSBuilder.cs
- PfsReader.cs — https://github.com/maxton/LibOrbisPkg/blob/master/LibOrbisPkg/PFS/PfsReader.cs
- PfsStructs.cs — https://github.com/maxton/LibOrbisPkg/blob/master/LibOrbisPkg/PFS/PfsStructs.cs
- Crypto.cs — https://github.com/maxton/LibOrbisPkg/blob/master/LibOrbisPkg/Util/Crypto.cs
- FlatPathTable.cs — https://github.com/maxton/LibOrbisPkg/blob/master/LibOrbisPkg/PFS/FlatPathTable.cs
- FSTree.cs — https://github.com/maxton/LibOrbisPkg/blob/master/LibOrbisPkg/PFS/FSTree.cs
- PFSCReader.cs — https://github.com/maxton/LibOrbisPkg/blob/master/LibOrbisPkg/PFS/PFSCReader.cs
- PFSCWriter.cs — https://github.com/maxton/LibOrbisPkg/blob/master/LibOrbisPkg/PFS/PFSCWriter.cs
- Pkg.cs — https://github.com/maxton/LibOrbisPkg/blob/master/LibOrbisPkg/PKG/Pkg.cs
- Entry.cs — https://github.com/maxton/LibOrbisPkg/blob/master/LibOrbisPkg/PKG/Entry.cs
- PkgTool/Program.cs — https://github.com/maxton/LibOrbisPkg/blob/master/PkgTool/Program.cs
- Tests — https://github.com/maxton/LibOrbisPkg/tree/master/LibOrbisPkgTests
- BT files — https://github.com/maxton/LibOrbisPkg/tree/master/LibOrbisPkg
