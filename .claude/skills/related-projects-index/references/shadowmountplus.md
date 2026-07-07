# ShadowMountPlus — PFS/FFPFS Compatibility Reference

Upstream repository: https://github.com/drakmor/ShadowMountPlus

ShadowMountPlus is a fully automated background "Auto-Mounter" payload for jailbroken PS5 consoles. It automatically detects, mounts, and installs game dumps from internal and external storage with no manual configuration. It is the primary reference implementation for how the PS5 kernel accepts PFS images and what content must live inside them.

> PFS support is marked experimental. `.ffpkg` (UFS2) is the recommended default format for normal use.

---

## Table of Contents

1. Project Structure
2. Supported Image Formats
3. PFS Mount Pipeline (Deep Dive)
4. LVD Attach Subsystem
5. nmount Options by Filesystem
6. Sector / Cluster Size Rules
7. Game Content Layout Requirements
8. param.json Parsing
9. Scan Paths and Directory Layout
10. Install and Registration Flow
11. Link Files and nullfs Mounts
12. Fakelib / Backport Overlay
13. app.db Integration
14. Runtime Configuration
15. Image Creation Scripts
16. System Paths Reference
17. Key Constants and Limits
18. Source File Index
19. Checklist for .ffpfs Image Generators

---

## Project Structure

```
shadowmountplus/
├── src/                        # All C implementation files
│   ├── main.c                  # Entry point
│   ├── sm_image.c              # Core image attach / nmount / unmount pipeline
│   ├── sm_mount_device.c       # LVD/MD backend device helpers
│   ├── sm_config_mount.c       # Runtime config parser (config.ini / autotune.ini)
│   ├── sm_scan.c               # Candidate discovery (game dir / image file scanning)
│   ├── sm_scan_tree.c          # Directory tree walker
│   ├── sm_scanner.c            # Top-level periodic scanner loop
│   ├── sm_install.c            # Mount + registration pipeline
│   ├── sm_install_queue.c      # Batched install queue (FW 12.00+)
│   ├── sm_gameinfo.c           # param.json parser
│   ├── sm_filesystem.c         # Link file helpers, title app dir queries
│   ├── sm_fakelib.c            # unionfs fakelib overlay for backports
│   ├── sm_appdb.c              # SQLite app.db integration
│   ├── sm_game_lifecycle.c     # Game exec/exit event monitoring (kqueue)
│   ├── sm_shellcore_flags.c    # SceShellCore event flag monitoring
│   ├── sm_kstuff.c             # kstuff auto-pause/resume around game launches
│   ├── sm_game_cache.c         # In-process game candidate cache
│   ├── sm_image_cache.c        # In-process image mount cache
│   ├── sm_path_state.c         # Missing param retry tracker
│   ├── sm_path_utils.c         # Path helpers
│   ├── sm_stability.c          # Source mtime/ctime stability check
│   ├── sm_title_state.c        # Per-title install attempt state
│   ├── sm_log.c                # Logging
│   ├── sm_kstuff.c             # kstuff toggle integration
│   ├── sm_mdbg.c               # Debug helpers
│   ├── sm_time.c               # Monotonic time helpers
│   ├── sm_shellcore_flags.c    # ShellCore event flags
│   ├── libkernel_sys_ext.c     # Extended kernel syscall wrappers
│   └── sm_fakelib.c            # Fakelib overlay management
├── include/
│   ├── sm_mount_defs.h         # LVD/MD ioctl constants, PFS mount options
│   ├── sm_types.h              # Core struct types (attach, config, scan candidate)
│   ├── sm_limits.h             # All capacity and timeout constants
│   ├── sm_paths.h              # All filesystem path constants
│   ├── sm_platform.h           # Platform includes, SCE SDK imports, IOVEC macros
│   └── *.h                     # Per-module headers
├── config.ini.example          # Full annotated runtime config template
├── mkexfat.sh                  # Linux script: create .exfat image
├── mkufs2.sh                   # FreeBSD script: create .ffpkg UFS2 image
├── make_image.bat              # Windows wrapper for New-OsfExfatImage.ps1
├── New-OsfExfatImage.ps1       # PowerShell exFAT image creator
├── Makefile                    # Build
└── README.md                   # User-facing documentation
```

---

## Supported Image Formats

