"""
Wine Compatibility Layer Adapter.
Manages isolated WINEPREFIX directories, Windows DLL overrides, and WINEDEBUG diagnostics.
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


class WineAdapter(RuntimeAdapterInterface):
    """Adapter for executing Windows PE applications via Wine."""

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

    def is_available(self, env: EnvironmentReport) -> bool:
        for r in env.available_runtimes:
            if r.runtime_id == "runtime.wine" and r.installed:
                return True
        return shutil.which("wine64") is not None or shutil.which("wine") is not None

    def validate(self, app: ApplicationDescription, env: EnvironmentReport) -> ValidationResult:
        errors: List[str] = []
        warnings: List[str] = []

        if app.format != BinaryFormat.PE:
            errors.append(f"Wine requires Windows PE format; target has format '{app.format.value}'")

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

        # Apply DLL overrides if specified
        if config and "dll_overrides" in config:
            env_vars = self.prefix_manager.set_dll_overrides(env_vars, config["dll_overrides"])

        if config and "environment_variables" in config:
            env_vars.update(config["environment_variables"])

        return {
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
        wine_bin = shutil.which("wine64") or shutil.which("wine") or "wine"
        cmd = [wine_bin, app.artifact_path] + (args or [])

        if dry_run:
            return ExecutionResult(
                success=True,
                exit_code=0,
                stdout=f"[Dry Run] Prepared Wine prefix: {context.get('prefix_path')}\nCommand: {' '.join(cmd)}",
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
                isolated_env_path=context.get("prefix_path"),
            )
        except subprocess.TimeoutExpired:
            return ExecutionResult(
                success=False,
                exit_code=-1,
                stdout="",
                stderr="Wine execution timed out after 15 seconds",
                execution_time_seconds=15.0,
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
