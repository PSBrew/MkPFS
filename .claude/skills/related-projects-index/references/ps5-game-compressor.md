# PS5 Game Compressor — Reference

Upstream: https://github.com/juma-sayeh/PS5-Game-Compressor

Executive summary
- Standalone PS5 payload with a built-in web UI to compress, unpack, validate, repair, and move ShadowMountPlus-mounted games — jobs continue even if the browser closes.
- Produces FF-PFSC containers: default is nested exFAT image inside PFSC; optional nested PFS for experimentation. APR Emu titles are detected and indexed (ampr_emu.index) automatically when needed.
- Implements a high-throughput windowed PFSC compressor (64 KiB blocks) using zlib (default level 7), per-block gain thresholding, and a parallel read/deflate/write pipeline.
- Ships a per-block SHA‑256 validation sidecar (.vhash) for PFSC images and a post-mount repair engine that detects and fixes mismatched/damaged blocks in-place or via copy-replace.
- Integrates tightly with ShadowMountPlus: writes per-image sector and read-only hints, restarts SMP via Payload Manager if needed, and validates mounted images byte-for-byte against the original.

Why it matters
- Validates MkPFS assumptions on a real PS5: PFSC block sizing, nested image layouts, APR Emu flows, and ShadowMountPlus mount settings (sector/read-only) under console I/O and kernel behavior.
- The validation/repair pipeline and .vhash format provide a concrete, testable model for PFSC integrity at block granularity that we can mirror in MkPFS (for diagnostics, fuzz tests, and field support).
- The destructive in-place stream shows practical strategies for minimal free-space conversions; informs MkPFS docs on safe vs. destructive modes and expected budgeting.

Architecture and deep dive

PFSC container and outer layout
- PFSC constants: magic=0x43534650, headerSize=0x30, blockOffsets at 0x400, first data at 0x10000, block size=65536. Offsets table entries are 8 bytes each; header grows to fit (padded to 64 KiB).
  - Source: src/pfs_repair.c (PFSC_* defines), pfsc_header_span(), and src/pfs_compress.c constants.
- Game Compressor wraps the PFSC as a compressed file inside a fixed outer PFS with a minimal directory structure: superroot, flat_path_table, uroot, and the nested image file (usually pfs_image.dat or <title>.exfat).
  - Wrapper verification ensures inode flags/sizes and flat path table hash match the fixed layout before performing outer “slack” cleanup.
  - Source: pfs_repair.c → outer_verify_gamecompressor_wrapper(), outer_verify_fixed_wrapper_dirs().

Compression engine (PFSC writer)
- Streaming, windowed pipeline with parallel read/deflate/write tasks and bounded in-RAM window buffers:
  - Workers, permits, and lane sizing are tuned for 64 KiB blocks; defaults include PFSC_WINDOW_COMP_CHUNK_BLOCKS=8 and a large staged output buffer (up to ~16 MiB).
  - Defaults: zlib level GC_PFSC_ZLIB_LEVEL=7, minimum gain GC_PFSC_THRESHOLD_GAIN=5 (skip weakly compressible blocks), and force-raw for executables (GC_PFSC_FORCE_RAW_EXEC=1) to preserve behavior.
  - Scheduler predicts per-file gain and ordering; reverse streaming helpers support destructive mode.
  - Source: src/pfs_compress.c (pfsc_window_pool_t, pfsc_output_buffer, PFSC_WINDOW_* defines, GC_PFSC_* defaults).

Destructive in-place stream (low-free-space mode)
- Journaled mutation with rollback support while transforming a folder into a PFSC container on the same volume:
  - Journal header magic "GCSTRM2", versioned records, tracked credit/budget, and per-file reverse progress; maintains reserve bytes and computes current credit from deleted+committed work.
  - Reverse-ahead threads produce temporary reversed fragments to free space before committing final writes; reconciles and finalizes atomically per-file where possible.
  - Modes: safe keep/delete-after-verified vs destructive (only for same-storage, non-cancellable phase); budget and reserve defaults aim to minimize risk.
  - Source: src/pfs_compress.c (destructive_stream_*)

Validation hashes (.vhash sidecar)
- Separate .vhash file stores SHA‑256 per 64 KiB logical block with a small header describing PFSC logical size, nested size, block count, nested name, and nested type.
  - Header magic PFS_VHASH_MAGIC="PFSCVHS1"; algorithm ID = SHA‑256; nested name embedded for identity; reader validates freshness: used/stale/invalid/missing.
  - Source: src/pfs_validate_hash.c (writer/reader API, SHA‑256 implementation, header layout).

