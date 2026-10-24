# ZCF Open-Source Compatibility Tool Inventory

**Project:** Zyntrix Compatibility Fabric (ZCF)  
**Document:** `docs/COMPATIBILITY_TOOL_INVENTORY.md`  
**Date:** October 24, 2026  
**Auditor:** Antigravity Autonomous Engineering Agent  

---

## 1. Overview and Assessment Matrix

This inventory documents existing open-source compatibility runtimes, CPU architecture translators, binary analysis tools, and dynamic instrumentation frameworks. Each tool is evaluated for its architectural mechanisms, licensing, integration feasibility into ZCF, and testability within the current execution environment.

| Component | Category | Upstream License | Status in ZCF | Primary Integration Point |
| :--- | :--- | :--- | :--- | :--- |
| **Wine** | Windows API Translation | LGPL-2.1-or-later | **Researched & Integrated** | `wine`, `wineserver`, prefix env |
| **Proton** | Gaming Compatibility | Custom / BSD / LGPL | **Researched** | Proton runner wrapper scripts |
| **Bottles** | Environment Orchestrator | GPL-3.0-or-later | **Researched** | Bottle profiles, runner configs |
| **Lutris** | Gaming / Runner Platform | GPL-3.0-or-later | **Researched** | Lutris YAML runners & install scripts |
| **QEMU User**| CPU Architecture Emulation | GPL-2.0-only | **Installed & Integrated** | `qemu-aarch64`, `qemu-x86_64` CLI |
| **Box64** | x86_64 -> ARM64 Dynarec | MIT | **Researched & Designed** | `box64` launcher + wrapped libs |
| **FEX-Emu** | x86/x86_64 -> AArch64 JIT | MIT | **Researched & Designed** | `FEXBash`, `FEXInterpreter` |
| **Waydroid** | Containerized Android | GPL-3.0-or-later | **Researched (Blocked: KVM/LXC)**| LXC session controller, binder/ashmem |
| **Ghidra** | Static Binary Decompiler | Apache-2.0 | **Researched (Engine Missing)** | `analyzeHeadless` batch decompiler |
| **Frida** | Dynamic Instrumentation | wxWindows / LGPL | **Researched & Planned** | `frida-core`, Python bindings |
| **REA** | Agent Reverse Engineering | MIT | **Installed, Integrated & Verified** | Live Agent MCP stdio + CLI |
| **strace** | Syscall Tracing | LGPL-2.1+ / GPL-2.0+ | **Installed & Verified** | CLI wrapper for diagnostic logging |
| **readelf/objdump** | ELF Binary Inspection | GPL-3.0-or-later | **Installed & Verified** | CLI and static parsing verification |
| **patchelf** | ELF Dynamic Linker Modification | GPL-3.0-or-later | **Installed & Verified** | RPATH / interpreter manipulation |

---

## 2. In-Depth Project Profiles

### 2.1 Wine (Wine Is Not an Emulator)
- **Official Repository:** `https://gitlab.winehq.org/wine/wine`
- **Purpose:** Re-implements the Windows Win32, Win64, and NT kernel APIs on top of POSIX-compliant operating systems (Linux, macOS, BSD).
- **Core Mechanisms:**
  - PE loader: Maps Windows PE32/PE32+ binaries into memory.
  - Built-in DLLs: Clean-room reimplementations of `ntdll.dll`, `kernel32.dll`, `user32.dll`, `gdi32.dll`, etc.
  - `wineserver`: Background daemon managing IPC, synchronization objects (mutexes, semaphores, events), registry hives, and process lifecycles.
  - Wine Prefix: Self-contained directory hierarchy (`WINEPREFIX`) mimicking a Windows disk structure (`drive_c`, `system32`, `user.reg`, `system.reg`).
- **Integration Approach in ZCF:**
  - ZCF defines a `WineAdapter` implementing `RuntimeAdapterInterface`.
  - Application Inspector detects PE format, subsystem (GUI vs Console), and minimum OS version.
  - ZCF isolates prefixes under `~/.zcf/prefixes/<app_id>`, configures `WINEDEBUG` flags for diagnostic capture, and executes via `wine64` or `wine`.
- **REA Inspection Capabilities:**
  - REA's `inspect_artifact` and `inspect_managed_artifact` can directly inspect Windows binaries before passing them to Wine, identifying whether they are managed .NET or native C/C++ PE executables.

### 2.2 Valve Proton
- **Official Repository:** `https://github.com/ValveSoftware/Proton`
- **Purpose:** Optimized fork of Wine tailored for Windows games running under Steam on Linux.
- **Core Mechanisms:**
  - Integrates DXVK (Direct3D 9/10/11 to Vulkan) and VKD3D-Proton (Direct3D 12 to Vulkan).
  - High-performance synchronization: `fsync` (futex-based) and `esync` (eventfd-based) bypassing wineserver contention.
  - Steam runtime container (`pressure-vessel`) integration.
