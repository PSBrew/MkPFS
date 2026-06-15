# PS5-PKGs: Official PS5 Package Build Tools

## Identity

- **Source:** [DNNDHH/PS5-PKGs](https://github.com/DNNDHH/PS5-PKGs)
- **Local artifact folder:** `related-projects/ps5-pkgs`
- **Language:** C++ (samples), prebuilt Windows binaries
- **License:** None declared
- **Stars:** 54 | **Forks:** 8
- **Indexed:** 2026-06-14
- **Default branch:** main
- **Last push:** 2024-02-18

## Scope

This report covers the PS5-PKGs repository, a collection of official Sony Prospero (PS5) build tools and supporting DLLs for creating PS5 game packages. It is a redistribution of the SDK tooling rather than an open-source implementation.

## Executive Summary

PS5-PKGs provides the official Sony PS5 package creation pipeline as prebuilt Windows binaries. The core tools are `prospero-pub-cmd.exe` (CLI package builder), `prospero-pub-param.exe` (parameter editor), and the supporting `libScePubTools.dll` / `prospero-pub-wpf.dll` libraries. The repo also bundles WPF GUI framework DLLs (Prism, Unity container), a sample GP5 project, PS5 system module PRX files, a core dump utility, an API web browser sample, and external helper tools for texture compression and audio encoding.

The repository has no license declaration and no build system for the binaries themselves; it serves as a distribution point for tools extracted from the PS5 SDK.

## Repository Structure

```
PS5-PKGs/
  prospero-pub-cmd.exe          # CLI package creation tool (PS5 SDK)
  prospero-pub-param.exe        # Parameter editor tool (PS5 SDK)
  libScePubTools.dll            # Core Sony publishing tools library
  prospero-pub-wpf.dll          # WPF GUI for publishing tools
  Prism.dll                     # Prism MVVM framework (WPF dependency)
  Prism.Wpf.dll                 # Prism WPF extensions
  Prism.Unity.Wpf.dll           # Prism Unity container integration
  Unity.Abstractions.dll        # Unity DI container abstractions
  Unity.Container.dll           # Unity DI container implementation
  CommonServiceLocator.dll      # Service locator pattern support
  Microsoft.Expression.Interactions.dll  # Expression Blend interactions
  System.Windows.Interactivity.dll       # WPF interaction triggers
  Sample/
    PPSX40000.GP5               # Sample GP5 project file
    PackageFileCache/           # Package file cache directory
    img_create.bat              # Image creation batch script
  sce_module/
    libScePfs.prx               # PS5 PFS filesystem module
    libc.prx                    # PS5 C runtime
    libSceFace.prx              # Face recognition module
    libSceFaceTracker.prx       # Face tracking module
    libSceJobManager.prx        # Job manager module
    libSceJobManager_nosubmission.prx  # Job manager (no submission)
    libSceNpCppWebApi.prx       # NP C++ Web API module
  PS5_CoreDump/
    console_template.cpp        # Core dump console template (C++)
    console_template.h          # Core dump console header
  ps5_api_webbrowser/
    api_webbrowser_dialog.sln   # Visual Studio solution
    api_webbrowser_dialog.vcxproj  # VS project file
    main.cpp                    # Entry point
    webbrowser_dialog_menu.cpp  # Dialog menu implementation
    webbrowser_dialog_menu.h    # Dialog menu header
    application.h               # Application header
    screenshot.png              # Screenshot
  ext/
    sc2.exe                     # Scene compiler tool
    p2d.exe                     # Pixel-to-description tool
    ric.exe                     # Resource image compiler
    ispc_texcomp.dll            # ISPC texture compressor
    libatrac9.dll               # ATRAC9 audio codec library
  README.md                     # Minimal description + screenshot
```

## Key Components

### Package Build Tools (Prospero SDK)

- **`prospero-pub-cmd.exe`**: Command-line tool for creating PS5 `.pkg` files from GP5 project definitions. This is the primary package creation tool from the PS5 SDK (Prospero).
- **`prospero-pub-param.exe`**: Parameter editing tool for package metadata.
- **`libScePubTools.dll`**: Core library implementing the publishing toolchain.
- **`prospero-pub-wpf.dll`**: WPF-based GUI wrapper for the publishing tools.

### WPF GUI Dependencies

The repo bundles the full WPF framework dependency chain: Prism (MVVM framework), Unity (dependency injection), and Microsoft Expression interactions. These support the `prospero-pub-wpf.dll` GUI application.

### Sample Project

`Sample/PPSX40000.GP5` is a sample GP5 project file (PS5 game project format). `img_create.bat` demonstrates the image creation workflow. `PackageFileCache/` is a working directory for package building.

### PS5 System Modules (`sce_module/`)

Prebuilt PRX files (PS5 executable modules) including:
- `libScePfs.prx` - PFS filesystem implementation (directly relevant to mkpfs PFS exploration)
- `libc.prx` - PS5 C runtime library
- Other system service modules (face tracking, job manager, NP web API)

### External Helpers (`ext/`)

- `sc2.exe` - Scene compiler
- `p2d.exe` - Pixel-to-description converter
- `ric.exe` - Resource image compiler
- `ispc_texcomp.dll` - Intel ISPC texture compressor
- `libatrac9.dll` - Sony ATRAC9 audio codec

### PS5 API Web Browser Sample

A C++ Visual Studio project demonstrating the PS5 web browser API dialog, with full source (`.cpp`, `.h`, `.sln`, `.vcxproj`).

## Operational Notes

1. **Windows-only binaries.** All executables and DLLs are PE format (Windows x64). No Linux/macOS support.
2. **No license.** The repository declares no license. The tools are extracted from the proprietary Sony PS5 SDK and are likely redistributable only with appropriate SDK licensing.
3. **No build system.** The binaries are prebuilt; there is no CMake/Makefile for building the tools themselves.
4. **`libScePfs.prx`** is directly relevant to PFS image format investigation. This module implements the PS5 kernel's PFS filesystem and may contain format constants or behavior hints useful for mkpfs development.
5. **GP5 format** is the Sony game project file format that defines package contents, metadata, and build parameters for `prospero-pub-cmd.exe`.
6. **Minimal documentation.** The README contains only a title and a screenshot of the GUI tool.

## Constraints and Caveats

- Proprietary Sony SDK tools; redistribution rights unclear.
- No source code for the core tools (prebuilt binaries only).
- No license file in the repository.
- Repository is a point-in-time snapshot; last updated February 2024.
- 54 stars, 8 forks. Moderate community interest.
- No CI, no tests, no build automation.

## Source Index

| Item | Local path | Upstream |
|------|-----------|----------|
| README.md | [local](../ps5-pkgs/README.md) | [upstream](https://github.com/DNNDHH/PS5-PKGs/blob/main/README.md) |
| prospero-pub-cmd.exe | [local](../ps5-pkgs/prospero-pub-cmd.exe) | [upstream](https://github.com/DNNDHH/PS5-PKGs/blob/main/prospero-pub-cmd.exe) |
| libScePubTools.dll | [local](../ps5-pkgs/libScePubTools.dll) | [upstream](https://github.com/DNNDHH/PS5-PKGs/blob/main/libScePubTools.dll) |
| Sample/PPSX40000.GP5 | [local](../ps5-pkgs/Sample/PPSX40000.GP5) | [upstream](https://github.com/DNNDHH/PS5-PKGs/blob/main/Sample/PPSX40000.GP5) |
| sce_module/libScePfs.prx | [local](../ps5-pkgs/sce_module/libScePfs.prx) | [upstream](https://github.com/DNNDHH/PS5-PKGs/blob/main/sce_module/libScePfs.prx) |

## Relevance to mkpfs

- `libScePfs.prx` is a binary implementation of Sony's PFS filesystem that can be reverse-engineered for format insights.
- `prospero-pub-cmd.exe` and the GP5 sample show how Sony's official tooling structures packages, useful for understanding the packaging pipeline.
- The `ext/` tools (sc2, p2d, ric) are part of the asset pipeline that feeds into package creation.

---

*This document was generated by scanning the PS5-PKGs repository. For definitive content, cross-reference with the submodule at `related-projects/ps5-pkgs/`.*
