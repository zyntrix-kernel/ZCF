"""
Native Package Manager and PackageKit Bridge for ZCF.
Enforces transparent installation of missing compatibility runtimes and libraries.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from typing import Dict, List, Optional


class PackageInstallerBridge:
    """Interfaces with host distribution package managers (PackageKit, apt, dnf, pacman, zypper)."""

    PACKAGE_MAPPINGS: Dict[str, Dict[str, str]] = {
        "wine": {
            "debian": "wine wine64",
            "ubuntu": "wine wine64",
            "arch": "wine wine-gecko wine-mono",
            "fedora": "wine",
            "rhel": "wine",
            "opensuse": "wine",
            "alpine": "wine",
        },
        "qemu-user": {
            "debian": "qemu-user qemu-user-binfmt",
            "ubuntu": "qemu-user qemu-user-binfmt",
            "arch": "qemu-user-static qemu-user-static-binfmt",
            "fedora": "qemu-user-static",
            "rhel": "qemu-user-static",
            "opensuse": "qemu-linux-user",
            "alpine": "qemu-aarch64",
        },
        "bwrap": {
            "debian": "bubblewrap",
            "ubuntu": "bubblewrap",
            "arch": "bubblewrap",
            "fedora": "bubblewrap",
            "rhel": "bubblewrap",
            "opensuse": "bubblewrap",
            "alpine": "bubblewrap",
        },
        "xvfb": {
            "debian": "xvfb xauth",
            "ubuntu": "xvfb xauth",
            "arch": "xorg-server-xvfb",
            "fedora": "xorg-x11-server-Xvfb",
            "rhel": "xorg-x11-server-Xvfb",
            "opensuse": "xorg-x11-server",
            "alpine": "xvfb",
        },
        "winetricks": {
            "debian": "winetricks",
            "ubuntu": "winetricks",
            "arch": "winetricks",
            "fedora": "winetricks",
            "rhel": "winetricks",
            "opensuse": "winetricks",
            "alpine": "winetricks",
        },
        "waydroid": {
            "debian": "waydroid",
            "ubuntu": "waydroid",
            "arch": "waydroid",
            "fedora": "waydroid",
            "rhel": "waydroid",
            "opensuse": "waydroid",
            "alpine": "waydroid",
        },
        "box64": {
            "debian": "box64",
            "ubuntu": "box64",
            "arch": "box64-bin",
            "fedora": "box64",
            "rhel": "box64",
            "opensuse": "box64",
            "alpine": "box64",
        },
        "proton": {
            "debian": "steam",
            "ubuntu": "steam",
            "arch": "steam",
            "fedora": "steam",
            "rhel": "steam",
            "opensuse": "steam",
            "alpine": "steam",
        },
    }

    def __init__(self, distro: Optional[str] = None):
        self.distro = (distro or self._detect_distribution()).lower()

    def _detect_distribution(self) -> str:
        if os.path.exists("/etc/os-release"):
            try:
                with open("/etc/os-release", "r", encoding="utf-8") as f:
                    for line in f:
                        if line.startswith("ID="):
                            return line.split("=", 1)[1].strip().strip('"')
                        elif line.startswith("ID_LIKE="):
                            return line.split("=", 1)[1].strip().strip('"').split()[0]
            except Exception:
                pass
        return "debian"

    def get_install_command(self, generic_target: str) -> Optional[List[str]]:
        """Returns the appropriate command to install a generic dependency."""
        pkg_map = self.PACKAGE_MAPPINGS.get(generic_target.lower(), {})
        target_pkg = pkg_map.get(self.distro, pkg_map.get("debian", generic_target))

        # Check for PackageKit (pkcon) first - distro standard for user desktop installs
        if shutil.which("pkcon"):
            return ["pkcon", "install", "-y"] + target_pkg.split()

        # Check if Polkit graphical authorization (pkexec) should be preferred over headless sudo
        auth_cmd = "pkexec" if (hasattr(sys.stdin, "isatty") and not sys.stdin.isatty() and shutil.which("pkexec")) else "sudo"

        # Match based on available package manager or target distribution
        if self.distro in ("arch", "manjaro") or (shutil.which("pacman") and not shutil.which("apt-get")):
            return [auth_cmd, "pacman", "-S", "--noconfirm"] + target_pkg.split()
        elif self.distro in ("fedora", "rhel", "centos") or shutil.which("dnf"):
            return [auth_cmd, "dnf", "install", "-y"] + target_pkg.split()
        elif self.distro in ("opensuse", "suse") or shutil.which("zypper"):
            return [auth_cmd, "zypper", "install", "-y"] + target_pkg.split()
        elif self.distro in ("alpine",) or shutil.which("apk"):
            return [auth_cmd, "apk", "add"] + target_pkg.split()
        elif shutil.which("apt-get") or self.distro in ("debian", "ubuntu"):
            return [auth_cmd, "apt-get", "install", "-y"] + target_pkg.split()

        return [auth_cmd, "apt-get", "install", "-y"] + target_pkg.split()

    def install(self, generic_target: str, interactive: bool = True) -> bool:
        """Executes the package installation command."""
        cmd = self.get_install_command(generic_target)
        if not cmd:
            return False

        if interactive:
            print(f"[ZCF Auto-Installer] Preparing to install required dependency '{generic_target}'...")
            print(f"Command: {' '.join(cmd)}")
            confirm = input("Proceed with installation? [Y/n]: ").strip().lower()
            if confirm and confirm not in ("y", "yes"):
                print("[ZCF] Installation cancelled by user.")
                return False

        try:
            res = subprocess.run(cmd, check=True, timeout=300)
            return res.returncode == 0
        except Exception as e:
            print(f"[ZCF] Installation failed: {e}")
            return False