Source: [include/sm_types.h](https://github.com/drakmor/ShadowMountPlus/blob/main/include/sm_types.h), [src/sm_image.c](https://github.com/drakmor/ShadowMountPlus/blob/main/src/sm_image.c#L149)

| Extension | Filesystem | Mount name | Attach backend | Status |
|-----------|-----------|------------|----------------|--------|
| `.ffpkg`  | UFS2      | `ufs`      | LVD or MD (configurable) | Recommended |
| `.exfat`  | exFAT     | `exfatfs`  | LVD or MD (configurable) | External-drive compat |
| `.ffpfs`  | PFS       | `pfs`      | LVD only       | Experimental |

Detection is extension-based, case-insensitive:

```c
// src/sm_image.c
static image_fs_type_t detect_image_fs_type(const char *name) {
  const char *dot = strrchr(name, '.');
  if (!dot)                         return IMAGE_FS_UNKNOWN;
  if (strcasecmp(dot, ".ffpkg") == 0) return IMAGE_FS_UFS;
  if (strcasecmp(dot, ".exfat") == 0) return IMAGE_FS_EXFAT;
  if (strcasecmp(dot, ".ffpfs") == 0) return IMAGE_FS_PFS;
  return IMAGE_FS_UNKNOWN;
}
```

**Image type enum:**

```c
// include/sm_types.h
typedef enum {
  IMAGE_FS_UNKNOWN = 0,
  IMAGE_FS_UFS,
  IMAGE_FS_EXFAT,
  IMAGE_FS_PFS,
} image_fs_type_t;
```

---

## PFS Mount Pipeline (Deep Dive)

The full pipeline for mounting a `.ffpfs` file goes through these stages:

### 1. Scanner finds image file

`sm_scan_tree_walk` walks configured scan roots and calls `on_image_file` for every regular file whose name passes `is_supported_image_file_name`.  
Source: [src/sm_scan_tree.c](https://github.com/drakmor/ShadowMountPlus/blob/main/src/sm_scan_tree.c)

### 2. Stability check

Before mounting, the source file's `mtime`/`ctime` must be at least `stability_wait_seconds` (default: 10) seconds old.  
Source: [src/sm_mount_device.c](https://github.com/drakmor/ShadowMountPlus/blob/main/src/sm_mount_device.c) — `is_source_stable_for_mount`

### 3. Mount-point naming

```c
// src/sm_image.c — build_image_mount_point
snprintf(mount_name + base_len, sizeof(mount_name) - base_len, "_%08x",
         sm_fnv1a32(file_path));
snprintf(mount_point, MAX_PATH, "%s/%s", IMAGE_MOUNT_BASE, mount_name);
```

Result: `/mnt/shadowmnt/<basename_without_ext>_<fnv1a32_hex>`  
Example: `/mnt/shadowmnt/PPSA12345_a1b2c3d4`

### 4. Backend selection

For PFS, the backend is always LVD — there is no MD fallback:

```c
// src/sm_image.c — select_image_backend
static attach_backend_t select_image_backend(const runtime_config_t *cfg,
                                             image_fs_type_t fs_type) {
  if (fs_type == IMAGE_FS_EXFAT) return cfg->exfat_backend;
  if (fs_type == IMAGE_FS_UFS)   return cfg->ufs_backend;
  return ATTACH_BACKEND_LVD;   // PFS always LVD
}
```

Source: [src/sm_image.c](https://github.com/drakmor/ShadowMountPlus/blob/main/src/sm_image.c)

### 5. LVD attach (`/dev/lvdctl`)

`attach_lvd_backend` opens `/dev/lvdctl`, fills `lvd_ioctl_attach_v0_t`, and calls `ioctl(fd, SCE_LVD_IOC_ATTACH_V0, &req)`.

Key fields for PFS:
- `image_type = LVD_ATTACH_IMAGE_TYPE_PFS_SAVE_DATA` (= **5**)
- `sector_size = lvd_pfs_sector_size` (runtime default: **32768**, compile-time fallback: 4096)
- `secondary_unit = sector_size` (same as sector_size for non-exFAT)
- `flags = normalize_lvd_raw_flags(LVD_ATTACH_RAW_FLAGS_SINGLE_RO or _RW)`
- `layer_count = 1`
- `layers[0].source_type = LVD_ENTRY_TYPE_FILE` (1, for normal image files)
- `layers[0].flags = LVD_ENTRY_FLAG_NO_BITMAP` (0x1)
- `layers[0].path = <image file path>`
- `layers[0].offset = 0`
- `layers[0].size = file_size`
- `device_id = -1` (kernel auto-assigns)

The kernel creates a block device at `/dev/lvdN` where N is the assigned unit ID.

Source: [src/sm_image.c](https://github.com/drakmor/ShadowMountPlus/blob/main/src/sm_image.c), [include/sm_mount_defs.h](https://github.com/drakmor/ShadowMountPlus/blob/main/include/sm_mount_defs.h)

### 6. nmount (PFS-specific)

After LVD attach, `perform_image_nmount` calls `nmount(iov_pfs, iovlen, mount_flags)`:

```c
// src/sm_image.c — iov_pfs array
struct iovec iov_pfs[] = {
    IOVEC_ENTRY("from"),       IOVEC_ENTRY(devname),       // /dev/lvdN
    IOVEC_ENTRY("fspath"),     IOVEC_ENTRY(mount_point),   // /mnt/shadowmnt/...
    IOVEC_ENTRY("fstype"),     IOVEC_ENTRY("pfs"),
    IOVEC_ENTRY("sigverify"),  IOVEC_ENTRY("0"),
    IOVEC_ENTRY("mkeymode"),   IOVEC_ENTRY("SD"),
    IOVEC_ENTRY("budgetid"),   IOVEC_ENTRY("game"),
    IOVEC_ENTRY("playgo"),     IOVEC_ENTRY("0"),
    IOVEC_ENTRY("disc"),       IOVEC_ENTRY("0"),
    IOVEC_ENTRY("ekpfs"),      IOVEC_ENTRY("0000...0000"), // 64 hex chars, all zero
    IOVEC_ENTRY("async"),      IOVEC_ENTRY(NULL),
    IOVEC_ENTRY("noatime"),    IOVEC_ENTRY(NULL),
    IOVEC_ENTRY("automounted"), IOVEC_ENTRY(NULL),
    IOVEC_ENTRY("errmsg"),     {(void *)mount_errmsg, sizeof(mount_errmsg)},
    IOVEC_ENTRY("force"),      IOVEC_ENTRY(NULL),          // only when force_mount=1
};
```

Mount flags for PFS: `MNT_RDONLY` (0) when read-only, `0` for read-write (same as exFAT).  
UFS uses different mount flags (`UFS_NMOUNT_FLAG_RO = 0x10000001u`, `UFS_NMOUNT_FLAG_RW = 0x10000000u`).

Source: [src/sm_image.c](https://github.com/drakmor/ShadowMountPlus/blob/main/src/sm_image.c), [include/sm_mount_defs.h](https://github.com/drakmor/ShadowMountPlus/blob/main/include/sm_mount_defs.h)

### 7. Mount validation

After nmount succeeds:
1. `statfs(mount_point)` must succeed.
2. `mounted_sfs.f_bsize` (cluster/block size) must be ≥ device sector size used at attach time.  
   If not, mount is rejected, an autotune rule is written to `autotune.ini`, and user is notified.
3. `opendir(mount_point)` must succeed.

Source: [src/sm_image.c](https://github.com/drakmor/ShadowMountPlus/blob/main/src/sm_image.c) — `validate_mounted_image`

### 8. Image cache registration

On success the mount is registered in an in-process cache (`g_image_cache`, max 64 entries).  
On failure or shutdown, `unmount_image` calls `unmount(mount_point, ...)` then detaches via `ioctl(lvd_fd, SCE_LVD_IOC_DETACH, &req)`.

---

## LVD Attach Subsystem

Source: [include/sm_mount_defs.h](https://github.com/drakmor/ShadowMountPlus/blob/main/include/sm_mount_defs.h), [include/sm_types.h](https://github.com/drakmor/ShadowMountPlus/blob/main/include/sm_types.h)

### Control paths

```c
#define LVD_CTRL_PATH "/dev/lvdctl"   // LVD attach/detach
#define MD_CTRL_PATH  "/dev/mdctl"    // MD attach/detach (not used for PFS)
```

### ioctl codes

```c
#define SCE_LVD_IOC_ATTACH_V0  0xC0286D00   // V0/base attach (used here)
#define SCE_LVD_IOC_ATTACH_V1  0xC0286D09   // V1/extended attach (not used)
#define SCE_LVD_IOC_DETACH     0xC0286D01
```

### Image type values

```c
#define LVD_ATTACH_IMAGE_TYPE_SINGLE             0    // exFAT
#define LVD_ATTACH_IMAGE_TYPE_PFS_SAVE_DATA      5    // PFS (.ffpfs)
#define LVD_ATTACH_IMAGE_TYPE_UFS_DOWNLOAD_DATA  7    // UFS2 (.ffpkg)
```

Validator accepts types 0..0xC (13 values total).

### Raw attach flags → normalization

UFS uses the DD (download-data) family; exFAT and PFS use the single-image family:

```c
#define LVD_ATTACH_RAW_FLAGS_SINGLE_RO  0x9    // exFAT and PFS read-only
#define LVD_ATTACH_RAW_FLAGS_SINGLE_RW  0x8    // exFAT and PFS read-write
#define LVD_ATTACH_RAW_FLAGS_DD_RO      0xD    // UFS read-only
#define LVD_ATTACH_RAW_FLAGS_DD_RW      0xC    // UFS read-write
```

Raw flags are normalized by the kernel wrapper before validation. The bit mapping (raw→normalized):
`0x1→0x08`, `0x2→0x80`, `0x4→0x02`, `0x8→0x10`.

### Layer descriptor

```c
typedef struct {
  uint16_t source_type;    // 1 = file, 2 = device/special source
  uint16_t flags;          // bit0 = no bitmap file (always set for image files)
  uint32_t reserved0;
  const char *path;        // image file path
  uint64_t offset;         // 0
  uint64_t size;           // file size
  const char *bitmap_path; // NULL
  uint64_t bitmap_offset;  // 0
  uint64_t bitmap_size;    // 0
} lvd_ioctl_layer_v0_t;
```

Source: [include/sm_types.h](https://github.com/drakmor/ShadowMountPlus/blob/main/include/sm_types.h)

### Attach request

```c
typedef struct {
  uint32_t io_version;       // 0 for V0
  int32_t  device_id;        // -1 for auto-assign; filled with unit on return
  uint32_t sector_size;      // user-visible sector size for /dev/lvdN
  uint32_t secondary_unit;   // granularity; 0x10000 for exFAT, = sector_size for others
  uint16_t flags;            // normalized attach flags
  uint16_t image_type;       // 0=single, 5=pfs, 7=ufs
  uint32_t layer_count;      // 1
  uint64_t device_size;      // total file size
  lvd_ioctl_layer_v0_t *layers_ptr;
} lvd_ioctl_attach_v0_t;
```

---

## nmount Options by Filesystem

### PFS (`.ffpfs`)

| Key | Value | Notes |
|-----|-------|-------|
| `fstype` | `pfs` | Selects the PFS kernel module |
| `from` | `/dev/lvdN` | Block device from LVD attach |
| `fspath` | `/mnt/shadowmnt/<name>_<hash>` | Mount destination |
| `sigverify` | `"0"` | Signature verification disabled |
| `mkeymode` | `"SD"` | Master key derivation mode; other valid values: `GD`, `AC` |
| `budgetid` | `"game"` | Budget domain; alternative: `"system"` |
| `playgo` | `"0"` | PlayGo streaming disabled |
| `disc` | `"0"` | Disc mode disabled |
| `ekpfs` | `"000...000"` (64 hex chars) | 256-bit EKPFS key, all zero for unsigned images |
| `async` | (null) | Async I/O |
| `noatime` | (null) | No access time updates |
| `automounted` | (null) | Marks as auto-mounted |
| `errmsg` | (256-byte buffer) | Receives kernel error text |
| `force` | (null) | Only added when `force_mount=1` |

Mount flags for PFS: `MNT_RDONLY` for read-only, `0` for read-write.

Source: [src/sm_image.c](https://github.com/drakmor/ShadowMountPlus/blob/main/src/sm_image.c) `iov_pfs`, [include/sm_mount_defs.h](https://github.com/drakmor/ShadowMountPlus/blob/main/include/sm_mount_defs.h)

### UFS2 (`.ffpkg`)

| Key | Value |
|-----|-------|
| `fstype` | `ufs` |
| `from` | `/dev/lvdN` or `/dev/mdN` |
| `fspath` | mount point |
| `budgetid` | `"game"` |
| `async` | (null) |
| `noatime` | (null) |
| `automounted` | (null) |

Mount flags: `UFS_NMOUNT_FLAG_RO = 0x10000001` or `UFS_NMOUNT_FLAG_RW = 0x10000000`.  
UFS uses the DD attach family (`LVD_ATTACH_IMAGE_TYPE_UFS_DOWNLOAD_DATA = 7`).

### exFAT (`.exfat`)

| Key | Value |
|-----|-------|
| `fstype` | `exfatfs` |
| `from` | `/dev/lvdN` or `/dev/mdN` |
| `fspath` | mount point |
| `budgetid` | `"game"` |
| `large` | `"yes"` |
| `timezone` | `"static"` |
| `async`, `noatime`, `ignoreacl`, `automounted` | (null) |

Mount flags: `MNT_RDONLY` or `0`. Secondary unit is `0x10000` (fixed).

---

## Sector / Cluster Size Rules

Source: [include/sm_mount_defs.h](https://github.com/drakmor/ShadowMountPlus/blob/main/include/sm_mount_defs.h), [src/sm_config_mount.c](https://github.com/drakmor/ShadowMountPlus/blob/main/src/sm_config_mount.c), [config.ini.example](https://github.com/drakmor/ShadowMountPlus/blob/main/config.ini.example)

### Compile-time defaults (code initialization)

```c
// include/sm_mount_defs.h
#define LVD_SECTOR_SIZE_EXFAT  512u
#define LVD_SECTOR_SIZE_UFS    4096u
#define LVD_SECTOR_SIZE_PFS    4096u    // used when no config.ini is present
```

Code initialization (`sm_config_mount.c` line 268):
```c
state->cfg.lvd_sector_pfs = LVD_SECTOR_SIZE_PFS;  // = 4096
```

### Documented/recommended config defaults (`config.ini.example`)

```ini
# Defaults: lvd_exfat=512, lvd_ufs=4096, lvd_pfs=32768, md_exfat=512, md_ufs=512
# lvd_pfs_sector_size=32768
```

> Discrepancy: The compile-time constant `LVD_SECTOR_SIZE_PFS = 4096` is used when no config file is present. However, the README and `config.ini.example` document the default as `32768`. This is the recommended value to set, not necessarily the bare code default. Users with a `config.ini` that uncommends `lvd_pfs_sector_size=32768` (or any value ≥ image cluster size) will work as documented.

The code always reads from `runtime_config()->lvd_sector_pfs` at mount time.

### Validation rule

After mount, the kernel's reported `f_bsize` (cluster size) must be ≥ device sector_size:

```c
if (fs_block_size < (uint64_t)min_device_sector) {
    // Mount rejected; autotune writes image_sector override to autotune.ini
}
```

Practical recommendation: Build PFS images with a cluster/block size of at least 32768 bytes. This covers both users who have `lvd_pfs_sector_size=32768` in their config (as documented/recommended) and provides headroom for any custom values. If a user's sector size setting exceeds your cluster size, the mount will be rejected and ShadowMountPlus will write an `image_sector` autotune entry.

### Per-image override

```ini
# config.ini or autotune.ini
image_sector=PPSA12345.ffpfs:65536
```

Match is by filename only (no path). If the mounted FS cluster size is smaller than the sector, ShadowMountPlus auto-writes an `image_sector` rule to `autotune.ini`.

---

## Game Content Layout Requirements

Source: [src/sm_gameinfo.c](https://github.com/drakmor/ShadowMountPlus/blob/main/src/sm_gameinfo.c), [src/sm_filesystem.c](https://github.com/drakmor/ShadowMountPlus/blob/main/src/sm_filesystem.c), [README.md](https://github.com/drakmor/ShadowMountPlus/blob/main/README.md)

### Mandatory files

```
<image root>/
└── sce_sys/
    └── param.json          ← REQUIRED: scanner reads titleId and titleName
```

### Effectively required in practice

```
<image root>/
├── eboot.bin               ← lifecycle health checks treat missing eboot.bin as stale/invalid
└── sce_sys/
    └── param.json
```

Specifically, `source_path_needs_cleanup` returns `true` (marks source for cleanup) when `eboot.bin` is absent:

```c
// src/sm_filesystem.c
char eboot_path[MAX_PATH];
snprintf(eboot_path, sizeof(eboot_path), "%s/eboot.bin", source_path);
// ...
return !path_exists(eboot_path);
```

### Recommended full layout for normal game/homebrew

```
<image root>/
├── eboot.bin
├── sce_sys/
│   ├── param.json          ← required
│   ├── icon0.png           ← copied to /user/appmeta/<TITLE_ID>/ and /user/app/<TITLE_ID>/
│   ├── param.sfo           ← optional; copied to appmeta
│   └── snd0.at9            ← optional; triggers snd0info DB update after install
├── sce_module/             ← optional; PRX modules
├── media/                  ← optional; game assets
└── ...                     ← other game payload at image root
```

### Layout constraint: NO extra top-level folder

Valid:
```
/sce_sys/param.json         ← directly under image root
/eboot.bin
```

Invalid:
```
/GAME_FOLDER/sce_sys/param.json   ← extra nesting layer
/GAME_FOLDER/eboot.bin
```

The scanner calls `directory_has_param_json(mount_point)` which checks for `sce_sys/param.json` relative to the candidate directory, not recursively.

---

## param.json Parsing

Source: [src/sm_gameinfo.c](https://github.com/drakmor/ShadowMountPlus/blob/main/src/sm_gameinfo.c)

The parser is a simple string search, not a full JSON parser:

```c
// Reads: titleId or title_id (fallback)
int res = extract_json_string(buf, "titleId", out_id, MAX_TITLE_ID);
if (res != 0)
    res = extract_json_string(buf, "title_id", out_id, MAX_TITLE_ID);

// Reads: titleName (prefers en-US locale object if present)
const char *en_ptr = strstr(buf, "\"en-US\"");
const char *search_start = en_ptr ? en_ptr : buf;
extract_json_string(search_start, "titleName", out_name, MAX_TITLE_NAME);

// If no titleName found, falls back to titleId
if (out_name[0] == '\0')
    strlcpy(out_name, out_id, MAX_TITLE_NAME);
```

Constraints:
- Max file size: `MAX_PARAM_JSON_SIZE = 1 MiB`
- Max title ID length: `MAX_TITLE_ID = 32`
- Max title name length: `MAX_TITLE_NAME = 256`

Supported title ID formats (from game lifecycle code):
- `PPSA` prefix (PS5 native)
- `CUSA` prefix (PS4 BC)

Minimum valid param.json:
```json
{
  "titleId": "PPSA12345"
}
```

Recommended param.json:
```json
{
  "titleId": "PPSA12345",
  "titleName": "My Game Title"
}
```

Or with locale support:
```json
{
  "titleId": "PPSA12345",
  "localizedParameters": {
    "en-US": {
      "titleName": "My Game Title"
    }
  }
}
```

---

## Scan Paths and Directory Layout

Source: [include/sm_paths.h](https://github.com/drakmor/ShadowMountPlus/blob/main/include/sm_paths.h), [README.md](https://github.com/drakmor/ShadowMountPlus/blob/main/README.md)

### Default scan roots (compiled in)

```c
// include/sm_paths.h
#define SM_DEFAULT_SCAN_PATHS_INITIALIZER {
  "/data/homebrew",
  "/data/etaHEN/games",
  "/mnt/ext0/homebrew",        // Extended storage (SSD expansion bay)
  "/mnt/ext0/etaHEN/games",
  "/mnt/ext1/homebrew",        // M.2 drive
  "/mnt/ext1/etaHEN/games",
  "/mnt/usb0/homebrew",        // USB drives (0-7)
  ... (usb1-7 variants)
  "/mnt/usb0/etaHEN/games",
  ... (usb1-7 variants)
  "/mnt/usb0", "/mnt/usb1", ... "/mnt/usb7",   // USB roots
  "/mnt/ext0", "/mnt/ext1",
  NULL
}
```

`IMAGE_MOUNT_BASE = "/mnt/shadowmnt"` is always added automatically.

### Recommended directory structure

Flat mode (`scan_depth=1`, default):
```
/data/homebrew/<TITLE_ID>/          ← direct folder game (contains sce_sys/param.json)
/data/homebrew/<TITLE_ID>.ffpkg     ← UFS2 image
/data/homebrew/<TITLE_ID>.ffpfs     ← PFS image
/data/homebrew/backports/<TITLE_ID>/ ← backport overlays (excluded from game scan)
```

Nested mode (`scan_depth=2`):
```
/data/homebrew/PS5/<Collection>/<TITLE_ID>/
/mnt/ext0/etaHEN/games/<Collection>/<TITLE_ID>.ffpkg
```

### Scan loop behavior

- Full scan every `scan_interval_seconds` (default: 15s)
- New/modified sources deferred until `stability_wait_seconds` old (default: 10s)
- `backports/` subdirectory skipped during normal game scan at depth 0
- `/mnt/shadowmnt` is scanned for content inside mounted images

---

## Install and Registration Flow

Source: [src/sm_install.c](https://github.com/drakmor/ShadowMountPlus/blob/main/src/sm_install.c), [src/sm_scan.c](https://github.com/drakmor/ShadowMountPlus/blob/main/src/sm_scan.c)

### Step 1: Metadata staging

From `<source>/sce_sys/` the following are copied:
- To `/user/app/<TITLE_ID>/sce_sys/` — full `sce_sys` directory copy
- To `/user/app/<TITLE_ID>/icon0.png` — icon copy at app root level
- To `/user/appmeta/<TITLE_ID>/` — only files matching appmeta filter:
  - `param.json`, `param.sfo`
  - `*.png`, `*.dds`, `*.at9`

### Step 2: nullfs mount

```c
// mount_title_nullfs
// Creates: nullfs /system_ex/app/<TITLE_ID> -> <source_path>
```

This makes the game content accessible to ShellCore at `/system_ex/app/<TITLE_ID>`.

### Step 3: Link files

```c
// Written to /user/app/<TITLE_ID>/mount.lnk      → source_path
// Written to /user/app/<TITLE_ID>/mount_img.lnk  → image file path (if image-backed)
```

`mount.lnk` contains the active mount source path (either a direct game folder or the image mount point `/mnt/shadowmnt/...`).  
`mount_img.lnk` contains the original `.ffpkg`/`.ffpfs`/`.exfat` image file path.

### Step 4: App registration

- **FW < 12.00:** calls `sceAppInstUtilAppInstallTitleDir(title_id, APP_BASE "/", 0)` via dlopen of `/system/common/lib/libSceAppInstUtil.sprx`
- **FW ≥ 12.00:** forced to use `sceAppInstUtilAppInstallAll` (batch mode)

Return codes:
- `0` → new install success
- `0x80990002` → restored (already existed, silently recovered)
- Other → failure, user notification

### snd0.at9 handling

If `sce_sys/snd0.at9` is present, `update_snd0info` updates the app.db `snd0info` rows after registration.

---

## Link Files and nullfs Mounts

Source: [src/sm_filesystem.c](https://github.com/drakmor/ShadowMountPlus/blob/main/src/sm_filesystem.c), [include/sm_paths.h](https://github.com/drakmor/ShadowMountPlus/blob/main/include/sm_paths.h)

### System path layout

```
/user/app/<TITLE_ID>/
├── sce_sys/            ← staged metadata copy
│   ├── param.json
│   └── ...
├── icon0.png           ← staged icon copy
├── mount.lnk           ← plain text file: active source path
└── mount_img.lnk       ← plain text file: original image file path (if image)

/user/appmeta/<TITLE_ID>/
├── param.json          ← copied from sce_sys
├── icon0.png
└── ...

/system_ex/app/<TITLE_ID>/    ← nullfs mount of game source
├── eboot.bin
├── sce_sys/param.json
└── ...

/mnt/shadowmnt/<name>_<hash>/ ← image mount point (LVD + nmount)
├── eboot.bin
├── sce_sys/param.json
└── ...
```

### Mount detection on startup

On re-scan or restart, existing `/mnt/shadowmnt/*` mounts are detected via `statfs` + `f_mntonname` matching, and their `mount.lnk` is re-read to restore the in-process cache.

### Cleanup conditions

An installed title is cleaned up (unmounted/uninstalled) when:
- Source path no longer exists
- Source path is under `image_mount_base` but the backing image file is gone
- Source path is under `/system_ex/app` (should not normally happen)
- `eboot.bin` is missing from the source path

---

## Fakelib / Backport Overlay

Source: [src/sm_fakelib.c](https://github.com/drakmor/ShadowMountPlus/blob/main/src/sm_fakelib.c)

ShadowMountPlus can mount overlay libraries into a running game's sandbox:

```c
// unionfs overlay
struct iovec overlay_iov[] = {
    IOVEC_ENTRY("fstype"),    IOVEC_ENTRY("unionfs"),
    IOVEC_ENTRY("from"),      IOVEC_ENTRY(source_path),
    IOVEC_ENTRY("fspath"),    IOVEC_ENTRY(mount_path),
    IOVEC_ENTRY("copymode"),  IOVEC_ENTRY("transparent"),
    IOVEC_ENTRY("notime"),    IOVEC_ENTRY(NULL),
    IOVEC_ENTRY("fnodup"),    IOVEC_ENTRY(NULL)
};
```

Overlay sources:
1. Per-game fakelib: `/mnt/sandbox/<TITLE_ID>_XXX/app0/fakelib` → sandbox `common/lib`
2. Global fakelib: `/data/shadowmount/fakelib` → same sandbox `common/lib`

Backport folder: `<scanpath>/backports/<TITLE_ID>/` — applied to the matched game's mount.  
The `backports` directory is explicitly excluded from normal game candidate scanning.

---

## app.db Integration

Source: [src/sm_appdb.c](https://github.com/drakmor/ShadowMountPlus/blob/main/src/sm_appdb.c)

```c
#define APP_DB_PATH "/system_data/priv/mms/app.db"
```

Uses SQLite3 (`/system/common/lib/libSqlite.sprx`). Operations:
- Query installed title IDs to determine whether a game needs registration or remount
- Update `snd0info` rows when `snd0.at9` is present
- Cache invalidated on title list changes

Retry behavior: up to 25 retries for `SQLITE_BUSY`/`SQLITE_LOCKED`, with 200ms sleep between retries and a 5000ms busy timeout.

---

## Runtime Configuration

Config file: `/data/shadowmount/config.ini`  
Autotune file: `/data/shadowmount/autotune.ini` (auto-written by ShadowMountPlus)

Source: [src/sm_config_mount.c](https://github.com/drakmor/ShadowMountPlus/blob/main/src/sm_config_mount.c), [config.ini.example](https://github.com/drakmor/ShadowMountPlus/blob/main/config.ini.example)

### Key settings relevant to PFS image generation

| Key | Default | Notes |
|-----|---------|-------|
| `lvd_pfs_sector_size` | `32768` | Most important for PFS: must be ≤ image cluster size |
| `mount_read_only` | `1` | 1=ro, 0=rw for all images unless overridden per-image |
| `image_rw=<filename>` | — | Per-image read-write override |
| `image_ro=<filename>` | — | Per-image read-only override |
| `image_sector=<filename>:<size>` | — | Per-image sector size override |
| `force_mount` | `0` | Mount even damaged filesystems |
| `stability_wait_seconds` | `10` | Source must be this old before mounting |
| `scan_depth` | `1` | 1=flat, 2=one level deeper |

### Config precedence for sector/pause delays

`autotune.ini` (highest) → `image_sector` in `config.ini` → compile-time defaults

### Firmware-specific behavior

- FW ≥ 12.00: `app_install_all_enabled` is forced to `true` regardless of config

---

## Image Creation Scripts

### mkexfat.sh — Linux exFAT image creator

Source: [mkexfat.sh](https://github.com/drakmor/ShadowMountPlus/blob/main/mkexfat.sh)

```sh
./mkexfat.sh <game_root_dir> [output.exfat]
```

- Requires: `exfatprogs`, `exfat-fuse`, `fuse3`, `rsync`
- Auto-selects cluster profile:
  - Large-file average ≥ 1MB → 64K cluster
  - Otherwise → 32K cluster
- Calculates image size: `data_bytes (rounded to cluster) + FAT + bitmap + dir entries + 32MB metadata + dynamic headroom (0.5%, min 64MB, max 512MB)`
- Validates `eboot.bin` presence before proceeding

### mkufs2.sh — FreeBSD UFS2 image creator

Source: [mkufs2.sh](https://github.com/drakmor/ShadowMountPlus/blob/main/mkufs2.sh)

```sh
./mkufs2.sh <game_root_dir> [output.ffpkg]
```

- Only runs on FreeBSD (uses `mdconfig`, `newfs`, `/dev/mdX`)
- Fixed UFS2 profile: `newfs -O 2 -b 65536 -f 65536 -m 0 -S 4096 -i <bytes_per_inode>`
- Auto-tunes `-i` based on file/directory count:
  - Default: `262144` (normal game dumps)
  - Lower: `131072` for tens of thousands of files
  - Minimum: `65536` for very file-dense images
  - Formula: `inode_count = file_count + dir_count + 2048`; `bytes_per_inode = image_size / inode_count` (rounded down to multiple of 4096)

### make_image.bat + New-OsfExfatImage.ps1 — Windows exFAT

Source: [make_image.bat](https://github.com/drakmor/ShadowMountPlus/blob/main/make_image.bat), [New-OsfExfatImage.ps1](https://github.com/drakmor/ShadowMountPlus/blob/main/New-OsfExfatImage.ps1)

```bat
make_image.bat "C:\images\game.exfat" "C:\payload\GAME_ROOT"
```

Requires OSFMount: https://www.osforensics.com/tools/mount-disk-images.html

---

## System Paths Reference

Source: [include/sm_paths.h](https://github.com/drakmor/ShadowMountPlus/blob/main/include/sm_paths.h)

| Constant | Value | Purpose |
|----------|-------|---------|
| `IMAGE_MOUNT_BASE` | `/mnt/shadowmnt` | Base directory for all image mounts |
| `APP_BASE` | `/user/app` | Staged game directories + link files |
| `APPMETA_BASE` | `/user/appmeta` | Staged game metadata (icon, param.json, etc.) |
| `APP_DB_PATH` | `/system_data/priv/mms/app.db` | PS5 app database (SQLite) |
| `CONFIG_FILE` | `/data/shadowmount/config.ini` | Runtime config |
| `AUTOTUNE_FILE` | `/data/shadowmount/autotune.ini` | Auto-written sector/delay overrides |
| `LOG_FILE` | `/data/shadowmount/debug.log` | Debug log (rotated to `.1`) |
| `DEFAULT_GLOBAL_FAKELIB_PATH` | `/data/shadowmount/fakelib` | Global backport overlay libs |
| `KILL_FILE` | `/data/shadowmount/STOP` | Graceful shutdown trigger |
| `NOTIFY_ICON_FILE` | `/user/data/shadowmount/smp_icon.png` | Toast notification icon |
| `DEFAULT_BACKPORTS_DIR_NAME` | `backports` | Subdirectory excluded from game scan |

Game sandbox path (while running):
- `/mnt/sandbox/<TITLE_ID>_XXX/app0/` — game's app0 (content)
- `/mnt/sandbox/<TITLE_ID>_XXX/app0/fakelib` — per-game fakelib source for overlay

System install target:
- `/system_ex/app/<TITLE_ID>/` — nullfs mount of game source

---

## Key Constants and Limits

Source: [include/sm_limits.h](https://github.com/drakmor/ShadowMountPlus/blob/main/include/sm_limits.h)

| Constant | Value | Meaning |
|----------|-------|---------|
| `MAX_IMAGE_MOUNTS` | 64 | Max concurrently tracked image mounts |
| `MAX_PENDING` | 512 | Max scan candidates per cycle |
| `MAX_IMAGE_MODE_RULES` | 128 | Max `image_ro`/`image_rw`/`image_sector` rules |
| `MAX_FAILED_MOUNT_ATTEMPTS` | 2 | Retries before giving up on a candidate |
| `MAX_IMAGE_MOUNT_ATTEMPTS` | 3 | Mount retries per image |
| `MAX_MISSING_PARAM_SCAN_ATTEMPTS` | 3 | Retries for missing param.json |
| `MAX_SCAN_PATHS` | 256 | Max scan roots |
| `DEFAULT_SCAN_INTERVAL_US` | 15,000,000 (15s) | Full scan loop interval |
| `DEFAULT_STABILITY_WAIT_SECONDS` | 10 | Minimum source age |
| `MAX_PATH` | 1024 | Max path length |
| `MAX_TITLE_ID` | 32 | Max title ID string length |
| `MAX_TITLE_NAME` | 256 | Max title name string length |
| `MAX_PARAM_JSON_SIZE` | 1 MiB | Max param.json file size |
| `LVD_NODE_WAIT_US` | 100,000 (100ms) | Poll interval waiting for /dev/lvdN |
| `LVD_NODE_WAIT_RETRIES` | 100 | → up to 10s wait for device node |

---

## Source File Index

| File | Purpose |
|------|---------|
| [src/sm_image.c](https://github.com/drakmor/ShadowMountPlus/blob/main/src/sm_image.c) | Core: detect format, LVD attach, nmount, validate, unmount |
| [src/sm_mount_device.c](https://github.com/drakmor/ShadowMountPlus/blob/main/src/sm_mount_device.c) | LVD/MD backend ops, device node wait, mount resolution |
| [include/sm_mount_defs.h](https://github.com/drakmor/ShadowMountPlus/blob/main/include/sm_mount_defs.h) | All LVD/PFS/UFS/exFAT constants and ioctl codes |
| [include/sm_types.h](https://github.com/drakmor/ShadowMountPlus/blob/main/include/sm_types.h) | Struct types: lvd layer, attach request, runtime config, scan candidate |
| [include/sm_limits.h](https://github.com/drakmor/ShadowMountPlus/blob/main/include/sm_limits.h) | All capacity limits and timeout values |
| [include/sm_paths.h](https://github.com/drakmor/ShadowMountPlus/blob/main/include/sm_paths.h) | All filesystem path constants and default scan path list |
| [include/sm_platform.h](https://github.com/drakmor/ShadowMountPlus/blob/main/include/sm_platform.h) | Platform includes, SCE SDK function declarations, IOVEC macros |
| [src/sm_gameinfo.c](https://github.com/drakmor/ShadowMountPlus/blob/main/src/sm_gameinfo.c) | param.json parser (titleId/titleName extraction) |
| [src/sm_scan.c](https://github.com/drakmor/ShadowMountPlus/blob/main/src/sm_scan.c) | Candidate discovery: game dirs + image files |
| [src/sm_scan_tree.c](https://github.com/drakmor/ShadowMountPlus/blob/main/src/sm_scan_tree.c) | Directory tree walker with depth control |
| [src/sm_scanner.c](https://github.com/drakmor/ShadowMountPlus/blob/main/src/sm_scanner.c) | Periodic scan loop coordinator |
| [src/sm_install.c](https://github.com/drakmor/ShadowMountPlus/blob/main/src/sm_install.c) | Mount+metadata stage+nullfs+registration pipeline |
| [src/sm_filesystem.c](https://github.com/drakmor/ShadowMountPlus/blob/main/src/sm_filesystem.c) | Link file I/O, health checks, cleanup logic |
| [src/sm_appdb.c](https://github.com/drakmor/ShadowMountPlus/blob/main/src/sm_appdb.c) | SQLite app.db queries and snd0info updates |
| [src/sm_config_mount.c](https://github.com/drakmor/ShadowMountPlus/blob/main/src/sm_config_mount.c) | config.ini / autotune.ini parser and runtime config state |
| [src/sm_fakelib.c](https://github.com/drakmor/ShadowMountPlus/blob/main/src/sm_fakelib.c) | unionfs fakelib overlay for sandbox |
| [src/sm_game_lifecycle.c](https://github.com/drakmor/ShadowMountPlus/blob/main/src/sm_game_lifecycle.c) | kqueue-based game exec/exit event monitoring |
| [src/sm_shellcore_flags.c](https://github.com/drakmor/ShadowMountPlus/blob/main/src/sm_shellcore_flags.c) | SceShellCore kernel event flags monitoring |
| [src/sm_kstuff.c](https://github.com/drakmor/ShadowMountPlus/blob/main/src/sm_kstuff.c) | kstuff sysentvec toggle around game launches |
| [src/sm_stability.c](https://github.com/drakmor/ShadowMountPlus/blob/main/src/sm_stability.c) | Source mtime/ctime age check |
| [src/main.c](https://github.com/drakmor/ShadowMountPlus/blob/main/src/main.c) | ELF entry point, thread startup |
| [config.ini.example](https://github.com/drakmor/ShadowMountPlus/blob/main/config.ini.example) | Full annotated config template |
| [mkexfat.sh](https://github.com/drakmor/ShadowMountPlus/blob/main/mkexfat.sh) | Linux exFAT image creator |
| [mkufs2.sh](https://github.com/drakmor/ShadowMountPlus/blob/main/mkufs2.sh) | FreeBSD UFS2 image creator |

---

## Checklist for .ffpfs Image Generators

Based on full source analysis, the following is the validated checklist for generating PFS images compatible with ShadowMountPlus:

1. Extension: Output file must have `.ffpfs` extension (case-insensitive match).
2. Filesystem type: Must mount as `pfs` via `nmount` with `fstype=pfs`.
3. LVD attach type: `LVD_ATTACH_IMAGE_TYPE_PFS_SAVE_DATA` (= 5), single-image family (not DD).
4. Cluster / block size ≥ 32768 (recommended): `statfs.f_bsize` must be ≥ selected sector size.
5. Content at image root: `sce_sys/param.json` directly at image root; no extra top-level folder.
6. param.json: Must contain `titleId` or `title_id`; `titleName` recommended. `PPSA`/`CUSA` formats supported.
7. eboot.bin at image root: required in practice for health checks.
8. Zero EKPFS key: `ekpfs=000...000` and `sigverify=0` for unsigned testing/dev flows.
9. mkeymode/budget: `mkeymode=SD`, `budgetid=game`.
10. No bitmap file: `LVD_ENTRY_FLAG_NO_BITMAP` always set.
11. Source stability: `mtime/ctime` ≥ `stability_wait_seconds` (default 10s).
12. Provide sector-size headroom: consider 65536 block size for broad compatibility.
13. Optional assets: `icon0.png`, `snd0.at9`, `param.sfo`.

---

For authoritative details, consult the upstream repository and linked file paths above.
