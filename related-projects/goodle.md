# goodle: OodleLZ Wrapper for Go

## Identity

- **Source:** [oriath-net/goodle](https://github.com/oriath-net/goodle)
- **Local artifact folder:** `related-projects/goodle`
- **Language:** Go (cgo)
- **License:** The Unlicense (public domain)
- **Indexed:** 2026-06-14
- **Default branch:** main

## Scope

This report covers the `goodle` repository, a small cgo-based shim that wraps the closed-source OodleLZ decompression library for use in Go programs. It is designed as a drop-in replacement for the `gooz` package.

## Executive Summary

`goodle` is a thin Go wrapper around the native OodleLZ decompression library (`OodleLZ_Decompress` C API). It exists to replace a pure-Go or mocked `gooz` implementation with actual calls to the proprietary Oodle shared library. The package name is `gooz` so it acts as a transparent substitute: users add a `replace` directive in their `go.mod` to swap in real Oodle decompression.

The repository contains exactly 2 source files (one per platform), a `go.mod`, a `COPYING` (Unlicense), and a `README.md`. There are no tests, no CI configuration, and no external Go dependencies beyond `golang.org/x/sys/windows` on Windows.

## Repository Structure

```
goodle/
  COPYING              # Unlicense (public domain)
  README.md            # Usage instructions
  go.mod               # Module: github.com/oriath-net/goodle, Go 1.19
  glue_unix.go         # Linux/macOS: cgo + liboo2core linking
  glue_windows.go      # Windows: runtime DLL loading via syscall
```

## Architecture and Implementation

### Package Declaration

Both files declare `package gooz`, making goodle a drop-in replacement for the original `gooz` package. Consumers use `go.mod` `replace` directives to swap them at build time.

### Shared API: `Decompress`

Both platforms expose the same function signature:

```go
func Decompress(in []byte, out []byte) (int, error)
```

**Behavior:**
1. Calls `OodleLZ_Decompress` with the input and output byte slices.
2. Output buffer length is significant to the decompressor (caller must know the decompressed size in advance).
3. Returns number of decompressed bytes on success.
4. Returns error if the native call returns a negative code or if the decompressed size does not match `len(out)`.

**Common parameters passed to `OodleLZ_Decompress`:**

| Parameter | Value | Meaning |
|---|---|---|
| fuzzSafe | 1 | `OodleLZ_FuzzSafe_Yes` |
| checkCRC | 1 | `OodleLZ_CheckCRC_Yes` |
| verbosity | 0 | `OodleLZ_Verbosity_None` |
| decBufBase | nil/0 | No external decode buffer |
| decBufSize | 0 | No external decode buffer |
| fpCallback | nil/0 | No callback |
| callbackUserData | nil/0 | No callback |
| decoderMemory | nil/0 | No external decoder memory |
| decoderMemorySize | 0 | No external decoder memory |
| threadPhase | 3 | `OodleLZ_Decode_ThreadPhaseAll` |

### Linux/macOS (`glue_unix.go`)

**Mechanism:** cgo with static link-time binding.

```go
// #cgo LDFLAGS: -loo2core
// #include <stdlib.h>
// int OodleLZ_Decompress(...);
import "C"
```

- Links against `-loo2core` at build time.
- The shared library must be named `liboo2core.so` (Linux) or `liboo2core.dylib` (macOS) and placed in a standard library search path (e.g., `/usr/local/lib`).
- Uses `unsafe.Pointer` to pass byte slice data to the C function.
- Error handling: negative return code becomes an error; size mismatch also becomes an error.

**Key constraint:** No `init()` function, no runtime library resolution. The library must be present at compile time and at runtime. No environment variable override on Unix.

### Windows (`glue_windows.go`)

**Mechanism:** Runtime DLL loading via `golang.org/x/sys/windows`.

```go
import "golang.org/x/sys/windows"
var oodleDLL *windows.DLL
```

**DLL resolution order (in `init()`):**
1. If `OODLE_DLL` environment variable is set, use that as the sole candidate path.
2. Otherwise probe these filenames in order:
   - `oo2core_9_win64.dll`
   - `oo2core_8_win64.dll`
   - `oo2core_7_win64.dll`
   - `oo2core_6_win64.dll`
   - `oo2core_5_win64.dll`
   - `oo2core_4_win64.dll`
   - `oo2core_3_win64.dll`
3. If none load, `log.Fatal` terminates the process.

**`Decompress` on Windows:**
- Looks up `OodleLZ_Decompress` via `oodleDLL.FindProc("OodleLZ_Decompress")` on every call.
- Panics if `FindProc` fails (should be impossible after successful `init()`).
- Calls the proc via `fn.Call(...)` with uintptr arguments.
- Same error handling as Unix: negative code or size mismatch.

**Key difference from Unix:** Windows uses runtime loading (no compile-time link dependency), but the DLL must be findable at program start (`init()`).

## OodleLZ API Reference (as consumed by goodle)

`goodle` calls only one Oodle function:

```
int OodleLZ_Decompress(
    const void *compBuf,       // compressed input
    size_t compBufSize,        // compressed input length
    void *rawBuf,              // decompression output buffer
    size_t rawLen,             // output buffer size (must match actual decompressed size)
    int fuzzSafe,              // 1 = yes
    int checkCRC,              // 1 = yes
    int verbosity,             // 0 = silent
    void *decBufBase,          // nil = internal
    size_t decBufSize,         // 0
    void *fpCallback,          // nil
    void *callbackUserData,    // nil
    void *decoderMemory,       // nil
    size_t decoderMemorySize,  // 0
    int threadPhase            // 3 = all threads
) -> int                       // bytes written, or negative on error
```

**Return value contract:**
- Positive: number of bytes decompressed into `rawBuf`.
- Negative: error code (Oodle-specific, not further decoded by goodle).
- goodle additionally enforces `r == len(out)` as a correctness check.

## Supported Oodle Versions

| Platform | Library name | Versions probed |
|---|---|---|
| Windows | `oo2core_N_win64.dll` | 3, 4, 5, 6, 7, 8, 9 |
| Linux | `liboo2core.so` | Any version linked at build time |
| macOS | `liboo2core.dylib` | Any version linked at build time |

The Oodle library itself is proprietary (by RAD Game Tools / Epic Games). Users must obtain their own copy. goodle does not bundle or redistribute it.

## Module Configuration

**go.mod:**
```
module github.com/oriath-net/goodle
go 1.19
```

- No external Go dependencies declared in go.mod (Windows build requires `golang.org/x/sys/windows` but it is not listed in go.mod).
- Go 1.19 minimum.
- No `go.sum` file present.

## Operational Notes

1. **Caller must know decompressed size.** The output buffer must be exactly the right size; Oodle does not return the decompressed size. goodle enforces this with a strict equality check.
2. **No partial decompression.** If the output buffer is too small or too large, the call fails.
3. **No streaming API.** Only full-buffer-to-full-buffer decompression is supported.
4. **No compression.** Only `OodleLZ_Decompress` is wrapped; `OodleLZ_Compress` is not exposed.
5. **Fuzz-safe and CRC-checked by default.** Both are hardcoded to 1 (enabled). No way to disable without modifying source.
6. **No error code interpretation.** Negative Oodle return codes are passed through as raw integers in the error string. The caller cannot distinguish specific Oodle errors.
7. **Windows `FindProc` called per invocation.** The proc handle is looked up on every `Decompress` call, not cached. This is a minor performance consideration.
8. **Windows fatal on missing DLL.** If the DLL is not found at init time, the process terminates with `log.Fatal`. There is no graceful fallback.

## Constraints and Caveats

- Oodle is closed-source and requires a commercial license from RAD Game Tools / Epic Games for redistribution.
- Unix platforms require the shared library at compile time (cgo link) and at runtime. No runtime discovery.
- No `go.sum` file means the Windows dependency on `golang.org/x/sys/windows` is unresolved in the module graph (may cause issues with `go mod tidy`).
- No tests or CI in the repository.
- The package name `gooz` in the source may confuse import paths when used alongside the original `gooz` package.
- 0 forks, 1 star, 3 commits total. Very low activity.

## Source Index

| File | Local path | Upstream |
|---|---|---|
| README.md | [local](../goodle/README.md) | [upstream](https://github.com/oriath-net/goodle/blob/main/README.md) |
| glue_unix.go | [local](../goodle/glue_unix.go) | [upstream](https://github.com/oriath-net/goodle/blob/main/glue_unix.go) |
| glue_windows.go | [local](../goodle/glue_windows.go) | [upstream](https://github.com/oriath-net/goodle/blob/main/glue_windows.go) |
| go.mod | [local](../goodle/go.mod) | [upstream](https://github.com/oriath-net/goodle/blob/main/go.mod) |
| COPYING | [local](../goodle/COPYING) | [upstream](https://github.com/oriath-net/goodle/blob/main/COPYING) |

## Reuse Checklist

- [ ] Obtain Oodle shared library (`liboo2core.so` / `liboo2core.dylib` / `oo2core_N_win64.dll`).
- [ ] Place library in standard path (Unix) or alongside executable / set `OODLE_DLL` (Windows).
- [ ] Add `replace github.com/someone/gooz => github.com/oriath-net/goodle` to consumer `go.mod`.
- [ ] Ensure caller knows exact decompressed size before calling `Decompress`.
- [ ] Handle negative return codes as opaque errors (no further classification available).
