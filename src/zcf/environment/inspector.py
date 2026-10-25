"""
Host environment inspector.
Audits OS distribution, architecture, installed compatibility runtimes, and analysis utilities.
"""

from __future__ import annotations

import os
import platform
import shutil
import subprocess
from typing import Any, Dict, List, Optional

from zcf.core.models import DisplayServer, EnvironmentReport, RuntimeInfo


class EnvironmentInspector:
    """Discovers host capabilities, system libraries, and installed compatibility runtimes."""

    def inspect(self) -> EnvironmentReport:
        os_type = platform.system().lower()
        arch = platform.machine().lower()
        if arch in ("amd64", "x86_64"):
            canonical_arch = "x86_64"
        elif arch in ("arm64", "aarch64"):
            canonical_arch = "arm64"
        elif arch in ("i386", "i686"):
            canonical_arch = "i386"
        else:
            canonical_arch = arch

        distribution = None
        release = platform.release()

        if os_type == "linux":
            distribution, release = self._get_linux_distribution()

        cpu_model = platform.processor() or "Unknown CPU"
        cores = os.cpu_count() or 1
        memory_mb = self._get_memory_mb()

        display = self._detect_display_server(os_type)
        runtimes = self._discover_runtimes(os_type)

        bwrap_path = shutil.which("bwrap")
        can_sandbox = os_type == "linux" and bwrap_path is not None

        vulkan_avail = (
            shutil.which("vulkaninfo") is not None
            or shutil.which("vulkaninfo.exe") is not None
            or os.path.exists("/usr/lib/libvulkan.so.1")
            or os.path.exists("/usr/lib/x86_64-linux-gnu/libvulkan.so.1")
        )

        return EnvironmentReport(
            os_name=os_type,
            architecture=canonical_arch,
            kernel_version=platform.version(),
            distribution=distribution,
            release=release,
            cpu_model=cpu_model,
            logical_cores=cores,
            total_memory_mb=memory_mb,
            display_server=display,
            available_runtimes=runtimes,
            graphics_capabilities={
                "vulkan_supported": vulkan_avail,
                "opengl_version": None,
                "hardware_acceleration": True,
            },
            isolation_features={
                "can_sandbox": can_sandbox,
                "bwrap_installed": bwrap_path is not None,
                "bwrap_path": bwrap_path,
                "namespaces_available": os_type == "linux",
                "root_privileges": os.geteuid() == 0 if hasattr(os, "geteuid") else False,
            },
        )

    def _get_linux_distribution(self) -> tuple[Optional[str], Optional[str]]:
        if os.path.exists("/etc/os-release"):
            distro_id = None
            version_id = None
            try:
                with open("/etc/os-release", "r", encoding="utf-8") as f:
                    for line in f:
                        if line.startswith("ID="):
                            distro_id = line.strip().split("=")[1].strip('"')
                        elif line.startswith("VERSION_ID="):
                            version_id = line.strip().split("=")[1].strip('"')
                return distro_id, version_id
            except Exception:
                pass
        return "linux", platform.release()

    def _get_memory_mb(self) -> int:
        if hasattr(os, "sysconf") and "SC_PAGE_SIZE" in os.sysconf_names and "SC_PHYS_PAGES" in os.sysconf_names:
            try:
                pages = os.sysconf("SC_PHYS_PAGES")
                page_size = os.sysconf("SC_PAGE_SIZE")
                return (pages * page_size) // (1024 * 1024)
            except Exception:
                pass
        if os.name == "nt":
            try:
                import ctypes
                class MEMORYSTATUSEX(ctypes.Structure):
                    _fields_ = [
                        ("dwLength", ctypes.c_ulong),
                        ("dwMemoryLoad", ctypes.c_ulong),
                        ("ullTotalPhys", ctypes.c_ulonglong),
                        ("ullAvailPhys", ctypes.c_ulonglong),
                        ("ullTotalPageFile", ctypes.c_ulonglong),
                        ("ullAvailPageFile", ctypes.c_ulonglong),
                        ("ullTotalVirtual", ctypes.c_ulonglong),
                        ("ullAvailVirtual", ctypes.c_ulonglong),
                        ("sullAvailExtendedVirtual", ctypes.c_ulonglong),
                    ]
                stat = MEMORYSTATUSEX()
                stat.dwLength = ctypes.sizeof(MEMORYSTATUSEX)
                if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(stat)):
                    return int(stat.ullTotalPhys // (1024 * 1024))
            except Exception:
                pass
        return 8192

    def _detect_display_server(self, os_type: str) -> DisplayServer:
        if os_type == "windows":
            return DisplayServer.WINDOWS
        if os.environ.get("WAYLAND_DISPLAY"):
            return DisplayServer.WAYLAND
        if os.environ.get("DISPLAY"):
            return DisplayServer.X11
        return DisplayServer.HEADLESS

    def _discover_runtimes(self, os_type: str) -> List[RuntimeInfo]:
        runtimes: List[RuntimeInfo] = []

        # 1. Native Execution
        runtimes.append(
            RuntimeInfo(
                runtime_id="runtime.native",
                name="Native Host Runtime",
                installed=True,
                version=platform.release(),
                binary_path=None,
                supported_formats=["elf" if os_type == "linux" else "pe", "script"],
                supported_architectures=["x86_64", "arm64", "all"],
            )
        )

        # 2. Wine / Proton
        wine_bin = shutil.which("wine64") or shutil.which("wine")
        wine_installed = wine_bin is not None
        wine_version = self._get_command_version(wine_bin, ["--version"]) if wine_installed else None

        runtimes.append(
            RuntimeInfo(
                runtime_id="runtime.wine",
                name="Wine Compatibility Layer",
                installed=wine_installed,
                version=wine_version,
                binary_path=wine_bin,
                supported_formats=["pe"],
                supported_architectures=["x86_64", "i386"],
            )
        )

        # 3. QEMU User-Mode Emulators
        qemu_aarch64 = shutil.which("qemu-aarch64") or shutil.which("qemu-aarch64-static")
        qemu_installed = qemu_aarch64 is not None
        qemu_ver = self._get_command_version(qemu_aarch64, ["--version"]) if qemu_installed else None

        runtimes.append(
            RuntimeInfo(
                runtime_id="runtime.qemu-user",
                name="QEMU User-Mode Architecture Emulation",
                installed=qemu_installed,
                version=qemu_ver,
                binary_path=qemu_aarch64,
                supported_formats=["elf"],
                supported_architectures=["arm64", "arm", "riscv64", "i386", "x86_64"],
            )
        )

        # 4. Box64
        box64_bin = shutil.which("box64")
        box64_installed = box64_bin is not None
        box64_ver = self._get_command_version(box64_bin, ["-v"]) if box64_installed else None

        runtimes.append(
            RuntimeInfo(
                runtime_id="runtime.box64",
                name="Box64 Dynamic x86_64 Emulator",
                installed=box64_installed,
                version=box64_ver,
                binary_path=box64_bin,
                supported_formats=["elf"],
                supported_architectures=["x86_64"],
            )
        )

        # 5. Valve Proton
        from zcf.runtimes.proton import ProtonAdapter
        proton_bin = ProtonAdapter()._find_proton_binary()
        proton_installed = proton_bin is not None
        runtimes.append(
            RuntimeInfo(
                runtime_id="runtime.proton",
                name="Valve Proton Gaming Runtime",
                installed=proton_installed,
                version="Steam-Managed" if proton_installed else None,
                binary_path=proton_bin,
                supported_formats=["pe"],
                supported_architectures=["x86_64"],
            )
        )

        # 6. Waydroid Android Container
        waydroid_bin = shutil.which("waydroid")
        waydroid_installed = waydroid_bin is not None
        runtimes.append(
            RuntimeInfo(
                runtime_id="runtime.android",
                name="Waydroid Android Container Runtime",
                installed=waydroid_installed,
                version=self._get_command_version(waydroid_bin, ["version"]) if waydroid_installed else None,
                binary_path=waydroid_bin,
                supported_formats=["archive"],
                supported_architectures=["arm64", "x86_64", "universal"],
            )
        )

        return runtimes

    def _get_command_version(self, binary_path: Optional[str], args: List[str]) -> Optional[str]:
        if not binary_path:
            return None
        try:
            res = subprocess.run([binary_path] + args, capture_output=True, text=True, timeout=3)
            first_line = (res.stdout or res.stderr or "").strip().splitlines()
            return first_line[0] if first_line else None
        except Exception:
            return None
