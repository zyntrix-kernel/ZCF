"""
Native Host Runtime Adapter.
Executes binaries and scripts matching the host operating system and CPU architecture.
"""

from __future__ import annotations

import os
import shutil
import sys
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


class NativeAdapter(BaseRuntimeAdapter):
    """Adapter for native host execution."""

    def get_id(self) -> str:
        return "runtime.native"

    def get_name(self) -> str:
        return "Native Host Runtime"

    def get_version(self, env: Optional[EnvironmentReport] = None) -> Optional[str]:
        if env:
            return f"{env.os_name} {env.kernel_version} ({env.architecture})"
        return "native-kernel"

    def get_capabilities(self) -> Dict[str, Any]:
        return {
            "supported_formats": [BinaryFormat.ELF.value, BinaryFormat.SCRIPT.value],
            "supported_architectures": [Architecture.X86_64.value, Architecture.ARM64.value, Architecture.ALL.value],
            "supported_workloads": [w.value for w in WorkloadType],
            "requires_vulkan": False,
            "requires_wayland": False,
            "supports_sandboxing": True,
            "supports_virtual_display": True,
            "isolation_features": ["bubblewrap", "namespaces"],
            "known_limitations": ["Host architecture must match target binary."],
        }

    def is_available(self, env: EnvironmentReport) -> bool:
        return True

    def validate(self, app: ApplicationDescription, env: EnvironmentReport) -> ValidationResult:
        errors: List[str] = []
        warnings: List[str] = []

        # Validate format against host OS
        if env.os_name == "linux":
            if app.format == BinaryFormat.PE:
                errors.append("Windows PE executables cannot run natively on Linux; requires Wine or Proton.")
            elif app.format == BinaryFormat.ARCHIVE:
                errors.append(f"Archive / package format '{app.format.value}' cannot execute natively on Linux; requires container or runtime.")
            elif app.format == BinaryFormat.ELF:
                if app.architecture != Architecture.ALL and app.architecture.value != env.architecture:
                    errors.append(
                        f"Architecture mismatch: binary is {app.architecture.value}, host is {env.architecture}; requires emulation."
                    )
            elif app.format not in (BinaryFormat.ELF, BinaryFormat.SCRIPT):
                errors.append(f"Format '{app.format.value}' is not supported for native Linux execution.")
        elif env.os_name == "windows":
            if app.format == BinaryFormat.ELF:
                errors.append("Linux ELF executables cannot run natively on Windows host; requires WSL2 or VM.")
            elif app.format == BinaryFormat.ARCHIVE:
                errors.append(f"Archive / package format '{app.format.value}' cannot execute natively on Windows.")
            elif app.format == BinaryFormat.PE:
                if app.architecture.value not in ("x86_64", "i386", env.architecture):
                    errors.append(f"Architecture mismatch: {app.architecture.value} on {env.architecture} Windows")
            elif app.format not in (BinaryFormat.PE, BinaryFormat.SCRIPT):
                errors.append(f"Format '{app.format.value}' is not supported for native Windows execution.")

        return ValidationResult(valid=len(errors) == 0, errors=errors, warnings=warnings)

    def prepare_environment(
        self, app: ApplicationDescription, config: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        env_vars = os.environ.copy()
        if config and "environment_variables" in config:
            env_vars.update(config["environment_variables"])
        return {
            "environment_variables": env_vars,
            "working_directory": os.path.dirname(os.path.abspath(app.artifact_path)),
        }

    def build_command(
        self, app: ApplicationDescription, context: Dict[str, Any], args: Optional[List[str]] = None
    ) -> List[str]:
        target = os.path.abspath(app.artifact_path)
        app_args = args or []

        # Determine if script requires explicit interpreter
        if app.format == BinaryFormat.SCRIPT:
            if target.endswith(".py"):
                interp = sys.executable or shutil.which("python3") or shutil.which("python") or "python3"
                return [interp, target] + app_args
            elif target.endswith(".sh"):
                interp = shutil.which("bash") or shutil.which("sh") or "bash"
                return [interp, target] + app_args

        return [target] + app_args

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