Repair engine (validate/repair)
- Opens the outer PFS, inspects the nested PFSC, and verifies the GameCompressor fixed wrapper; scans blocks comparing mounted reads vs software decode:
  - Uses tinfl (miniz) for software decompression when needed; cross-checks against the mounted device to identify bad blocks.
  - Maintains a scan journal (JOURNAL_MAGIC="PFSRJNL1") with block counts, PFSC header/table hashes, matched/mismatched counts, and progress; supports resume.
  - Repairs damaged PFSC offset table/data ranges, can operate in-place or copy-replace based on available space; zeros outer PFS slack regions for deterministic tail/dir padding.
  - Source: src/pfs_repair.c (pfsc_open/read/decode, journal_*, pfs_repair_ffpfsc_outer_slack()).

ShadowMountPlus integration
- Writes per-image mount hints and sector settings to ShadowMount config:
  - image_sector=<outer>.ffpfsc:65536 (PFSC outer device sector); image_ro=<nested>.exfat for APR Emu exFAT images; cleans per-title hints on refresh.
  - Can request manual scans, upsert manual.lst entries, and restart ShadowMountPlus via Payload Manager when needed.
  - Source: src/gc_shadowmount.c (upsert/remove hints, manual scan, restart logic).

Web UI and API surface
- Tiny HTTP server (default port 5910), serves a single-page app and a narrow JSON API; key endpoints include:
  - GET /api/status; POST /api/gc/{compress,make-image,uncompress,validate-repair,validate-only,read-speed-test}
  - POST /api/gc/{move-to-usb,move-to-internal,copy-to-usb,copy-to-internal,delete-game-data,build-ampr-index,update-ampr,restore-ampr-original}
  - POST /api/gc/{job/cancel,queue/cancel}; GET /api/gc/icon; control/handoff endpoints for launcher handoff/shutdown.
  - Source: src/gc_websrv.c routes; src/gc_api.h; handlers in src/gc_api.c.

APR Emu support
- Auto-builds ampr_emu.index for APR titles and applies SMP read-only + sector-size settings; exposes an APR-EMU version picker backed by a public manifest, with caching under /data/GameCompressor.
  - Source: README.md, src/ampr_index.c/h, HTML UI.

Power guard
- Keeps the console awake during long jobs by resetting power-down timers, pinging ShellCore user-activity hooks, and turning off screensaver if it triggers.
  - Source: src/gc_power_guard.c.

Key upstream files/pages
- README.md — Features, requirements, APR Emu workflows, usage.
- src/pfs_compress.c — PFSC writer, streaming window, destructive mode journal, zlib integration, scheduler.
- src/pfs_block_pipeline.c — Fixed-block buffer alloc/flush helpers used by the streaming pipeline.
- src/pfs_validate_hash.c — .vhash SHA‑256 sidecar writer/reader and header.
- src/pfs_repair.c — Mount-validated PFSC scan/repair, outer fixed-wrapper verification, slack cleanup, miniz decode.
- src/gc_shadowmount.c — ShadowMount hints (image_sector/image_ro), manual scan and restart.
- src/gc_websrv.c, src/gc_api.h — HTTP server and API routing.
- assets/game-compressor.html — Browser UI served from the payload.
- payload-manager/game-compressor.elf.json — Payload Manager metadata (checksum, name).

Notes / gotchas
- Default nested image is exFAT inside PFSC for broad compatibility; nested PFS is labeled “Experimental”.
- Destructive mode is restricted and unsafe once the mutation phase begins; prefer keep or delete-after-verified when space allows.
- APR Emu titles require ampr_emu.index and correct SMP read-only/sector settings for stable internal-SSD playback; GC automates these but pre-existing exFAT without index is a manual edge case.
- The .vhash identity must match logical size, nested size, block count, nested name/type; mismatches are treated as stale/invalid.

Source index
- https://github.com/juma-sayeh/PS5-Game-Compressor
- https://github.com/juma-sayeh/PS5-Game-Compressor/blob/main/src/pfs_compress.c
- https://github.com/juma-sayeh/PS5-Game-Compressor/blob/main/src/pfs_block_pipeline.c
- https://github.com/juma-sayeh/PS5-Game-Compressor/blob/main/src/pfs_repair.c
- https://github.com/juma-sayeh/PS5-Game-Compressor/blob/main/src/pfs_validate_hash.c
- https://github.com/juma-sayeh/PS5-Game-Compressor/blob/main/src/gc_shadowmount.c
- https://github.com/juma-sayeh/PS5-Game-Compressor/blob/main/src/gc_websrv.c
- https://github.com/juma-sayeh/PS5-Game-Compressor/blob/main/src/gc_api.h
- https://github.com/juma-sayeh/PS5-Game-Compressor/blob/main/assets/game-compressor.html
- https://github.com/juma-sayeh/PS5-Game-Compressor/blob/main/payload-manager/game-compressor.elf.json
