"""
Diagnostic Engine for ZCF.
Normalizes runtime error logs, detects comprehensive failure signatures, and maps errors to actionable remediations.
"""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass
from typing import Any, Dict, List, Optional


@dataclass
class DiagnosticEvent:
    signature: str
    severity: str  # "error", "warning", "info"
    matched_text: str
    root_cause: str
    remediation: str
    confidence: float

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


DIAGNOSTIC_RULES = [
    {
        "signature": "missing_shared_library",
        "pattern": re.compile(
            r"error while loading shared libraries:\s+([^:]+):\s+cannot open shared object file", re.IGNORECASE
        ),
        "severity": "error",
        "root_cause_template": "Missing Linux shared library dependency: '{0}'",
        "remediation_template": "Install the missing shared library package using your distribution package manager (e.g. apt search {0}).",
        "confidence": 0.98,
    },
    {
        "signature": "glibc_symbol_version_missing",
        "pattern": re.compile(r"/lib[0-9a-z_/-]+/libc\.so\.[0-9]+:\s+version\s+`([^']+)'\s+not found", re.IGNORECASE),
        "severity": "error",
        "root_cause_template": "Target binary requires newer GNU C Library ({0}) than host glibc provides.",
        "remediation_template": "Execute inside an updated distribution container or upgrade host glibc runtime.",
        "confidence": 0.95,
    },
    {
        "signature": "undefined_symbol_error",
        "pattern": re.compile(r"undefined symbol:\s+([a-zA-Z0-9_]+)", re.IGNORECASE),
        "severity": "error",
        "root_cause_template": "Dynamic symbol lookup failed for symbol '{0}'. Library ABI mismatch.",
        "remediation_template": "Rebuild against matching shared library headers or verify LD_LIBRARY_PATH resolution.",
        "confidence": 0.92,
    },
    {
        "signature": "wine_dll_not_found",
        "pattern": re.compile(r"err:module:(?:import_dll|load_builtin_dll)\s+Library\s+([^ ]+)\s+not found", re.IGNORECASE),
        "severity": "error",
        "root_cause_template": "Windows DLL dependency not found: '{0}'",
        "remediation_template": "Install the required Windows runtime dependency via winetricks or place '{0}' in the application directory.",
        "confidence": 0.95,
    },
    {
        "signature": "wine_directx_missing",
        "pattern": re.compile(r"(?:d3dcompiler_[0-9]+\.dll|d3dx[0-9]+_[0-9]+\.dll)\s+(?:not found|failed to load)", re.IGNORECASE),
        "severity": "error",
        "root_cause_template": "DirectX runtime component missing in Wine prefix.",
        "remediation_template": "Install DirectX runtime components via winetricks ('winetricks d3dx9 d3dcompiler_47').",
        "confidence": 0.96,
    },
    {
        "signature": "vulkan_initialization_failure",
        "pattern": re.compile(r"(?:vkCreateInstance failed|VK_ERROR_INCOMPATIBLE_DRIVER|Cannot find a compatible Vulkan installable client driver)", re.IGNORECASE),
        "severity": "error",
        "root_cause_template": "Vulkan hardware driver initialization failed (ICD driver missing or incompatible).",
        "remediation_template": "Install host Vulkan GPU driver (e.g. mesa-vulkan-drivers / nvidia-vulkan-icd) or enable DXVK fallback.",
        "confidence": 0.97,
    },
    {
        "signature": "exec_format_error",
        "pattern": re.compile(r"cannot execute binary file:\s+Exec format error", re.IGNORECASE),
        "severity": "error",
        "root_cause_template": "Binary architecture or format is not supported by the native host kernel.",
        "remediation_template": "Use an architecture emulation runner such as QEMU User ('qemu-aarch64') or Box64.",
        "confidence": 0.99,
    },
    {
        "signature": "bad_interpreter_error",
        "pattern": re.compile(r"bad interpreter:\s+([^:]+):\s+No such file or directory", re.IGNORECASE),
        "severity": "error",
        "root_cause_template": "Script shebang interpreter '{0}' is not present on the host filesystem.",
        "remediation_template": "Install the required language interpreter (e.g. python3, bash) or adjust shebang to '#!/usr/bin/env ...'.",
        "confidence": 0.99,
    },
    {
        "signature": "illegal_instruction_trap",
        "pattern": re.compile(r"(?:Illegal instruction|SIGILL)", re.IGNORECASE),
        "severity": "error",
        "root_cause_template": "CPU encountered an unsupported machine instruction (e.g. AVX2, AVX-512, SSE4.2, NEON).",
        "remediation_template": "Use Box64/QEMU with instruction translation flags, or recompile with generic CPU flags.",
        "confidence": 0.92,
    },
    {
        "signature": "qemu_unsupported_syscall",
        "pattern": re.compile(r"qemu:\s+Unsupported syscall:\s+([0-9]+)", re.IGNORECASE),
        "severity": "error",
        "root_cause_template": "QEMU user-mode emulation encountered an unimplemented Linux system call: #{0}",
        "remediation_template": "Upgrade to a newer QEMU release or report the unimplemented syscall to QEMU upstream.",
        "confidence": 0.90,
    },
    {
        "signature": "missing_display",
        "pattern": re.compile(r"(?:cannot open display|failed to open wayland display|No protocol specified)", re.IGNORECASE),
        "severity": "error",
        "root_cause_template": "Application requires a graphical display server (X11/Wayland), but none was accessible.",
        "remediation_template": "Run inside an active desktop session or start a virtual framebuffer with 'xvfb-run <command>'.",
        "confidence": 0.95,
    },
    {
        "signature": "wine_page_fault",
        "pattern": re.compile(r"wine:\s+Unhandled (?:page fault|exception)\s+(?:on|code)\s+([0-9a-fx]+)", re.IGNORECASE),
        "severity": "error",
        "root_cause_template": "Wine process encountered an unhandled memory page fault or NT exception: {0}",
        "remediation_template": "Capture a full diagnostic trace with 'WINEDEBUG=+seh,+relay' to isolate the failing DLL or memory address.",
        "confidence": 0.85,
    },
    {
        "signature": "wine_mono_missing",
        "pattern": re.compile(r"(?:Wine Mono is not installed|Mono not found)", re.IGNORECASE),
        "severity": "warning",
        "root_cause_template": ".NET application requires Wine Mono to execute managed CIL code.",
        "remediation_template": "Install the Wine Mono package ('sudo apt install wine-mono') or install official Microsoft .NET in the prefix.",
        "confidence": 0.95,
    },
    {
        "signature": "audio_device_error",
        "pattern": re.compile(r"(?:ALSA lib|pulse: Connection refused|DirectSound: CreateSoundBuffer failed)", re.IGNORECASE),
        "severity": "warning",
        "root_cause_template": "Audio subsystem initialization failed; PipeWire/PulseAudio server unreachable.",
        "remediation_template": "Ensure user PipeWire or PulseAudio daemon is running ('systemctl --user start pipewire').",
        "confidence": 0.90,
    },
]


class DiagnosticEngine:
    """Parses and classifies runtime logs into structured diagnostic events."""

    def analyze_log(self, log_content: str) -> List[DiagnosticEvent]:
        events: List[DiagnosticEvent] = []
        lines = log_content.splitlines()

        for line in lines:
            for rule in DIAGNOSTIC_RULES:
                match = rule["pattern"].search(line)
                if match:
                    groups = match.groups()
                    target = groups[0] if groups else ""
                    rc = rule["root_cause_template"].format(target)
                    rem = rule["remediation_template"].format(target)

                    events.append(
                        DiagnosticEvent(
                            signature=rule["signature"],
                            severity=rule["severity"],
                            matched_text=line.strip(),
                            root_cause=rc,
                            remediation=rem,
                            confidence=rule["confidence"],
                        )
                    )
        return events
