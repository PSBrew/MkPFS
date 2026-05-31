# MkPFS

[![PyPI](https://img.shields.io/pypi/v/mkpfs?style=flat-square&logo=pypi&logoColor=white&color=2563eb)](https://pypi.org/project/mkpfs/)
[![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-2563eb?style=flat-square&logo=python&logoColor=white)](https://www.python.org/downloads/release/python-3110/)
[![License](https://img.shields.io/badge/license-GPL--3.0-0f172a?style=flat-square)](LICENSE)
[![Status](https://img.shields.io/badge/status-active%20development-1d4ed8?style=flat-square)](https://github.com/PSBrew/MkPFS/actions)
[![Platforms](https://img.shields.io/badge/platforms-Windows%20%7C%20macOS%20%7C%20Linux-2563eb?style=flat-square)](#installation)
[![Profiles](https://img.shields.io/badge/profiles-PS4%20%2F%20PS5-3b82f6?style=flat-square)](#command-reference)

MkPFS is a command-line tool and Python library for building, verifying, inspecting, browsing, and extracting PlayStation FileSystem (PFS) disk images. It works with common image naming conventions such as `.ffpfs`, `.ffpfsc`, `.pfs`, `.dat`, and `.bin`, and fits both direct image workflows and PKG or FPKG inner-PFS generation.

**Quick links:** [Installation](#installation) · [Command reference](#command-reference) · [Development](#development) · [Related projects](#related-projects) · [Sponsor](https://github.com/sponsors/RenanGBarreto)

## 🎯 Why MkPFS

MkPFS is designed to be a clean and practical entry point for PlayStation PFS image workflows:

- Create and manage PFS disk images for PlayStation-oriented workflows
- Verify structure, payload hashes, layout consistency, and source-tree matches
- Inspect image contents quickly with a tree view instead of digging through raw structures
- Work with common image extensions such as `.ffpfs`, `.pfs`, `.dat`, and `.bin`
- Use the generated images with tools like [ShadowMountPlus](https://github.com/drakmor/ShadowMountPlus)
- Build the inner PFS filesystem used inside PKG or FPKG workflows
- Use the same core workflow from both the CLI and the Python library
- Explore a bundled, source-backed knowledge base for PFS and PKG research

## ✨ Main Features


<table>
  <tr>
    <td width="55%" valign="top">
      <h3>⚙️ Create PFS Images Fast</h3>
      <p>
        Turn a prepared folder into a PFS image with compression, optional encryption, profile selection, inode mode control,
        dry runs, and post-build verification support. MkPFS is built around the actual image lifecycle instead
        of forcing you through low-level manual steps.
      </p>
      <p>
        Great for repeatable packaging workflows, rapid iteration, and PKG/FPKG inner-PFS generation.
      </p>
    </td>
    <td width="45%" valign="top">
      <img src="assets/images/screenshot-create.svg" alt="MkPFS create workflow placeholder" width="100%" />
    </td>
  </tr>
  <tr>
    <td width="45%" valign="top">
      <img src="assets/images/screenshot-check.svg" alt="MkPFS verification workflow placeholder" width="100%" />
    </td>
    <td width="55%" valign="top">
      <h3>🔍 Verify With Confidence</h3>
      <p>
        Run structural checks, confirm payload hashes, compare an image to its source tree, and inspect CRC32
        or manifest digest expectations. The goal is to make validation obvious and repeatable instead of an
        afterthought.
      </p>
      <p>
        The <code>verify</code> alias is especially handy when you want that intent to be visible in scripts, release pipelines,
        and compatibility checks before using the image with ShadowMountPlus or packaging it into a PKG/FPKG workflow.
      </p>
    </td>
  </tr>
  <tr>
    <td width="55%" valign="top">
      <h3>⚙️ Use CLI or Library</h3>
      <p>
        MkPFS is positioned as a command-line tool and Python library for the same core image workflow:
        create, verify, browse, and manage images from both the CLI and direct library calls.
      </p>
      <p>
        That makes MkPFS useful for automation-heavy users, scripting, and integration in advanced workflows.
      </p>
    </td>
    <td width="45%" valign="top">
          </td>
  </tr>
</table>


## 📦 Installation

### Run from a local checkout

```bash
uv sync --group dev
uv run mkpfs -h
```

### Install as a local tool

```bash
uv tool install .
mkpfs -h
```

### Install from PyPI

```bash
uv tool install mkpfs
mkpfs -h
```

### Build distributables

```bash
uv build
uv run --frozen twine check dist/*
```

## Command Reference

MkPFS keeps the command surface focused on the image lifecycle. The CLI currently supports `pack`, `verify`, `inspect`, `tree`, and `unpack`.

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
mkpfs pack [-h] {folder,file} ...
```

Use `pack folder` to build from a directory tree, or `pack file` to stage one file into a single-file image.

### `pack folder`

```text
mkpfs pack folder [-h] [--adjust-output-file-extension | --no-adjust-output-file-extension]
                  [--compress | --no-compress] [--threshold-gain THRESHOLD_GAIN]
                  [--block-size BLOCK_SIZE] [--version {PS4,PS5}] [--inode-bits {32,64}]
                  [--case-sensitive | --case-insensitive] [--cpu-count CPU_COUNT]
                  [--compression-level COMPRESSION_LEVEL] [--signed] [--encrypted]
                  [--ekpfs-key EKPFS_KEY] [--require-game-files] [--verbose]
                  [--dry-run] [--verify] source_dir image_file
```

Examples:

```bash
mkpfs pack folder ./input ./game.ffpfs
mkpfs pack folder ./input ./game.ffpfs --encrypted
mkpfs pack folder ./input ./game.ffpfs --require-game-files --verify
```

| Parameter | Description |
| --- | --- |
| `source_dir` | Source app or homebrew folder to pack. |
| `image_file` | Output image file path. |
| `-h`, `--help` | Show help and exit. |
| `--adjust-output-file-extension` | Automatically adjust the output extension to match the detected pack mode. This is the default. |
| `--no-adjust-output-file-extension` | Keep the requested output file name unchanged. |
| `--compress` | Enable PFSC block compression. This is the default. |
| `--no-compress` | Disable PFSC block compression. |
| `--threshold-gain THRESHOLD_GAIN` | Minimum per-block gain percent required to keep PFSC-compressed blocks. Default: `20`. |
| `--block-size BLOCK_SIZE` | PFS block size in bytes, or `auto`. Default: `auto`, which resolves to `65536`. |
| `--version {PS4,PS5}` | PFS profile version. Default: `PS4`. |
| `--inode-bits {32,64}` | Inode width mode bit. Default: `32`. |
| `--case-sensitive` | Build a case-sensitive image. |
| `--case-insensitive` | Set the case-insensitive mode bit. This is the default behavior. |
| `--cpu-count CPU_COUNT` | Number of CPU cores to use for PFSC compression. `0` means all available cores. |
| `--compression-level COMPRESSION_LEVEL` | Zlib compression level from `0` to `9`. Default: `7`. |
| `--signed` | Build a signed PFS image using a zero EKPFS key and seed. |
| `--encrypted` | Encrypt filesystem blocks with AES-XTS. |
| `--ekpfs-key EKPFS_KEY` | Optional 64-hex EKPFS key. When omitted with `--encrypted`, MkPFS uses an all-zero key. |
| `--require-game-files` | Require `sce_sys/param.json` and `eboot.bin` before packing. |
| `--verbose` | Print verbose per-file decisions during packing. |
| `--dry-run` | Scan, layout, and report only. Do not write an image file. |
| `--verify` | Run `mkpfs verify` automatically after a successful pack. |

Notes:

- Folder output names are adjusted automatically by default.
- MkPFS chooses `.ffpfs` when `sce_sys/param.json` exposes a title ID, otherwise it falls back to `.ffpfsc`.
- `--ekpfs-key` is only meaningful when used with `--encrypted`.

### `pack file`

```text
mkpfs pack file [-h] [--adjust-output-file-extension | --no-adjust-output-file-extension]
                [--compress | --no-compress] [--threshold-gain THRESHOLD_GAIN]
                [--block-size BLOCK_SIZE] [--version {PS4,PS5}] [--inode-bits {32,64}]
                [--case-sensitive | --case-insensitive] [--cpu-count CPU_COUNT]
                [--compression-level COMPRESSION_LEVEL] [--signed] [--encrypted]
                [--ekpfs-key EKPFS_KEY] [--verbose] [--dry-run] [--verify]
                source_file image_file
```

Examples:

```bash
mkpfs pack file ./payload.bin ./payload.ffpfsc
mkpfs pack file ./payload.bin ./payload.ffpfsc --verify
```

| Parameter | Description |
| --- | --- |
| `source_file` | Single source file to pack. |
| `image_file` | Output image file path. |
| `-h`, `--help` | Show help and exit. |
| `--adjust-output-file-extension` | Automatically adjust the output extension to match the detected pack mode. This is the default. |
| `--no-adjust-output-file-extension` | Keep the requested output file name unchanged. |
| `--compress` | Enable PFSC block compression. This is the default. |
| `--no-compress` | Disable PFSC block compression. |
| `--threshold-gain THRESHOLD_GAIN` | Minimum per-block gain percent required to keep PFSC-compressed blocks. Default: `20`. |
| `--block-size BLOCK_SIZE` | PFS block size in bytes, or `auto`. Default: `auto`, which resolves to `65536`. |
| `--version {PS4,PS5}` | PFS profile version. Default: `PS4`. |
| `--inode-bits {32,64}` | Inode width mode bit. Default: `32`. |
| `--case-sensitive` | Build a case-sensitive image. |
| `--case-insensitive` | Set the case-insensitive mode bit. This is the default behavior. |
| `--cpu-count CPU_COUNT` | Number of CPU cores to use for PFSC compression. `0` means all available cores. |
| `--compression-level COMPRESSION_LEVEL` | Zlib compression level from `0` to `9`. Default: `7`. |
| `--signed` | Build a signed PFS image using a zero EKPFS key and seed. |
| `--encrypted` | Encrypt filesystem blocks with AES-XTS. |
| `--ekpfs-key EKPFS_KEY` | Optional 64-hex EKPFS key. When omitted with `--encrypted`, MkPFS uses an all-zero key. |
| `--verbose` | Print verbose per-file decisions during packing. |
| `--dry-run` | Scan, layout, and report only. Do not write an image file. |
| `--verify` | Run `mkpfs verify` automatically after a successful pack. |

Notes:

- Single-file packing stages the file into a temporary one-file tree before building.
- The default adjusted extension for single-file output is `.ffpfsc`.

### `verify`

```text
mkpfs verify [-h] [--source-dir SOURCE_DIR | --source-file SOURCE_FILE]
             [--expect-crc32 EXPECT_CRC32]
             [--expect-manifest-sha256 EXPECT_MANIFEST_SHA256]
             [--ekpfs-key EKPFS_KEY] [--new-crypt] image_file
```

Examples:

```bash
mkpfs verify ./game.ffpfs
mkpfs verify ./single.ffpfsc --source-file ./payload.bin
mkpfs verify ./game.ffpfs --source-dir ./input --expect-crc32 0x7F528D1F
```

| Parameter | Description |
| --- | --- |
| `image_file` | Path to the input `.ffpfs` image. |
| `-h`, `--help` | Show help and exit. |
| `--source-dir SOURCE_DIR` | Optional source folder for hierarchy and payload comparison. |
| `--source-file SOURCE_FILE` | Optional source file for single-file image comparison. Mutually exclusive with `--source-dir`. |
| `--expect-crc32 EXPECT_CRC32` | Expected cumulative data CRC32 in hex. Verification fails if the computed value differs. |
| `--expect-manifest-sha256 EXPECT_MANIFEST_SHA256` | Expected manifest SHA256 as 64 hex characters. Verification fails if it differs. |
| `--ekpfs-key EKPFS_KEY` | Optional 64-hex EKPFS key for encrypted images. |
| `--new-crypt` | Use the alternate `newCrypt` EKPFS derivation. |

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
mkpfs tree [-h] [--ekpfs-key EKPFS_KEY] [--new-crypt] image_file
```

Examples:

```bash
mkpfs tree ./game.ffpfs
```

| Parameter | Description |
| --- | --- |
| `image_file` | Path to the input `.ffpfs` image. |
| `-h`, `--help` | Show help and exit. |
| `--ekpfs-key EKPFS_KEY` | Optional 64-hex EKPFS key for encrypted images. |
| `--new-crypt` | Use the alternate `newCrypt` EKPFS derivation. |

### `unpack`

```text
mkpfs unpack [-h] [--overwrite] [--ekpfs-key EKPFS_KEY] [--new-crypt] image_file output_dir
```

Examples:

```bash
mkpfs unpack ./game.ffpfs ./extracted/
mkpfs unpack ./game.ffpfs ./extracted/ --overwrite
```

| Parameter | Description |
| --- | --- |
| `image_file` | Path to the input `.ffpfs` image. |
| `output_dir` | Destination directory for extraction. |
| `-h`, `--help` | Show help and exit. |
| `--overwrite` | Overwrite an existing output path. |
| `--ekpfs-key EKPFS_KEY` | Optional 64-hex EKPFS key for encrypted images. |
| `--new-crypt` | Use the alternate `newCrypt` EKPFS derivation. |

## 🔁 Typical Workflow

```bash
# 1. Pack an image from a source tree
mkpfs pack folder ./input ./output.ffpfs

# 2. Verify the generated image
mkpfs verify ./output.ffpfs

# 3. Inspect the final tree layout
mkpfs tree ./output.ffpfs
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

## 💙 Special thanks and Contributors

Special thanks to the people and communities helping shape MkPFS:

- **RenanGBarreto** — main creator and maintainer of MkPFS
- **Darkmor** — creator of [ShadowMountPlus](https://github.com/drakmor/ShadowMountPlus), whose work helped inspire practical PFS mounting workflows
- **The PlayStation and reverse-engineering community** — for tools, research threads, testing feedback, technical notes, and historical knowledge
- **Community-maintained references and wiki pages** — especially the projects and archives that preserve PFS, PKG, and FPKG implementation details

## Related projects

- [ShadowMountPlus](https://github.com/drakmor/ShadowMountPlus) — practical PS5 auto-mounter and a key reference for `.ffpfs` compatibility
- [PSDevWiki PFS](https://www.psdevwiki.com/ps4/PFS) — community reference for PFS on-disk structures
- [PSDevWiki PKG files](https://www.psdevwiki.com/ps4/PKG_files) — PKG format reference and tooling pointers
- [ShadPKG HOWWORKS](https://github.com/seregonwar/ShadPKG/blob/main/docs/HOWWORKS.md) — implementation-focused PKG/PFS decryption walkthrough
- [Wololo: PS4 FPKG writeup by Flatz](https://wololo.net/ps4-fpkg-writeup-by-flatz/) — historical writeup on FPKG/PKG techniques
