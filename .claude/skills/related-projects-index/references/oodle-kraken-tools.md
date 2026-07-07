# Oodle/Kraken Decompression Tools — Reference

Open-source tools and shims for decompressing Oodle-compressed data (Kraken, Mermaid, Selkie, Leviathan, and related codecs).

Upstreams
- oozextract (Rust): https://github.com/lvlvllvlvllvlvl/oozextract
- goodle (Go Oodle shim): https://github.com/oriath-net/goodle
- liboo2core (prebuilt Linux .so): https://github.com/Fortniteleakjp/oo2core_9_Linux
- Format/codec background: https://fgiesen.wordpress.com/2021/07/09/entropy-coding-in-oodle-data-the-big-picture/

Local sandbox locations
- oozextract: tmp/exploration-ppr-pfs/oozextract/ (if present)

## Executive summary
- Practical options for Oodle decompression: a pure‑Rust decoder stack covering multiple codecs; a thin Go shim that calls the official Oodle SDK; and third‑party prebuilt vendor libraries for Linux.
- Coverage spans Kraken, Mermaid, Selkie, Leviathan (often also LZNA and Bitknit) and offers both CLI and library usage.
- Useful for validating per‑block Oodle decompression in asset archives and tooling adjacent to PFS workflows.

## Why it matters
- MkPFS and adjacent tools frequently encounter Oodle‑compressed payloads. These projects enable cross‑validation and testing without relying exclusively on proprietary SDKs, and provide a fallback when SDKs are unavailable.

## oozextract (Rust)
- URL: https://github.com/lvlvllvlvllvlvl/oozextract
- Language: Rust
- Stars: Low but comprehensive coverage
- Description: Open source Kraken / Mermaid / Selkie / Leviathan / LZNA / Bitknit decompressor
- Status: "probably fuzz safe, you can trust the input if you like"
- API: `Extractor` struct with `read_from_stream` and synchronous `read` methods
- Build: `cargo build --release --features cli` produces `unoodle` CLI binary
- Crate types: builds as `cdylib` (shared library) and `rlib` (static lib)

## goodle (Go)
- URL: https://github.com/oriath-net/goodle
- Language: Go
- Description: Go bindings/shim for `OodleLZ_Decompress` from RAD Game Tools' Oodle SDK; drop‑in replacement for `gooz`.
- Note: Users must supply their own Oodle shared library. Windows: `oo2core_N_win64.dll` (prefers v9, probes 3–9, `OODLE_DLL` override). Linux/macOS: `liboo2core.so`/`.dylib` in standard library paths.
- API: `Decompress(in []byte, out []byte) (int, error)` — caller must know exact decompressed size.

## liboo2core (Oodle SDK shared library)
- URL: https://github.com/Fortniteleakjp/oo2core_9_Linux
- Language: Native (precompiled .so)
- Description: Precompiled `liboo2corelinux64.so.9` for Linux x86_64
- API (as exposed by Oodle SDK):
  - `OO_SINTa OodleLZ_Decompress(const void* compBuf, OO_SINTa compBufSize, void* rawBuf, OO_SINTa rawBufSize, ...)`
  - `OO_SINTa OodleLZ_Compress(OodleLZ_Compressor compressor, const void* rawBuf, OO_SINTa rawLen, void* compBuf, OodleLZ_CompressionLevel level, ...)`
  - `const char* OodleLZ_Compressor_GetName(OodleLZ_Compressor compressor)`
- Compressor IDs: Kraken=8, Mermaid=9, Selkie=10, Leviathan=12
- Note: Proprietary; Linux only in this repo. macOS requires different sources or cross‑compilation.

## Oodle compression format notes
- Chunk size: Often 128 KiB input chunks compressed independently
- Block sizes: Commonly 64–512 KiB (configurable by producer)
- Entropy coding: Huffman, ANS (Asymmetric Numeral Systems), or raw
- Signature/prefix: No fixed magic; 0x8C (and sometimes 0x0A) seen as common lead bytes, but not definitive
- Detection: No single magic; heuristic signals include 0x8C/0x0A prefix and high entropy (~7.0–7.5 bits/byte)
- Reference: Fabian Giesen, "Entropy coding in Oodle Data — the big picture"

## Notes / gotchas
- Proprietary SDK: Official Oodle libraries are closed‑source; redistribution may be restricted. Validate licensing before use.
- Platform differences: Windows frequently uses runtime DLL loading; Linux/macOS depend on system library search paths.
- Security/safety: Open decoders may not perfectly match vendor edge‑cases; test against ground‑truth where possible.

## Source index (upstream)
- oozextract: https://github.com/lvlvllvlvllvlvl/oozextract
- goodle: https://github.com/oriath-net/goodle
- Prebuilt Linux liboo2core: https://github.com/Fortniteleakjp/oo2core_9_Linux
- Codec background (Giesen): https://fgiesen.wordpress.com/2021/07/09/entropy-coding-in-oodle-data-the-big-picture/