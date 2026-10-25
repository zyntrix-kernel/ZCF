# ZCF Automated Testing and Verification Report

**Project:** Zyntrix Compatibility Fabric (ZCF)  
**Document:** `docs/TESTING.md`  
**Date:** October 25, 2026  
**Test Framework:** Python `unittest` standard test runner  
**Test Execution Environments:** Windows 11 Pro Host + WSL2 Ubuntu 26.04 LTS (with xvfb)  
**Milestone:** 3 (Close the Remaining Security and Evidence Gaps)  

---

## 1. Test Strategy and Philosophy

ZCF enforces strict automated verification. Tests cover both positive execution paths and failure/negative paths. Speculative claims of compatibility are rejected; every capability asserted by the framework is backed by automated tests against real binaries, synthetic test fixtures, and distribution integration files.

### Test Categories (23 Modules, 138 Tests)
1. **Desktop UX & Beginner Dialogs (`test_desktop_ux.py`):** Tests Zenity/KDialog graphical modals, non-interactive fallbacks, Freedesktop specification path escaping (`%`, `$`, `"`, `\`), and rejection of control characters and newlines with `ValueError`.
2. **Graphical User Interface (`test_gui.py`):** Tests standalone Tkinter/ttk `ZCFControlCenter` tabs (Launch, Runtimes, Components, Prefixes, Diag), unified Wine and Proton prefix lifecycle management, application inspection updates, and log diagnosis without UI freezing under `xvfb`.
3. **Windows Component Manager (`test_components.py`):** Tests component definitions (Visual C++, DirectX D3DX9, Wine Mono, DXVK), strict all-DLL filesystem verification (`system32`/`syswow64`), removal of metadata fallback, automated winetricks handling, non-blocking monotonic deadline loops, process killing on timeout, and cleanup of stale metadata on installation failures.
4. **Prefix Lifecycle & Storage Manager (`test_prefix_lifecycle.py`):** Tests default prefix persistence, protection of prefixes with missing or corrupt metadata, active process lock detection, disposable vs persistent preview, dry-run state isolation, and containment within configured roots.
5. **Compatibility Database & Migration (`test_database.py`):** Tests v3 database schema migration, downgrading of unsupported real-application claims (Notepad, 7-Zip, Notepad++, FTL, F-Droid) to unverified community status, verified fixture seed entries from actual fixture bytes, migration failure visibility with `status: "failed"` and error tracking, strict structured test evidence requirements, artifact hash verification, profile deletion, and path traversal prevention.
6. **Compatibility Database v2 & Provenance (`test_database_v2.py`):** Tests schema validation, provenance tiers (`COMMUNITY_UNTESTED`, `AUTOMATED_TEST`, `MAINTAINER_VERIFIED`), evidence statuses, advanced queries, and community submission workflows.
7. **Execution Lifecycle Orchestration (`test_orchestrator_lifecycle.py`):** Tests the 9-phase execution lifecycle, native python execution, Wine dry-run orchestration, Bubblewrap fail-closed security (`SecurityViolationError`), non-blocking monotonic deadline streaming timeouts under rapid stdout flood, output truncation cap (512 KB), virtual display lifecycle cleanup on all exit paths, Freedesktop escaping/unintegration, negative timeout rejection, policy timeout clamping, truthful `RLIMIT_AS` resource limits reporting, and pipe closure preventing hanging reader threads.
8. **Application Inspection Tests (`test_inspector.py`):** Validates raw PE32+, ELF64 (x86_64, AArch64), shell scripts, corrupted files, and nonexistent paths.
9. **Mach-O Binary Parser Tests (`test_macho.py`):** Validates 32-bit, 64-bit, and Universal Fat Mach-O binary parsing, CPU subtypes, and load command verification.
10. **Android APK Package Tests (`test_apk.py`):** Validates zip-based APK analysis, dex file counts, manifest presence, and multi-ABI native library detection.
11. **Environment Audit Tests (`test_environment.py`):** Validates runtime detection, memory parsing, logical CPU enumeration, truthful Bubblewrap and Vulkan discovery, and display server discovery.
12. **Compatibility Planning Tests (`test_planner.py`):** Evaluates deterministic constraint satisfaction: native matching, Wine detection, QEMU architecture emulation, mandatory prerequisite enforcement (blocking Proton when Vulkan is missing for DXVK, blocking Waydroid when Wayland or `/dev/binder` is missing), Android APK install vs launch command generation, and evidence integrity guards (rejecting stale SHA-256 hashes, placeholder hashes, fixture benchmarks on real apps, and contradictory provenance).
13. **Runtime Adapter Tests (`test_runtimes.py`):** Tests adapter validation, prefix generation, environment variable isolation, and dry-run execution.
14. **Execution Orchestrator Tests (`test_execution_runner.py`):** Tests end-to-end runner initialization, package manager command generation across distributions, virtual display lifecycle, and desktop notifications.
15. **Linux Distribution Integration Tests (`test_distro_integration.py`):** Validates `binfmt.d/zcf.conf` syntax, `.desktop` launcher keys, AppStream metadata XML schema, shell completions (bash, zsh, fish), and manual page groff syntax.
16. **Diagnostic Engine Tests (`test_diagnostics.py`):** Tests regex pattern matching against known failure signatures: missing shared libraries, missing DLLs, page faults, display server errors, and exec format errors.
17. **Automated Remediator Tests (`test_remediator.py`):** Validates distribution-specific package command synthesis (Debian/Ubuntu, Arch, Fedora/RHEL, Alpine, openSUSE), DLL overrides, and wrapper generation.
18. **Research Engine Tests (`test_research_engine.py`):** Tests the 11-step empirical investigation workflow, hypothesis generation with confidence scoring, REA evidence correlation, and automated knowledge base cataloging.
19. **Compatibility Sync Tests (`test_sync.py`):** Validates portable JSON bundle export, cryptographic hashing, schema and count validation, atomic import with automatic rollback on error, and untrusted third-party provenance downgrading.
20. **Bubblewrap Sandbox Tests (`test_sandbox.py`):** Validates Bubblewrap `bwrap` command isolation, strict path canonicalization and ancestor symlink resolution, rejection of sensitive system directories (`/`, `/etc`, `/usr`, `/run`, `/var`), symlink escape prevention, containment within approved prefix roots, narrow Wayland display socket binding, rejection of conflicting read-only and writable mounts, fail-closed enforcement when bwrap is missing, and resource control status.
21. **Security Controller Tests (`test_security.py`):** Validates path traversal defenses, environment secret scrubbing across modes (`minimized_desktop`, `strict_allowlist`, `filter_secrets`), display variable preservation (`XAUTHORITY`), default network isolation across all workloads with explicit opt-in, and workload-aware timeout defaults and boundaries.
22. **Web Console & REST API Tests (`test_web_console.py`):** Validates local loopback browser control center, ThreadingHTTPServer concurrent requests, HTTP security headers (`nosniff`, `DENY`, CSP), single-page dashboard HTML delivery, REST API endpoints (`/api/env`, `/api/db`, `/api/db/profile`, `/api/prefixes`, `/api/prefixes/cleanup`, `/api/dashboard`, `/api/inspect`, `/api/plan`, `/api/test`, `/api/diag`), DNS rebinding protection (Host header validation), CSRF / cross-site fetch rejection, payload size caps (2MB), path traversal prevention, and remote exposure restrictions.
23. **CLI Workflows & Command Dispatch (`test_cli_workflows.py`):** Validates symmetric desktop integration (`integrate --list`, `integrate --remove`), background maintenance (`service list-prefixes`, `service cleanup-prefixes`), database profile verification with structured test evidence, profile deletion, dry-run outcome recording with honest `UNTESTED` status, live execution recording, and blocked execution exits with code 2.

---

## 2. Test Execution Commands and Observed Outcomes

### 2.1 Windows 11 Pro Host
```powershell
$env:PYTHONPATH="src"
$env:ZCF_NON_INTERACTIVE="1"
python -m unittest discover -s tests -v
```
**Outcome:** Ran 138 tests in 27.442s — **OK (100% Passed, 0 Failures, 0 Errors)**

### 2.2 Linux Environment (WSL2 Ubuntu 26.04 with Xvfb)
```bash
PYTHONPATH=src xvfb-run -a python3 -m unittest discover -s tests -v
```
**Outcome:** Ran 138 tests in 28.019s — **OK (100% Passed, 0 Failures, 0 Errors)**

---

## 3. Test Result Summary

| Metric | Windows 11 Pro Host | WSL2 Ubuntu (xvfb) |
|---|---|---|
| Tests Collected | 138 | 138 |
| Tests Passed | 138 | 138 |
| Tests Failed | 0 | 0 |
| Tests Errored | 0 | 0 |
| Tests Skipped | 0 | 0 |
| Success Rate | **100%** | **100%** |
| Execution Duration | 27.44s | 28.02s |
