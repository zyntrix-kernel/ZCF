"""
Valve Proton Compatibility Adapter for ZCF.
Orchestrates Proton runners, DXVK Vulkan translations, and Steam compatibility data paths.
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
from zcf.runtimes.prefix_manager import WinePrefixManager


PROTON_SEARCH_PATHS = [
    os.path.expanduser("~/.steam/root/compatibilitytools.d"),
    os.path.expanduser("~/.local/share/Steam/compatibilitytools.d"),
    os.path.expanduser("~/.steam/steam/steamapps/common"),
    os.path.expanduser("~/.local/share/Steam/steamapps/common"),
    "/usr/share/steam/compatibilitytools.d",
]


class ProtonAdapter(RuntimeAdapterInterface):
    """Adapter for running Windows gaming and high-performance applications via Proton."""

    def __init__(self, prefix_manager: Optional[WinePrefixManager] = None):
        self.prefix_manager = prefix_manager or WinePrefixManager(base_dir=os.path.expanduser("~/.zcf/proton_prefixes"))

    def get_id(self) -> str:
        return "runtime.proton"

    def get_name(self) -> str:
        return "Valve Proton Gaming Runtime"

    def is_available(self, env: EnvironmentReport) -> bool:
        for r in env.available_runtimes:
            if r.runtime_id == "runtime.proton" and r.installed:
                return True
        return self._find_proton_binary() is not None

    def validate(self, app: ApplicationDescription, env: EnvironmentReport) -> ValidationResult:
        errors: List[str] = []
        warnings: List[str] = []

        if app.format != BinaryFormat.PE:
            errors.append(f"Proton requires Windows PE executable format; target is '{app.format.value}'")

        proton_bin = self._find_proton_binary()
        if not proton_bin:
            errors.append("Proton executable not found in standard Steam compatibility paths")

        if not env.graphics_capabilities.get("vulkan_supported", False):
            warnings.append(
                "Host system lacks verified Vulkan driver; DXVK performance may fall back to CPU or fail."
            )

        return ValidationResult(valid=len(errors) == 0, errors=errors, warnings=warnings)

    def prepare_environment(
        self, app: ApplicationDescription, config: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        prefix_path = self.prefix_manager.get_prefix_path(app.sha256)
        os.makedirs(prefix_path, exist_ok=True)

        env_vars = os.environ.copy()
        env_vars["STEAM_COMPAT_DATA_PATH"] = prefix_path
        env_vars["STEAM_COMPAT_CLIENT_INSTALL_PATH"] = os.path.expanduser("~/.steam/root")
        env_vars["PROTON_USE_WINED3D"] = "0" if config and config.get("use_dxvk", True) else "1"

        if config and "environment_variables" in config:
            env_vars.update(config["environment_variables"])

        return {
            "proton_binary": self._find_proton_binary() or "proton",
            "prefix_path": prefix_path,
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
        proton_bin = context.get("proton_binary", "proton")
        cmd = [proton_bin, "run", app.artifact_path] + (args or [])

        if dry_run:
            return ExecutionResult(
                success=True,
                exit_code=0,
                stdout=f"[Dry Run] Prepared Proton environment at {context.get('prefix_path')}\nCommand: {' '.join(cmd)}",
                stderr="",
                execution_time_seconds=0.0,
                command=cmd,
                isolated_env_path=context.get("prefix_path"),
            )

        start_time = time.time()
        try:
            res = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                cwd=context.get("working_directory"),
                env=context.get("environment_variables"),
                timeout=20,
            )
            elapsed = time.time() - start_time
            return ExecutionResult(
                success=res.returncode == 0,
                exit_code=res.returncode,
                stdout=res.stdout,
                stderr=res.stderr,
                execution_time_seconds=elapsed,
                command=cmd,
                isolated_env_path=context.get("prefix_path"),
            )
        except Exception as e:
            return ExecutionResult(
                success=False,
                exit_code=-1,
                stdout="",
                stderr=str(e),
                execution_time_seconds=time.time() - start_time,
                command=cmd,
                isolated_env_path=context.get("prefix_path"),
            )

    def _find_proton_binary(self) -> Optional[str]:
        # Check PATH first
        in_path = shutil.which("proton")
        if in_path:
            return in_path

        # Scan Steam search directories
        for base in PROTON_SEARCH_PATHS:
            if os.path.exists(base):
                for entry in os.listdir(base):
                    if entry.lower().startswith("proton"):
                        p_bin = os.path.join(base, entry, "proton")
                        if os.path.exists(p_bin) and os.access(p_bin, os.X_OK):
                            return p_bin
        return None