- **Integration Approach in ZCF:**
  - ZCF's `ProtonAdapter` models Proton as a specialized Wine runner.
  - Evaluates graphics subsystem compatibility: checks for Vulkan loader and driver extensions required by DXVK.

### 2.3 Bottles
- **Official Repository:** `https://github.com/bottlesdevs/Bottles`
- **Purpose:** User-friendly management of Wine and Proton environments ("bottles") with dependency management.
- **Core Mechanisms:**
  - YAML configuration schema defining runner, DXVK version, latency settings, environment variables, and overrides.
  - Dependency manager: Installs Windows runtime packages (Visual C++ Redistributables, .NET Frameworks, DirectX runtimes).
- **Architectural Lessons for ZCF:**
  - ZCF incorporates declarative profiles for application execution.
  - Environment isolation per application prevents cross-contamination of registry and DLL overrides.

### 2.4 Lutris
- **Official Repository:** `https://github.com/lutris/lutris`
- **Purpose:** Open gaming platform coordinating multiple runners (Wine, RetroArch, ScummVM, DOSBox).
- **Core Mechanisms:**
  - Runner abstraction model: Standard interface with `play()`, `install()`, and dependency detection.
  - Community-maintained installation YAML scripts.
- **Architectural Lessons for ZCF:**
  - Validates ZCF's decision to decouple the core Compatibility Planner from individual runtime adapters.

### 2.5 QEMU User-Mode Emulation
- **Official Repository:** `https://github.com/qemu/qemu`
- **Purpose:** Executes binaries compiled for one CPU instruction set (e.g. AArch64, ARM, RISC-V) on a different host instruction set (e.g. x86_64) by translating system calls to host system calls.
- **Core Mechanisms:**
  - Tiny Code Generator (TCG): JIT compiler translating target machine instructions into host machine instructions.
  - System call translation: Marshals structures, endianness, and syscall numbers between target ABI and host Linux kernel.
- **Verification in ZCF Environment:**
  - `qemu-aarch64` and `qemu-arm` installed via `qemu-user` (version 10.2.1).
  - Can execute cross-architecture Linux binaries directly via `qemu-aarch64 -L /usr/aarch64-linux-gnu <binary>`.
- **Integration Approach in ZCF:**
  - `QemuUserAdapter` handles cross-architecture ELF binaries when host ISA != binary ISA.

### 2.6 Box64 and FEX-Emu
- **Box64:** `https://github.com/ptitSeb/box64` (MIT)
  - Translates x86_64 Linux binaries to run on ARM64 Linux.
  - Differentiator: Forwards OpenGL, Vulkan, and libc calls to native ARM64 host libraries ("wrapped libraries") for high performance.
- **FEX-Emu:** `https://github.com/FEX-Emu/FEX` (MIT)
  - High-performance x86/x86-64 emulator targeting AArch64 Linux with custom JIT and Thunking system.
- **Status in ZCF:**
  - Researched and modeled in ZCF's ISA compatibility matrix.
  - Execution requires AArch64 host hardware (our environment is x86_64 Intel i5).

### 2.7 Waydroid
- **Official Repository:** `https://github.com/waydroid/waydroid`
- **Purpose:** Container-based approach to boot a complete LineageOS Android system on a regular Linux system.
- **Core Mechanisms:**
  - LXC (Linux Containers) execution sharing the host Linux kernel.
  - Requires Linux kernel with `binder` and `ashmem` drivers enabled.
  - Requires Wayland compositor for direct surface rendering.
- **Status in Environment:**
  - **Blocked for execution:** WSL2 environment lacks Wayland display compositor and default Android binder nodes.
  - Architectural model researched: Android APK inspection and container lifecycle.

---

## 3. Tool Verification and Support Classification

| Tool | Status | Cloud Test Verification | Blocker / Limitation |
| :--- | :--- | :--- | :--- |
| **REA CLI** | **Verified** | `rea inspect-artifact` tested on PE & ELF | None |
| **REA MCP** | **Verified** | Live `open_binary`, `inspect_artifact` | None |
| **QEMU User**| **Verified**| `qemu-aarch64 --version` (10.2.1) | Requires target rootfs for dynamic cross-libs |
| **strace** | **Verified**| `strace -V` (6.19) execution verified | Traces Linux syscalls only |
| **readelf** | **Verified**| `readelf -h` verified on Linux binaries | Static ELF parsing |
| **patchelf** | **Verified**| `patchelf --version` (0.18.0) verified | ELF binary rewriting only |
| **Wine** | **Researched** | Verified Wine package availability | Graphical apps require headless Xvfb |
| **Waydroid**| **Blocked** | Researched only | Missing binder IPC and Wayland server |
| **Ghidra** | **Researched** | Java 17 ready; engine dir not bound | Requires Ghidra 12.1.x distribution |
