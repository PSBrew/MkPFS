# Oodle/Kraken Decompression Tools

Open-source tools for decompressing Oodle-compressed data (Kraken, Mermaid, Selkie, Leviathan codecs).

## oozextract (Rust)

- **URL**: https://github.com/lvlvllvlvllvlvl/oozextract
- **Language**: Rust
- **Stars**: Low but comprehensive
- **Description**: Open source Kraken / Mermaid / Selkie / Leviathan / LZNA / Bitknit decompressor
- **Status**: "probably fuzz safe, you can trust the input if you like"
- **API**: `Extractor` struct with `read_from_stream` and synchronous `read` methods
- **Build**: `cargo build --release --features cli` produces `unoodle` CLI binary
- **Crate**: Builds as `cdylib` (shared library) and `rlib` (static lib)
- **Location**: `tmp/exploration-ppr-pfs/oozextract/`

## goode (Go)

- **URL**: https://github.com/oriath-net/goodle
- **Language**: Go
- **Description**: Go bindings for ooDecompress from RAD Game Tools' Oodle SDK
- **Note**: Users must supply their own `liboo2core.so` shared library

## liboo2core (Oodle SDK shared library)

- **URL**: https://github.com/Fortniteleakjp/oo2core_9_Linux
- **Language**: Native (precompiled .so)
- **Description**: Precompiled `liboo2corelinux64.so.9` for Linux x86_64
- **API**: C functions exposed:
  - `OO_SINTa OodleLZ_Decompress(const void* compBuf, OO_SINTa compBufSize, void* rawBuf, OO_SINTa rawBufSize, ...)`
  - `OO_SINTa OodleLZ_Compress(OodleLZ_Compressor compressor, const void* rawBuf, OO_SINTa rawLen, void* compBuf, OodleLZ_CompressionLevel level, ...)`
  - `const char* OodleLZ_Compressor_GetName(OodleLZ_Compressor compressor)`
- **Compressor IDs**: Kraken=8, Mermaid=9, Selkie=10, Leviathan=12
- **Note**: Linux only. macOS requires cross-compilation or a different source.

## Oodle Compression Format Notes

- **Chunk size**: 128 KiB input chunks compressed independently
- **Block sizes**: 64 KiB to 512 KiB (configurable)
- **Entropy coding**: Huffman, ANS (Asymmetric Numeral Systems), or raw
- **Signature**: Oodle streams typically start with a header byte; 0x8C is a common indicator
- **Detection**: No single magic bytes; look for 0x8C/0x0A prefix patterns or high entropy (~7.0-7.5)
- **Reference**: https://fgiesen.wordpress.com/2021/07/09/entropy-coding-in-oodle-data-the-big-picture/
