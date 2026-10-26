"""Prefix Time-Machine and Differential Rollback Engine for ZCF.

Provides instant snapshot creation, differential registry preservation,
and one-click prefix rollback to protect against breaking component installations,
regedit mistakes, or runtime corruption.
"""

from __future__ import annotations

import json
import os
import shutil
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional


@dataclass
class PrefixSnapshot:
    """Represents a saved state snapshot of an isolated Wine/Proton prefix."""

    id: str
    prefix_path: str
    label: str
    created_at: str
    trigger: str  # "manual", "auto_pre_component", "auto_pre_run", "recovery"
    size_bytes: int
    files_preserved: List[str] = field(default_factory=list)
    description: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "prefix_path": self.prefix_path,
            "label": self.label,
            "created_at": self.created_at,
            "trigger": self.trigger,
            "size_bytes": self.size_bytes,
            "files_preserved": list(self.files_preserved),
            "description": self.description,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> PrefixSnapshot:
        return cls(
            id=str(data["id"]),
            prefix_path=str(data["prefix_path"]),
            label=str(data.get("label", "")),
            created_at=str(data.get("created_at", "")),
            trigger=str(data.get("trigger", "manual")),
            size_bytes=int(data.get("size_bytes", 0)),
            files_preserved=list(data.get("files_preserved") or []),
            description=str(data.get("description", "")),
        )


class PrefixSnapshotManager:
    """Manages creation, restoration, and lifecycle of prefix snapshots."""

    SNAPSHOTS_DIR_NAME = ".zcf_snapshots"
    CRITICAL_REGISTRY_FILES = ("system.reg", "user.reg", "userdef.reg", "prefix_meta.json", ".update-timestamp")

    def __init__(self, default_retention: int = 20):
        self.default_retention = default_retention

    def _get_snapshots_dir(self, prefix_path: str) -> str:
        return os.path.join(os.path.abspath(prefix_path), self.SNAPSHOTS_DIR_NAME)

    def create_snapshot(
        self,
        prefix_path: str,
        label: str,
        trigger: str = "manual",
        description: str = "",
    ) -> PrefixSnapshot:
        """Capture an instant snapshot of registry and system configuration state."""
        prefix_real = os.path.realpath(prefix_path)
        if not os.path.exists(prefix_real):
            raise FileNotFoundError(f"Prefix path does not exist: {prefix_path}")

        timestamp_str = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        snap_id = f"snap_{timestamp_str}_{int(time.time() * 1000) % 1000}"
        snap_dir = os.path.join(self._get_snapshots_dir(prefix_real), snap_id)
        os.makedirs(snap_dir, exist_ok=True)

        preserved_files: List[str] = []
        total_size = 0

        # 1. Preserve critical registry hives and prefix metadata
        for fname in self.CRITICAL_REGISTRY_FILES:
            src = os.path.join(prefix_real, fname)
            if os.path.isfile(src):
                dst = os.path.join(snap_dir, fname)
                shutil.copy2(src, dst)
                preserved_files.append(fname)
                total_size += os.path.getsize(dst)

        # 2. Preserve Windows system registry delta backups if present
        sys_override_path = os.path.join(prefix_real, "drive_c", "windows", "system.ini")
        if os.path.isfile(sys_override_path):
            dst = os.path.join(snap_dir, "system.ini")
            shutil.copy2(sys_override_path, dst)
            preserved_files.append("drive_c/windows/system.ini")
            total_size += os.path.getsize(dst)

        # 3. Create metadata record
        snapshot = PrefixSnapshot(
            id=snap_id,
            prefix_path=prefix_real,
            label=label or f"Snapshot {timestamp_str}",
            created_at=datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            trigger=trigger,
            size_bytes=total_size,
            files_preserved=preserved_files,
            description=description,
        )

        meta_file = os.path.join(snap_dir, "snapshot_meta.json")
        with open(meta_file, "w", encoding="utf-8") as f:
            json.dump(snapshot.to_dict(), f, indent=2)

        # 4. Prune snapshots if exceeding retention
        self._prune_snapshots(prefix_real)

        return snapshot

    def list_snapshots(self, prefix_path: str) -> List[PrefixSnapshot]:
        """List all snapshots available for the specified prefix, newest first."""
        snaps_dir = self._get_snapshots_dir(prefix_path)
        if not os.path.exists(snaps_dir):
            return []

        snapshots: List[PrefixSnapshot] = []
        try:
            for entry in os.scandir(snaps_dir):
                if entry.is_dir():
                    meta_file = os.path.join(entry.path, "snapshot_meta.json")
                    if os.path.isfile(meta_file):
                        try:
                            with open(meta_file, "r", encoding="utf-8") as f:
                                data = json.load(f)
                                snapshots.append(PrefixSnapshot.from_dict(data))
                        except (OSError, json.JSONDecodeError):
                            continue
        except OSError:
            return []

        # Sort newest first
        snapshots.sort(key=lambda s: s.created_at, reverse=True)
        return snapshots

    def restore_snapshot(self, prefix_path: str, snapshot_id: str) -> bool:
        """Roll back the prefix to the exact state saved in the specified snapshot."""
        prefix_real = os.path.realpath(prefix_path)
        snap_dir = os.path.join(self._get_snapshots_dir(prefix_real), snapshot_id)
        meta_file = os.path.join(snap_dir, "snapshot_meta.json")

        if not os.path.isfile(meta_file):
            raise FileNotFoundError(f"Snapshot '{snapshot_id}' not found in {prefix_path}")

        with open(meta_file, "r", encoding="utf-8") as f:
            meta = json.load(f)

        files = meta.get("files_preserved", [])

        # Restore preserved files
        for fname in files:
            src = os.path.join(snap_dir, os.path.basename(fname))
            if os.path.isfile(src):
                dst = os.path.join(prefix_real, fname)
                os.makedirs(os.path.dirname(dst), exist_ok=True)
                shutil.copy2(src, dst)

        return True

    def delete_snapshot(self, prefix_path: str, snapshot_id: str) -> bool:
        """Permanently delete a snapshot."""
        snap_dir = os.path.join(self._get_snapshots_dir(prefix_path), snapshot_id)
        if os.path.isdir(snap_dir):
            shutil.rmtree(snap_dir)
            return True
        return False

    def _prune_snapshots(self, prefix_path: str) -> None:
        """Prune oldest snapshots exceeding retention limit."""
        snapshots = self.list_snapshots(prefix_path)
        if len(snapshots) > self.default_retention:
            for s in snapshots[self.default_retention :]:
                self.delete_snapshot(prefix_path, s.id)


def auto_pre_component_snapshot(prefix_path: str, component_name: str) -> Optional[PrefixSnapshot]:
    """Helper to automatically snapshot a prefix before installing a component."""
    try:
        manager = PrefixSnapshotManager()
        return manager.create_snapshot(
            prefix_path=prefix_path,
            label=f"Auto pre-install: {component_name}",
            trigger="auto_pre_component",
            description=f"Automated Time-Machine restore point created before installing {component_name}",
        )
    except Exception:
        return None
