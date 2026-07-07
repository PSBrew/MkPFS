# PKGTool — PKG Container Reverse-Engineering Reference

Upstream repository: https://github.com/thesupersonic16/PKGTool

## Executive Summary

PKGTool provides a practical read/extract and partial write/repack implementation for a PKG archive format via `PKGArchive`. Its strongest value is that the repository contains both the archive parser/writer and the supporting HedgeLib reader/writer primitives needed to verify the binary layout directly from source. Its write path is intentionally incomplete and includes constraints that matter for any faithful reimplementation.

## Table of Contents

1. Scope and Identity
2. Project Structure
3. Supported Workflow Modes
4. Plain-English: How PKG Works Here
5. On-Disk Format Specification
6. Compression Stream Behavior
7. Read/Extract Flow
8. Write/Repack Flow
9. Key Constraints and Implementation Gaps
10. HedgeLib Dependency Findings
11. Python Implementation Blueprint
12. Source Index
13. Reindex Delta vs Older Draft

## Scope and Identity

This reference focuses on the PKG container format as implemented by this repository:

- Archive class: `HedgeLib.Archives.PKGArchive`
- Core parser/writer: [PKGTool/PKGArchive.cs](https://github.com/thesupersonic16/PKGTool/blob/master/PKGTool/PKGArchive.cs)
- CLI orchestration: [PKGTool/Program.cs](https://github.com/thesupersonic16/PKGTool/blob/master/PKGTool/Program.cs)

Note on naming:

- Your legacy draft used "PSF/PKG" terminology.
- This repository itself implements a `.pkg` archive format only (class name `PKGArchive`).

## Project Structure

```text
PKGTool/
├── PKGArchive.cs
├── Program.cs
├── Addon.cs
└── PKGTool.csproj
HedgeLib/
├── HedgeLib/
│   ├── IO/ExtendedBinary.cs
│   └── Archives/
│       ├── Archive.cs
│       └── ArchiveFile.cs
└── HedgeTools/...
```

High-value files:

- https://github.com/thesupersonic16/PKGTool/blob/master/PKGTool/PKGArchive.cs
- https://github.com/thesupersonic16/PKGTool/blob/master/PKGTool/Program.cs
- https://github.com/thesupersonic16/PKGTool/blob/master/PKGTool/PKGTool.csproj
- https://github.com/thesupersonic16/PKGTool/blob/master/PKGTool.sln
- https://github.com/thesupersonic16/PKGTool/blob/master/.gitmodules
- https://github.com/Radfordhound/HedgeLib/blob/8b4c988fa04c9c85afa4486d5115cfb79f23331a/HedgeLib/HedgeLib/IO/ExtendedBinary.cs
- https://github.com/Radfordhound/HedgeLib/blob/8b4c988fa04c9c85afa4486d5115cfb79f23331a/HedgeLib/HedgeLib/Archives/Archive.cs
- https://github.com/Radfordhound/HedgeLib/blob/8b4c988fa04c9c85afa4486d5115cfb79f23331a/HedgeLib/HedgeLib/Archives/ArchiveFile.cs

## Supported Workflow Modes

| Mode | Behavior | Status in Tool |
|------|----------|----------------|
| Extract from `.pkg` | Parses header/table, loads entries, decompresses flagged payloads | Implemented |
| Repack from directory | Adds files to archive and writes table/payloads | Implemented (limited) |
| Write compressed entries | Compression flag/stream emission during save | Not implemented |
| CRC32 generation | CRC field at header offset 0x00 | Not implemented |

Evidence:

- Load path and decompress branch in PKGArchive.cs
- Save path TODO comments and hardcoded values in PKGArchive.cs

## Plain-English: How PKG Works Here

Think of a `.pkg` file here as a simple archive container:

- The start of the file has a tiny header (CRC placeholder + file count).
- Then comes a fixed-size table that says, for each file: name, original size, stored size, data offset, compressed flag.
- After the table, payload bytes are stored, and each table row points to its payload offset.

Load flow:
1. Read file count from header.
2. Read all table rows.
3. Seek to each `DataOffset`.
4. If `Compressed` is false, read raw bytes sized by `DataUncompressedSize`.
5. If `Compressed` is true, run the custom back-reference decoder and rebuild original bytes.

Write flow (current implementation):
- Writes valid table + payload layout for uncompressed entries.
- Does not compute real CRC.
- Does not write compressed payload streams.
- Stores file names in fixed 64-byte field (beware >64 char names).

## On-Disk Format Specification

Endianness:
- Reader/writer created with `isBigEndian = false` in PKGArchive.
- HedgeLib ExtendedBinary defaults to little-endian when `IsBigEndian == false`.

Header:
- `0x00..0x03`: CRC32 placeholder (`uint32`)
- `0x04..0x07`: file count (`int32`)

File table (per-entry size = `0x54` bytes):
- `0x00..0x3F` (64 bytes): filename buffer
- `0x40..0x43` (`uint32`): uncompressed size
- `0x44..0x47` (`uint32`): stored size
- `0x48..0x4B` (`uint32`): absolute payload offset
- `0x4C` (`byte`): compressed flag (`1` or `0`)
- `0x4D..0x4F` (3 bytes): unknown attributes

Reader behavior:
- `ReadSignature(0x40).Replace("\0", "")` strips all NULs from 64-byte name.

Writer behavior:
- Creates `char[0x40]`, copies file name, writes fixed 64-char field.

## Compression Stream Behavior

Compressed entries are decoded by `ReadAndDecompress`.

Compressed payload header (12 bytes):
- `uint32 decompressedSize`
- `uint32 compressedSize`
- `byte copyByte` (escape marker)
- `3 bytes` reserved/skipped

Decode algorithm highlights:
- Loop while output length `< decompressedSize`.
- If byte != copyByte → emit literally.
- If byte == copyByte:
  - Read `returnByte`. If it equals `copyByte`, emit a literal copyByte.
  - Else, possibly decrement `returnByte`, compute back-reference offset, read `length`, copy from output.
- Termination controlled by `decompressedSize` (not `compressedSize`).

## Read/Extract Flow

- File path → `ExtractPKG`
- Directory path → `RepackPKG`

Extract steps:
1. Create output dir from input file stem.
2. `PKGArchive.Load(path)`.
3. For each entry, `Extract` to disk.

## Write/Repack Flow

Repack steps:
1. `archive.AddDirectory(dirPath, false)`
2. `archive.Save(dirPath + ".pkg")`

Save path details:
- Reserve `crc32` offset, write file count.
- For each file: write name buffer, uncompressed size, stored size (same), reserve payload offset, write zero attrs.
- Fill payload offsets and write data.
- Fill CRC with `0u`.

Offsets:
- `FillInOffset` writes absolute offsets by default in HedgeLib writer.

## Key Constraints and Implementation Gaps

1. CRC is placeholder-only.
2. Writer does not emit compressed entries.
3. Unknown 3-byte attributes not populated.
4. Repack is non-recursive (`AddDirectory(..., false)`).
5. Basename flattening risk: directory structure not preserved by default.
6. Filename >64 chars can fail on save.
7. Decompressor ignores `compressedSize` as strict bound.

## HedgeLib Dependency Findings

- PKGTool.csproj references HedgeLib subprojects; solution includes HedgeLib and editor projects.
- `.gitmodules` declares `HedgeLib` submodule URL.

## Implementation Blueprint

- Reader parity first (endianness, 64-byte names, decompressor behavior).
- Stable uncompressed writer (fixed-size records, absolute offsets, zero CRC/attrs).
- Round-trip fixtures (edge cases: long names, nested dirs, unusual bytes).
- Explore compressor and CRC coverage if parity with compressed entries is required.

## Source Index

- https://github.com/thesupersonic16/PKGTool/blob/master/PKGTool/PKGArchive.cs
- https://github.com/thesupersonic16/PKGTool/blob/master/PKGTool/Program.cs
- https://github.com/thesupersonic16/PKGTool/blob/master/PKGTool/Addon.cs
- https://github.com/thesupersonic16/PKGTool/blob/master/PKGTool/PKGTool.csproj
- https://github.com/thesupersonic16/PKGTool/blob/master/PKGTool.sln
- https://github.com/thesupersonic16/PKGTool/blob/master/.gitmodules
- https://github.com/Radfordhound/HedgeLib
