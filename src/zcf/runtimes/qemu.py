"""
QEMU User-Mode Emulation Adapter.
Enables execution of cross-architecture Linux ELF binaries via instruction translation.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from typing import Any, Callable, Dict, List, Optional

from zcf.core.models import (
    ApplicationDescription,
    Architecture,
    BinaryFormat,
    EnvironmentReport,
    ExecutionResult,
    ValidationResult,
    WorkloadType,
)
from zcf.runtimes.base import BaseRuntimeAdapter

ARCH_QEMU_BINARY_MAP = {
    Architecture.ARM64: "qemu-aarch64",
    Architecture.ARM: "qemu-arm",
    Architecture.RISCV64: "qemu-riscv64",
    Architecture.I386: "qemu-i386",
    Architecture.X86_64: "qemu-x86_64",
}

SYSROOT_MAP = {
    Architecture.ARM64: "/usr/aarch64-linux-gnu",
    Architecture.ARM: "/usr/arm-linux-gnueabihf",
    Architecture.RISCV64: "/usr/riscv64-linux-gnu",
    Architecture.I386: "/usr/i686-linux-gnu",
    Architecture.X86_64: "/usr/x86_64-linux-gnu",
}


class QemuUserAdapter(BaseRuntimeAdapter):
    """Adapter for running cross-architecture Linux ELF executables."""

    def get_id(self) -> str:
        return "runtime.qemu-user"

    def get_name(self) -> str:
        return "QEMU User-Mode Architecture Emulation"

    def get_version(self, env: Optional[EnvironmentReport] = None) -> Optional[str]:
        if env:
            for r in env.available_runtimes:
                if r.runtime_id == "runtime.qemu-user" and r.version:
                    return r.version

        for b in ARCH_QEMU_BINARY_MAP.values():
            bin_path = shutil.which(b) or shutil.which(f"{b}-static")
            if bin_path:
                try:
                    out = subprocess.check_output([bin_path, "--version"], text=True, timeout=5)
                    first_line = out.splitlines()[0] if out else ""
                    return first_line.split("version")[-1].strip() if "version" in first_line else first_line
                except Exception:
                    pass
        return None

    def get_capabilities(self) -> Dict[str, Any]:
        return {
            "supported_formats": [BinaryFormat.ELF.value],
            "supported_architectures": [
                Architecture.ARM64.value,
                Architecture.ARM.value,
                Architecture.RISCV64.value,
                Architecture.I386.value,
                Architecture.X86_64.value,
            ],
            "supported_workloads": [WorkloadType.CLI_TOOL.value, WorkloadType.DESKTOP_GUI.value],
            "requires_vulkan": False,
            "requires_wayland": False,
            "supports_sandboxing": True,
            "supports_virtual_display": True,
            "isolation_features": ["sysroot", "bubblewrap"],
            "known_limitations": [
                "Target dynamically-linked ELF binaries require multiarch sysroot libraries installed on host.",
            ],
        }

    def is_available(self, env: EnvironmentReport) -> bool:
        for r in env.available_runtimes:
            if r.runtime_id == "runtime.qemu-user":
                return r.installed
        return any(
            shutil.which(b) is not None or shutil.which(f"{b}-static") is not None
            for b in ARCH_QEMU_BINARY_MAP.values()
        )

    def check_prerequisites(self, app: ApplicationDescription, env: EnvironmentReport) -> List[str]:
        missing: List[str] = []
        qemu_bin = ARCH_QEMU_BINARY_MAP.get(app.architecture)
        if qemu_bin:
            resolved = shutil.which(qemu_bin) or shutil.which(f"{qemu_bin}-static")
            if not resolved:
                missing.append(f"QEMU user emulator for {app.architecture.value} ('{qemu_bin}') is not installed.")
        return missing

    def validate(self, app: ApplicationDescription, env: EnvironmentReport) -> ValidationResult:
        errors: List[str] = []
        warnings: List[str] = []

        if app.format != BinaryFormat.ELF:
            errors.append(f"QEMU User mode requires Linux ELF format; target has format '{app.format.value}'")

        qemu_bin = ARCH_QEMU_BINARY_MAP.get(app.architecture)
        available_in_env = any(
            r.runtime_id == "runtime.qemu-user" and r.installed for r in env.available_runtimes
        )
        binary_on_path = (shutil.which(qemu_bin) or shutil.which(f"{qemu_bin}-static")) if qemu_bin else None

        if not available_in_env and not binary_on_path:
            errors.append(
                f"Missing QEMU user binary for architecture '{app.architecture.value}' (expected '{qemu_bin}')"
            )

        if app.architecture.value == env.architecture:
            warnings.append(
                f"Target architecture '{app.architecture.value}' matches host; native execution is preferred over emulation."
            )

        return ValidationResult(valid=len(errors) == 0, errors=errors, warnings=warnings)

    def prepare_environment(
        self, app: ApplicationDescription, config: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        env_vars = os.environ.copy()
        qemu_bin = ARCH_QEMU_BINARY_MAP.get(app.architecture, "qemu-aarch64")
        resolved_bin = shutil.which(qemu_bin) or shutil.which(f"{qemu_bin}-static") or qemu_bin

        # Default multiarch sysroot if available
        sysroot = SYSROOT_MAP.get(app.architecture)
        if sysroot and not os.path.exists(sysroot):
            sysroot = None

        if config and "environment_variables" in config:
            env_vars.update(config["environment_variables"])

        return {
            "qemu_binary": resolved_bin,
            "sysroot": sysroot,
            "environment_variables": env_vars,
            "working_directory": os.path.dirname(os.path.abspath(app.artifact_path)),
        }

    def build_command(
        self, app: ApplicationDescription, context: Dict[str, Any], args: Optional[List[str]] = None
    ) -> List[str]:
        qemu_bin = context.get("qemu_binary") or ARCH_QEMU_BINARY_MAP.get(app.architecture, "qemu-aarch64")
        abs_target = os.path.abspath(app.artifact_path)
        app_args = args or []

        sysroot = context.get("sysroot")
        if sysroot and os.path.exists(sysroot):
            return [qemu_bin, "-L", sysroot, abs_target] + app_args

        return [qemu_bin, abs_target] + app_args

    def execute(
        self,
        app: ApplicationDescription,
        context: Dict[str, Any],
        args: Optional[List[str]] = None,
        dry_run: bool = False,
        stream_callback: Optional[Callable[[str], None]] = None,
        timeout: Optional[int] = None,
    ) -> ExecutionResult:
        cmd = self.build_command(app, context, args)
        return self._execute_process(
            cmd=cmd,
            context=context,
            dry_run=dry_run,
            stream_callback=stream_callback,
            timeout=timeout,
        )
