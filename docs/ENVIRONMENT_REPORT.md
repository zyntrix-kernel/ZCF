# ZCF Environment and Host Diagnostic Report

**Project:** Zyntrix Compatibility Fabric (ZCF)  
**Document:** `docs/ENVIRONMENT_REPORT.md`  
**Date of Audit:** October 24, 2026  
**Auditor:** Antigravity Autonomous Engineering Agent  
**Environment Classification:** Dual Host/Guest Hybrid (Windows 11 Pro Host + WSL2 Ubuntu 26.04 LTS)

---

## 1. Executive Summary

An exhaustive diagnostic audit was conducted across the execution environment to assess available operating systems, architectures, resource constraints, developer toolchains, container/virtualization capabilities, and compatibility infrastructure. 

The environment operates as a high-performance hybrid configuration:
1. **Primary Host:** Microsoft Windows 11 Pro (10.0.26300) x86_64 running PowerShell and native developer toolchains.
2. **Integrated Linux Subsystem:** Canonical Ubuntu 26.04 LTS (Resolute Raccoon) running under WSL2 on Linux kernel `6.18.33.1-microsoft-standard-WSL2`, featuring passwordless `sudo`, `apt` package management, and direct cross-filesystem bridging via `/mnt/c/`.

Internet access is unrestricted, enabling official package downloads, git cloning, and live registry resolution (`pypi.org`, `registry.npmjs.org`, `github.com`). Node.js 24, Python 3.14, Rust/Cargo 1.98, and modern binary inspection utilities are fully verified.

---

## 2. Hardware and Operating System Specifications

### 2.1 Hardware Architecture
- **CPU:** Intel(R) Core(TM) i5-14400F
  - Total Cores / Threads: 16 logical CPUs (10 physical cores / 16 threads)
  - Microarchitecture: x86_64 Little Endian (39-bit physical, 48-bit virtual address sizes)
  - BogoMIPS: ~4991.99
- **Memory Allocation:**
  - Linux Guest (WSL2): 7.7 GiB total, 6.9 GiB available, 2.0 GiB swap
  - Windows Host: Adequate physical memory supporting multi-gigabyte builds
- **Storage and Filesystem Layout:**
  - C: Drive: 45.9 GB free of 208.9 GB total
  - D: Drive: 119.5 GB free of 119.5 GB total
  - F: Drive: 706.1 GB free of 706.1 GB total
  - WSL2 Virtual Disk (`/dev/sdd`): 947 GB available of 1007 GB (1% utilization)
  - Active Workspace: `C:\Users\USER\Desktop\Zyntrix\Zyntrix OS\ZCF` (mapped in WSL as `/mnt/c/Users/USER/Desktop/Zyntrix/Zyntrix OS/ZCF`)

### 2.2 Operating System Details
- **Windows Host:**
  - OS Name: Microsoft Windows 11 Pro
  - OS Version: 10.0.26300 (Build 2009 / 26300)
  - Shell: PowerShell 5.1 / PowerShell Core
- **Linux Subsystem (WSL2):**
  - Distribution: Ubuntu 26.04 LTS (Resolute Raccoon)
  - Kernel: `Linux zyntrix 6.18.33.1-microsoft-standard-WSL2 #1 SMP PREEMPT_DYNAMIC Fri Jun 5 01:12:21 UTC 2026 x86_64`
  - Privilege Level: Non-root user with passwordless `sudo` escalation (`sudo -n true` verified: exit code 0)
  - Package Management: `apt` (version 2.9+, Resolute release repositories functional)

---

## 3. Toolchain and Developer Ecosystem

