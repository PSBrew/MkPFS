# MkPFS

[![PyPI](https://img.shields.io/pypi/v/mkpfs?style=flat-square&logo=pypi&logoColor=white&color=2563eb)](https://pypi.org/project/mkpfs/)
[![Python 3.8+](https://img.shields.io/badge/python-3.8%2B-2563eb?style=flat-square&logo=python&logoColor=white)](https://www.python.org/downloads/release/python-380/)
[![License](https://img.shields.io/badge/license-GPL--3.0-0f172a?style=flat-square)](LICENSE)
[![Status](https://img.shields.io/badge/status-production%2Fstable-1d4ed8?style=flat-square)](https://github.com/PSBrew/MkPFS/actions)
[![Platforms](https://img.shields.io/badge/platforms-Windows%20%7C%20macOS%20%7C%20Linux-2563eb?style=flat-square)](#installation)
[![Profiles](https://img.shields.io/badge/profiles-PS4%20%2F%20PS5-3b82f6?style=flat-square)](#command-reference)
[![GitHub Sponsors](https://img.shields.io/badge/Fund%20Development-GitHub%20Sponsors-e11d48?style=flat-square&logo=githubsponsors&logoColor=white)](https://github.com/sponsors/RenanGBarreto)

MkPFS is a command-line tool and Python library for building, verifying, inspecting, browsing, and extracting PlayStation FileSystem (PFS) disk images. 
It works with common image naming conventions such as `.ffpfs`, `.ffpfsc`, `.pfs`, `.dat`, `.exfat`, and `.bin`, and fits both direct image workflows and PKG or FPKG inner-PFS generation.

[Quick Start](#-quick-start) · [Compression Statistics](#-compression-statistics) · [Installation](#-installation) · [GUI](#-gui) · [Command reference](#command-reference) · [Development](#-development) · [Related projects](#related-projects) · [Sponsor](https://github.com/sponsors/RenanGBarreto)

## 🎯 Why MkPFS

MkPFS is designed to be a clean and practical entry point for PlayStation PFS image workflows:

- Create and manage PFS disk images for PlayStation-oriented workflows
- Verify structure, payload hashes, layout consistency, and source-tree matches
- Inspect image contents quickly with a tree view instead of digging through raw structures
- Work with common image extensions such as `.ffpfs`, `.ffpfsc`, `.pfs`, `.dat`, `.exfat`, and `.bin`.
- Use the generated images with tools like [MicroMount](https://github.com/drakmor/ShadowMountPlus) and [ShadowMountPlus](https://github.com/drakmor/ShadowMountPlus)
- Build the inner PFS filesystem used inside PKG or FPKG workflows
- Use the same core workflow from both the CLI and the Python library
- Explore a bundled, source-backed knowledge base for PFS and PKG research

## 🚀 Quick Start

### Using the command line

```bash
# Install/Update using pip
python -m pip install -U "mkpfs[gui]"

# Creating Images: Option 1: .exfat -> .ffpfsc (Works with ShadowMountPlus)  (Maximum compatibility)
python -m mkpfs pack file './BREW1234.exfat' './BREW1234.ffpfsc'

# Creating Images: Option 2: .ffpkg -> .ffpfsc (Works with ShadowMountPlus) 
python -m mkpfs pack file './BREW1234.ffpkg' './BREW1234.ffpfsc'

# Creating Images: Option 3: Game folder -> .ffpfsc in one pass (default: exFAT-wrapped, no temp file)
python -m mkpfs pack folder './BREW1234-app' './BREW1234.ffpfsc'

# Creating Images: Option 4: Game folder packed directly as PFS (advanced single-pass)
python -m mkpfs pack folder --raw './BREW1234-app/' './BREW1234.ffpfs'

# Creating Images: Option 5: Game folder wrapped twice into PFS (advanced two-pass)
python -m mkpfs pack folder --raw --no-compress --no-adjust-output-file-extension './BREW1234-app' './pfs_image.dat'
python -m mkpfs pack file './pfs_image.dat' './BREW1234.ffpfsc'
rm './pfs_image.dat'

# Extracting Existing Images (Reverse operation; --deep lists/extracts inside a wrapped exFAT)
python -m mkpfs unpack  --deep './BREW1234.ffpfsc' './BREW1234-extracted/'
```

### Using the UI

```bash
python -m pip install -U "mkpfs[gui]"
python -m mkpfs.gui
```

## ⚠️ Limitations and Known Issues

- `exfat->ffpfsc` is the most stable format for compressed game backups. `pack folder` produces this layout by
  default: it wraps the folder in an exFAT image and compresses that into the `.ffpfsc` in a single pass, with no
  temporary `.exfat` on disk.
- `pack folder --raw` packs the folder directly into a PFS image without the exFAT wrapper. When file compression is
  enabled, the image is created and verification passes, but the console reads the files incorrectly due to technical
  limitations, so this advanced option provides no practical benefit for game backups. Prefer the default wrapped
  layout.
- With the default `--block-size 65536`, very small files can cause significant block-alignment waste, which may make
  the resulting image larger than the source in corner cases.
    - For small-file-heavy folders, prefer the two-pass strategy (`raw-folder -> .dat -> .ffpfsc`) or try a smaller
      block size such as `--block-size 16384` or `--block-size 32768`.
- Antivirus scanning can reduce conversion speed, especially during the write phase or when processing many loose
  files. If you trust this software in your environment and need higher throughput, temporarily disabling real-time
  scanning can help. If you are unsure, keep antivirus enabled and expect slower conversions.

## 💖 Sponsorship

MkPFS is easier to sustain when users who benefit from it help fund it.

<p>
  <a href="https://github.com/sponsors/RenanGBarreto">
    <img alt="GitHub Sponsors" src="https://img.shields.io/badge/Fund%20Development-GitHub%20Sponsors-e11d48?style=flat-square&logo=githubsponsors&logoColor=white" />
  </a>
</p>

Support helps with:

- Ongoing CLI improvements
- The Python library and reusable internals
- Better test coverage and compatibility work
- More documentation, examples, and research notes

Sponsor here:
- https://github.com/sponsors/RenanGBarreto

Or donate directly using:
 - **BTC:**  **`141kKRoDpaS6PNC2yxSi8vziDFTmzCnArE`**
 - **USDT (TRC-20):**  **`TQb7bUYSYRmdWgALHCejH33dNij9XyTAnU`**
 - **USDT (ERC-20):**  **`0x63c0b4b21133c4068375ae7566dafcf1398cf6fb`**

## 📦 Installation

### Run from a local checkout

### Install from PyPI

```bash
python -m pip install -U "mkpfs[gui]"
python -m mkpfs -h
```

### Install from source

```bash
uv sync --group dev
uv run mkpfs -h
```

#### Install as a local tool

```bash
uv tool install .
mkpfs -h
```

#### Build distributables

```bash
uv build
uv run --frozen twine check dist/*
```

## 🖥️ GUI

MkPFS includes an optional simple graphical interface built with [CustomTkinter](https://github.com/TomSchimansky/CustomTkinter). 
It covers all five operations (pack folder, pack file, verify, inspect, tree, unpack) and supports multiple languages.


### Running the GUI

```bash
python -m mkpfs.gui
```

Or, if installed via pip:

```bash
mkpfs-gui
```

## 📊 Compression Statistics

Using the compression from MkPFS, you can have your game files reduced by **40-60%**, drastically reducing the size of the image. 
The PlayStation kernel is already able to read the files natively in the PFSC format with minimal performance impact!

The numbers below are measured from a real homebrew title that previously had 6.5 GB of game files:

| Format | Description | Size    | Space saved     |
| --- | --- |---------|-----------------|
| `.exfat` | Raw game image (exFAT) | ~6.5 GB | baseline        |
| `.ffpkg` | Raw game image (UFS) | ~6.5 GB | baseline        |
| `.exfat.ffpfsc` | PFSC-compressed wrapper around the exFAT image | ~3.4 GB | **-47%**        |
| `.ffpkg.ffpfsc` | PFSC-compressed wrapper around the UFS image | ~3.4 GB | **-47%**        |
| `.ffpfs` | Source folder packed directly into a PFSC image | ~3.5 GB | **-46%** |

Both single-file wrapping (`pack file`) and folder-based packing (`pack folder`) produce compressed images of equivalent size, giving you flexibility without sacrificing efficiency.

### Compiling to a standalone .exe (Windows)

Install PyInstaller and build a single-file executable:

```bash
pip install pyinstaller
```

```powershell
pyinstaller --onefile --windowed `
  --name MkPFS `
  --icon assets\images\icon.png `
  --collect-all customtkinter `
  --collect-all PIL `
  --add-data "assets;assets" `
  --hidden-import cryptography `
  mkpfs\gui.py
```

The resulting `MkPFS.exe` is placed in the `dist\` folder. No Python installation is required to run it.

Notes:

- `--onefile` bundles everything into a single executable. Use `--onedir` instead for faster startup at the cost of a folder output.
- `--windowed` suppresses the console window. Remove it to keep a terminal for debugging.
- `--collect-all customtkinter` and `--collect-all PIL` ensure theme files and image codecs are included.
- `--add-data "assets;assets"` bundles the `assets/images/icon.png` used for the window icon.


## Command Reference

MkPFS keeps the command surface focused on the image lifecycle. 
The CLI currently supports `pack`, `verify`, `inspect`, `tree`, and `unpack`.

### Top-level CLI

```text
mkpfs [-h] {pack,verify,inspect,tree,unpack} ...
```

| Parameter | Description |
| --- | --- |
| `-h`, `--help` | Show the top-level help text and exit. |
| `pack` | Pack a folder or a single file into a PFS image. |
| `verify` | Validate image structure and payload checksums. |
| `inspect` | Inspect image metadata and integrity summary. |
| `tree` | Print the image tree representation. |
| `unpack` | Extract files from an image into a destination directory. |

### `pack`

```text
mkpfs pack [-h] {folder,file,exfat} ...
```

Use `pack folder` to build a PS image from a directory tree, `pack file` to treat one file as a virtual single-file tree, or `pack exfat` to build a raw `.exfat` image from a directory tree without compressing it into a `.ffpfsc`.

### `pack folder`

By default, `pack folder` wraps the folder in an exFAT image and compresses that into the `.ffpfsc` in a single pass, with no temporary `.exfat` on disk (the most PS-compatible layout). Use `--raw` to instead pack the folder directly into a PFS image.

```text
mkpfs pack folder [-h] [--adjust-output-file-extension | --no-adjust-output-file-extension]
                  [--raw]
                  [--compress | --no-compress] [--threshold-gain THRESHOLD_GAIN]
                  [--block-size BLOCK_SIZE] [--version {PS4,PS5}] [--inode-bits {32,64}]
                  [--case-sensitive | --case-insensitive] [--cpu-count CPU_COUNT]
                  [--compression-level COMPRESSION_LEVEL]
                  [--max-compressed-ratio MAX_COMPRESSED_RATIO]
                  [--min-compress-size MIN_COMPRESS_SIZE]
                  [--skip-executable-compression] [--signed] [--encrypted]
                  [--ekpfs-key EKPFS_KEY] [--require-game-files] [--temp-folder TEMP_FOLDER] [--verbose] [--dry-run] [--verify] [--verify-structure | --no-verify-structure] [--skip-verification]
                  source_dir image_file
```

Examples:

```bash
mkpfs pack folder ./input ./game.ffpfs
mkpfs pack folder ./input ./game.ffpfs --encrypted
mkpfs pack folder ./input ./game.ffpfs --require-game-files --verify
mkpfs pack folder ./input ./game.ffpfs --temp-folder ./tmp/mkpfs
```

| Parameter | Description                                                                                                                                                                                                                                   |
| --- |-----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| `source_dir` | Source app or homebrew folder to pack.                                                                                                                                                                                                        |
| `image_file` | Output image file path.                                                                                                                                                                                                                       |
| `-h`, `--help` | Show help and exit.                                                                                                                                                                                                                           |
| `--raw` | Pack the folder directly into a PFS image instead of the default exFAT-wrapped `.ffpfsc`.                                                                                                                                                      |
| `--adjust-output-file-extension` | Automatically adjust the output extension to match the detected pack mode. This is the default.                                                                                                                                               |
| `--no-adjust-output-file-extension` | Keep the requested output file name unchanged.                                                                                                                                                                                                |
| `--compress` | Enable PFSC block compression. This is the default.                                                                                                                                                                                           |
| `--no-compress` | Disable PFSC block compression.                                                                                                                                                                                                               |
| `--threshold-gain THRESHOLD_GAIN` | Minimum per-block gain percent required to keep PFSC-compressed blocks. Default: `0`.                                                                                                                                                         |
| `--block-size BLOCK_SIZE` | PFS block size in bytes, `auto`, or `auto-fit`. Default: `auto`, which resolves to `65536`; `auto-fit` picks 4096..65536 by estimated file-data padding.                                                                                      |
| `--version {PS4,PS5}` | PFS profile version. Default: `PS5`.                                                                                                                                                                                                          |
| `--inode-bits {32,64}` | Inode width mode bit. Default: `32`. (NOTE: 64 bits migth be unstable)                                                                                                                                                                        |
| `--case-sensitive` | Build a case-sensitive image.                                                                                                                                                                                                                 |
| `--case-insensitive` | Set the case-insensitive mode bit. This is the default behavior.                                                                                                                                                                              |
| `--cpu-count CPU_COUNT` | Number of CPU cores to use for PFSC compression. `0` means auto `min(16, max(1, cpu_count() - 1))`, non-zero uses `max(1, user value)`.                                                                                                       |
| `--compression-level COMPRESSION_LEVEL` | Zlib compression level from `0` to `9`. Default: `9`.                                                                                                                                                                                         |
| `--max-compressed-ratio MAX_COMPRESSED_RATIO` | Maximum PFSC size as percent of the raw file size. Use `100` to store files raw only when PFSC is larger than the raw file. Default: `100`.                                                                                                    |
| `--min-compress-size MIN_COMPRESS_SIZE` | Store files smaller than this many bytes raw without trying PFSC compression. When omitted (or set to `0`), MkPFS uses the resolved `--block-size` value, `65536` for `--block-size auto`, or the selected value for `--block-size auto-fit`. |
| `--skip-executable-compression`               | Skip compression in important executable files. Default: enabled.                                                                                                                                                                             |
| `--signed`                                    | Build a signed PFS image using a zero EKPFS key and seed.                                                                                                                                                                                     |
| `--encrypted`                                 | Encrypt filesystem blocks with AES-XTS.                                                                                                                                                                                                       |
| `--ekpfs-key EKPFS_KEY`                       | Optional 64-hex EKPFS key. When omitted with `--encrypted`, MkPFS uses an all-zero key.                                                                                                                                                       |
| `--require-game-files`                        | Require `sce_sys/param.json` and `eboot.bin` before packing.                                                                                                                                                                                  |
| `--no-ampr-index`                             | Do not generate `ampr_emu.index` even when `fakelib/libSceAmpr.sprx` is present.                                                                                                                                                              |
| `--temp-folder TEMP_FOLDER`                   | Directory used for temporary pack artifacts, including the one-file staging tree and PFSC spool files. Default: the system temp folder.                                                                                                       |
| `--verbose`                                   | Print verbose per-file decisions during packing.                                                                                                                                                                                              |
| `--dry-run`                                   | Scan, layout, and report only. Do not write an image file.                                                                                                                                                                                    |
| `--verify`                                    | Run `mkpfs verify` automatically after a successful pack.                                                                                                                                                                                     |

Notes:

- Folder output names are adjusted automatically by default.
- MkPFS chooses `.ffpfs` when `sce_sys/param.json` exposes a title ID, otherwise it falls back to `.ffpfsc`.
- When the source folder contains `fakelib/libSceAmpr.sprx`, MkPFS regenerates an `ampr_emu.index` in the folder before packing so it is included in the image and stays in sync with the current files. The rebuild is metadata-only and inexpensive. Use `--no-ampr-index` to skip it and preserve any existing index.
- OS-generated metadata is never packed: macOS entries (`.DS_Store`, `._*`, `__MACOSX`, `.Spotlight-V100`, ...) and Windows entries (`Thumbs.db`, `desktop.ini`, `$RECYCLE.BIN`, ...) are skipped during scanning and excluded from the AMPR index.
- `--ekpfs-key` is only meaningful when used with `--encrypted`.

### `pack file`

```text
mkpfs pack file [-h] [--adjust-output-file-extension | --no-adjust-output-file-extension]
                [--compress | --no-compress] [--threshold-gain THRESHOLD_GAIN]
                [--block-size BLOCK_SIZE] [--version {PS4,PS5}] [--inode-bits {32,64}]
                [--case-sensitive | --case-insensitive] [--cpu-count CPU_COUNT]
                [--compression-level COMPRESSION_LEVEL]
                [--max-compressed-ratio MAX_COMPRESSED_RATIO]
                [--min-compress-size MIN_COMPRESS_SIZE]
                [--use-spool]
                [--skip-executable-compression] [--signed] [--encrypted]
                [--ekpfs-key EKPFS_KEY] [--temp-folder TEMP_FOLDER] [--verbose] [--dry-run] [--verify]
                source_file image_file
```

Examples:

```bash
mkpfs pack file ./payload.exfat ./payload.ffpfsc
mkpfs pack file ./payload.exfat ./payload.ffpfsc --verify
mkpfs pack file ./payload.exfat ./payload.ffpfsc --temp-folder ./tmp/mkpfs
```

| Parameter                                     | Description                                                                                                                                                                                             |
|-----------------------------------------------|---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| `source_file`                                 | Single source file to pack.                                                                                                                                                                             |
| `image_file`                                  | Output image file path.                                                                                                                                                                                 |
| `-h`, `--help`                                | Show help and exit.                                                                                                                                                                                     |
| `--adjust-output-file-extension`              | Automatically adjust the output extension to match the detected pack mode. This is the default.                                                                                                         |
| `--no-adjust-output-file-extension`           | Keep the requested output file name unchanged.                                                                                                                                                          |
| `--compress`                                  | Enable PFSC block compression. This is the default.                                                                                                                                                     |
| `--no-compress`                               | Disable PFSC block compression.                                                                                                                                                                         |
| `--threshold-gain THRESHOLD_GAIN`             | Minimum per-block gain percent required to keep PFSC-compressed blocks. Default: `0`.                                                                                                                   |
| `--block-size BLOCK_SIZE`                     | PFS block size in bytes, `auto`, or `auto-fit`. Default: `auto`, which resolves to `65536`; `auto-fit` picks 4096..65536 by estimated file-data padding.                                                |
| `--version {PS4,PS5}`                         | PFS profile version. Default: `PS5`.                                                                                                                                                                    |
| `--inode-bits {32,64}`                        | Inode width mode bit. Default: `32`.                                                                                                                                                                    |
| `--case-sensitive`                            | Build a case-sensitive image.                                                                                                                                                                           |
| `--case-insensitive`                          | Set the case-insensitive mode bit. This is the default behavior.                                                                                                                                        |
| `--cpu-count CPU_COUNT`                       | Number of CPU cores to use for PFSC compression. `0` means auto `min(16, max(1, cpu_count() - 1))`, non-zero uses `max(1, user value)`.                                                                         |
| `--compression-level COMPRESSION_LEVEL`       | Zlib compression level from `0` to `9`. Default: `9`.                                                                                                                                                   |
| `--max-compressed-ratio MAX_COMPRESSED_RATIO` | Maximum PFSC size as percent of the raw file size. Use `100` to store files raw only when PFSC is larger than the raw file. Default: `100`.                                                                |
| `--min-compress-size MIN_COMPRESS_SIZE`       | Store files smaller than this many bytes raw without trying PFSC compression. When omitted (or set to `0`), MkPFS uses the resolved `--block-size` value, `65536` for `--block-size auto`, or the selected value for `--block-size auto-fit`.                                              |
| `--rename-inner-image`                          | Rename inner image filename to a safe normalized name (default).                                                                                                                                        |
| `--no-rename-inner-image`                       | Disable renaming of the inner image filename.                                                                                                                                                         |
| `--use-spool`                                   | Force the legacy staged/spool builder for single-file packing instead of the default direct-to-image streaming.                                                                                       |
| `--skip-executable-compression`                 | Skip compression in important executable files. Default: enabled.                                                                                                                                       |
| `--signed`                                      | Build a signed PFS image using a zero EKPFS key and seed.                                                                                                                                               |
| `--encrypted`                                 | Encrypt filesystem blocks with AES-XTS.                                                                                                                                                                 |
| `--ekpfs-key EKPFS_KEY`                       | Optional 64-hex EKPFS key. When omitted with `--encrypted`, MkPFS uses an all-zero key.                                                                                                                 |
| `--temp-folder TEMP_FOLDER`                   | Directory used for temporary pack artifacts, including the one-file staging tree and PFSC spool files. Default: the system temp folder.                                                                 |
| `--verbose`                                   | Print verbose per-file decisions during packing.                                                                                                                                                        |
| `--dry-run`                                   | Scan, layout, and report only. Do not write an image file.                                                                                                                                              |
| `--verify`                                    | Run `mkpfs verify` automatically after a successful pack.                                                                                                                                               |
| `--verify-structure`                          | Run quick structure verification after a successful pack (default).                                                                                                                                     |
| `--no-verify-structure`                       | Disable the default quick structure verification after a successful pack.                                                                                                                             |
| `--skip-verification`                         | Skip all post-pack verification.                                                                                                                                                                        |

Notes:

- `pack file` now uses the direct-to-image streaming builder by default for supported option combinations. It
  automatically falls back to the legacy staged/spool path for `--signed`, `--inode-bits 64`, and
  `--block-size auto-fit`, printing a short notice that explains the reason.
- Use `--use-spool` to force the legacy staged/spool builder even when streaming is supported.
- Single-file fallback mode stages the file in a temporary one-file tree using links, so the source payload is not
  duplicated on disk.
- Use `--temp-folder` when you want fallback staged files and any legacy PFSC spool files to live somewhere other than
  the system temp directory.
- The default adjusted extension for single-file output is `.ffpfsc`.
- If `pack file` fails on macOS with `OSError: [Errno 22] Invalid argument` during PFSC compression, rerun with `--cpu-count 1` to keep block compression in-process.
  If the source lives on a removable or network volume, also try a local `--temp-folder` on a writable APFS volume.

### `pack exfat`

Build a raw exFAT image from a source directory, without compressing it into a `.ffpfsc`. This is useful when you want a standalone `.exfat` to inspect, mount, or pass to `pack file` later. The same exFAT layout is produced cross-platform, with no external `mkexfat` tooling required.

```text
mkpfs pack exfat [-h] [--cluster-size CLUSTER_SIZE] [--overwrite] [--verbose] [--no-progress] source_dir [output]
```

Examples:

```bash
mkpfs pack exfat ./BREW1234-app ./BREW1234.exfat
mkpfs pack exfat ./BREW1234-app          # auto-name <titleId>.exfat alongside the source
```

| Parameter | Description |
| --- | --- |
| `source_dir` | Source app or homebrew folder to pack. |
| `output` | Output `.exfat` path, or a directory to auto-name `<titleId>.exfat`. When omitted, the image is written alongside the source. |
| `-h`, `--help` | Show help and exit. |
| `--cluster-size CLUSTER_SIZE` | exFAT cluster size in bytes or `auto`. Default: `auto` (32 KiB, or 64 KiB for trees with a large average file size). |
| `--overwrite` | Overwrite an existing output file. |
| `--verbose` | Print verbose output. |
| `--no-progress` | Disable the packing progress bar on stderr. |

Notes:

- OS-generated metadata is excluded from the image (see the `pack folder` notes for the full list).
- The resulting `.exfat` can be packed straight into a `.ffpfsc` with `mkpfs pack file ./BREW1234.exfat ./BREW1234.ffpfsc`.

### `verify`

```text
mkpfs verify [-h] [--source-dir SOURCE_DIR | --source-file SOURCE_FILE]
             [--expect-crc32 EXPECT_CRC32]
             [--expect-manifest-sha256 EXPECT_MANIFEST_SHA256]
             [--ekpfs-key EKPFS_KEY] [--new-crypt]
             [--format {auto,pfs,exfat}]
             image_file
```

Examples:

```bash
mkpfs verify ./game.ffpfs
mkpfs verify ./single.ffpfsc --source-file ./payload.exfat
mkpfs verify ./game.ffpfs --source-dir ./input --expect-crc32 0x7F528D1F
mkpfs verify ./BREW1234.exfat --source-dir ./BREW1234-app --format exfat
```

| Parameter | Description |
| --- | --- |
| `image_file` | Path to the input image (`.ffpfs`, `.ffpfsc`, or `.exfat`). |
| `-h`, `--help` | Show help and exit. |
| `--source-dir SOURCE_DIR` | Optional source folder for hierarchy and payload comparison. For exFAT images, this enables full file-by-file SHA-256 verification. |
| `--source-file SOURCE_FILE` | Optional source file for single-file image comparison. Mutually exclusive with `--source-dir`. Not supported for raw exFAT images. |
| `--expect-crc32 EXPECT_CRC32` | Expected cumulative data CRC32 in hex. Verification fails if the computed value differs. |
| `--expect-manifest-sha256 EXPECT_MANIFEST_SHA256` | Expected manifest SHA256 as 64 hex characters. Verification fails if it differs. |
| `--ekpfs-key EKPFS_KEY` | Optional 64-hex EKPFS key for encrypted images. |
| `--new-crypt` | Use the alternate `newCrypt` EKPFS derivation. |
| `--format {auto,pfs,exfat}` | Image format hint. `auto` (default) detects exFAT by extension/signature and treats everything else as PFS; `pfs` forces PFS handling; `exfat` forces exFAT handling. |

### `inspect`

```text
mkpfs inspect [-h] [--format {text,json}] [--ekpfs-key EKPFS_KEY] [--new-crypt] image_file
```

Examples:

```bash
mkpfs inspect ./game.ffpfs
mkpfs inspect ./game.ffpfs --format json
```

| Parameter | Description |
| --- | --- |
| `image_file` | Path to the input `.ffpfs` image. |
| `-h`, `--help` | Show help and exit. |
| `--format {text,json}` | Output format for the inspection report. Default: `text`. |
| `--ekpfs-key EKPFS_KEY` | Optional 64-hex EKPFS key for encrypted images. |
| `--new-crypt` | Use the alternate `newCrypt` EKPFS derivation. |

### `tree`

```text
mkpfs tree [-h] [--deep] [--ekpfs-key EKPFS_KEY] [--new-crypt] image_file
```

Examples:

```bash
mkpfs tree ./game.ffpfs
mkpfs tree ./game.ffpfsc --deep
```

| Parameter | Description |
| --- | --- |
| `image_file` | Path to the input `.ffpfs` image. |
| `-h`, `--help` | Show help and exit. |
| `--deep` | When the image wraps a single exFAT, list the files inside it instead of the inner `.exfat`. |
| `--ekpfs-key EKPFS_KEY` | Optional 64-hex EKPFS key for encrypted images. |
| `--new-crypt` | Use the alternate `newCrypt` EKPFS derivation. |

### `unpack`

```text
mkpfs unpack [-h] [--overwrite] [--deep] [--only PATH]
             [--ekpfs-key EKPFS_KEY] [--new-crypt]
             [--format {auto,pfs,exfat}] [--no-progress]
             image_file output_dir
```

Examples:

```bash
mkpfs unpack ./game.ffpfs ./extracted/
mkpfs unpack ./game.ffpfs ./extracted/ --overwrite
mkpfs unpack ./game.ffpfsc ./extracted/ --deep
mkpfs unpack ./game.ffpfsc ./extracted/ --deep --only sce_sys --only eboot.bin
mkpfs unpack ./BREW1234.exfat ./BREW1234-extracted/ --format exfat
```

| Parameter | Description |
| --- | --- |
| `image_file` | Path to the input image (`.ffpfs`, `.ffpfsc`, or `.exfat`). |
| `output_dir` | Destination directory for extraction. |
| `-h`, `--help` | Show help and exit. |
| `--overwrite` | Overwrite an existing output path. |
| `--deep` | When a PFS image wraps a single exFAT, extract the files inside it instead of the inner `.exfat`. Has no effect for raw `.exfat` images. |
| `--only PATH` | With `--deep`, extract only this inner exFAT path (a file, or a folder and everything under it). Repeatable. Only the matching entries are read, so cherry-picking a few files from a large image is cheap. |
| `--ekpfs-key EKPFS_KEY` | Optional 64-hex EKPFS key for encrypted images. |
| `--new-crypt` | Use the alternate `newCrypt` EKPFS derivation. |
| `--format {auto,pfs,exfat}` | Image format hint. `auto` (default) detects exFAT by extension/signature and treats everything else as PFS; `pfs` forces PFS handling; `exfat` forces exFAT handling. |
| `--no-progress` | Disable the extraction progress bar on stderr. |


## 💻 Example Output

```bash
$ mkpfs pack folder --verify --compress "./BREW00000-app" "./BREW00000.ffpfs"
======================================================================
PFS Image Builder - Parameters
======================================================================
  Source path:       ./BREW00000-app
  Output path:       ./BREW00000.ffpfs
  Version:           1 (PS4)
  Header magic:      PFS (20130315)
  Compression Setup: PFSC (0x43534650)
  Block size:        65,536 bytes (64 KiB)
  Inode width:       32-bit
  PFS mode:          0x0008  (Bit 0=signed, Bit 1=64-bit inodes, Bit 2=encrypted, Bit 3=case insensitive)
    Signed:          no
    64-bit inodes:   no
    Encrypted:       no
    New crypt:       no
    Case insensitive: yes
  Compression:       enabled
  Game-file checks:   disabled
  Threshold gain:    20%
  CPU cores:         7 (auto, capped at 16)
  Zlib level:        9
  Dry run:           no
======================================================================

Discovering files...
[################################] 100% scan

Compressing 180 files (5.87 GB) using 10 CPU cores...
[################################] 100% compress @ 68.75 MB/s            

Writing PFS image to ./BREW00000.ffpfs...
[################################] 100% write @ 728.27 MB/s

Successfully wrote 3.21 GB image
======================================================================
Build Summary
======================================================================
  Input path:              ./BREW00000-app
  Output path:             ./BREW00000.ffpfs
  Total files:             180
  Total uncompressed size: 5.87 GB
  Total stored size:       3.21 GB

  Compression Statistics:
    Compressed files:       53
    Uncompressed files:     127
    Actual gain achieved:   45.40%
    All-PFSC gain:          46.51%  (3.14 GB if every file used PFSC)

  Block Alignment Waste:
    Block size:             64 KiB (65,536 bytes)
    Wasted space:           6.75 MB (0.21% of file data blocks)

  Elapsed time:            92.46s
  Throughput:              65.05 MB/s


Running post-create check...
======================================================================
PFS Check Report
======================================================================
Image:                 ./BREW00000.ffpfs
Version:               1 (PS4)
Header magic:          PFS (20130315)
Compression Setup:     PFSC (0x43534650)
Read-only:             yes
Mode:                  0x0008  (Bit 0=signed, Bit 1=64-bit inodes, Bit 2=encrypted, Bit 3=case insensitive)
  Signed:              no
  64-bit inodes:       no
  Encrypted:           no
  Case insensitive:    yes
Block size:            65,536 bytes
Inodes:                196
Directories:           14
Files:                 180
Compressed files:      53
Files hash-checked:    180
Data CRC32:            0x7A6E1B38
Manifest SHA256:       5eee3aed04394d0abf978037ccfc6ddcf9c3945fa11816fe14f11d5853e5553e
Logical file bytes:    3,443,395,982
Stored file bytes:     6,306,784,749
flat_path_table keys:  193
Warnings:              0
Errors:                0
======================================================================

```

## 🛠️ Development

Set up the local environment:

```bash
uv sync --group dev
uv run pre-commit install
```

Run the validation commands:

```bash
./run-tests.sh
uv run --frozen ruff format .
uv run --frozen ruff check .
```

## 💙 Special thanks

Special thanks to the people and communities helping shape MkPFS:

- **Renan @ PSBrew**: main creator and maintainer of MkPFS
- **Darkmor @ ShadowMountPlus**: creator of [ShadowMountPlus](https://github.com/drakmor/ShadowMountPlus), whose work helped inspire practical PFS mounting workflows
- **The PlayStation and reverse-engineering community**: for tools, research threads, testing feedback, technical notes, and historical knowledge
- **Community-maintained references and wiki pages**: especially the projects and archives that preserve PFS, PKG, and FPKG implementation details

## 💻 Contributors

<a href="https://github.com/PSBrew/MkPFS/graphs/contributors">
  <img src="https://contrib.rocks/image?repo=PSBrew/MkPFS" />
</a>

## 📘 Disclaimer

This software is intended for archival, backup, preservation, and homebrew purposes only.

Users are responsible for complying with all applicable laws and regulations in their jurisdiction.

## 🔗 Related projects

- [ShadowMountPlus](https://github.com/drakmor/ShadowMountPlus): Practical PS5 auto-mounter and a key reference for `.ffpfs` compatibility
- [PSDevWiki PFS](https://www.psdevwiki.com/ps4/PFS): Community reference for PFS on-disk structures
- [PSDevWiki PKG files](https://www.psdevwiki.com/ps4/PKG_files): PKG format reference and tooling pointers
- [ShadPKG HOWWORKS](https://github.com/seregonwar/ShadPKG/blob/main/docs/HOWWORKS.md): Implementation-focused PKG/PFS decryption walkthrough
- [Wololo: PS4 FPKG writeup by Flatz](https://wololo.net/ps4-fpkg-writeup-by-flatz/): Historical writeup on FPKG/PKG techniques
