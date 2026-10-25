# Zyntrix Compatibility Fabric (ZCF)

[![License: Apache 2.0](https://img.shields.io/badge/License-Apache_2.0-blue.svg)](LICENSE)
[![Platform: Cross-Distribution](https://img.shields.io/badge/Platform-Linux%20%7C%20Windows-green.svg)](#)
[![Python: 3.10+](https://img.shields.io/badge/Python-3.10%2B-blue.svg)](#)
[![Tests: 127 Passed (100%)](https://img.shields.io/badge/Tests-127%20Passed%20(100%25)-brightgreen.svg)](docs/TESTING.md)
[![CI: Passing](https://img.shields.io/badge/CI-Passing-brightgreen.svg)](.github/workflows/ci.yml)
[![Release: v0.2.0 Distro-Grade](https://img.shields.io/badge/Release-v0.2.0%20Distro--Grade-blue.svg)](#)
[![REA: 6.7.0 Verified](https://img.shields.io/badge/REA-6.7.0%20Verified-purple.svg)](docs/REA_SETUP.md)

**Universal application compatibility platform, runtime orchestrator, and evidence-backed research infrastructure.**  
*Engineered by Zyntrix Labs for Zyntrix OS and designed for default inclusion in top-tier Linux distributions (Fedora, Ubuntu, Debian, Arch Linux, openSUSE).*

---

## 1. What is ZCF?

The **Zyntrix Compatibility Fabric (ZCF)** is an open-source, distribution-independent platform designed to coordinate existing compatibility technologies, investigate software execution behavior, diagnose incompatibilities, and distribute reproducible fixes throughout the Linux ecosystem.

ZCF is **not** a replacement for Wine, Proton, QEMU, or Box64. Instead, it serves as the **unifying coordination, kernel integration, and intelligence layer**:
- **Kernel `binfmt_misc` Integration:** Transparently runs Windows `.exe` and foreign architecture binaries directly from the shell or file manager via `/usr/bin/zcf-runner`.
- **Freedesktop Desktop & MIME Integration:** XDG launcher (`.desktop`), MIME XML, and AppStream metadata compliant with GNOME Software and KDE Discover.
- **Execution Engine (`zcf run`):** Seamless one-step execution coordinating prefix creation, Bubblewrap sandboxing, and automated headless virtual display (`xvfb`).
- **Application Inspector:** Safely inspects PE, ELF, Mach-O, Android APKs, scripts, and archives without binary execution.
- **Environment Inspector:** Discovers host OS, CPU ISA, GPU/Vulkan capabilities, and available compatibility runtimes.
- **Compatibility Planner:** Evaluates multi-dimensional constraints (ISA, OS API, libraries, graphics) to provide explainable runtime recommendations with transparent confidence scoring.
- **Runtime Adapters:** Standardized lifecycle interfaces for Native Linux, Wine, Proton, QEMU User-Mode, Box64, and Android.
- **Diagnostic & Remediation Engine:** Normalizes runtime error logs, detects failure signatures, and surfaces distribution-tailored fix instructions (Debian/Ubuntu, Arch, Fedora/RHEL, Alpine, openSUSE).
- **Compatibility Research Workflow:** 11-step empirical investigation correlating REA static evidence with dynamic traces to formulate hypotheses and test workarounds.
- **Sandboxing & Isolation:** Bubblewrap (`bwrap`) integration enforcing read-only system mounts, isolated network namespaces, and environment scrubbing.
- **Manual Pages & Completions:** Complete groff user manual (`man zcf`) and tab-completion for Bash, Zsh, and Fish.
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
# Set PYTHONPATH to src directory (when running from source)
export PYTHONPATH=src          # Linux / macOS
$env:PYTHONPATH="src"          # Windows PowerShell
```

### 3.1 Graphical Control Center (Zero-Terminal GUI for Beginners)
Beginners can run advanced tasks without ever opening a terminal. Launch the standalone Control Center:
```bash
zcf gui         # or simply run 'zcf-gui' or click ZCF in your Linux Application Menu
```
The Control Center provides:
- **Application Launcher:** Browse any `.exe`, `.msi`, `.apk` or binary, inspect recommended runtime with live confidence score, toggle sandboxing, and launch.
- **One-Click Start Menu Integration:** Pin any Windows or foreign application into your Linux desktop launcher / application grid (`zcf integrate`).
- **Engine Health & 1-Click Install:** View real-time status of Wine, Proton, QEMU, Box64, Waydroid, and Bubblewrap with 1-click graphical package installation.
- **Windows Component Manager (Zero-Terminal Winetricks):** 1-click installation of Microsoft Visual C++ (2015-2022), DirectX End-User Runtimes (D3DX9/11), Wine Mono (.NET), and Vulkan DXVK.
- **Storage & Prefix Cleaner:** Audit compatibility container disk usage and clean stale temporary prefixes with a single click.
- **Automated Troubleshooter & REA:** Paste any error message to receive instant plain-language root-cause diagnosis and one-click remediation.

### 3.2 Local Web Console (Zero-Dependency Browser Interface)
For headless servers, remote SSH sessions, or users who prefer a web interface:
```bash
zcf console     # or 'zcf web' or run standalone 'zcf-console'
```
Binds securely to `http://127.0.0.1:8765` (loopback only) with no third-party web frameworks, providing:
- Live system telemetry & runtime health monitoring
- Browser-based binary header inspector and constraint planner
- Compatibility knowledge base search and filtering
- Prefix storage manager with active process lock detection
- Interactive failure log troubleshooter and auto-remediation synthesis
- Full JSON REST API (`/api/env`, `/api/db`, `/api/prefixes`, `/api/inspect`, `/api/plan`, `/api/diag`)

### 3.3 Unified Terminal Dashboard (for CLI Users)
```bash
zcf dashboard
```

### 3.4 Seamless Application Execution (with sandboxing & auto-display)
```bash
# Execute application through optimal runtime with Bubblewrap sandboxing
zcf run path/to/application.exe

# Allow bridged host network access (defaults to isolated namespace)
zcf run path/to/application.exe --allow-network

# Force headless virtual display (Xvfb) for servers and CI
zcf run path/to/application.exe --headless

# Transparent execution via binfmt_misc (once registered)
./application.exe
```

### 3.5 Integrate Application into Linux Desktop Menu
```bash
# Add application to application menu
zcf integrate path/to/application.exe --name "My Windows App"

# List all integrated applications
zcf integrate --list

# Remove an integrated application launcher
zcf integrate --remove path/to/application.exe
```

### 3.6 Host Environment Audit
```bash
zcf env
```

### 3.7 Inspect an Application
```bash
zcf inspect path/to/app.exe
```

### 3.8 Generate Compatibility Plan
```bash
zcf plan path/to/app.exe
```

### 3.9 Controlled Execution Test & Evidence Recording
```bash
# Perform dry-run plan simulation
zcf test path/to/app.exe --dry-run

# Execute live compatibility test and record outcome to local database
zcf test path/to/app.exe --execute --record --contributor "My Name"
```

### 3.10 Diagnose Runtime Failure Logs & Synthesize Fixes
```bash
zcf diag path/to/error.log --target path/to/app.exe
```

### 3.11 End-to-End Research Investigation
```bash
zcf research path/to/app.exe path/to/error.log
```

### 3.12 Query, Verify & Sync Compatibility Knowledge Base
```bash
# List all compatibility entries
zcf db list

# Submit community profile
zcf db submit --app path/to/app.exe --status verified_compatible

# Verify and promote profile with structured test evidence
zcf db verify --id community_app_12345678 --verifier "Maintainer Name"

# Delete a profile from storage
zcf db delete --id test_profile_id

# Export portable evidence bundle
zcf db export --output bundle.json

# Import and reconcile external bundle
zcf db import --file bundle.json
```

### 3.13 View Documentation Manual Page
```bash
man zcf
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
- **Runtime Adapter Authoring Guide:** [`docs/ADAPTER_AUTHORING.md`](docs/ADAPTER_AUTHORING.md)
- **Compatibility Profile Contribution Guidelines:** [`docs/CONTRIBUTING_PROFILES.md`](docs/CONTRIBUTING_PROFILES.md)
- **Security & Process Isolation Model:** [`docs/SECURITY_MODEL.md`](docs/SECURITY_MODEL.md)
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
$env:ZCF_NON_INTERACTIVE="1"
python -m unittest discover -s tests -v

# On Linux (or WSL2)
bash tests/run_tests.sh
```

All **127 automated tests** across **23 test suites** pass 100% across both Windows 11 host and Ubuntu 26.04 (WSL2 with xvfb). Synthetic fixtures are honestly distinguished from real application profiles, which default to unverified community status until independently reproduced.

---

## 7. Packaging & Distribution Specs

Production package manifests and staging scripts are provided under `packaging/` and `data/`:
- **Debian / Ubuntu:** Package builder `packaging/build_distro_packages.sh` (produces `build/zcf_0.2.0-1_all.deb`) and `packaging/debian/`
- **Arch Linux:** `packaging/arch/PKGBUILD`
- **Red Hat / Fedora:** `packaging/rpm/zcf.spec`
- **Flatpak:** `packaging/flatpak/org.zyntrix.zcf.json`
- **AppImage:** `packaging/appimage/AppRun`
- **Linux Kernel binfmt_misc:** `data/binfmt.d/zcf.conf`
- **Desktop & MIME:** `data/desktop/` and `data/mime/`
- **AppStream Metadata:** `data/metainfo/org.zyntrix.zcf.metainfo.xml`
- **Shell Completions:** `data/completions/` (bash, zsh, fish)
- **Systemd Units:** `data/systemd/`

---

## 8. License & Governance

Licensed under the **Apache License, Version 2.0**. See [`LICENSE`](LICENSE) for details.  
Compatibility database entries are published under **CC-BY-4.0**.  
See [`GOVERNANCE.md`](GOVERNANCE.md) and [`SECURITY.md`](SECURITY.md) for community charters.
