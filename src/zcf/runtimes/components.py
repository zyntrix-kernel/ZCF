"""
Windows Component & Runtime Manager for ZCF.
Provides verified installation of Visual C++, DirectX, Wine Mono, and DXVK runtimes into managed Wine prefixes.
"""

from __future__ import annotations

import json
import os
import queue
import shutil
import signal
import subprocess
import threading
import time
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
    assurance_level: str = "NONE"


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
        """
        Verifies if all required component signature files exist inside the target prefix.
        Requires all verification files to exist in system32 or syswow64.
        Never relies on prefix metadata as proof of current disk presence.
        """
        comp = self.get_component(component_key)
        if not comp or not os.path.exists(prefix_path):
            return False

        if not comp.verification_files:
            return False

        system32 = os.path.join(prefix_path, "drive_c", "windows", "system32")
        syswow64 = os.path.join(prefix_path, "drive_c", "windows", "syswow64")

        # Every single verification file must exist in at least one system directory
        for v_file in comp.verification_files:
            p32 = os.path.join(system32, v_file)
            p64 = os.path.join(syswow64, v_file)
            if not (os.path.exists(p32) or os.path.exists(p64)):
                return False

        return True

    def _remove_component_from_metadata(self, prefix_path: str, component_key: str) -> None:
        """Removes component from prefix_meta.json to prevent stale claims of installation."""
        meta_file = os.path.join(prefix_path, "prefix_meta.json")
        if not os.path.exists(meta_file):
            return
        try:
            with open(meta_file, "r", encoding="utf-8") as f:
                meta_data = json.load(f)
            components = meta_data.get("installed_components", [])
            if component_key in components:
                meta_data["installed_components"] = [c for c in components if c != component_key]
                with open(meta_file, "w", encoding="utf-8") as f:
                    json.dump(meta_data, f, indent=2)
        except Exception:
            pass

    def install(
        self,
        prefix_path: str,
        component_key: str,
        progress_callback: Optional[Callable[[str], None]] = None,
        timeout: float = 300.0,
    ) -> ComponentInstallResult:
        """Installs and verifies the specified component inside the prefix with deadline enforcement."""
        comp = self.get_component(component_key)
        if not comp:
            return ComponentInstallResult(
                success=False,
                component_key=component_key,
                component_name=component_key,
                verified=False,
                output="",
                error=f"Unknown component key: {component_key}",
                assurance_level="NONE",
            )

        os.makedirs(prefix_path, exist_ok=True)
        captured_output: List[str] = []

        def log(msg: str):
            captured_output.append(msg)
            if progress_callback:
                try:
                    progress_callback(msg)
                except Exception:
                    pass

        log(f"[ZCF Component Manager] Installing '{comp.name}' into prefix: {prefix_path}")

        # 1. Check if Winetricks is available on host
        winetricks_bin = shutil.which("winetricks")
        if not winetricks_bin and os.environ.get("ZCF_NON_INTERACTIVE") != "1":
            log("[ZCF Component Manager] 'winetricks' not found on PATH. Attempting automated package install...")
            installed = self.installer_bridge.install("winetricks", interactive=False)
            winetricks_bin = shutil.which("winetricks")

        if not winetricks_bin:
            self._remove_component_from_metadata(prefix_path, component_key)
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
                assurance_level="NONE",
            )

        env = os.environ.copy()
        env["WINEPREFIX"] = prefix_path
        env["WINEDEBUG"] = "-all"

        log(f"[ZCF Component Manager] Executing: {winetricks_bin} -q {comp.winetricks_verb}")
        proc_exit = 0
        timed_out = False

        popen_kwargs: Dict[str, Any] = {
            "env": env,
            "stdout": subprocess.PIPE,
            "stderr": subprocess.STDOUT,
            "text": True,
            "bufsize": 1,
            "universal_newlines": True,
        }
        if os.name != "nt":
            popen_kwargs["start_new_session"] = True

        try:
            proc = subprocess.Popen(
                [winetricks_bin, "-q", comp.winetricks_verb],
                **popen_kwargs,
            )

            out_queue: queue.Queue[Optional[str]] = queue.Queue(maxsize=1000)

            def reader():
                try:
                    if proc.stdout:
                        if hasattr(proc.stdout, "readline"):
                            for line in iter(proc.stdout.readline, ""):
                                if not line and proc.poll() is not None:
                                    break
                                try:
                                    out_queue.put(line, timeout=0.1)
                                except Exception:
                                    pass
                        elif hasattr(proc.stdout, "__iter__"):
                            for line in proc.stdout:
                                try:
                                    out_queue.put(line, timeout=0.1)
                                except Exception:
                                    pass
                except Exception:
                    pass
                finally:
                    try:
                        out_queue.put(None, timeout=0.5)
                    except Exception:
                        pass

            reader_thread = threading.Thread(target=reader, daemon=True)
            reader_thread.start()

            deadline = time.monotonic() + timeout

            while True:
                # Drain queue slice
                lines_read = 0
                while lines_read < 25:
                    try:
                        line = out_queue.get_nowait()
                    except queue.Empty:
                        break
                    if line is None:
                        break
                    lines_read += 1
                    log(line.strip())

                if time.monotonic() >= deadline:
                    timed_out = True
                    break

                ret = proc.poll()
                if ret is not None:
                    reader_thread.join(timeout=0.4)
                    while True:
                        try:
                            line = out_queue.get_nowait()
                            if line is None:
                                break
                            log(line.strip())
                        except queue.Empty:
                            break
                    if isinstance(ret, (int, float)):
                        proc_exit = int(ret)
                    elif callable(getattr(proc, "wait", None)):
                        try:
                            wait_res = proc.wait(timeout=0.1)
                            proc_exit = int(wait_res) if isinstance(wait_res, (int, float)) else 0
                        except Exception:
                            proc_exit = 0
                    else:
                        proc_exit = 0
                    break

                if lines_read == 0:
                    time.sleep(0.05)

            if timed_out:
                proc_exit = 124
                log(f"[ZCF Component Manager Error] Winetricks execution timed out after {timeout} seconds.")
                if os.name != "nt":
                    try:
                        child_pgid = proc.pid
                        try:
                            os.killpg(child_pgid, signal.SIGTERM)
                        except ProcessLookupError:
                            pass
                        time.sleep(0.4)
                        try:
                            os.killpg(child_pgid, signal.SIGKILL)
                        except ProcessLookupError:
                            pass
                    except Exception:
                        try:
                            proc.kill()
                        except Exception:
                            pass
                else:
                    try:
                        subprocess.run(["taskkill", "/F", "/T", "/PID", str(proc.pid)], capture_output=True)
                    except Exception:
                        try:
                            proc.kill()
                        except Exception:
                            pass
                try:
                    proc.wait(timeout=2)
                except Exception:
                    pass
                reader_thread.join(timeout=0.5)

        except Exception as e:
            log(f"[ZCF Component Manager Error] Winetricks execution failed: {e}")
            proc_exit = 1

        if proc_exit != 0:
            self._remove_component_from_metadata(prefix_path, component_key)
            if timed_out:
                err = f"Winetricks execution timed out after {timeout} seconds."
            else:
                err = f"Winetricks installer failed with exit code {proc_exit}."
            log(f"[ZCF Component Manager Error] {err}")
            return ComponentInstallResult(
                success=False,
                component_key=component_key,
                component_name=comp.name,
                verified=False,
                output="\n".join(captured_output),
                error=err,
                assurance_level="NONE",
            )

        # 2. Verify installation outcome on disk
        verified = self.is_installed_in_prefix(prefix_path, component_key)
        if not verified:
            self._remove_component_from_metadata(prefix_path, component_key)
            err = f"Verification failed: required DLLs ({', '.join(comp.verification_files)}) were not detected in prefix."
            log(f"[ZCF Component Manager] Verification FAILED for '{comp.name}'.")
            return ComponentInstallResult(
                success=False,
                component_key=component_key,
                component_name=comp.name,
                verified=False,
                output="\n".join(captured_output),
                error=err,
                assurance_level="NONE",
            )

        # 3. Record in prefix metadata as history
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
            assurance_level="FILESYSTEM_SIGNATURE_PRESENCE",
        )
