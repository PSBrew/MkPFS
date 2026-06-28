# PS5 Game Compressor — Reference

Upstream: https://github.com/juma-sayeh/PS5-Game-Compressor

Executive summary
- Standalone PS5 payload with a built-in web UI to compress, unpack, validate, repair, and move ShadowMountPlus-mounted games.
- Default output is a compressed FF-PFSC container wrapping an exFAT image; optional nested PFS image is available for testing.
- Integrates APR Emu support: builds/refreshes ampr_emu.index and applies ShadowMountPlus read-only + sector-size settings when needed.
- Headless-safe jobs: long operations continue on-console if the browser tab closes; progress, ETA, and history are tracked.
- Requires ShadowMountPlus and kstuff-lite (>= 1.07 Beta) on a PS5 homebrew environment; deploys as game-compressor.elf.

Why it matters
- Complements MkPFS by enabling on-console conversion/validation/repair without a PC, exercising the same PFSC format assumptions in a real PS5 environment.
- Provides a field workflow to validate and repair PFSC block issues, useful for stress-testing PFSC produced by tools like MkPFS.
- APR Emu integration keeps ampr_emu.index consistent for APR titles and demonstrates ShadowMountPlus setting requirements for internal SSD usage.

Key upstream files/pages
- README.md — Overview, features, requirements, usage, and APR Emu integration notes.
- src/pfs_compress.c — PFSC writer path for nested image compression.
- src/pfs_repair.c — PFSC repair routines for detected block issues.
- src/pfs_decompress.c — Unpack path for compressed images.
- src/pfs_validate_hash.c — Validation and integrity checks.
- src/gc_shadowmount.c — ShadowMountPlus integration and mount orchestration.
- src/pfs_block_pipeline.c — Block I/O and compression pipeline helpers.
- src/gc_websrv.c — Minimal web server and job orchestration on PS5.
- assets/game-compressor.html — Browser UI served by the payload.
- payload-manager/game-compressor.elf.json — Payload Manager metadata (checksum, display info).
- Makefile — Build rules; uses PS5 payload SDK via PS5_PAYLOAD_SDK env var.

Notes / gotchas
- "PFS Experimental" nested-image option is available but the default and recommended path is nested exFAT inside FF-PFSC for compatibility.
- Destructive compression mode is risky and constrained to same-storage folder compression; otherwise defaults to safer keep/delete-after-verified flows.
- Not a reusable library; it is a PS5-side payload intended for environments with ShadowMountPlus and kstuff-lite.

Source index
- https://github.com/juma-sayeh/PS5-Game-Compressor
- https://github.com/juma-sayeh/PS5-Game-Compressor/blob/main/src/pfs_compress.c
- https://github.com/juma-sayeh/PS5-Game-Compressor/blob/main/src/pfs_repair.c
- https://github.com/juma-sayeh/PS5-Game-Compressor/blob/main/src/pfs_decompress.c
- https://github.com/juma-sayeh/PS5-Game-Compressor/blob/main/src/pfs_validate_hash.c
- https://github.com/juma-sayeh/PS5-Game-Compressor/blob/main/src/gc_shadowmount.c
- https://github.com/juma-sayeh/PS5-Game-Compressor/blob/main/src/pfs_block_pipeline.c
- https://github.com/juma-sayeh/PS5-Game-Compressor/blob/main/src/gc_websrv.c
- https://github.com/juma-sayeh/PS5-Game-Compressor/blob/main/assets/game-compressor.html
- https://github.com/juma-sayeh/PS5-Game-Compressor/blob/main/payload-manager/game-compressor.elf.json
