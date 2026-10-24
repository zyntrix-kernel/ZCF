"""
Wine Compatibility Layer Adapter.
Manages isolated WINEPREFIX directories, Windows DLL overrides, and WINEDEBUG diagnostics.
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
from zcf.runtimes.prefix_manager import WinePrefixManager


class WineAdapter(BaseRuntimeAdapter):
    """Adapter for executing Windows PE applications and MSI installers via Wine."""

    def __init__(self, prefix_manager: Optional[WinePrefixManager] = None, base_prefix_dir: Optional[str] = None):
        if prefix_manager:
            self.prefix_manager = prefix_manager
        elif base_prefix_dir:
            self.prefix_manager = WinePrefixManager(base_dir=base_prefix_dir)
        else:
            self.prefix_manager = WinePrefixManager()

    def get_id(self) -> str:
        return "runtime.wine"

    def get_name(self) -> str:
        return "Wine Compatibility Layer"

    def get_version(self, env: Optional[EnvironmentReport] = None) -> Optional[str]:
        if env:
            for r in env.available_runtimes:
                if r.runtime_id == "runtime.wine" and r.version:
                    return r.version

        wine_bin = shutil.which("wine64") or shutil.which("wine")
        if wine_bin:
            try:
                out = subprocess.check_output([wine_bin, "--version"], text=True, timeout=5).strip()
                return out
            except Exception:
                pass
        return None

    def get_capabilities(self) -> Dict[str, Any]:
        return {
            "supported_formats": [BinaryFormat.PE.value, "msi"],
            "supported_architectures": [Architecture.X86_64.value, Architecture.I386.value],
            "supported_workloads": [WorkloadType.DESKTOP_GUI.value, WorkloadType.CLI_TOOL.value, WorkloadType.INSTALLER.value],
            "requires_vulkan": False,
            "requires_wayland": False,
            "supports_sandboxing": True,
            "supports_virtual_display": True,
            "isolation_features": ["prefix", "winedebug", "dll_overrides", "bubblewrap"],
            "known_limitations": [
                "Kernel ring-0 anti-cheat drivers are unsupported in Wine userspace.",
                "DirectX 12 requires modern Vulkan 1.3 drivers on host GPU.",
            ],
        }

    def is_available(self, env: EnvironmentReport) -> bool:
        for r in env.available_runtimes:
            if r.runtime_id == "runtime.wine":
                return r.installed
        return shutil.which("wine64") is not None or shutil.which("wine") is not None

    def check_prerequisites(self, app: ApplicationDescription, env: EnvironmentReport) -> List[str]:
        missing: List[str] = []
        if not self.is_available(env):
            missing.append("Wine (wine64 or wine) package is not installed on host Linux system.")
        return missing

    def validate(self, app: ApplicationDescription, env: EnvironmentReport) -> ValidationResult:
        errors: List[str] = []
        warnings: List[str] = []

        is_msi = app.artifact_path.lower().endswith(".msi") or app.installer_format == "msi"
        if app.format != BinaryFormat.PE and not is_msi:
            errors.append(f"Wine requires Windows PE format or MSI installer; target has format '{app.format.value}'")

        if not self.is_available(env):
            errors.append("Wine (wine64 or wine) is not installed on this host system")

        if app.security_indicators.get("has_anti_cheat"):
            warnings.append(
                "Application contains anti-cheat signatures; kernel-level drivers may prevent Wine compatibility."
            )

        if app.is_managed:
            warnings.append("Application contains .NET CLI metadata; may require Wine Mono or dotnet runtime.")

        return ValidationResult(valid=len(errors) == 0, errors=errors, warnings=warnings)

    def prepare_environment(
        self, app: ApplicationDescription, config: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        prefix_path = self.prefix_manager.get_prefix_path(app.sha256)
        os.makedirs(prefix_path, exist_ok=True)

        env_vars = os.environ.copy()
        env_vars["WINEPREFIX"] = prefix_path
        env_vars["WINEDEBUG"] = config.get("winedebug", "-all") if config else "-all"
        env_vars["WINEARCH"] = "win64" if app.architecture == Architecture.X86_64 else "win32"

        # Apply DLL overrides if specified
        if config and "dll_overrides" in config:
            env_vars = self.prefix_manager.set_dll_overrides(env_vars, config["dll_overrides"])

        if config and "environment_variables" in config:
            env_vars.update(config["environment_variables"])

        return {
            "prefix_path": prefix_path,
            "environment_variables": env_vars,
            "working_directory": os.path.dirname(os.path.abspath(app.artifact_path)),
        }

    def build_command(
        self, app: ApplicationDescription, context: Dict[str, Any], args: Optional[List[str]] = None
    ) -> List[str]:
        wine_bin = shutil.which("wine64") or shutil.which("wine") or "wine"
        abs_target = os.path.abspath(app.artifact_path)
        app_args = args or []

        # Check if target is an MSI installer
        if abs_target.lower().endswith(".msi") or app.installer_format == "msi":
            return [wine_bin, "msiexec", "/i", abs_target] + app_args

        return [wine_bin, abs_target] + app_args

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

    def cleanup(self, app: ApplicationDescription, context: Dict[str, Any]) -> None:
        prefix_path = context.get("prefix_path")
        if prefix_path and context.get("ephemeral", False):
            self.prefix_manager.cleanup_prefix(prefix_path)
