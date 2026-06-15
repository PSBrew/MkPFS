# PKG Passcode Finder -- Brute-Force PS5 PKG Passcode Recovery

- Canonical source: https://github.com/bobg-github/PS5PKGPasscodeFinder
- Local artifact folder: [related-projects/pkg-passcode-finder](pkg-passcode-finder)
- Indexed on: 2026-06-14
- Source type: git repository (VB.NET / WPF, .NET Framework 4.8)

## Executive Summary

PKG Passcode Finder is a Windows-only WPF application written in VB.NET that brute-forces the 31-character alphanumeric passcode required by Sony's `prospero-pub-cmd.exe` to extract PS5 `.pkg` files. It generates random passcodes, invokes the official SDK tool with each candidate, and checks the output for success. The approach is purely random with no heuristics; the alphabet is 62 characters at length 31, making the search space astronomically large (62^31). The tool is best understood as a proof-of-concept or last-resort recovery mechanism rather than a practical brute-force solution.

## Table of Contents

1. Scope and Identity
2. Project Structure
3. How It Works
4. Brute-Force Strategy
5. External Dependency
6. Key Constraints and Observations
7. Source Index

## Scope and Identity

This report covers the PKG Passcode Finder repository, a single-window WPF application:

- Window: `MainWindow` (XAML + code-behind)
- Entry: `Application.xaml` / `Application.xaml.vb`
- Project: `PS5PKGPasscodeFinder.vbproj`

## Project Structure

```text
related-projects/pkg-passcode-finder/
├── PS5PKGPasscodeFinder.sln             # Visual Studio solution
├── README.md
└── PS5PKGPasscodeFinder/
    ├── PS5PKGPasscodeFinder.vbproj      # .NET Framework 4.8, WPF
    ├── App.config
    ├── Application.xaml                 # WPF app definition
    ├── Application.xaml.vb
    ├── MainWindow.xaml                  # UI layout
    ├── MainWindow.xaml.vb               # Core logic (all in one file)
    └── My Project/
        ├── AssemblyInfo.vb
        ├── app.manifest
        ├── Resources.Designer.vb
        ├── Resources.resx
        ├── Settings.Designer.vb
        ├── Settings.settings
        └── MyExtensions/
            └── MyWpfExtension.vb
```

High-value files:

- [related-projects/pkg-passcode-finder/PS5PKGPasscodeFinder/MainWindow.xaml.vb](pkg-passcode-finder/PS5PKGPasscodeFinder/MainWindow.xaml.vb)
- [related-projects/pkg-passcode-finder/PS5PKGPasscodeFinder/MainWindow.xaml](pkg-passcode-finder/PS5PKGPasscodeFinder/MainWindow.xaml)
- [related-projects/pkg-passcode-finder/PS5PKGPasscodeFinder/PS5PKGPasscodeFinder.vbproj](pkg-passcode-finder/PS5PKGPasscodeFinder/PS5PKGPasscodeFinder.vbproj)

## How It Works

1. User selects a `.pkg` file via "Browse" button.
2. User selects an output directory via another "Browse" button.
3. Clicking "Start" launches a parallel brute-force loop.
4. Each worker generates a random 31-character passcode from the alphabet `A-Z a-z 0-9` (62 chars).
5. Each passcode is deduplicated via a `ConcurrentDictionary(Of String, Boolean)`.
6. For each candidate, the tool spawns `prospero-pub-cmd.exe img_extract --passcode <passcode> <pkg> <outdir>` as a child process.
7. Standard output is captured synchronously. If it does not contain `"[Error]"`, the passcode is declared found.
8. UI updates happen via `Dispatcher.Invoke` back to the WPF thread.

## Brute-Force Strategy

| Parameter | Value |
|-----------|-------|
| Alphabet | `ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789` |
| Length | 31 characters |
| Search space | 62^31 (approximately 1.8 x 10^55) |
| Strategy | Random with deduplication |
| Parallelism | `Environment.ProcessorCount * 2` threads |
| Shared RNG | Single `Random()` instance, synchronized via `SyncLock` |

The approach generates random passcodes and checks each against `prospero-pub-cmd.exe`. There is no dictionary, no partial-key optimization, and no GPU acceleration. The `ConcurrentDictionary` prevents retesting but does not enable systematic enumeration.

## External Dependency

The tool requires `prospero-pub-cmd.exe` from the PS5 SDK (Prospero) to be present in the working directory. It invokes:

```bash
prospero-pub-cmd.exe img_extract --passcode <PASSCODE> <PKG_PATH> <OUTPUT_PATH>
```

Success is determined by checking whether the process output contains the string `[Error]`.

## Key Constraints and Observations

1. **Impractical search space.** At 62^31 possible passcodes, random brute force is not feasible for any reasonable timeframe. The tool would need the passcode to be extremely short or constrained to work.
2. **Windows-only.** Requires .NET Framework 4.8 and WPF. No cross-platform support.
3. **GUI-only.** No CLI interface. All interaction through the WPF window.
4. **Synchronous process execution.** Each passcode attempt blocks on `ReadToEnd()` + `WaitForExit()`, making the parallelism partially serialized per invocation.
5. **Thread safety concern.** `PasscodeFound` is checked and set without `Volatile.Read`/`Interlocked` operations across threads, though in practice the worst case is a few extra attempts after a find.
6. **No progress persistence.** Tested passcodes are stored in memory only; restarting loses all progress.
7. **No result output.** When a passcode is found, a `MsgBox` displays but the passcode value is not written to a file or the UI text boxes.
8. **The tool depends on Sony's `prospero-pub-cmd.exe`** being available, which is part of the proprietary PS5 SDK.

## Source Index

Core sources:

- [related-projects/pkg-passcode-finder/PS5PKGPasscodeFinder/MainWindow.xaml.vb](pkg-passcode-finder/PS5PKGPasscodeFinder/MainWindow.xaml.vb) -- all application logic
- [related-projects/pkg-passcode-finder/PS5PKGPasscodeFinder/MainWindow.xaml](pkg-passcode-finder/PS5PKGPasscodeFinder/MainWindow.xaml) -- UI layout
- [related-projects/pkg-passcode-finder/PS5PKGPasscodeFinder/PS5PKGPasscodeFinder.vbproj](pkg-passcode-finder/PS5PKGPasscodeFinder/PS5PKGPasscodeFinder.vbproj) -- project file (.NET 4.8)

Upstream references:

- https://github.com/bobg-github/PS5PKGPasscodeFinder

## Relevance to mkpfs

- Demonstrates the role of the passcode in PKG extraction: it is required by `prospero-pub-cmd.exe img_extract` and controls whether decryption succeeds.
- Confirms that the passcode is a 31-character alphanumeric string, consistent with what LibOrbisPkg and the LibOrbisPkg wiki document.
- The dependency on `prospero-pub-cmd.exe` for extraction underscores the value of open-source alternatives like mkpfs that do not require the official SDK.
- The tool's approach (spawn external process, check output for errors) shows how end-users interact with PKG extraction workflows today.

---

*This document was generated by scanning the PS5PKGPasscodeFinder repository. For definitive content, cross-reference with the submodule at `related-projects/pkg-passcode-finder/`.*
