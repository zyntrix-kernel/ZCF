"""Runner Fleet and ProtonUp Manager for ZCF.

Discovers local compatibility runners (Wine, Proton, GE-Proton, Lutris, Bottles),
fetches remote releases (GE-Proton from GloriousEggroll), verifies SHA-512 checksums,
installs custom runners to ~/.zcf/runners/, and dynamically registers them into
the ZCF RuntimeRegistry.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import tarfile
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

from zcf.runtimes.proton import ProtonAdapter


@dataclass
class DiscoveredRunner:
    """Represents an installed runner discovered on the host system."""

    id: str
    name: str
    path: str
    runner_type: str  # "ge-proton", "valve-proton", "wine-ge", "lutris-wine", "custom"
    version: str
    is_system: bool = False
    is_active: bool = False
    binary_path: Optional[str] = None
    capabilities: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "path": self.path,
            "runner_type": self.runner_type,
            "version": self.version,
            "is_system": self.is_system,
            "is_active": self.is_active,
            "binary_path": self.binary_path,
            "capabilities": list(self.capabilities),
        }


@dataclass
class AvailableRemoteRelease:
    """Represents a downloadable remote runner release from upstream."""

    tag_name: str
    name: str
    download_url: str
    checksum_url: Optional[str]
    size_bytes: int
    published_at: str
    runner_type: str = "ge-proton"
    description: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "tag_name": self.tag_name,
            "name": self.name,
            "download_url": self.download_url,
            "checksum_url": self.checksum_url,
            "size_bytes": self.size_bytes,
            "published_at": self.published_at,
            "runner_type": self.runner_type,
            "description": self.description,
        }


class RunnerFleetManager:
    """Manages local and remote compatibility tool runners."""

    GE_PROTON_GITHUB_API = "https://api.github.com/repos/GloriousEggroll/proton-ge-custom/releases"

    def __init__(self, runners_dir: Optional[str] = None):
        if runners_dir:
            self.runners_dir = os.path.abspath(runners_dir)
        else:
            self.runners_dir = os.path.expanduser("~/.zcf/runners")
        os.makedirs(self.runners_dir, exist_ok=True)

    def get_search_directories(self) -> List[str]:
        """Return the standard directories scanned for Proton and Wine runners."""
        dirs = [
            self.runners_dir,
            os.path.expanduser("~/.local/share/Steam/compatibilitytools.d"),
            "/usr/share/steam/compatibilitytools.d",
            os.path.expanduser("~/.local/share/lutris/runners/wine"),
            os.path.expanduser("~/.local/share/bottles/runners"),
        ]
        return [os.path.abspath(d) for d in dirs if os.path.isdir(d)]

    def discover_local_runners(self) -> List[DiscoveredRunner]:
        """Scan local filesystem roots for compatibility runners."""
        runners: List[DiscoveredRunner] = []
        seen_paths = set()

        search_dirs = self.get_search_directories()
        for base_dir in search_dirs:
            if not os.path.exists(base_dir):
                continue
            try:
                for entry in os.scandir(base_dir):
                    if not entry.is_dir():
                        continue
                    r_path = os.path.realpath(entry.path)
                    if r_path in seen_paths:
                        continue
                    seen_paths.add(r_path)

                    runner = self._inspect_runner_dir(r_path, entry.name)
                    if runner:
                        runners.append(runner)
            except (PermissionError, OSError):
                continue

        # Check for system wine
        wine_bin = shutil.which("wine")
        if wine_bin and os.path.realpath(wine_bin) not in seen_paths:
            seen_paths.add(os.path.realpath(wine_bin))
            runners.append(
                DiscoveredRunner(
                    id="runtime.wine.system",
                    name="System Wine",
                    path=os.path.dirname(os.path.dirname(wine_bin)) if os.path.dirname(wine_bin).endswith("bin") else os.path.dirname(wine_bin),
                    runner_type="system-wine",
                    version="system",
                    is_system=True,
                    binary_path=wine_bin,
                    capabilities=["x86_64", "wow64", "directx", "vulkan"],
                )
            )

        return runners

    def _inspect_runner_dir(self, dir_path: str, dir_name: str) -> Optional[DiscoveredRunner]:
        """Inspect a candidate directory and determine runner metadata."""
        # 1. Proton check: Look for proton executable or compatibilitytool.vdf
        proton_bin = os.path.join(dir_path, "proton")
        wine_bin = os.path.join(dir_path, "bin", "wine")
        if not os.path.exists(wine_bin):
            wine_bin = os.path.join(dir_path, "files", "bin", "wine")

        if not os.path.exists(proton_bin) and not os.path.exists(wine_bin):
            return None

        runner_type = "custom"
        version_name = dir_name

        if "GE-Proton" in dir_name or "Proton-GE" in dir_name:
            runner_type = "ge-proton"
        elif "Proton" in dir_name or os.path.exists(proton_bin):
            runner_type = "valve-proton"
        elif "lutris" in dir_path.lower():
            runner_type = "lutris-wine"
        elif "wine" in dir_name.lower():
            runner_type = "wine-ge"

        # Check for version file
        version_file = os.path.join(dir_path, "version")
        if os.path.isfile(version_file):
            try:
                with open(version_file, "r", encoding="utf-8") as vf:
                    line = vf.readline().strip()
                    if line:
                        version_name = line
            except OSError:
                pass

        capabilities = ["x86_64", "wow64", "dxvk", "vkd3d_proton", "esync", "fsync"]
        runner_id = f"runtime.{runner_type}.{dir_name.lower().replace(' ', '_').replace('.', '_')}"

        return DiscoveredRunner(
            id=runner_id,
            name=dir_name,
            path=dir_path,
            runner_type=runner_type,
            version=version_name,
            is_system=False,
            binary_path=proton_bin if os.path.exists(proton_bin) else wine_bin,
            capabilities=capabilities,
        )

    def fetch_available_releases(self, limit: int = 10) -> List[AvailableRemoteRelease]:
        """Fetch latest releases of GE-Proton from GitHub API."""
        releases: List[AvailableRemoteRelease] = []
        req = urllib.request.Request(
            f"{self.GE_PROTON_GITHUB_API}?per_page={limit}",
            headers={"User-Agent": "ZCF-RunnerFleetManager/1.0", "Accept": "application/vnd.github.v3+json"},
        )
        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                for item in data:
                    tag = item.get("tag_name", "")
                    name = item.get("name") or tag
                    assets = item.get("assets", [])
                    tar_url = None
                    sum_url = None
                    size_bytes = 0
                    for asset in assets:
                        aname = asset.get("name", "")
                        if aname.endswith(".tar.gz") or aname.endswith(".tar.xz"):
                            tar_url = asset.get("browser_download_url")
                            size_bytes = int(asset.get("size", 0))
                        elif aname.endswith(".sha512sum"):
                            sum_url = asset.get("browser_download_url")

                    if tar_url:
                        releases.append(
                            AvailableRemoteRelease(
                                tag_name=tag,
                                name=name,
                                download_url=tar_url,
                                checksum_url=sum_url,
                                size_bytes=size_bytes,
                                published_at=item.get("published_at", ""),
                                runner_type="ge-proton",
                                description=item.get("body", "")[:300],
                            )
                        )
        except (urllib.error.URLError, TimeoutError, OSError, json.JSONDecodeError):
            # Fallback list of known stable releases if offline
            releases = [
                AvailableRemoteRelease(
                    tag_name="GE-Proton9-25",
                    name="GE-Proton9-25",
                    download_url="https://github.com/GloriousEggroll/proton-ge-custom/releases/download/GE-Proton9-25/GE-Proton9-25.tar.gz",
                    checksum_url="https://github.com/GloriousEggroll/proton-ge-custom/releases/download/GE-Proton9-25/GE-Proton9-25.sha512sum",
                    size_bytes=520000000,
                    published_at="2024-10-15T00:00:00Z",
                    runner_type="ge-proton",
                    description="Offline cached release reference for GE-Proton9-25",
                ),
                AvailableRemoteRelease(
                    tag_name="GE-Proton9-24",
                    name="GE-Proton9-24",
                    download_url="https://github.com/GloriousEggroll/proton-ge-custom/releases/download/GE-Proton9-24/GE-Proton9-24.tar.gz",
                    checksum_url="https://github.com/GloriousEggroll/proton-ge-custom/releases/download/GE-Proton9-24/GE-Proton9-24.sha512sum",
                    size_bytes=518000000,
                    published_at="2024-09-20T00:00:00Z",
                    runner_type="ge-proton",
                    description="Offline cached release reference for GE-Proton9-24",
                ),
            ]
        return releases

    def verify_archive_checksum(self, archive_path: str, expected_sha512: str) -> bool:
        """Verify the SHA-512 cryptographic checksum of a downloaded runner archive."""
        hasher = hashlib.sha512()
        with open(archive_path, "rb") as f:
            while chunk := f.read(1024 * 1024):
                hasher.update(chunk)
        calculated = hasher.hexdigest().strip().lower()
        clean_expected = expected_sha512.strip().lower()
        # In sha512sum files, it often appears as "<hash>  filename"
        if " " in clean_expected:
            clean_expected = clean_expected.split()[0]
        return calculated == clean_expected

    def install_runner(
        self,
        archive_path: str,
        target_name: Optional[str] = None,
        expected_sha512: Optional[str] = None,
        symlink_to_steam: bool = True,
    ) -> DiscoveredRunner:
        """Safely extract and install a downloaded runner archive into ~/.zcf/runners/."""
        if not os.path.isfile(archive_path):
            raise FileNotFoundError(f"Runner archive does not exist: {archive_path}")

        if expected_sha512:
            if not self.verify_archive_checksum(archive_path, expected_sha512):
                raise ValueError("SHA-512 checksum verification failed for runner archive.")

        # Determine target directory name
        base_filename = os.path.basename(archive_path)
        dir_name = target_name or base_filename.replace(".tar.gz", "").replace(".tar.xz", "")
        dest_dir = os.path.join(self.runners_dir, dir_name)

        if os.path.exists(dest_dir):
            shutil.rmtree(dest_dir)
        os.makedirs(dest_dir, exist_ok=True)

        # Extract archive with zip-slip path traversal protection
        with tarfile.open(archive_path, "r:*") as tar:
            target_real = os.path.realpath(dest_dir)
            for member in tar.getmembers():
                member_path = os.path.realpath(os.path.join(dest_dir, member.name))
                if not member_path.startswith(target_real + os.sep) and member_path != target_real:
                    raise PermissionError(f"Archive entry attempted directory traversal: {member.name}")

            # Safely unpack
            tar.extractall(path=dest_dir)

        # If archive had a top-level single directory, adjust if needed
        sub_items = os.listdir(dest_dir)
        if len(sub_items) == 1 and os.path.isdir(os.path.join(dest_dir, sub_items[0])):
            nested = os.path.join(dest_dir, sub_items[0])
            for item in os.listdir(nested):
                shutil.move(os.path.join(nested, item), dest_dir)
            os.rmdir(nested)

        # Optionally symlink to Steam compatibilitytools.d
        if symlink_to_steam:
            steam_tools = os.path.expanduser("~/.local/share/Steam/compatibilitytools.d")
            if os.path.isdir(steam_tools):
                steam_link = os.path.join(steam_tools, dir_name)
                try:
                    if not os.path.exists(steam_link):
                        os.symlink(dest_dir, steam_link)
                except OSError:
                    pass

        runner = self._inspect_runner_dir(dest_dir, dir_name)
        if not runner:
            runner = DiscoveredRunner(
                id=f"runtime.custom.{dir_name.lower().replace('.', '_')}",
                name=dir_name,
                path=dest_dir,
                runner_type="custom",
                version=dir_name,
                binary_path=os.path.join(dest_dir, "proton") if os.path.exists(os.path.join(dest_dir, "proton")) else os.path.join(dest_dir, "bin", "wine"),
                capabilities=["x86_64", "wow64"],
            )
        return runner

    def register_fleet_with_registry(self, registry: Any) -> int:
        """Register all discovered runners into the ZCF RuntimeRegistry."""
        count = 0
        runners = self.discover_local_runners()
        for r in runners:
            if r.runner_type in ("ge-proton", "valve-proton") and r.binary_path:
                adapter = ProtonAdapter(
                    custom_id=r.id,
                    custom_name=r.name,
                    proton_binary=r.binary_path,
                )
                try:
                    registry.register(adapter)
                    count += 1
                except Exception:
                    pass
        return count
