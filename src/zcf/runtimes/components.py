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
        "vkd3d": ComponentDefinition(
            key="vkd3d",
            name="Vulkan VKD3D Direct3D 12 Translation",
            description="Translates DirectX 12 graphics API calls to native Vulkan for modern AAA titles.",
            winetricks_verb="vkd3d",
            verification_files=["d3d12.dll"],
        ),
        "corefonts": ComponentDefinition(
            key="corefonts",
            name="Microsoft TrueType Core Fonts",
            description="Essential Windows typography (Arial, Times New Roman, Courier) required for GUI text rendering.",
            winetricks_verb="corefonts",
            verification_files=["arial.ttf"],
        ),
        "dotnet48": ComponentDefinition(
            key="dotnet48",
            name="Microsoft .NET Framework 4.8",
            description="Full Microsoft .NET Framework runtime for enterprise and modern Windows applications.",
            winetricks_verb="dotnet48",
            verification_files=["mscoree.dll"],
        ),
        "d3dcompiler_47": ComponentDefinition(
            key="d3dcompiler_47",
            name="Direct3D HLSL Shader Compiler (v47)",
            description="HLSL shader bytecode assembler and translator required for modern Unreal Engine and Unity games.",
            winetricks_verb="d3dcompiler_47",
            verification_files=["d3dcompiler_47.dll"],
        ),
        "vcrun2010": ComponentDefinition(
            key="vcrun2010",
            name="Microsoft Visual C++ 2010 SP1 Runtime",
            description="Legacy Visual C++ standard runtime libraries for DirectX 9/10 era software.",
            winetricks_verb="vcrun2010",
            verification_files=["msvcr100.dll", "msvcp100.dll"],
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
        Requires all verification files to exist in system32, syswow64, Fonts, or .NET framework directories.
        Never relies on prefix metadata as proof of current disk presence.
        """
        comp = self.get_component(component_key)
        if not comp or not os.path.exists(prefix_path):
            return False

        if not comp.verification_files:
            return False

        system32 = os.path.join(prefix_path, "drive_c", "windows", "system32")
        syswow64 = os.path.join(prefix_path, "drive_c", "windows", "syswow64")
        fonts_dir = os.path.join(prefix_path, "drive_c", "windows", "Fonts")
        dotnet_dirs = [
            os.path.join(prefix_path, "drive_c", "windows", "Microsoft.NET", "Framework", "v4.0.30319"),
            os.path.join(prefix_path, "drive_c", "windows", "Microsoft.NET", "Framework64", "v4.0.30319"),
        ]

        search_dirs = [system32, syswow64]
        for v_file in comp.verification_files:
            v_lower = v_file.lower()
            current_dirs = search_dirs.copy()
            if v_lower.endswith(".ttf") or v_lower.endswith(".fon"):
                current_dirs.append(fonts_dir)
            if "mscor" in v_lower:
                current_dirs.extend(dotnet_dirs)

            found = False
            for d in current_dirs:
                if not os.path.isdir(d):
                    continue
                try:
                    for entry in os.listdir(d):
                        if entry.lower() == v_lower:
                            found = True
                            break
                except Exception:
                    pass
                if found:
                    break

            if not found:
                return False

        return True

    def get_dll_overrides(self, prefix_path: str) -> Dict[str, str]:
        """
        Retrieves active DLL overrides configured in user.reg or prefix_meta.json.
        Returns a dictionary mapping dll names (without extension) to load modes (e.g. 'native,builtin', 'disabled').
        """
        overrides: Dict[str, str] = {}
        if not os.path.exists(prefix_path):
            return overrides

        # 1. Check user.reg in prefix
        user_reg = os.path.join(prefix_path, "user.reg")
        if os.path.exists(user_reg):
            try:
                with open(user_reg, "r", encoding="utf-8", errors="replace") as f:
                    in_section = False
                    for line in f:
                        line_str = line.strip()
                        if line_str.startswith("[") and line_str.endswith("]"):
                            # Wine section header may have timestamp suffix, e.g. [Software\Wine\DllOverrides] 169000000 0
                            clean_hdr = line_str[1:-1].split()[0]
                            in_section = clean_hdr.lower() in ("software\\wine\\dlloverrides", "software\\\\wine\\\\dlloverrides")
                            continue
                        if in_section:
                            if not line_str or line_str.startswith("#") or line_str.startswith(";"):
                                continue
                            if "=" in line_str:
                                k, v = line_str.split("=", 1)
                                k = k.strip().strip('"')
                                v = v.strip().strip('"')
                                if not v:
                                    v = "disabled"
                                overrides[k.lower()] = v
            except Exception:
                pass

        # 2. Merge with prefix_meta.json (meta overrides take precedence or fill gaps)
        meta_file = os.path.join(prefix_path, "prefix_meta.json")
        if os.path.exists(meta_file):
            try:
                with open(meta_file, "r", encoding="utf-8") as f:
                    meta = json.load(f)
                meta_overrides = meta.get("dll_overrides", {})
                if isinstance(meta_overrides, dict):
                    for k, v in meta_overrides.items():
                        overrides[str(k).lower()] = str(v)
            except Exception:
                pass

        return overrides

    def set_dll_override(self, prefix_path: str, dll_name: str, mode: str) -> bool:
        """
        Configures a DLL override (native, builtin, native,builtin, builtin,native, disabled)
        inside user.reg and records it in prefix_meta.json.
        """
        if not os.path.exists(prefix_path):
            return False

        clean_dll = dll_name.lower().removesuffix(".dll").strip()
        if not clean_dll:
            return False

        valid_modes = {"native,builtin", "builtin,native", "native", "builtin", "disabled", ""}
        clean_mode = mode.lower().strip()
        if clean_mode not in valid_modes:
            clean_mode = "native,builtin"

        reg_val = '""' if clean_mode == "disabled" else f'"{clean_mode}"'

        # 1. Update user.reg
        user_reg = os.path.join(prefix_path, "user.reg")
        if os.path.exists(user_reg):
            try:
                with open(user_reg, "r", encoding="utf-8", errors="replace") as f:
                    lines = f.readlines()

                new_lines: List[str] = []
                in_section = False
                section_found = False
                key_updated = False

                for line in lines:
                    line_str = line.strip()
                    if line_str.startswith("["):
                        if in_section and not key_updated:
                            # Append before leaving section
                            new_lines.append(f'"{clean_dll}"={reg_val}\n')
                            key_updated = True
                        clean_hdr = line_str[1:-1].split()[0]
                        in_section = clean_hdr.lower() in ("software\\wine\\dlloverrides", "software\\\\wine\\\\dlloverrides")
                        if in_section:
                            section_found = True
                    elif in_section and "=" in line_str:
                        k = line_str.split("=", 1)[0].strip().strip('"').lower()
                        if k == clean_dll:
                            new_lines.append(f'"{clean_dll}"={reg_val}\n')
                            key_updated = True
                            continue

                    new_lines.append(line)

                if section_found and in_section and not key_updated:
                    new_lines.append(f'"{clean_dll}"={reg_val}\n')
                    key_updated = True

                if not section_found:
                    new_lines.append("\n[Software\\\\Wine\\\\DllOverrides]\n")
                    new_lines.append(f'"{clean_dll}"={reg_val}\n')

                with open(user_reg, "w", encoding="utf-8") as f:
                    f.writelines(new_lines)
            except Exception:
                pass

        # 2. Update prefix_meta.json
        meta_file = os.path.join(prefix_path, "prefix_meta.json")
        try:
            meta = {}
            if os.path.exists(meta_file):
                with open(meta_file, "r", encoding="utf-8") as f:
                    meta = json.load(f)
            overrides = meta.get("dll_overrides", {})
            overrides[clean_dll] = clean_mode
            meta["dll_overrides"] = overrides
            with open(meta_file, "w", encoding="utf-8") as f:
                json.dump(meta, f, indent=2)
        except Exception:
            pass

        return True

    def remove_dll_override(self, prefix_path: str, dll_name: str) -> bool:
        """Removes a configured DLL override from user.reg and prefix_meta.json."""
        if not os.path.exists(prefix_path):
            return False

        clean_dll = dll_name.lower().removesuffix(".dll").strip()
        if not clean_dll:
            return False

        # 1. Remove from user.reg
        user_reg = os.path.join(prefix_path, "user.reg")
        if os.path.exists(user_reg):
            try:
                with open(user_reg, "r", encoding="utf-8", errors="replace") as f:
                    lines = f.readlines()

                new_lines: List[str] = []
                in_section = False
                for line in lines:
                    line_str = line.strip()
                    if line_str.startswith("["):
                        clean_hdr = line_str[1:-1].split()[0]
                        in_section = clean_hdr.lower() in ("software\\wine\\dlloverrides", "software\\\\wine\\\\dlloverrides")
                    elif in_section and "=" in line_str:
                        k = line_str.split("=", 1)[0].strip().strip('"').lower()
                        if k == clean_dll:
                            continue  # Delete line
                    new_lines.append(line)

                with open(user_reg, "w", encoding="utf-8") as f:
                    f.writelines(new_lines)
            except Exception:
                pass

        # 2. Remove from prefix_meta.json
        meta_file = os.path.join(prefix_path, "prefix_meta.json")
        if os.path.exists(meta_file):
            try:
                with open(meta_file, "r", encoding="utf-8") as f:
                    meta = json.load(f)
                overrides = meta.get("dll_overrides", {})
                if clean_dll in overrides:
                    del overrides[clean_dll]
                    meta["dll_overrides"] = overrides
                    with open(meta_file, "w", encoding="utf-8") as f:
                        json.dump(meta, f, indent=2)
            except Exception:
                pass

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
