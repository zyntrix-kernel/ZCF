"""
Box64 Dynamic Translation Adapter for ZCF.
Executes x86_64 Linux binaries on ARM64 hosts with wrapped native hardware libraries.
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


class Box64Adapter(RuntimeAdapterInterface):
    """Adapter for running x86_64 Linux executables on ARM64 Linux hosts."""

    def get_id(self) -> str:
        return "runtime.box64"

    def get_name(self) -> str:
        return "Box64 Dynamic x86_64 Emulator"

    def is_available(self, env: EnvironmentReport) -> bool:
        for r in env.available_runtimes:
            if r.runtime_id == "runtime.box64":
                return r.installed
        return shutil.which("box64") is not None

    def validate(self, app: ApplicationDescription, env: EnvironmentReport) -> ValidationResult:
        errors: List[str] = []
        warnings: List[str] = []

        if app.format != BinaryFormat.ELF:
            errors.append(f"Box64 requires Linux ELF format; target is '{app.format.value}'")

        if app.architecture != Architecture.X86_64:
            errors.append(f"Box64 exclusively translates x86_64 binaries; target is '{app.architecture.value}'")

        if not self.is_available(env):
            errors.append("Box64 binary ('box64') is not installed on host system")

        if env.architecture != "arm64":
            warnings.append(
                f"Host CPU architecture is '{env.architecture}'; Box64 is optimized for ARM64 hardware."
            )

        return ValidationResult(valid=len(errors) == 0, errors=errors, warnings=warnings)

    def prepare_environment(
        self, app: ApplicationDescription, config: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        env_vars = os.environ.copy()
        env_vars["BOX64_LOG"] = str(config.get("log_level", 0)) if config else "0"
        env_vars["BOX64_DYNAREC"] = "1"
        env_vars["BOX64_SHOWSEGV"] = "1"

        if config and "environment_variables" in config:
            env_vars.update(config["environment_variables"])

        return {
            "box64_binary": shutil.which("box64") or "box64",
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
        box_bin = context.get("box64_binary", "box64")
        cmd = [box_bin, app.artifact_path] + (args or [])

        if dry_run:
            return ExecutionResult(
                success=True,
                exit_code=0,
                stdout=f"[Dry Run] Prepared Box64 execution:\nCommand: {' '.join(cmd)}",
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
                timeout=15,
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
        except Exception as e:
            return ExecutionResult(
                success=False,
                exit_code=-1,
                stdout="",
                stderr=str(e),
                execution_time_seconds=time.time() - start_time,
                command=cmd,
            )
