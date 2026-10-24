"""
Android Container Runtime Adapter for ZCF.
Orchestrates Waydroid / LXC container sessions for executing Android APKs.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import time
from typing import Any, Dict, List, Optional

from zcf.core.models import (
    ApplicationDescription,
    BinaryFormat,
    EnvironmentReport,
    ExecutionResult,
    ValidationResult,
)
from zcf.runtimes.base import RuntimeAdapterInterface


class AndroidContainerAdapter(RuntimeAdapterInterface):
    """Adapter for running Android APKs via Waydroid container orchestration."""

    def get_id(self) -> str:
        return "runtime.android"

    def get_name(self) -> str:
        return "Waydroid Android Container Runtime"

    def is_available(self, env: EnvironmentReport) -> bool:
        for r in env.available_runtimes:
            if r.runtime_id == "runtime.android":
                return r.installed
        return shutil.which("waydroid") is not None

    def validate(self, app: ApplicationDescription, env: EnvironmentReport) -> ValidationResult:
        errors: List[str] = []
        warnings: List[str] = []

        if app.format != BinaryFormat.ARCHIVE or app.runtime_family != "android-art":
            errors.append("Android Container Adapter requires Android APK package format")

        if not self.is_available(env):
            errors.append("Waydroid CLI ('waydroid') is not installed on this host system")

        if not os.path.exists("/dev/binder"):
            warnings.append("Kernel binder IPC driver (/dev/binder) not detected; required for Android IPC.")

        if env.display_server.value != "wayland":
            warnings.append("Waydroid requires an active Wayland display compositor for surface rendering.")

        return ValidationResult(valid=len(errors) == 0, errors=errors, warnings=warnings)

    def prepare_environment(
        self, app: ApplicationDescription, config: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        return {
            "waydroid_binary": shutil.which("waydroid") or "waydroid",
            "environment_variables": os.environ.copy(),
            "working_directory": os.path.dirname(app.artifact_path),
        }

    def execute(
        self,
        app: ApplicationDescription,
        context: Dict[str, Any],
        args: Optional[List[str]] = None,
        dry_run: bool = False,
    ) -> ExecutionResult:
        waydroid_bin = context.get("waydroid_binary", "waydroid")
        cmd = [waydroid_bin, "app", "install", app.artifact_path]

        if dry_run:
            return ExecutionResult(
                success=True,
                exit_code=0,
                stdout=f"[Dry Run] Prepared Waydroid APK container deployment:\nCommand: {' '.join(cmd)}",
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
                timeout=30,
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
