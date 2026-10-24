"""
QEMU User-Mode Emulation Adapter.
Enables execution of cross-architecture Linux ELF binaries via instruction translation.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import time
from typing import Any, Dict, List, Optional

from zcf.core.models import (
    ApplicationDescription,
    Architecture,
    BinaryFormat,
    EnvironmentReport,
    ExecutionResult,
    ValidationResult,
)
from zcf.runtimes.base import RuntimeAdapterInterface


ARCH_QEMU_BINARY_MAP = {
    Architecture.ARM64: "qemu-aarch64",
    Architecture.ARM: "qemu-arm",
    Architecture.RISCV64: "qemu-riscv64",
    Architecture.I386: "qemu-i386",
    Architecture.X86_64: "qemu-x86_64",
}


class QemuUserAdapter(RuntimeAdapterInterface):
    """Adapter for running cross-architecture Linux ELF executables."""

    def get_id(self) -> str:
        return "runtime.qemu-user"

    def get_name(self) -> str:
        return "QEMU User-Mode Architecture Emulation"

    def is_available(self, env: EnvironmentReport) -> bool:
        for r in env.available_runtimes:
            if r.runtime_id == "runtime.qemu-user":
                return r.installed
        return any(shutil.which(b) is not None for b in ARCH_QEMU_BINARY_MAP.values())

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
        sysroot = None
        if app.architecture == Architecture.ARM64:
            if os.path.exists("/usr/aarch64-linux-gnu"):
                sysroot = "/usr/aarch64-linux-gnu"
        elif app.architecture == Architecture.ARM:
            if os.path.exists("/usr/arm-linux-gnueabihf"):
                sysroot = "/usr/arm-linux-gnueabihf"

        return {
            "qemu_binary": resolved_bin,
            "sysroot": sysroot,
            "environment_variables": env_vars,
            "working_directory": os.path.dirname(app.artifact_path),
        }

    def execute(
        self,
        app: ApplicationDescription,
        context: Dict[str, Any],
        args: Optional[List[str]] = None,
        dry_run: bool = False,
    ) -> ExecutionResult:
        qemu_bin = context.get("qemu_binary", "qemu-aarch64")
        cmd = [qemu_bin]
        if context.get("sysroot"):
            cmd.extend(["-L", context["sysroot"]])
        cmd.append(app.artifact_path)
        if args:
            cmd.extend(args)

        if dry_run:
            return ExecutionResult(
                success=True,
                exit_code=0,
                stdout=f"[Dry Run] QEMU User plan verified:\nCommand: {' '.join(cmd)}",
                stderr="",
                execution_time_seconds=0.0,
                command=cmd,
            )

        start_time = time.time()
        try:
            res = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                cwd=context.get("working_directory"),
                env=context.get("environment_variables"),
                timeout=10,
            )
            elapsed = time.time() - start_time
            return ExecutionResult(
                success=res.returncode == 0,
                exit_code=res.returncode,
                stdout=res.stdout,
                stderr=res.stderr,
                execution_time_seconds=elapsed,
                command=cmd,
            )
        except subprocess.TimeoutExpired:
            return ExecutionResult(
                success=False,
                exit_code=-1,
                stdout="",
                stderr="QEMU execution timed out after 10 seconds",
                execution_time_seconds=10.0,
                command=cmd,
            )
        except Exception as e:
            return ExecutionResult(
                success=False,
                exit_code=-1,
                stdout="",
                stderr=str(e),
                execution_time_seconds=time.time() - start_time,
                command=cmd,
            )
