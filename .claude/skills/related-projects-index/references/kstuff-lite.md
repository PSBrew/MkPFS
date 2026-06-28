# kstuff-lite — Deep Reference

Upstream repository: https://github.com/EchoStretch/kstuff-lite

Executive summary
- PS5-oriented payload bundle: a loader plus a kernel payload with syscall/trap hooks, mount automation, crypto helpers, and optional observability.
- Practical value for MkPFS: demonstrates how titles are discovered and mounted, how PFS/PKG crypto flows are serviced in practice, and how bind-mounts and link files integrate with the PS5 UI/runtime.
- Performance focus: faster FPKG/SELF handling, small caches for HMAC and XTS, Zen 2-tuned crypto path via isa-l_crypto; optional observability mode (KSTUFF_OBS=1).

Scope
- Topic focus: PS5 payload loading, syscall interception, FPKG/PFS crypto, auto-mounting flow.
- Evidence policy: derived from the upstream repo (paths below); treat repo files as ground truth.

Project structure (top-level highlights)
- ps5-kstuff-ldr/ — Loader (maps payload, manages auto-mounts, scans titles)
  - main.c — entry, payload mapping, mount automation
  - https://github.com/EchoStretch/kstuff-lite/blob/main/ps5-kstuff-ldr/main.c
- ps5-kstuff/ — Kernel payload and uelf helpers
  - uelf/main.c — syscall/trap dispatch hub
    - https://github.com/EchoStretch/kstuff-lite/blob/main/ps5-kstuff/uelf/main.c
  - uelf/pfs_crypto.c — PFS HMAC/XTS helper/cache
    - https://github.com/EchoStretch/kstuff-lite/blob/main/ps5-kstuff/uelf/pfs_crypto.c
  - uelf/fpkg.c — FPKG-specific crypto/message handling
    - https://github.com/EchoStretch/kstuff-lite/blob/main/ps5-kstuff/uelf/fpkg.c
  - uelf/fself.c — SELF/FSELF parsing and handling
    - https://github.com/EchoStretch/kstuff-lite/blob/main/ps5-kstuff/uelf/fself.c
  - uelf/npdrm.c — Debug NPDRM mailbox flows
    - https://github.com/EchoStretch/kstuff-lite/blob/main/ps5-kstuff/uelf/npdrm.c
  - uelf/pfs_crypto.h, shared_area.h — caches and shared-area controls
    - https://github.com/EchoStretch/kstuff-lite/blob/main/ps5-kstuff/uelf/pfs_crypto.h
    - https://github.com/EchoStretch/kstuff-lite/blob/main/ps5-kstuff/uelf/shared_area.h
  - Makefile — build flags, KSTUFF_OBS, arch tuning
    - https://github.com/EchoStretch/kstuff-lite/blob/main/ps5-kstuff/Makefile
- ci-ps5-kstuff-ldr.sh — build orchestration
  - https://github.com/EchoStretch/kstuff-lite/blob/main/ci-ps5-kstuff-ldr.sh

Supported variants / artifacts
- payload.bin — standard kernel payload build
- debug-reader.bin — emitted when KSTUFF_OBS=1 (observability-enabled build)
- Mount sources the loader can handle: UFS (.ffpkg), PFS (.ffpfs), exFAT (.exfat); fallback to raw folder path when mount fails

Architecture and flow
1) Loader (ps5-kstuff-ldr)
- Maps embedded payload into memory, sets segment protections, jumps to payload entry
- Scans /user/app and image sources; can be disabled by creating /data/.kstuff_noautomount
- Auto-mounts images or binds raw folder content when mounting fails; manages bind mounts to /system_ex/app/<TITLE_ID>

2) Payload/uelf (ps5-kstuff/uelf)
- Dispatches syscalls and traps to specific handlers (mprotect, mount family, FSELF/FPKG/NPDRM, crypto mailboxes)
- Optimizes crypto handling:
  - Caches expanded XTS keys and HMAC-SHA256 state in small ring buffers
  - Coalesces adjacent XTS messages (batch processing) and uses DMEM fast path when possible
  - Replaces broader crypto libs with isa-l_crypto + a minimal PS5 adapter; adds a fast SHA-256 path tuned for Zen 2
