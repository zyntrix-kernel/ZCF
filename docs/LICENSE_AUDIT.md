# ZCF Licensing and Third-Party Compliance Audit

**Project:** Zyntrix Compatibility Fabric (ZCF)  
**Document:** `docs/LICENSE_AUDIT.md`  
**Date:** October 24, 2026  
**Auditor:** Antigravity Autonomous Engineering Agent  
**Core Framework License:** Apache License, Version 2.0  

---

## 1. Licensing Philosophy and Ecosystem Strategy

The core Zyntrix Compatibility Fabric (ZCF) platform is developed and released under the **Apache License, Version 2.0**. This choice is deliberate:
1. **Permissive and Ecosystem-Friendly:** Allows broad adoption across community Linux distributions (Debian, Arch, Fedora, openSUSE), enterprise distributions (RHEL, SLES, Ubuntu Pro), and independent systems (Zyntrix OS) without viral copyleft restrictions imposing constraints on external tooling.
2. **Patent Grant and Trademark Protection:** Protects community contributors through explicit patent licensing provisions (Section 3 of Apache-2.0) while safeguarding the Zyntrix trademark from unauthorized endorsement.
3. **No Forced Subscriptions or Artificial Paywalls:** The core compatibility engine, CLI, runtime orchestrator, and local database remain 100% free and open source forever.

---

## 2. Third-Party Component and Runtime License Audit

ZCF integrates with and orchestrates numerous third-party tools. To guarantee license compliance, ZCF uses **isolated process boundaries (CLI, pipes, sockets, and MCP protocols)** rather than static or dynamic in-process linking. Under established software copyright law and open-source licensing principles, orchestrating external independent programs via standard IPC does not create a derivative work of those programs.

| Target Component | License | Relationship to ZCF | Compliance & Isolation Mechanism |
| :--- | :--- | :--- | :--- |
| **REA (Reverse Engineer Anything)** | MIT | External Analysis Instrument | Invoked via stdio MCP protocol and CLI; no proprietary bundling. |
| **Wine** | LGPL-2.1-or-later | Managed Compatibility Runtime | Invoked via `execve` / subprocess; prefixes isolated; no shared library linking. |
| **Valve Proton** | Mixed (BSD, LGPL, GPL) | Managed Compatibility Runtime | Managed via runner invocation scripts; zero static linkage. |
| **QEMU User** | GPL-2.0-only | Emulation Engine | Invoked as external binary (`qemu-aarch64`); zero library entanglement. |
| **Box64** | MIT | Dynamic Translation Runtime | Invoked as external launcher; fully compliant with permissive terms. |
| **FEX-Emu** | MIT | Architecture Emulation Engine | Invoked as external executor; compliant. |
| **Waydroid** | GPL-3.0-or-later | Optional Container Runtime | Container management via standalone IPC. |
| **readelf / objdump** | GPL-3.0-or-later | Host Inspection Tool | Invoked as standard CLI tool; parses output streams. |
| **strace** | LGPL-2.1+ / GPL-2.0+ | Syscall Diagnostic Tool | Standalone process invocation. |
| **patchelf** | GPL-3.0-or-later | ELF Manipulation Utility | Standalone binary execution. |

---

## 3. Data Licensing and Compatibility Knowledge Base

- **Compatibility Database Entries (`schemas/compatibility_entry.schema.json`):**
  - Released under **Creative Commons Attribution 4.0 International (CC-BY-4.0)** or **Open Database License (ODbL)**.
  - Ensures compatibility knowledge (fixes, workarounds, test results) remains a public good, freely distributable across any Linux distribution without proprietary capture.
- **Documentation and Architecture Specs:**
  - Published under **CC-BY-4.0**.

---

## 4. Verification and Attribution Notice

All original source code files in the ZCF repository include standard Apache-2.0 copyright and licensing headers. Third-party projects analyzed during research are cited with full upstream repository URLs, author attributions, and licensing notices in compliance with their respective requirements.