| Component | Windows Host Version | Linux (WSL2) Version | Verification Status |
| :--- | :--- | :--- | :--- |
| **Node.js** | v24.18.0 | Available via nvm/apt | **Verified Active** |
| **npm** | 11.16.0 | 11.16.0 (bridged) | **Verified Active** |
| **Python** | 3.14.6 (64-bit) | 3.14.4 (64-bit) | **Verified Active** |
| **Rust / Cargo**| 1.98.1 | Available | **Verified Active** |
| **Git** | 2.55.0.windows.3 | 2.55.0 | **Verified Active** |
| **Java / JDK** | OpenJDK 17.0.20.1 Hotspot | Available via apt | **Verified Active** |
| **curl** | 8.18.0 | 8.18.0 OpenSSL 3.5.5 | **Verified Active** |
| **strace** | N/A | 6.19+ds-0ubuntu5 | **Installed & Verified** |
| **file** | N/A | 5.45 | **Verified Active** |
| **readelf** | N/A | GNU readelf 2.44 | **Verified Active** |
| **objdump** | N/A | GNU objdump 2.44 | **Verified Active** |
| **patchelf** | N/A | 0.18.0 | **Verified Active** |
| **QEMU User** | N/A | 1:10.2.1+ds-1ubuntu3.3 | **Installed & Configured** |

---

## 4. Reverse Engineering and Dynamic Analysis Infrastructure

### 4.1 REA (Reverse Engineer Anything)
- **Package:** `rea-agents@6.7.0` (MIT License, maintained by morluto)
- **Local Source Checkout:** Cloned at `research/targets/rea` (Commit tree verified)
- **Integration Status:**
  - Registration configured in `C:\Users\USER\.gemini\config\mcp_config.json`
  - REA Agent Skill installed in `C:\Users\USER\.gemini\config\skills\reverse-engineer-anything` (Skill Version 42, 207 MCP tools cataloged)
  - **Live MCP Connection Verified:** Successfully executed `open_binary`, `inspect_artifact`, and `close_binary` through direct Agent Model Context Protocol calls.
  - **Live CLI Capabilities Verified:** Executed `npx -y rea-agents@6.7.0 inspect-artifact` and `inspect-managed-artifact` producing valid Evidence JSON objects with sha256 hashes and structural graphs.

### 4.2 Native Engine Backends
- **Built-in Safe Engines:**
  - `rea-artifact-graph` (v1): Functional. Provides root manifest, file occurrences, content hashing, and structural classification without binary execution.
  - `rea-dotnet-static` (v1): Functional. Provides PE/CLI header decoding, CLI data directory inspection, and CLR metadata analysis without executing the binary.
  - `sqlite` provider: Functional on Node.js 24 with native DatabaseSync limits.
- **Deep Decompiler Backends:**
  - `ghidra`: JDK 17 is detected on host; requires `GHIDRA_INSTALL_DIR` pointing to an extracted Ghidra 12.1.x distribution.
  - `hopper`: Unsupported on win32 (macOS target only).
  - `ida`: Not configured (requires commercial IDA Pro license and upstream MCP bridge).
  - `kuna`: Not configured (requires standalone kuna binary).

---

## 5. Security Boundaries, Execution Privileges, and Sandboxing

1. **Process Isolation:**
   - Linux commands execute in a dedicated WSL2 lightweight VM with its own namespace, PID tree, and memory bounds.
   - Host Windows commands run under standard user privileges without elevation.
2. **File Permissions & Safety:**
   - No untrusted binaries will be executed directly during analysis.
   - Application inspection relies on static parsing of binary headers (MZ, PE, ELF, Mach-O) and REA's safe artifact graph provider.
   - Execution tests are strictly constrained to test fixtures, controlled synthetic binaries, and safe mock runners.
3. **Display & Graphical Subsystem:**
   - Headless environment (no physical X11 or Wayland display server active). GUI applications require virtual framebuffers (`Xvfb`) or headless configuration flags.
4. **Network Access Policy:**
   - Outbound HTTPS traffic permitted for public package indexes and source repositories.
   - No sensitive credentials, auth tokens, or private environment variables are stored in project outputs or logs.
