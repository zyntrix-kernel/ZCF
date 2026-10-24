"""
Diagnostic Engine for ZCF.
Normalizes runtime error logs, detects failure signatures, and maps errors to actionable remediations.
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
        "signature": "wine_dll_not_found",
        "pattern": re.compile(r"err:module:(?:import_dll|load_builtin_dll)\s+Library\s+([^ ]+)\s+not found", re.IGNORECASE),
        "severity": "error",
        "root_cause_template": "Windows DLL dependency not found: '{0}'",
        "remediation_template": "Install the required Windows runtime dependency via winetricks or place '{0}' in the application directory.",
        "confidence": 0.95,
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
