"""
Windows Component & Runtime Manager for ZCF.
Provides verified installation of Visual C++, DirectX, Wine Mono, and DXVK runtimes into managed Wine prefixes.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

from zcf.execution.installer import PackageInstallerBridge


@dataclass
class ComponentDefinition:
    key: str
    name: str
    description: str
    winetricks_verb: str
    verification_files: List[str]
    required_architecture: Optional[str] = None


@dataclass
class ComponentInstallResult:
    success: bool
    component_key: str
    component_name: str
    verified: bool
    output: str
    error: Optional[str] = None


class WindowsComponentManager:
    """Manages installation, verification, and diagnostics of Windows runtime components."""

    COMPONENTS: Dict[str, ComponentDefinition] = {
        "vcrun2022": ComponentDefinition(
            key="vcrun2022",
            name="Microsoft Visual C++ 2015-2022 Runtime",
            description="C/C++ standard runtime libraries required by modern Windows software and games.",
            winetricks_verb="vcrun2022",
            verification_files=["vcruntime140.dll", "msvcp140.dll"],
        ),
        "d3dx9": ComponentDefinition(
            key="d3dx9",
            name="Microsoft DirectX End-User Runtimes (D3DX9)",
            description="DirectX 9 legacy helper libraries required by 3D games and multimedia applications.",
            winetricks_verb="d3dx9",
            verification_files=["d3dx9_43.dll"],
        ),
        "mono": ComponentDefinition(
            key="mono",
            name="Microsoft .NET Desktop Runtime (Wine Mono)",
            description="Open-source implementation of the Microsoft .NET Framework for Wine applications.",
            winetricks_verb="mono",
            verification_files=["mscoree.dll"],
        ),
        "dxvk": ComponentDefinition(
            key="dxvk",
            name="Vulkan DXVK Acceleration Layer",
            description="Translates DirectX 9/10/11 graphics API calls to ultra-fast native Vulkan.",
            winetricks_verb="dxvk",
            verification_files=["dxgi.dll", "d3d11.dll"],
        ),
    }

    def __init__(self):
        self.installer_bridge = PackageInstallerBridge()

    def list_components(self) -> List[ComponentDefinition]:
        return list(self.COMPONENTS.values())

    def get_component(self, key: str) -> Optional[ComponentDefinition]:
        return self.COMPONENTS.get(key)

    def is_installed_in_prefix(self, prefix_path: str, component_key: str) -> bool:
        """Verifies if the component's signature files exist inside the target prefix."""
        comp = self.get_component(component_key)
        if not comp or not os.path.exists(prefix_path):
            return False

        # Check filesystem verification DLLs in system32 and syswow64
        system32 = os.path.join(prefix_path, "drive_c", "windows", "system32")
        syswow64 = os.path.join(prefix_path, "drive_c", "windows", "syswow64")

        found = False
        for v_file in comp.verification_files:
            p32 = os.path.join(system32, v_file)
            p64 = os.path.join(syswow64, v_file)
            if os.path.exists(p32) or os.path.exists(p64):
                found = True
                break

        if found:
            return True

        # Check prefix metadata file as secondary verification
        meta_file = os.path.join(prefix_path, "prefix_meta.json")
        if os.path.exists(meta_file):
            try:
                with open(meta_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    if component_key in data.get("installed_components", []):
                        return True
            except Exception:
                pass

        return False

    def install(
        self,
        prefix_path: str,
        component_key: str,
        progress_callback: Optional[Callable[[str], None]] = None,
    ) -> ComponentInstallResult:
        """Installs and verifies the specified component inside the prefix."""
        comp = self.get_component(component_key)
        if not comp:
            return ComponentInstallResult(
                success=False,
                component_key=component_key,
                component_name=component_key,
                verified=False,
                output="",
                error=f"Unknown component key: {component_key}",
            )

        os.makedirs(prefix_path, exist_ok=True)
        captured_output: List[str] = []

        def log(msg: str):
            captured_output.append(msg)
            if progress_callback:
                progress_callback(msg)

        log(f"[ZCF Component Manager] Installing '{comp.name}' into prefix: {prefix_path}")

        # 1. Check if Winetricks is available on host
        winetricks_bin = shutil.which("winetricks")
        if not winetricks_bin and os.environ.get("ZCF_NON_INTERACTIVE") != "1":
            log("[ZCF Component Manager] 'winetricks' not found on PATH. Attempting automated package install...")
            installed = self.installer_bridge.install("winetricks", interactive=False)
            winetricks_bin = shutil.which("winetricks")

        if not winetricks_bin:
            err = (
                f"Winetricks is required to install component '{comp.name}' ({comp.key}), "
                f"but is not installed on this system. Install it via: "
                f"{' '.join(self.installer_bridge.get_install_command('winetricks') or ['winetricks'])}"
            )
            log(f"[ZCF Component Manager Error] {err}")
            return ComponentInstallResult(
                success=False,
                component_key=component_key,
                component_name=comp.name,
                verified=False,
                output="\n".join(captured_output),
                error=err,
            )

        env = os.environ.copy()
        env["WINEPREFIX"] = prefix_path
        env["WINEDEBUG"] = "-all"

        log(f"[ZCF Component Manager] Executing: {winetricks_bin} -q {comp.winetricks_verb}")
        proc_exit = 0
        try:
            proc = subprocess.Popen(
                [winetricks_bin, "-q", comp.winetricks_verb],
                env=env,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
            )
            if proc.stdout:
                for line in proc.stdout:
                    log(line.strip())
            proc_exit = proc.wait(timeout=300)
        except Exception as e:
            log(f"[ZCF Component Manager Error] Winetricks execution failed: {e}")
            proc_exit = 1

        if proc_exit != 0:
            err = f"Winetricks installer failed with exit code {proc_exit}."
            log(f"[ZCF Component Manager Error] {err}")
            return ComponentInstallResult(
                success=False,
                component_key=component_key,
                component_name=comp.name,
                verified=False,
                output="\n".join(captured_output),
                error=err,
            )

        # 2. Verify installation outcome on disk
        verified = self.is_installed_in_prefix(prefix_path, component_key)
        if not verified:
            err = f"Verification failed: required DLLs ({', '.join(comp.verification_files)}) were not detected in prefix."
            log(f"[ZCF Component Manager] Verification FAILED for '{comp.name}'.")
            return ComponentInstallResult(
                success=False,
                component_key=component_key,
                component_name=comp.name,
                verified=False,
                output="\n".join(captured_output),
                error=err,
            )

        # 3. Record in prefix metadata
        meta_file = os.path.join(prefix_path, "prefix_meta.json")
        meta_data: Dict[str, Any] = {}
        if os.path.exists(meta_file):
            try:
                with open(meta_file, "r", encoding="utf-8") as f:
                    meta_data = json.load(f)
            except Exception:
                pass
        components = meta_data.get("installed_components", [])
        if component_key not in components:
            components.append(component_key)
        meta_data["installed_components"] = components
        try:
            with open(meta_file, "w", encoding="utf-8") as f:
                json.dump(meta_data, f, indent=2)
        except Exception:
            pass
        log(f"[ZCF Component Manager] Verification SUCCESS for '{comp.name}'.")

        return ComponentInstallResult(
            success=True,
            component_key=component_key,
            component_name=comp.name,
            verified=True,
            output="\n".join(captured_output),
            error=None,
        )
