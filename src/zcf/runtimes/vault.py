"""Universal Game Save Vault for ZCF.

Discovers Windows save game locations inside Wine/Proton prefixes,
creates compressed backups in ~/.zcf/vault/, and enables zero-risk
prefix resets and cross-runner save migration.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import tarfile
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


@dataclass
class DiscoveredSavePath:
    """Represents a discovered game save folder inside a prefix."""

    folder_name: str
    absolute_path: str
    relative_to_drive_c: str
    category: str  # "appdata_local", "appdata_roaming", "documents", "saved_games", "local_low"
    size_bytes: int
    files_count: int

    def to_dict(self) -> Dict[str, Any]:
        return {
            "folder_name": self.folder_name,
            "absolute_path": self.absolute_path,
            "relative_to_drive_c": self.relative_to_drive_c,
            "category": self.category,
            "size_bytes": self.size_bytes,
            "files_count": self.files_count,
        }


@dataclass
class SaveVaultEntry:
    """Represents an archived save game backup stored in the Vault."""

    vault_id: str
    app_name: str
    created_at: str
    source_prefix: str
    archive_path: str
    size_bytes: int
    sha256: str
    saved_locations: List[Dict[str, Any]] = field(default_factory=list)
    notes: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "vault_id": self.vault_id,
            "app_name": self.app_name,
            "created_at": self.created_at,
            "source_prefix": self.source_prefix,
            "archive_path": self.archive_path,
            "size_bytes": self.size_bytes,
            "sha256": self.sha256,
            "saved_locations": list(self.saved_locations),
            "notes": self.notes,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> SaveVaultEntry:
        return cls(
            vault_id=str(data["vault_id"]),
            app_name=str(data["app_name"]),
            created_at=str(data.get("created_at", "")),
            source_prefix=str(data.get("source_prefix", "")),
            archive_path=str(data.get("archive_path", "")),
            size_bytes=int(data.get("size_bytes", 0)),
            sha256=str(data.get("sha256", "")),
            saved_locations=list(data.get("saved_locations") or []),
            notes=str(data.get("notes", "")),
        )


class GameSaveVault:
    """Manages discovery, archiving, and migration of game save data."""

    def __init__(self, vault_dir: Optional[str] = None):
        if vault_dir:
            self.vault_dir = os.path.abspath(vault_dir)
        else:
            self.vault_dir = os.path.expanduser("~/.zcf/vault")
        os.makedirs(self.vault_dir, exist_ok=True)

    def discover_save_locations(
        self, prefix_path: str, app_name_filter: Optional[str] = None
    ) -> List[DiscoveredSavePath]:
        """Scan a prefix for candidate Windows save game directories."""
        prefix_real = os.path.realpath(prefix_path)
        drive_c = os.path.join(prefix_real, "drive_c")
        if not os.path.isdir(drive_c):
            return []

        users_dir = os.path.join(drive_c, "users")
        if not os.path.isdir(users_dir):
            return []

        discovered: List[DiscoveredSavePath] = []
        filter_lower = app_name_filter.lower().strip() if app_name_filter else None

        # Search across all Windows user profiles in prefix
        for user_entry in os.scandir(users_dir):
            if not user_entry.is_dir() or user_entry.name in ("Public", "Default"):
                continue

            user_root = user_entry.path
            search_targets = [
                (os.path.join(user_root, "AppData", "Local"), "appdata_local"),
                (os.path.join(user_root, "AppData", "LocalLow"), "local_low"),
                (os.path.join(user_root, "AppData", "Roaming"), "appdata_roaming"),
                (os.path.join(user_root, "Documents", "My Games"), "documents"),
                (os.path.join(user_root, "Saved Games"), "saved_games"),
            ]

            for parent_dir, cat in search_targets:
                if not os.path.isdir(parent_dir):
                    continue
                try:
                    for app_folder in os.scandir(parent_dir):
                        if not app_folder.is_dir():
                            continue
                        fname = app_folder.name
                        if fname in ("Microsoft", "Windows", "Temp", "CrashDumps"):
                            continue

                        if filter_lower and filter_lower not in fname.lower():
                            continue

                        # Calculate directory size and count
                        total_bytes = 0
                        fcount = 0
                        for root, _, files in os.walk(app_folder.path):
                            for f in files:
                                fcount += 1
                                try:
                                    total_bytes += os.path.getsize(os.path.join(root, f))
                                except OSError:
                                    pass

                        if fcount > 0:
                            rel = os.path.relpath(app_folder.path, drive_c)
                            discovered.append(
                                DiscoveredSavePath(
                                    folder_name=fname,
                                    absolute_path=app_folder.path,
                                    relative_to_drive_c=rel,
                                    category=cat,
                                    size_bytes=total_bytes,
                                    files_count=fcount,
                                )
                            )
                except (PermissionError, OSError):
                    continue

        return discovered

    def backup_save(
        self,
        prefix_path: str,
        app_name: str,
        notes: str = "",
    ) -> SaveVaultEntry:
        """Discover and backup game save data into the Vault."""
        prefix_real = os.path.realpath(prefix_path)
        locations = self.discover_save_locations(prefix_real, app_name_filter=app_name)
        if not locations:
            # Check if an exact subfolder exists
            raise FileNotFoundError(f"No save game directories found for '{app_name}' in prefix {prefix_path}")

        app_slug = "".join(c if c.isalnum() or c in ("-", "_") else "_" for c in app_name.lower())
        app_vault_dir = os.path.join(self.vault_dir, app_slug)
        os.makedirs(app_vault_dir, exist_ok=True)

        timestamp_str = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        vault_id = f"vault_{app_slug}_{timestamp_str}"
        archive_name = f"{vault_id}.tar.gz"
        archive_path = os.path.join(app_vault_dir, archive_name)

        drive_c = os.path.join(prefix_real, "drive_c")

        # Archive each discovered location with path relative to drive_c
        with tarfile.open(archive_path, "w:gz") as tar:
            for loc in locations:
                tar.add(loc.absolute_path, arcname=loc.relative_to_drive_c)

        # Calculate SHA-256
        hasher = hashlib.sha256()
        with open(archive_path, "rb") as f:
            while chunk := f.read(1024 * 1024):
                hasher.update(chunk)
        archive_sha = hasher.hexdigest()
        archive_size = os.path.getsize(archive_path)

        entry = SaveVaultEntry(
            vault_id=vault_id,
            app_name=app_name,
            created_at=datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            source_prefix=prefix_real,
            archive_path=archive_path,
            size_bytes=archive_size,
            sha256=archive_sha,
            saved_locations=[loc.to_dict() for loc in locations],
            notes=notes,
        )

        meta_path = os.path.join(app_vault_dir, f"{vault_id}.json")
        with open(meta_path, "w", encoding="utf-8") as f:
            json.dump(entry.to_dict(), f, indent=2)

        return entry

    def list_backups(self, app_name_filter: Optional[str] = None) -> List[SaveVaultEntry]:
        """List all save game backups in the vault, newest first."""
        entries: List[SaveVaultEntry] = []
        filter_lower = app_name_filter.lower().strip() if app_name_filter else None

        if not os.path.isdir(self.vault_dir):
            return []

        for root, _, files in os.walk(self.vault_dir):
            for file in files:
                if file.endswith(".json") and file.startswith("vault_"):
                    try:
                        with open(os.path.join(root, file), "r", encoding="utf-8") as f:
                            data = json.load(f)
                            entry = SaveVaultEntry.from_dict(data)
                            if not filter_lower or filter_lower in entry.app_name.lower():
                                entries.append(entry)
                    except (OSError, json.JSONDecodeError):
                        continue

        entries.sort(key=lambda e: e.created_at, reverse=True)
        return entries

    def restore_save(self, vault_id: str, target_prefix_path: str) -> bool:
        """Restore a save archive from the vault into target prefix drive_c."""
        target_drive_c = os.path.join(os.path.realpath(target_prefix_path), "drive_c")
        if not os.path.isdir(target_drive_c):
            raise FileNotFoundError(f"Target prefix drive_c not found: {target_drive_c}")

        # Find entry
        entry = None
        for b in self.list_backups():
            if b.vault_id == vault_id:
                entry = b
                break

        if not entry:
            raise FileNotFoundError(f"Vault entry '{vault_id}' not found.")

        if not os.path.isfile(entry.archive_path):
            raise FileNotFoundError(f"Vault archive file missing: {entry.archive_path}")

        # Extract safely into target drive_c
        with tarfile.open(entry.archive_path, "r:gz") as tar:
            target_real = os.path.realpath(target_drive_c)
            for member in tar.getmembers():
                dest_path = os.path.realpath(os.path.join(target_drive_c, member.name))
                if not dest_path.startswith(target_real + os.sep) and dest_path != target_real:
                    raise PermissionError(f"Directory traversal detected in archive: {member.name}")
            tar.extractall(path=target_drive_c)

        return True

    def delete_backup(self, vault_id: str) -> bool:
        """Delete a save vault archive and its metadata."""
        for b in self.list_backups():
            if b.vault_id == vault_id:
                if os.path.isfile(b.archive_path):
                    os.remove(b.archive_path)
                meta_path = b.archive_path.replace(".tar.gz", ".json")
                if os.path.isfile(meta_path):
                    os.remove(meta_path)
                return True
        return False