- Improves stability and error handling in mailbox/NPDRM/SELF flows (explicit validation, better handling of FPU/debug register/save-restore states)

Important constants / config / paths
- Build flags (Makefile):
  - KSTUFF_OBS — toggles observability; emits debug-reader.bin; enables shared-area snapshot support
  - UELF_ARCH — e.g., -march=znver2 -mtune=znver2 (Zen 2 tuning)
- Runtime markers and paths:
  - /data/.kstuff_noautomount — disables automatic title mounting by the loader
  - /user/app — primary scan root for installed titles
  - /system_ex/app/<TITLE_ID> — bind-mount destination for active game content
  - mount.lnk — text file under /user/app/<TITLE_ID> pointing to active source path
- Crypto/cache sizes (headers):
  - PFS_HMAC_SHA256_CACHE_SLOTS = 2
  - PFS_XTS_KEY_CACHE_SLOTS = 2
  - SHARED_AREA_SIZE = 8192
  - SHARED_FAKE_KEY_SLOTS = 63

Layout and validation rules (operational)
- Mount detection path: loader attempts UFS, PFS, exFAT images; if none work, binds the raw folder
- Bind mount creation: creates /system_ex/app/<TITLE_ID> mount point and binds selected source there
- Title scan respects the no-automount marker; re-detects and rebinds persisted titles via link files/mount discovery

Technical findings (from upstream code and README)
- Loader + payload split reduces complexity in early init; loader manages mapping and mount decisions; payload handles syscalls/crypto
- Crypto path optimizations significantly reduce repeated work: adjacent-XTS coalescing, fast DMEM path, state caching, lighter SHA-256
- FSELF parsing caches headers, lazily loads authinfo, skips redundant operations, and guards overlapping copies
- NPDRM mailbox flows are treated as debug-oriented and include stricter error partitioning
- Observability mode enables debug readers and snapshot support for the shared area

Compatibility and behavior notes
- Requires a working PS5 payload SDK to build (validated in ci-ps5-kstuff-ldr.sh)
- Auto-mounting is permissive by design; disabling via /data/.kstuff_noautomount is recommended for controlled debugging
- Behavior is firmware-sensitive (PS4/PS5 syscall IDs, ShellCore lookup nuances)

Actionable checklist (for agents using this as reference)
- When reasoning about auto-mount flows and bind mounts, start with:
  - ps5-kstuff-ldr/main.c — mount detection, bind mount creation, scan loop
- For crypto/key-derivation/FPKG details in practice, read:
  - ps5-kstuff/uelf/pfs_crypto.c, fpkg.c — key caching, message coalescing, mailbox handling
- For SELF parsing quirks (PS4 vs PS5 styles, lazy authinfo), read:
  - ps5-kstuff/uelf/fself.c
- For NPDRM debug flows, read:
  - ps5-kstuff/uelf/npdrm.c
- Use Makefile/ci script to confirm build-time options and environment assumptions

Source index (upstream)
- Loader entry: https://github.com/EchoStretch/kstuff-lite/blob/main/ps5-kstuff-ldr/main.c
- Payload dispatch: https://github.com/EchoStretch/kstuff-lite/blob/main/ps5-kstuff/uelf/main.c
- PFS crypto: https://github.com/EchoStretch/kstuff-lite/blob/main/ps5-kstuff/uelf/pfs_crypto.c
- FPKG: https://github.com/EchoStretch/kstuff-lite/blob/main/ps5-kstuff/uelf/fpkg.c
- FSELF: https://github.com/EchoStretch/kstuff-lite/blob/main/ps5-kstuff/uelf/fself.c
- NPDRM: https://github.com/EchoStretch/kstuff-lite/blob/main/ps5-kstuff/uelf/npdrm.c
- Caches/share: https://github.com/EchoStretch/kstuff-lite/blob/main/ps5-kstuff/uelf/pfs_crypto.h
- Build: https://github.com/EchoStretch/kstuff-lite/blob/main/ps5-kstuff/Makefile
- CI script: https://github.com/EchoStretch/kstuff-lite/blob/main/ci-ps5-kstuff-ldr.sh
