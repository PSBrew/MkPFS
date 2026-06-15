# PSDevWiki PS5: PlayStation 5 Developer Wiki

## Identity

- **Source:** [psdevwiki.com/ps5](https://www.psdevwiki.com/ps5/)
- **Type:** MediaWiki (community wiki, not a git repo)
- **License:** GNU FDL 1.2
- **Articles:** 70 (as of 2026-06-14)
- **Discord:** https://discord.gg/2M9ECQPgPt
- **Indexed:** 2026-06-14

## Scope

Community-maintained wiki covering PS5 hardware, system software, file structures, partitions, filesystems, encryption keys, vulnerabilities, homebrew, and reverse engineering. Created February 2019.

## Key Pages (relevance to mkpfs)

### Filesystem

PS5 mount table with device-to-path mappings and filesystem flags:

| Device | Mount Point | Filesystem | Flags |
|--------|-------------|------------|-------|
| md0 | / | exfatfs | 0x5001 |
| dev/ssd0.system | /system | exfatfs | 0x1041 |
| dev/ssd0.system_ex | /system_ex | exfatfs | 0x1041 |
| dev/ssd0.system_data | /system_data | ufs | 0x10201000 |
| ssd0.user | /user | bfs | 0x1000 |
| dev/ssd0.update | /update | exfatfs | 0x1040 |
| dev/ssd0.preinst | /preinst | exfatfs | 0x1041 |
| dev/cd0 | /mnt/disc | udf2 | 0x1001 |
| dev/da1s1 | /mnt/usb0 | exfatfs | 0x1000 |

Filesystems used: exfatfs, tmpfs, devfs, ufs, bfs, udf2, nullfs.

### Partitions

SSD partition table:

| # | Name | Size | Filesystem |
|---|------|------|------------|
| 1 | ssd0.system_b | 640 MiB | exFAT (backup) |
| 2 | ssd0.system_ex_b | 1.50 GiB | exFAT (backup) |
| 3 | ssd0.system | 640 MiB | exFAT |
| 4 | ssd0.system_ex | 1.50 GiB | exFAT |
| 5 | ssd0.preinst | 148 MiB | exFAT |
| 6 | ssd0.app_temp0 | 1 GiB | UFS2 |
| 7 | ssd0.system_data | 8 GiB | UFS2 |
| 8 | ssd0.update | 4 GiB | exFAT |
| 9 | ssd0.swap | 8 GiB | RAW (SCE_EVENT) |
| 10 | (unknown) | 14 GiB | ? |
| 11 | (unknown) | 3.375 GiB | ? |
| 12 | ssd0.user | ~625 GiB | ? |
| 13 | ssd0.bd_rvlist | 1 MiB | Encrypted |

Sub-partitions: ssd0.app_swap, ssd0.hibernation, ssd0.swapx0/1/2.

### PKG Structure

Application package directory tree:

```
eboot.bin              # Boot file (required)
sce_modules/           # System libraries (.prx)
sce_sys/               # System directory
  about/right.sprx
  trophy2/trophy00.ucp
  uds/uds00.ucp
  icon0.png, icon0.dds
  param.json           # Package params
  pfs-version.dat      # PFS version marker
  playgo-chunk.dat, playgo-ficm.dat, playgo-hash-table.dat
  playgo-scenario.json
  save_data.png
  target-param.json
  license.dat, license.info
  origin-param.json
  nptite.dat, npbind.dat
```

### Keys

Comprehensive key material including:
- PS5 ROM keys (AES key seeds, RSA keys)
- PKG Metadata RSA-3072 keys (modulus, exponent, private exponent, P, Q, DP, DQ, QP)
- EncDec master keys and portability keys
- **pfs_sd_auth** key (0x58) - PFS SD authentication
- **pfs_sbl** key (0x54) - PFS secure boot loader
- M.2 storage metadata verification key and default encryption key
- RNPS keys (AES-CBC, RSA)
- EMC, EAP, kernel keys
- Passcode section

### Publishing Tools

Official SDK tools documented:
- `prospero-pub-cmd.exe` - CLI package builder
- `prospero-pub-param.exe` - Param file editor
- `ProsperoGP5Editor.exe` - GP5 project generator
- `vagconv2w.exe` / `vagconv2.exe` - VAG converter
- `at9tool.exe` - ATRAC9 encoder/decoder
- `sieaacformattool.exe` - AAC encoder/decoder
- `sieOpusFormatTool.exe` - Opus encoder/decoder

### Other Relevant Pages

- **Storage** - 825GB PCIe 4.0 SSD, proprietary controller, M.2 2282 expansion slot
- **Hypervisor** - PS5 hypervisor layer
- **Kernel** - PS5 kernel details, devices
- **Secure Modules** - secure module descriptions
- **PUP** - system update format
- **param.json** - package parameter format
- **Title ID** - title identifier format

## Operational Notes

1. WebFetch tool gets 403 from psdevwiki; use `curl -sL -A 'Mozilla/5.0 ...'` to fetch pages.
2. Content is wikitext rendered to HTML; strip HTML tags to extract text.
3. Wiki pages may contain outdated information; cross-reference with code and other sources.
4. Only 70 articles; coverage is shallow compared to PS4 wiki (ps3.psdevwiki.com has 5000+ articles).

## Relevance to mkpfs

- **Partition table** validates mkpfs partition layout assumptions.
- **PKG structure** documents the `sce_sys/` metadata and `pfs-version.dat` format.
- **Keys page** has `pfs_sd_auth` and `pfs_sbl` key entries relevant to PFS encryption.
- **Filesystem page** shows PFS is NOT directly listed (uses exfatfs, bfs, ufs) suggesting PFS is a container format within partitions, not a standalone filesystem on disk.
- **Publishing Tools** page confirms `prospero-pub-cmd.exe` usage and lists all SDK tools.
