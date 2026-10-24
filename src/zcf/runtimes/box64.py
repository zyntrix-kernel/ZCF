"""
Box64 Dynamic Translation Adapter for ZCF.
Executes x86_64 Linux binaries on ARM64 hosts with wrapped native hardware libraries.
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


class Box64Adapter(BaseRuntimeAdapter):
    """Adapter for running x86_64 Linux executables on ARM64 Linux hosts."""

    def get_id(self) -> str:
        return "runtime.box64"

    def get_name(self) -> str:
        return "Box64 Dynamic x86_64 Emulator"

    def get_version(self, env: Optional[EnvironmentReport] = None) -> Optional[str]:
        if env:
            for r in env.available_runtimes:
                if r.runtime_id == "runtime.box64" and r.version:
                    return r.version

        box_bin = shutil.which("box64")
        if box_bin:
            try:
                out = subprocess.check_output([box_bin, "-v"], text=True, timeout=5).strip()
                return out
            except Exception:
                pass
        return None

    def get_capabilities(self) -> Dict[str, Any]:
        return {
            "supported_formats": [BinaryFormat.ELF.value],
            "supported_architectures": [Architecture.X86_64.value],
            "supported_workloads": [WorkloadType.DESKTOP_GUI.value, WorkloadType.GAME.value, WorkloadType.CLI_TOOL.value],
            "requires_vulkan": False,
            "requires_wayland": False,
            "supports_sandboxing": True,
            "supports_virtual_display": True,
            "isolation_features": ["dynarec", "library_wrapping", "bubblewrap"],
            "known_limitations": [
                "Only translates x86_64 binaries (32-bit x86 requires box86).",
                "Optimized specifically for ARM64 CPU architectures.",
            ],
        }

    def is_available(self, env: EnvironmentReport) -> bool:
        for r in env.available_runtimes:
            if r.runtime_id == "runtime.box64":
                return r.installed
        return shutil.which("box64") is not None

    def check_prerequisites(self, app: ApplicationDescription, env: EnvironmentReport) -> List[str]:
        missing: List[str] = []
        if not self.is_available(env):
            missing.append("Box64 dynamic translator binary ('box64') is not installed.")
        return missing

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
            "working_directory": os.path.dirname(os.path.abspath(app.artifact_path)),
        }

    def build_command(
        self, app: ApplicationDescription, context: Dict[str, Any], args: Optional[List[str]] = None
    ) -> List[str]:
        box_bin = context.get("box64_binary") or shutil.which("box64") or "box64"
        abs_target = os.path.abspath(app.artifact_path)
        return [box_bin, abs_target] + (args or [])

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
