"""
Android Container Runtime Adapter for ZCF.
Orchestrates Waydroid / LXC container sessions for executing Android APKs.
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


class AndroidContainerAdapter(BaseRuntimeAdapter):
    """Adapter for running Android APKs via Waydroid container orchestration."""

    def get_id(self) -> str:
        return "runtime.android"

    def get_name(self) -> str:
        return "Waydroid Android Container Runtime"

    def get_version(self, env: Optional[EnvironmentReport] = None) -> Optional[str]:
        if env:
            for r in env.available_runtimes:
                if r.runtime_id == "runtime.android" and r.version:
                    return r.version

        waydroid_bin = shutil.which("waydroid")
        if waydroid_bin:
            try:
                out = subprocess.check_output([waydroid_bin, "version"], text=True, timeout=5).strip()
                return out
            except Exception:
                pass
        return None

    def get_capabilities(self) -> Dict[str, Any]:
        return {
            "supported_formats": [BinaryFormat.ARCHIVE.value, "apk"],
            "supported_architectures": [Architecture.UNIVERSAL.value, Architecture.ARM64.value, Architecture.X86_64.value],
            "supported_workloads": [WorkloadType.DESKTOP_GUI.value, WorkloadType.GAME.value],
            "requires_vulkan": False,
            "requires_wayland": True,
            "supports_sandboxing": True,
            "supports_virtual_display": False,
            "isolation_features": ["lxc_container", "binder_namespace"],
            "known_limitations": [
                "Requires Linux kernel ashmem and binder drivers (/dev/binder).",
                "Requires active Wayland session compositor.",
            ],
        }

    def is_available(self, env: EnvironmentReport) -> bool:
        for r in env.available_runtimes:
            if r.runtime_id == "runtime.android":
                return r.installed
        return shutil.which("waydroid") is not None

    def check_prerequisites(self, app: ApplicationDescription, env: EnvironmentReport) -> List[str]:
        missing: List[str] = []
        if not self.is_available(env):
            missing.append("Waydroid container package ('waydroid') is not installed.")
        if not os.path.exists("/dev/binder"):
            missing.append("Kernel binder IPC driver (/dev/binder) is missing on host kernel.")
        if env.display_server.value != "wayland":
            missing.append("Host is not running an active Wayland display compositor.")
        return missing

    def validate(self, app: ApplicationDescription, env: EnvironmentReport) -> ValidationResult:
        errors: List[str] = []
        warnings: List[str] = []

        is_apk = (app.format == BinaryFormat.ARCHIVE and app.runtime_family == "android-art") or app.artifact_path.lower().endswith(".apk")
        if not is_apk:
            errors.append("Android Container Adapter requires Android APK package format")

        if not self.is_available(env):
            errors.append("Waydroid CLI ('waydroid') is not installed on this host system")

        if not os.path.exists("/dev/binder"):
            errors.append("Kernel binder IPC driver (/dev/binder) not detected; required for Android IPC.")

        if env.display_server.value != "wayland":
            errors.append("Waydroid requires an active Wayland display compositor for surface rendering.")

        return ValidationResult(valid=len(errors) == 0, errors=errors, warnings=warnings)

    def prepare_environment(
        self, app: ApplicationDescription, config: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        config = config or {}
        action = config.get("action", "install_and_launch" if app.entry_point else "install")
        package_name = config.get("package_name") or app.entry_point
        return {
            "waydroid_binary": shutil.which("waydroid") or "waydroid",
            "environment_variables": os.environ.copy(),
            "working_directory": os.path.dirname(os.path.abspath(app.artifact_path)),
            "action": action,
            "package_name": package_name,
        }

    def build_command(
        self, app: ApplicationDescription, context: Dict[str, Any], args: Optional[List[str]] = None
    ) -> List[str]:
        waydroid_bin = context.get("waydroid_binary") or shutil.which("waydroid") or "waydroid"
        action = context.get("action", "install")
        target_package = context.get("package_name") or app.entry_point
        if action == "launch" and target_package:
            return [waydroid_bin, "app", "launch", target_package]
        abs_target = os.path.abspath(app.artifact_path)
        return [waydroid_bin, "app", "install", abs_target]

    def build_launch_command(self, package_name: str) -> List[str]:
        """Builds command to launch an installed Android package inside Waydroid container."""
        waydroid_bin = shutil.which("waydroid") or "waydroid"
        return [waydroid_bin, "app", "launch", package_name]

    def execute(
        self,
        app: ApplicationDescription,
        context: Dict[str, Any],
        args: Optional[List[str]] = None,
        dry_run: bool = False,
        stream_callback: Optional[Callable[[str], None]] = None,
        timeout: Optional[int] = None,
    ) -> ExecutionResult:
        action = context.get("action", "install_and_launch" if app.entry_point else "install")
        cmd = self.build_command(app, context, args)
        if dry_run:
            desc = "APK container installation and launch" if action == "install_and_launch" else ("APK application launch" if action == "launch" else "APK package installation")
            return ExecutionResult(
                success=True,
                exit_code=0,
                stdout=f"[Dry Run] Prepared Waydroid {desc}:\nCommand: {' '.join(cmd)}",
                stderr="",
                execution_time_seconds=0.0,
                command=cmd,
                effective_runtime=self.get_id(),
            )

        if action == "install_and_launch" and app.entry_point:
            # 1. First install the package
            install_cmd = [shutil.which("waydroid") or "waydroid", "app", "install", os.path.abspath(app.artifact_path)]
            install_res = self._execute_process(
                cmd=install_cmd,
                context=context,
                dry_run=dry_run,
                stream_callback=stream_callback,
                timeout=timeout,
            )
            if not install_res.success or install_res.exit_code != 0:
                install_res.stdout = f"[Waydroid Installation Failed]\n{install_res.stdout}"
                return install_res

            # 2. Launch installed application activity
            launch_cmd = self.build_launch_command(app.entry_point)
            launch_res = self._execute_process(
                cmd=launch_cmd,
                context=context,
                dry_run=dry_run,
                stream_callback=stream_callback,
                timeout=timeout,
            )
            launch_res.stdout = f"[Waydroid APK Installed & Launched: {app.entry_point}]\n{launch_res.stdout}"
            return launch_res

        # Default action: install only (or launch only if action == "launch")
        res = self._execute_process(
            cmd=cmd,
            context=context,
            dry_run=dry_run,
            stream_callback=stream_callback,
            timeout=timeout,
        )
        if res.success and res.exit_code == 0:
            if action == "install":
                msg = f"\n[ZCF Android] APK package '{app.file_name}' installed successfully inside Waydroid."
                if app.entry_point:
                    msg += f"\nLaunch with: zcf run --runtime runtime.android --action launch {app.entry_point}"
                res.stdout += msg
            elif action == "launch":
                res.stdout += f"\n[ZCF Android] Application '{app.entry_point}' launched inside Waydroid."
        return res
