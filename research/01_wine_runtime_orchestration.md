# Research Report: Wine Runtime Orchestration and Process Lifecycle

**Project:** Zyntrix Compatibility Fabric (ZCF)  
**Document:** `research/01_wine_runtime_orchestration.md`  
**Target:** Wine (WineHQ upstream source tree)  
**Auditor:** Antigravity Autonomous Engineering Agent  
**Methodology:** Direct Source Code Inspection + REA Binary Static Analysis  

---

## 1. Research Objective

Investigate how Wine bridges the Windows Win32/Win64 execution model onto POSIX/Linux hosts, focusing on:
1. Binary loading and format detection.
2. The role and lifecycle of `wineserver`.
3. Prefix isolation and registry management.
4. Diagnostic signal emission (`WINEDEBUG`).

---

## 2. Source-Level Findings

### 2.1 Binary Ingestion and PE Loader
In Wine, PE executables are not loaded by the Linux kernel's `execve` (unless registered with `binfmt_misc`). Instead, Wine acts as a userspace loader:
- When running `wine app.exe`, the Wine preloader (`wine-preloader` or `wine64-preloader`) initializes address space layout, reserving low memory (0x00000000 - 0x00010000) for 16/32-bit DOS/Win16 compatibility if enabled.
- The preloader then invokes `ntdll.so`, which reads the PE headers, parses sections (`.text`, `.data`, `.rdata`), maps pages with appropriate memory protections (`PROT_READ`, `PROT_WRITE`, `PROT_EXEC`), and resolves import directory entries (`IMAGE_IMPORT_DESCRIPTOR`).

### 2.2 The Wine Server (`wineserver`)
Unlike native Linux where synchronization and IPC are kernel-managed, Windows synchronization primitives (`HANDLE`, `CRITICAL_SECTION`, `Event`, `Mutex`, `Semaphore`) have no 1:1 kernel equivalent in Linux:
- `wineserver` is a dedicated daemon process launched per `WINEPREFIX`.
- Processes communicate with `wineserver` over a UNIX domain socket (`/tmp/.wine-<uid>/server-<dev>-<ino>/socket`).
- File handles, process IDs, thread IDs, and security descriptors are translated by `wineserver`.
- **Architectural implication for ZCF:** Multiple applications sharing a prefix share a single `wineserver`. Crashes or deadlocks in one application can corrupt the wineserver state. Therefore, ZCF must enforce **prefix isolation** per application.

### 2.3 Prefix Directory Layout (`WINEPREFIX`)
A Wine prefix is a self-contained directory tree containing:
- `dosdevices/`: Symlinks mapping Windows drive letters to host filesystem paths (`c:` -> `drive_c`, `z:` -> `/`).
- `drive_c/`: Windows directory hierarchy (`windows/system32`, `Program Files`, `ProgramData`).
- `system.reg`, `user.reg`, `userdef.reg`: Text-based representations of the Windows Registry hives (`HKEY_LOCAL_MACHINE`, `HKEY_CURRENT_USER`).

### 2.4 Diagnostic Channels (`WINEDEBUG`)
Wine provides a granular trace channel mechanism controlled by the `WINEDEBUG` environment variable:
- Syntax: `WINEDEBUG=[+|-]channel,...`
- Critical channels for diagnostic capture:
  - `+relay`: Logs every call across DLL boundaries with function parameters and return values.
  - `+module`: Logs DLL loading, failure to find DLLs, and export resolution failures.
  - `+seh`: Logs structured exception handling events (access violations, null pointer dereferences).
  - `+loaddll`: Logs each DLL as it is mapped into memory.

---

## 3. Extracted ZCF Engineering Patterns

1. **Deterministic Prefix Provisioning:** ZCF's `WineAdapter` must generate isolated prefixes (`~/.zcf/prefixes/<app_sha256>`) using template prefixes to minimize disk consumption while guaranteeing process isolation.
2. **Automated Diagnostic Logging:** When an application fails, ZCF automatically re-executes with `WINEDEBUG=+module,+seh` into a dedicated diagnostic pipe, feeding output to ZCF's `DiagnosticEngine`.
3. **PE Inspection Prior to Invocation:** By using REA's safe artifact graph provider (`inspect_artifact`) before launching Wine, ZCF pre-scans for missing native DLL dependencies, warning the user before invocation begins.
