# TLOU PSARC Tool — PSARC Archive Reference for TLOU

- Canonical source: https://github.com/amrshaheen61/TLOU_PSARC_Tool
- Local artifact folder: [related-projects/tlou-psarc-tool](tlou-psarc-tool)
- Indexed on: 2026-06-14
- Source type: git repository (C#/.NET Windows Forms)

## Executive Summary

TLOU PSARC Tool is a Windows-only GUI utility for extracting and reimporting files from `.psarc` archives used by The Last of Us (PS3/PS4). It provides a practical, working implementation of PSARC reading, decompression (Oodle and zlib), file-name resolution via MD5 hashing, and a partial write-back path. Its strongest value lies in demonstrating the PSARC on-disk layout, the multi-block compression table, and the name-lookup scheme that maps MD5 hashes back to original file paths.

## Table of Contents

1. Scope and Identity
2. Project Structure
3. Supported Workflow Modes
4. Plain-English: How PSARC Works Here
5. On-Disk Format Specification
6. Compression Behavior
7. Name Resolution (Hash Table)
8. Read/Extract Flow
9. Write/Import Flow
10. Key Constraints and Implementation Gaps
11. Stream Abstraction Layer
12. Python Implementation Blueprint
13. Source Index

## Scope and Identity

This reference focuses on the PSARC container format as implemented by:

- Archive class: `TLOU_PSARC_Tool.Core.Psarc`
- Compression: `TLOU_PSARC_Tool.Core.Compression`
- Stream I/O: `Helper.IStream`, `Helper.MStream`, `Helper.FStream`
- GUI: `TLOU_PSARC_Tool.Forms.FrmMain`

## Project Structure

```text
related-projects/tlou-psarc-tool/
├── TLOU PSARC Tool.sln
├── cso.dat                                    # sample/test PSARC data
├── README.md
├── LICENSE.txt
└── TLOU PSARC Tool/
    ├── TLOU PSARC Tool.csproj
    ├── Program.cs                             # entry point
    ├── App.config
    ├── oo2core_9_win64.dll                    # Oodle decompression native lib
    ├── Core/
    │   ├── Psarc.cs                           # PSARC parser, reader, writer
    │   ├── Compression.cs                     # Oodle + zlib decompression/compression
    │   └── Md5.cs                             # MD5 hash helper for name lookup
    ├── Forms/
    │   ├── FrmMain.cs                         # GUI logic (export/import)
    │   ├── FrmMain.Designer.cs
    │   └── FrmMain.resx
    ├── Helper/
    │   ├── IStream.cs                         # stream interface (endian-aware)
    │   ├── MStream.cs                         # memory-backed stream implementation
    │   └── FStream.cs                         # file-backed stream implementation
    └── Properties/
        └── AssemblyInfo.cs
```

High-value files:

- [related-projects/tlou-psarc-tool/TLOU PSARC Tool/Core/Psarc.cs](tlou-psarc-tool/TLOU%20PSARC%20Tool/Core/Psarc.cs)
- [related-projects/tlou-psarc-tool/TLOU PSARC Tool/Core/Compression.cs](tlou-psarc-tool/TLOU%20PSARC%20Tool/Core/Compression.cs)
- [related-projects/tlou-psarc-tool/TLOU PSARC Tool/Core/Md5.cs](tlou-psarc-tool/TLOU%20PSARC%20Tool/Core/Md5.cs)
- [related-projects/tlou-psarc-tool/TLOU PSARC Tool/Helper/IStream.cs](tlou-psarc-tool/TLOU%20PSARC%20Tool/Helper/IStream.cs)
- [related-projects/tlou-psarc-tool/TLOU PSARC Tool/Helper/MStream.cs](tlou-psarc-tool/TLOU%20PSARC%20Tool/Helper/MStream.cs)
- [related-projects/tlou-psarc-tool/TLOU PSARC Tool/Helper/FStream.cs](tlou-psarc-tool/TLOU%20PSARC%20Tool/Helper/FStream.cs)
- [related-projects/tlou-psarc-tool/TLOU PSARC Tool/Forms/FrmMain.cs](tlou-psarc-tool/TLOU%20PSARC%20Tool/Forms/FrmMain.cs)

## Supported Workflow Modes

| Mode | Behavior | Status |
|------|----------|--------|
| Extract from `.psarc` | Parses header, reads size array, resolves names via MD5, decompresses blocks | Implemented |
| Import into `.psarc` | Appends raw file data at end of archive, updates entry metadata | Implemented |
| Compression on import | Re-compresses blocks when writing back | Not implemented (writes uncompressed) |
| CRC/integrity checking | Validates archive integrity | Not implemented |

## Plain-English: How PSARC Works Here

A `.psarc` file is a compressed archive container used by Naughty Dog games. Think of it as:

1. **Header** (32 bytes): identifies the file as "PSAR", specifies compression format, entry count, data block size, and flags.
2. **Size array**: a table of compressed block sizes used to locate and decompress individual data blocks.
3. **Entry table**: each entry has a 16-byte MD5 hash (key), an index into the size array, a 5-byte big offset, and a 5-byte big uncompressed size.
4. **Data blocks**: actual file payloads, split into fixed-size chunks. Each chunk may be compressed independently.
5. **Name table**: the very first entry is a special file containing newline-separated paths. Each path is MD5-hashed to build a lookup dictionary that maps hashes back to human-readable names.

Loading flow:
1. Read header (big-endian).
2. Read the size array (block size table) located between entry table end and header headerSize.
3. Parse the first entry as the name table: decompress it, split by newlines, compute MD5 for each path, build a `hash -> name` dictionary.
4. Seek back and parse all remaining entries. Each entry's MD5 hash is looked up in the dictionary to recover its file path.
5. Each entry references one or more compressed blocks via `CompressedBlockSizeIndex` into the size array. Blocks are decompressed individually and concatenated.

## On-Disk Format Specification

Endianness: **Big-endian** throughout.

Reference comment in source: `http://aluigi.altervista.org/bms/brink.bms`

### Header (32 bytes)

| Offset | Size | Type | Field |
|--------|------|------|-------|
| 0x00 | 4 | char[4] | Magic: "PSAR" |
| 0x04 | 2 | int16 | Unknown (U1) |
| 0x06 | 2 | int16 | Unknown (U2) |
| 0x08 | 4 | char[4] | Compression format (e.g., "oodl", "zlib") |
| 0x0C | 4 | int32 | Header size (byte offset where data begins) |
| 0x10 | 4 | int32 | Entry size (byte size of each entry record) |
| 0x14 | 4 | int32 | Entry count |
| 0x18 | 4 | uint32 | Data block size (max uncompressed chunk size) |
| 0x1C | 4 | int32 | Flags |

### Size Array

Located immediately after the entry table (entries * entrySize bytes from start offset). Element width depends on `DataBlockSize`:

- 1 byte if `DataBlockSize` fits in 8 bits
- 2 bytes (uint16) if `DataBlockSize` fits in 16 bits
- 4 bytes (uint32) otherwise

Read from entry table end up to `header.headerSize`.

### Entry Record

| Offset | Size | Type | Field |
|--------|------|------|-------|
| 0x00 | 16 | byte[16] | MD5 hash of file path |
| 0x10 | 4 | int32 | CompressedBlockSizeIndex (index into size array) |
| 0x14 | 1 | byte | High byte of 5-byte uncompressed size |
| 0x15 | 4 | uint32 | Low 4 bytes of uncompressed size |
| 0x19 | 1 | byte | High byte of 5-byte offset |
| 0x1A | 4 | uint32 | Low 4 bytes of offset |

Total per entry: 31 bytes (0x1F). The 5-byte fields combine as: `value = (high_byte << 32) | low_uint32`.

### Block Decomposition

A file's data spans one or more blocks starting at `CompressedBlockSizeIndex`. For each block:

- If `ArraySize[index] == 0`, the block is stored uncompressed at `DataBlockSize` bytes.
- Otherwise, `ArraySize[index]` is the compressed size. Decompress using the header's compression format.
- Blocks are concatenated to produce the full file content.
- For files smaller than `DataBlockSize`, there is a single block.

## Compression Behavior

Supported formats (determined by header `CompressionFormat` field):

| Format ID | Algorithm | Library |
|-----------|-----------|---------|
| `"oodl"` | Oodle (Kraken default) | `oo2core_9_win64.dll` via P/Invoke |
| `"zlib"` | zlib/deflate | `Joveler.ZLibWrapper` |

Oodle decompression uses `OodleLZ_Decompress` with standard parameters (fuzz-safe, CRC-check, thread module 3). Compression uses `OodleLZ_Compress` with Kraken format at Normal level by default.

Decompression validates output size: throws if `verificationSize != decompressedSize`.

## Name Resolution (Hash Table)

The first entry in the archive is a special "names" file. Its content is a newline-separated list of all file paths in the archive. Resolution:

1. Decompress the names entry.
2. Split by `\n` (and `\r`).
3. For each path, compute `MD5(path)` and store in `HashNames[hash_hex] = path`.
4. When parsing subsequent entries, the 16-byte MD5 hash is hex-encoded and looked up in this dictionary.
5. If not found, the name falls back to `"0x" + hex_hash`.

Evidence: `Psarc.Load()` method in Psarc.cs.

## Read/Extract Flow

`FrmMain.Export()`:

1. Open file dialog for `.psarc`.
2. Open save dialog for `FilesMap.txt` (manifest of extracted files).
3. `Psarc.Load(path)` parses header, size array, names, and entries.
4. For each entry:
   - Create directory structure.
   - Decompress file data via `GetFile(entryName)` -> `GetFileRaw(entry)`.
   - Write bytes to disk.
   - Append path to `FilesMap.txt`.
5. Dispose the Psarc instance.

## Write/Import Flow

`FrmMain.Import()`:

1. Open file dialogs for `.psarc` and `FilesMap.txt`.
2. Validate all listed files exist and are present in the archive's entry dictionary.
3. For each file in `FilesMap.txt`:
   - Read file bytes from disk.
   - Call `Psarc.ImportFile(entryName, bytes)`:
     - Seek to end of file.
     - Write author signature bytes.
     - Set entry offset to current position.
     - Set entry uncompressed size.
     - Recalculate blocks as uncompressed (each block = `DataBlockSize` or remainder).
     - Write raw bytes (no compression).
4. Call `Psarc.Save()` -> `BuildHaeder()`:
   - Rebuild the size array from all entries' block metadata.
   - Write new header, entry table, and size array at file start.
   - If header grew/shrunk, insert or delete bytes and adjust all entry offsets.

## Key Constraints and Implementation Gaps

1. **No recompression on import**: Imported files are written uncompressed regardless of original compression format. `CalcBlocksSize` sets `CompressSize == DecompressSize` for all blocks.
2. **Windows-only**: Requires `oo2core_9_win64.dll` (Oodle) via P/Invoke. No cross-platform support.
3. **GUI-only**: No CLI interface. All interaction through Windows Forms.
4. **Author signature injected**: Every import appends "TLOU PSARC Tool By Amr Shaheen(amrshaheen61)" as raw bytes at the write position, which bloats the archive on repeated imports.
5. **Header rebuild fragility**: `BuildHaeder()` deletes/inserts bytes at file start to accommodate size array changes, adjusting all offsets. This is a risky operation on large files.
6. **Name table not updated**: The names entry (first entry) is not rewritten during import, so newly added paths would not be discoverable by other tools.
7. **No entry addition/removal**: Only existing entries can have their data replaced. New entries cannot be added; existing entries cannot be removed.
8. **Size array element width**: The switch statement for reading the size array includes placeholder cases for 3-byte and 8-byte values (`case 30`, `case 80`) that are unimplemented.

## Stream Abstraction Layer

The tool uses a three-layer stream abstraction:

- **`IStream`** (interface): Defines endian-aware read/write for all primitive types (byte, short, int, long, string), plus seek, insert, delete, and NUL-terminated string operations. Supports both big and little endian via the `Endian` property.
- **`MStream`** (memory): In-memory byte array stream. Used for temporary buffers (name table, decompressed data). Supports dynamic resize via `InsertBytes`/`DeleteBytes`.
- **`FStream`** (file): File-backed stream wrapping `FileStream`. Used for the main archive file.

The endian support is per-read/write call rather than per-stream: each `GetXxx`/`SetXxx` method accepts an optional offset and reads/writes in the stream's current endian setting.

## Python Implementation Blueprint

### Stage 1: Reader

Implement `read_psarc(path)`:

- Parse header (32 bytes, big-endian).
- Compute size array element width from `DataBlockSize`.
- Read size array between entry table end and `headerSize`.
- Parse first entry as names table: decompress, split by newlines, MD5-hash each path.
- Parse all entries: 16-byte MD5, block index, 5-byte uncompressed size, 5-byte offset.
- Resolve names via MD5 dictionary.

### Stage 2: Decompressor

- Support `"zlib"` (Python stdlib `zlib`).
- Support `"oodl"` via Oodle native library (platform-specific `.so`/`.dll` loading).
- Implement per-block decompression: read `ArraySize[index]` bytes, decompress to expected size.

### Stage 3: File extraction

- For each entry, gather blocks starting at `CompressedBlockSizeIndex`, decompress each, concatenate.
- Write to disk preserving directory structure.

### Stage 4: Writer (optional, lower priority)

- Uncompressed import: append raw bytes, rebuild header/size array.
- Note the limitations: no recompression, no name table update, signature injection.

## Source Index

Core sources:

- [related-projects/tlou-psarc-tool/TLOU PSARC Tool/Core/Psarc.cs](tlou-psarc-tool/TLOU%20PSARC%20Tool/Core/Psarc.cs) -- PSARC parser, reader, writer
- [related-projects/tlou-psarc-tool/TLOU PSARC Tool/Core/Compression.cs](tlou-psarc-tool/TLOU%20PSARC%20Tool/Core/Compression.cs) -- Oodle + zlib compress/decompress
- [related-projects/tlou-psarc-tool/TLOU PSARC Tool/Core/Md5.cs](tlou-psarc-tool/TLOU%20PSARC%20Tool/Core/Md5.cs) -- MD5 helper

Stream layer:

- [related-projects/tlou-psarc-tool/TLOU PSARC Tool/Helper/IStream.cs](tlou-psarc-tool/TLOU%20PSARC%20Tool/Helper/IStream.cs) -- endian-aware stream interface
- [related-projects/tlou-psarc-tool/TLOU PSARC Tool/Helper/MStream.cs](tlou-psarc-tool/TLOU%20PSARC%20Tool/Helper/MStream.cs) -- memory stream
- [related-projects/tlou-psarc-tool/TLOU PSARC Tool/Helper/FStream.cs](tlou-psarc-tool/TLOU%20PSARC%20Tool/Helper/FStream.cs) -- file stream

GUI:

- [related-projects/tlou-psarc-tool/TLOU PSARC Tool/Forms/FrmMain.cs](tlou-psarc-tool/TLOU%20PSARC%20Tool/Forms/FrmMain.cs) -- export/import orchestration

Upstream references:

- https://github.com/amrshaheen61/TLOU_PSARC_Tool
- http://aluigi.altervista.org/bms/brink.bms (PSARC BMS script reference cited in source)
