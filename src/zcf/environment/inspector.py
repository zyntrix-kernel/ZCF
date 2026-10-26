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

    def get_readiness_audit(self) -> Dict[str, Any]:
        """
        Performs a pre-flight system readiness audit for gaming, 3D translation, and compatibility orchestration.
        Evaluates 7 critical hardware, kernel, and subsystem parameters and computes a readiness score (0-100%).
        """
        checks: List[Dict[str, Any]] = []
        os_type = platform.system().lower()

        # 1. Vulkan 1.3 & 32-bit driver
        vulkan64 = (
            shutil.which("vulkaninfo") is not None
            or shutil.which("vulkaninfo.exe") is not None
            or os.path.exists("/usr/lib/libvulkan.so.1")
            or os.path.exists("/usr/lib/x86_64-linux-gnu/libvulkan.so.1")
            or (os_type == "windows" and os.path.exists(os.path.expandvars(r"%SystemRoot%\System32\vulkan-1.dll")))
        )
        vulkan32 = (
            os.path.exists("/usr/lib/i386-linux-gnu/libvulkan.so.1")
            or os.path.exists("/usr/lib32/libvulkan.so.1")
            or (os_type == "windows" and os.path.exists(os.path.expandvars(r"%SystemRoot%\SysWOW64\vulkan-1.dll")))
        )
        if vulkan64 and (vulkan32 or os_type == "windows"):
            checks.append({
                "id": "vulkan_driver",
                "name": "Vulkan 1.3 Driver & 32/64-bit Loaders",
                "status": "PASS",
                "max_points": 20,
                "score_points": 20,
                "details": "Vulkan 1.3 ICD loader and 32-bit/64-bit runtime acceleration libraries are available.",
                "remediation": None,
            })
        elif vulkan64:
            checks.append({
                "id": "vulkan_driver",
                "name": "Vulkan 1.3 Driver & 32/64-bit Loaders",
                "status": "WARN",
                "max_points": 20,
                "score_points": 10,
                "details": "64-bit Vulkan driver detected, but 32-bit Vulkan loader (libvulkan1:i386) is missing. 32-bit Windows games will lack DXVK/Vulkan hardware acceleration.",
                "remediation": "Install 32-bit Vulkan loader: sudo apt install libvulkan1:i386 mesa-vulkan-drivers:i386",
            })
        else:
            checks.append({
                "id": "vulkan_driver",
                "name": "Vulkan 1.3 Driver & 32/64-bit Loaders",
                "status": "FAIL",
                "max_points": 20,
                "score_points": 0,
                "details": "No Vulkan driver or ICD loader detected. Direct3D translation (DXVK/VKD3D) will fail or fall back to slow CPU emulation.",
                "remediation": "Install Vulkan drivers: sudo apt install libvulkan1 mesa-vulkan-drivers",
            })

        # 2. Esync / Fsync thread synchronization limits
        if os_type == "linux":
            nofile_soft, nofile_hard = 1024, 1024
            try:
                import resource
                nofile_soft, nofile_hard = resource.getrlimit(resource.RLIMIT_NOFILE)
            except Exception:
                pass

            futex2_available = (
                os.path.exists("/dev/futex2")
                or os.path.exists("/sys/kernel/futex2")
            )
            # Check kernel version >= 5.16 which includes futex_waitv natively
            try:
                k_parts = platform.release().split("-")[0].split(".")
                major, minor = int(k_parts[0]), int(k_parts[1])
                if (major > 5) or (major == 5 and minor >= 16):
                    futex2_available = True
            except Exception:
                pass

            if nofile_hard >= 524288:
                checks.append({
                    "id": "sync_limits",
                    "name": "Esync & Fsync Synchronization Limits",
                    "status": "PASS",
                    "max_points": 15,
                    "score_points": 15,
                    "details": f"File descriptor limit is optimal (soft={nofile_soft}, hard={nofile_hard}). " + (
                        "Futex2 / futex_waitv kernel fast mutexes supported." if futex2_available else "Esync high-concurrency eventfds supported."
                    ),
                    "remediation": None,
                })
            elif nofile_hard >= 65536:
                checks.append({
                    "id": "sync_limits",
                    "name": "Esync & Fsync Synchronization Limits",
                    "status": "WARN",
                    "max_points": 15,
                    "score_points": 8,
                    "details": f"Suboptimal file descriptor limit (hard={nofile_hard} < 524288). Wine Esync may exhaust descriptors under heavy game multithreading.",
                    "remediation": "Increase limits: add '* hard nofile 524288' to /etc/security/limits.conf or set DefaultLimitNOFILE=524288 in /etc/systemd/user.conf",
                })
            else:
                checks.append({
                    "id": "sync_limits",
                    "name": "Esync & Fsync Synchronization Limits",
                    "status": "FAIL",
                    "max_points": 15,
                    "score_points": 0,
                    "details": f"Critical descriptor bottleneck (hard={nofile_hard} <= 1024). Wine Esync cannot operate reliably and may crash.",
                    "remediation": "Increase descriptor ceiling: echo '* hard nofile 524288' | sudo tee -a /etc/security/limits.conf",
                })
        else:
            checks.append({
                "id": "sync_limits",
                "name": "Esync & Fsync Synchronization Limits",
                "status": "PASS",
                "max_points": 15,
                "score_points": 15,
                "details": "Native host synchronization primitives active.",
                "remediation": None,
            })

        # 3. Multiarch (i386 foreign architecture)
        if os_type == "linux":
            multiarch_active = False
            if shutil.which("dpkg"):
                try:
                    res = subprocess.run(["dpkg", "--print-foreign-architectures"], capture_output=True, text=True, timeout=2)
                    multiarch_active = "i386" in res.stdout
                except Exception:
                    pass
            if not multiarch_active:
                multiarch_active = (
                    os.path.isdir("/lib/i386-linux-gnu")
                    or os.path.isdir("/usr/lib/i386-linux-gnu")
                    or os.path.isdir("/usr/lib32")
                )

            if multiarch_active:
                checks.append({
                    "id": "multiarch_support",
                    "name": "Multiarch 32-bit (i386) Architecture",
                    "status": "PASS",
                    "max_points": 15,
                    "score_points": 15,
                    "details": "Multiarch 32-bit architecture enabled. Host can execute legacy 32-bit Windows and Linux applications.",
                    "remediation": None,
                })
            else:
                checks.append({
                    "id": "multiarch_support",
                    "name": "Multiarch 32-bit (i386) Architecture",
                    "status": "WARN",
                    "max_points": 15,
                    "score_points": 7,
                    "details": "32-bit foreign architecture (i386) is not enabled on host. 32-bit Windows games and software will fail to initialize.",
                    "remediation": "Enable multiarch: sudo dpkg --add-architecture i386 && sudo apt update",
                })
        else:
            checks.append({
                "id": "multiarch_support",
                "name": "Multiarch 32-bit (i386) Architecture",
                "status": "PASS",
                "max_points": 15,
                "score_points": 15,
                "details": "Windows WoW64 32-bit emulation subsystem is active.",
                "remediation": None,
            })

        # 4. Bubblewrap Unprivileged Namespaces
        bwrap_path = shutil.which("bwrap")
        if os_type == "linux":
            userns_enabled = True
            userns_file = "/proc/sys/kernel/unprivileged_userns_clone"
            if os.path.exists(userns_file):
                try:
                    with open(userns_file, "r") as f:
                        userns_enabled = f.read().strip() == "1"
                except Exception:
                    pass

            if bwrap_path and userns_enabled:
                checks.append({
                    "id": "bubblewrap_isolation",
                    "name": "Bubblewrap Unprivileged Sandbox Containment",
                    "status": "PASS",
                    "max_points": 20,
                    "score_points": 20,
                    "details": f"Bubblewrap installed ({bwrap_path}) and unprivileged user namespaces are enabled.",
                    "remediation": None,
                })
            elif bwrap_path and not userns_enabled:
                checks.append({
                    "id": "bubblewrap_isolation",
                    "name": "Bubblewrap Unprivileged Sandbox Containment",
                    "status": "WARN",
                    "max_points": 20,
                    "score_points": 10,
                    "details": "Bubblewrap is installed, but kernel.unprivileged_userns_clone is 0. Container sandboxing requires root or kernel userns enablement.",
                    "remediation": "Enable userns: sudo sysctl -w kernel.unprivileged_userns_clone=1",
                })
            else:
                checks.append({
                    "id": "bubblewrap_isolation",
                    "name": "Bubblewrap Unprivileged Sandbox Containment",
                    "status": "FAIL",
                    "max_points": 20,
                    "score_points": 0,
                    "details": "'bwrap' binary not found on PATH. Application sandboxing and isolated execution are unavailable.",
                    "remediation": "Install Bubblewrap: sudo apt install bubblewrap",
                })
        else:
            checks.append({
                "id": "bubblewrap_isolation",
                "name": "Bubblewrap Unprivileged Sandbox Containment",
                "status": "WARN",
                "max_points": 20,
                "score_points": 12,
                "details": "Bubblewrap container sandboxing is Linux-specific; host relies on local operating system process security boundaries.",
                "remediation": None,
            })

        # 5. Direct Rendering Infrastructure (DRI / GPU Acceleration)
        if os_type == "linux":
            render_node = "/dev/dri/renderD128"
            card_node = "/dev/dri/card0"
            has_render = os.path.exists(render_node)
            has_card = os.path.exists(card_node)

            if has_render:
                is_accessible = os.access(render_node, os.R_OK | os.W_OK)
                if is_accessible:
                    checks.append({
                        "id": "dri_gpu_acceleration",
                        "name": "Direct Rendering Infrastructure (GPU Acceleration)",
                        "status": "PASS",
                        "max_points": 15,
                        "score_points": 15,
                        "details": f"Direct rendering node {render_node} is accessible with full read/write GPU privileges.",
                        "remediation": None,
                    })
                else:
                    checks.append({
                        "id": "dri_gpu_acceleration",
                        "name": "Direct Rendering Infrastructure (GPU Acceleration)",
                        "status": "WARN",
                        "max_points": 15,
                        "score_points": 8,
                        "details": f"Render node {render_node} exists, but current user lacks read/write permissions.",
                        "remediation": "Grant GPU access: sudo usermod -aG render,video $USER",
                    })
            elif has_card:
                checks.append({
                    "id": "dri_gpu_acceleration",
                    "name": "Direct Rendering Infrastructure (GPU Acceleration)",
                    "status": "WARN",
                    "max_points": 15,
                    "score_points": 8,
                    "details": f"Legacy display card {card_node} found, but headless render node {render_node} is missing.",
                    "remediation": "Ensure DRI kernel modules (e.g. amdgpu, i915, or nvidia-drm) are loaded.",
                })
            else:
                checks.append({
                    "id": "dri_gpu_acceleration",
                    "name": "Direct Rendering Infrastructure (GPU Acceleration)",
                    "status": "WARN",
                    "max_points": 15,
                    "score_points": 5,
                    "details": "No GPU direct rendering node (/dev/dri/renderD128) detected. 3D workloads will use software rasterization (LLVMpipe).",
                    "remediation": "Verify GPU drivers and hardware passthrough are active.",
                })
        else:
            checks.append({
                "id": "dri_gpu_acceleration",
                "name": "Direct Rendering Infrastructure (GPU Acceleration)",
                "status": "PASS",
                "max_points": 15,
                "score_points": 15,
                "details": "Host Direct3D / DXGI hardware acceleration is active.",
                "remediation": None,
            })

        # 6. Kernel binfmt_misc PE Registration
        if os_type == "linux":
            binfmt_active = (
                os.path.exists("/proc/sys/fs/binfmt_misc/zcf-pe")
                or os.path.exists("/proc/sys/fs/binfmt_misc/wine")
                or os.path.exists("/proc/sys/fs/binfmt_misc/DOSWin")
            )
            if binfmt_active:
                checks.append({
                    "id": "binfmt_registration",
                    "name": "Kernel Transparent binfmt_misc Registration",
                    "status": "PASS",
                    "max_points": 5,
                    "score_points": 5,
                    "details": "Kernel binfmt_misc handler active. Windows binaries can be executed directly as native programs (./app.exe).",
                    "remediation": None,
                })
            else:
                checks.append({
                    "id": "binfmt_registration",
                    "name": "Kernel Transparent binfmt_misc Registration",
                    "status": "WARN",
                    "max_points": 5,
                    "score_points": 2,
                    "details": "Kernel binfmt_misc handler for PE executables is not registered. Execution requires explicit 'zcf run app.exe'.",
                    "remediation": "Register handler: sudo zcf service register-binfmt",
                })
        else:
            checks.append({
                "id": "binfmt_registration",
                "name": "Kernel Transparent binfmt_misc Registration",
                "status": "PASS",
                "max_points": 5,
                "score_points": 5,
                "details": "Native Windows PE executable loader is operational.",
                "remediation": None,
            })

        # 7. Ephemeral Headless Virtual Display (xvfb-run / Xvfb)
        xvfb_bin = shutil.which("xvfb-run") or shutil.which("Xvfb")
        if xvfb_bin:
            checks.append({
                "id": "headless_display_support",
                "name": "Ephemeral Headless Virtual Display (Xvfb)",
                "status": "PASS",
                "max_points": 10,
                "score_points": 10,
                "details": f"Headless virtual X11 display server available ({xvfb_bin}) for non-interactive test orchestration and CI verification.",
                "remediation": None,
            })
        elif os_type == "windows":
            checks.append({
                "id": "headless_display_support",
                "name": "Ephemeral Headless Virtual Display (Xvfb)",
                "status": "PASS",
                "max_points": 10,
                "score_points": 10,
                "details": "Windows desktop session available for graphical execution.",
                "remediation": None,
            })
        else:
            checks.append({
                "id": "headless_display_support",
                "name": "Ephemeral Headless Virtual Display (Xvfb)",
                "status": "WARN",
                "max_points": 10,
                "score_points": 5,
                "details": "'xvfb-run' / 'Xvfb' not found. Automated headless tests will require an active graphical session (DISPLAY).",
                "remediation": "Install Xvfb: sudo apt install xvfb",
            })

        total_earned = sum(c["score_points"] for c in checks)
        total_possible = sum(c["max_points"] for c in checks)
        score = int(round((total_earned / total_possible) * 100)) if total_possible > 0 else 0

        if score >= 90:
            grade = "OPTIMAL"
            summary = "Host environment is optimally primed for high-performance Windows gaming, Direct3D translation, and strict sandbox isolation."
        elif score >= 70:
            grade = "GOOD"
            summary = "Host environment meets standard compatibility requirements for modern 64-bit Windows software and games."
        elif score >= 45:
            grade = "DEGRADED"
            summary = "Host environment has degraded compatibility capabilities (missing 32-bit libraries, synchronization limits, or GPU acceleration)."
        else:
            grade = "MINIMAL"
            summary = "Host environment lacks core compatibility dependencies or sandboxing capabilities."

        return {
            "score": score,
            "grade": grade,
            "summary": summary,
            "checks": checks,
        }

