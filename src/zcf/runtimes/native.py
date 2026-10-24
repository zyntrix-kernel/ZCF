"""
Native Host Runtime Adapter.
Executes binaries and scripts matching the host operating system and CPU architecture.
"""

from __future__ import annotations

import os
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


class NativeAdapter(RuntimeAdapterInterface):
    """Adapter for native host execution."""

    def get_id(self) -> str:
        return "runtime.native"

    def get_name(self) -> str:
        return "Native Host Runtime"

    def is_available(self, env: EnvironmentReport) -> bool:
        return True

    def validate(self, app: ApplicationDescription, env: EnvironmentReport) -> ValidationResult:
        errors: List[str] = []
        warnings: List[str] = []

        # Validate format against host OS
        if env.os_name == "linux":
            if app.format == BinaryFormat.PE:
                errors.append("Windows PE executables cannot run natively on Linux; requires Wine or Proton.")
            elif app.format == BinaryFormat.ELF:
                if app.architecture != Architecture.ALL and app.architecture.value != env.architecture:
                    errors.append(
                        f"Architecture mismatch: binary is {app.architecture.value}, host is {env.architecture}; requires emulation."
                    )
        elif env.os_name == "windows":
            if app.format == BinaryFormat.ELF:
                errors.append("Linux ELF executables cannot run natively on Windows host; requires WSL2 or VM.")
            elif app.format == BinaryFormat.PE:
                if app.architecture.value not in ("x86_64", "i386", env.architecture):
                    errors.append(f"Architecture mismatch: {app.architecture.value} on {env.architecture} Windows")

        return ValidationResult(valid=len(errors) == 0, errors=errors, warnings=warnings)

    def prepare_environment(
        self, app: ApplicationDescription, config: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        env_vars = os.environ.copy()
        if config and "environment_variables" in config:
            env_vars.update(config["environment_variables"])
        return {
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
        cmd = [app.artifact_path] + (args or [])
        if dry_run:
            return ExecutionResult(
                success=True,
                exit_code=0,
                stdout="[Dry Run] Validated native command plan: " + " ".join(cmd),
                stderr="",
                execution_time_seconds=0.0,
                command=cmd,
                isolated_env_path=None,
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
                stderr="Execution timed out after 10 seconds",
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
