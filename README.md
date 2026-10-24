# Zyntrix Compatibility Fabric (ZCF)

[![License: Apache 2.0](https://img.shields.io/badge/License-Apache_2.0-blue.svg)](LICENSE)
[![Platform: Cross-Distribution](https://img.shields.io/badge/Platform-Linux%20%7C%20Windows-green.svg)](#)
[![Python: 3.10+](https://img.shields.io/badge/Python-3.10%2B-blue.svg)](#)
[![Tests: 31 Passed (100%)](https://img.shields.io/badge/Tests-31%20Passed%20(100%25)-brightgreen.svg)](docs/TESTING.md)
[![REA: 6.7.0 Verified](https://img.shields.io/badge/REA-6.7.0%20Verified-purple.svg)](docs/REA_SETUP.md)

**Universal application compatibility platform, runtime orchestrator, and evidence-backed research infrastructure.**

---

## 1. What is ZCF?

The **Zyntrix Compatibility Fabric (ZCF)** is an open-source, distribution-independent platform designed to coordinate existing compatibility technologies, investigate software execution behavior, diagnose incompatibilities, and distribute reproducible fixes throughout the Linux ecosystem.

ZCF is **not** a replacement for Wine, Proton, QEMU, or Box64. Instead, it serves as the **unifying coordination and intelligence layer**:
- **Application Inspector:** Safely inspects PE, ELF, Mach-O, Android APKs, scripts, and archives without binary execution.
- **Environment Inspector:** Discovers host OS, CPU ISA, GPU/Vulkan capabilities, and available compatibility runtimes.
- **Compatibility Planner:** Evaluates multi-dimensional constraints (ISA, OS API, libraries, graphics) to provide explainable runtime recommendations with transparent confidence scoring.
- **Runtime Adapters:** Standardized lifecycle interfaces for Native Linux, Wine, Proton, QEMU User-Mode, Box64, and Android.
- **Diagnostic & Remediation Engine:** Normalizes runtime error logs, detects failure signatures, and surfaces distribution-tailored fix instructions (Debian/Ubuntu, Arch, Fedora/RHEL, Alpine, openSUSE).
- **Compatibility Research Workflow:** 11-step empirical investigation correlating REA static evidence with dynamic traces to formulate hypotheses and test workarounds.
- **Sandboxing & Isolation:** Bubblewrap (`bwrap`) integration enforcing read-only system mounts, isolated network namespaces, and environment scrubbing.
- **Compatibility Database & Sync:** Versioned, machine-readable repository of tested compatibility profiles and portable sync bundles.
- **REA Integration:** Integrated with [REA (Reverse Engineer Anything)](https://github.com/morluto/rea) via CLI and live Model Context Protocol (MCP) stdio connections for deep static and dynamic reverse engineering.

---

## 2. Founding Principles

1. **Ecosystem Independence:** ZCF is designed for the entire Linux community. While Zyntrix OS is the flagship desktop environment, ZCF runs identically on Ubuntu, Fedora, Arch Linux, Debian, and dual Windows/WSL environments.
2. **Research First, Evidence Always:** Speculative claims of compatibility are rejected. Every profile and decision is backed by cryptographic hashes (SHA-256), authority tiers, and empirical test logs.
3. **Open-Source and Zero-Lock-In:** Released under the **Apache License, Version 2.0**. The core platform requires no subscriptions, proprietary cloud activation, or telemetry.

---

## 3. Quick Start & CLI Usage

ZCF requires **Python 3.10+** and has zero mandatory third-party dependencies for core operations.

```bash
# Set PYTHONPATH to src directory
export PYTHONPATH=src          # Linux / macOS
$env:PYTHONPATH="src"          # Windows PowerShell
```

### 3.1 Unified Dashboard
```bash
python -m zcf.cli.main dashboard
```

### 3.2 Host Environment Audit
```bash
python -m zcf.cli.main env
```

### 3.3 Inspect an Application
```bash
python -m zcf.cli.main inspect path/to/app.exe
```

### 3.4 Generate Compatibility Plan
```bash
python -m zcf.cli.main plan path/to/app.exe
```

### 3.5 Controlled Execution Test
```bash
python -m zcf.cli.main test path/to/app.exe --dry-run
```

### 3.6 Diagnose Runtime Failure Logs & Synthesize Fixes
```bash
python -m zcf.cli.main diag path/to/error.log --target path/to/app.exe
```

### 3.7 End-to-End Research Investigation
```bash
python -m zcf.cli.main research path/to/app.exe path/to/error.log
```

### 3.8 Query & Sync Compatibility Knowledge Base
```bash
# List all verified compatibility entries
python -m zcf.cli.main db list

# Export portable evidence bundle
python -m zcf.cli.main db export --output bundle.json

# Import and reconcile external bundle
python -m zcf.cli.main db import --file bundle.json
```

---

## 4. Reverse Engineering with REA

ZCF integrates with **REA 6.7.0** ([morluto/rea](https://github.com/morluto/rea)):
- **Live Agent MCP Server:** Configured in `~/.gemini/config/mcp_config.json` (`open_binary`, `inspect_artifact`, `close_binary`).
- **CLI Static Analysis:** Generates typed Evidence JSON records (`rea inspect-artifact`, `rea inspect-managed-artifact`).
- See [`docs/REA_SETUP.md`](docs/REA_SETUP.md) for full setup and diagnostic evidence.

---

## 5. Documentation Directory

- **Host Diagnostic Report:** [`docs/ENVIRONMENT_REPORT.md`](docs/ENVIRONMENT_REPORT.md)
- **REA Setup & Audit:** [`docs/REA_SETUP.md`](docs/REA_SETUP.md)
- **Compatibility Tool Inventory:** [`docs/COMPATIBILITY_TOOL_INVENTORY.md`](docs/COMPATIBILITY_TOOL_INVENTORY.md)
- **Compatibility Model & Taxonomy:** [`docs/COMPATIBILITY_MODEL.md`](docs/COMPATIBILITY_MODEL.md)
- **Architecture Specification:** [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md)
- **Architecture Decision Records:** [`docs/ADR/`](docs/ADR/)
- **Research Case Studies:** [`research/`](research/)
- **Test Suite Verification:** [`docs/TESTING.md`](docs/TESTING.md)
- **Licensing Compliance Audit:** [`docs/LICENSE_AUDIT.md`](docs/LICENSE_AUDIT.md)
- **Final Delivery Report:** [`DELIVERY_REPORT.md`](DELIVERY_REPORT.md)

---

## 6. Running the Test Suite

```bash
# On Windows PowerShell
$env:PYTHONPATH="src"
python -m unittest discover -s tests -v

# On Linux (or WSL2)
bash tests/run_tests.sh
```

All **31 automated tests** pass 100% across both Windows 11 host and Ubuntu 26.04 (WSL2).

---

## 7. Packaging & Distribution Specs

Production package manifests are provided under `packaging/`:
- **Debian / Ubuntu:** `packaging/debian/` (`control`, `rules`, `changelog`, `compat`)
- **Arch Linux:** `packaging/arch/PKGBUILD`
- **Red Hat / Fedora:** `packaging/rpm/zcf.spec`
- **Flatpak:** `packaging/flatpak/org.zyntrix.zcf.json`
- **AppImage:** `packaging/appimage/AppRun`

---

## 8. License & Governance

Licensed under the **Apache License, Version 2.0**. See [`LICENSE`](LICENSE) for details.  
Compatibility database entries are published under **CC-BY-4.0**.  
See [`GOVERNANCE.md`](GOVERNANCE.md) and [`SECURITY.md`](SECURITY.md) for community charters.
