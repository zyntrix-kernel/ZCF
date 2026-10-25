"""
Valve Proton Compatibility Adapter for ZCF.
Orchestrates Proton runners, DXVK Vulkan translations, and Steam compatibility data paths.
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

PROTON_SEARCH_PATHS = [
    os.path.expanduser("~/.steam/root/compatibilitytools.d"),
    os.path.expanduser("~/.local/share/Steam/compatibilitytools.d"),
    os.path.expanduser("~/.steam/steam/steamapps/common"),
    os.path.expanduser("~/.local/share/Steam/steamapps/common"),
    "/usr/share/steam/compatibilitytools.d",
]


class ProtonAdapter(BaseRuntimeAdapter):
    """Adapter for running Windows gaming and high-performance applications via Proton."""

    def __init__(self, prefix_manager: Optional[WinePrefixManager] = None):
        self.prefix_manager = prefix_manager or WinePrefixManager(base_dir=os.path.expanduser("~/.zcf/proton_prefixes"))

    def get_id(self) -> str:
        return "runtime.proton"

    def get_name(self) -> str:
        return "Valve Proton Gaming Runtime"

    def get_version(self, env: Optional[EnvironmentReport] = None) -> Optional[str]:
        if env:
            for r in env.available_runtimes:
                if r.runtime_id == "runtime.proton" and r.version:
                    return r.version

        proton_bin = self._find_proton_binary()
        if proton_bin:
            version_file = os.path.join(os.path.dirname(proton_bin), "version")
            if os.path.exists(version_file):
                try:
                    with open(version_file, "r", encoding="utf-8") as f:
                        return f.read().strip()
                except Exception:
                    pass
            return os.path.basename(os.path.dirname(proton_bin))
        return None

    def get_capabilities(self) -> Dict[str, Any]:
        return {
            "supported_formats": [BinaryFormat.PE.value],
            "supported_architectures": [Architecture.X86_64.value, Architecture.I386.value],
            "supported_workloads": [WorkloadType.GAME.value, WorkloadType.DESKTOP_GUI.value],
            "requires_vulkan": True,
            "requires_wayland": False,
            "supports_sandboxing": True,
            "supports_virtual_display": True,
            "isolation_features": ["steam_compat_data", "dxvk", "bubblewrap"],
            "known_limitations": [
                "Requires Vulkan 1.3 host driver for optimal DXVK translation.",
                "Steam-dependent DRM may require Steam runtime environment.",
            ],
        }

    def _find_proton_binary(self) -> Optional[str]:
        # 1. PATH lookup
        on_path = shutil.which("proton")
        if on_path:
            return on_path

        # 2. Known Steam directories
        for base_path in PROTON_SEARCH_PATHS:
            if not os.path.exists(base_path):
                continue
            for entry in os.listdir(base_path):
                candidate = os.path.join(base_path, entry, "proton")
                if os.path.isfile(candidate) and os.access(candidate, os.X_OK):
                    return candidate
        return None

    def is_available(self, env: EnvironmentReport) -> bool:
        for r in env.available_runtimes:
            if r.runtime_id == "runtime.proton":
                return r.installed
        return self._find_proton_binary() is not None

    def check_prerequisites(self, app: ApplicationDescription, env: EnvironmentReport) -> List[str]:
        missing: List[str] = []
        if not self._find_proton_binary():
            missing.append("Proton runner script not found in Steam compatibility directories.")
        if not env.graphics_capabilities.get("vulkan_supported", False):
            missing.append("Vulkan driver not detected; required for Proton DXVK translation layer.")
        return missing

    def validate(self, app: ApplicationDescription, env: EnvironmentReport) -> ValidationResult:
        errors: List[str] = []
        warnings: List[str] = []

        if app.format != BinaryFormat.PE:
            errors.append(f"Proton requires Windows PE executable format; target is '{app.format.value}'")

        proton_bin = self._find_proton_binary()
        if not proton_bin:
            errors.append("Proton executable not found in standard Steam compatibility paths")

        if not env.graphics_capabilities.get("vulkan_supported", False):
            errors.append("Proton requires Vulkan driver for DXVK acceleration; host lacks Vulkan support.")

        return ValidationResult(valid=len(errors) == 0, errors=errors, warnings=warnings)

    def prepare_environment(
        self, app: ApplicationDescription, config: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        is_dry_run = config.get("dry_run", False) if config else False
        prefix_path = self.prefix_manager.get_prefix_path(app.sha256)
        if not is_dry_run:
            os.makedirs(prefix_path, exist_ok=True)
            self.prefix_manager.record_usage(
                prefix_path=prefix_path,
                app_name=app.file_name or "Windows Game / Application",
                app_sha256=app.sha256,
                is_persistent=True,
                architecture="win64" if app.architecture == Architecture.X86_64 else "win32",
                runtime_type="proton",
            )

        env_vars = os.environ.copy()
        env_vars["STEAM_COMPAT_DATA_PATH"] = prefix_path
        env_vars["STEAM_COMPAT_CLIENT_INSTALL_PATH"] = os.path.expanduser("~/.steam/root")
        env_vars["PROTON_USE_WINED3D"] = "0" if (config is None or config.get("use_dxvk", True)) else "1"

        if config and "environment_variables" in config:
            env_vars.update(config["environment_variables"])

        return {
            "proton_binary": self._find_proton_binary() or "proton",
            "prefix_path": prefix_path,
            "environment_variables": env_vars,
            "working_directory": os.path.dirname(os.path.abspath(app.artifact_path)),
        }

    def build_command(
        self, app: ApplicationDescription, context: Dict[str, Any], args: Optional[List[str]] = None
    ) -> List[str]:
        proton_bin = context.get("proton_binary") or self._find_proton_binary() or "proton"
        abs_target = os.path.abspath(app.artifact_path)
        return [proton_bin, "run", abs_target] + (args or [])

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
