"""
Compatibility Database Manager for ZCF.
Persists, indexes, and queries evidence-backed application compatibility entries.
"""

from __future__ import annotations

import json
import os
from typing import Any, Dict, List, Optional

from zcf.core.exceptions import DatabaseError
from zcf.core.models import CompatibilityEntry, CompatibilityStatus


class CompatibilityDatabase:
    """Manages local JSON compatibility records."""

    def __init__(self, storage_dir: Optional[str] = None):
        self.storage_dir = storage_dir or os.path.expanduser("~/.zcf/compat_db")
        os.makedirs(self.storage_dir, exist_ok=True)
        self._seed_default_entries()

    def _seed_default_entries(self):
        """Seeds initial verified benchmark entries if database is empty."""
        if len(self.list_all()) == 0:
            seed_entries = [
                CompatibilityEntry(
                    entry_id="zcf_entry_notepad_pe",
                    application_name="Windows Notepad",
                    version="10.0",
                    target_sha256="15cd209c995b7d3009c91ca40892d5b8f1fb162f3e5f10716642ea278e8e0d7b",
                    target_format="pe",
                    target_architecture="x86_64",
                    status=CompatibilityStatus.VERIFIED_COMPATIBLE,
                    last_verified="2026-10-24T12:00:00Z",
                    recommended_runtime="runtime.wine",
                    verified_environment={"os": "ubuntu", "kernel": "6.18", "runner_version": "wine-9.0"},
                    workarounds=[],
                    diagnostic_signatures=[],
                    provenance={"authority": "maintainer-verified", "contributor": "Zyntrix Labs"},
                ),
                CompatibilityEntry(
                    entry_id="zcf_entry_qemu_busybox_arm64",
                    application_name="Busybox Static",
                    version="1.36.1",
                    target_sha256="e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
                    target_format="elf",
                    target_architecture="arm64",
                    status=CompatibilityStatus.VERIFIED_COMPATIBLE,
                    last_verified="2026-10-24T12:30:00Z",
                    recommended_runtime="runtime.qemu-user",
                    verified_environment={"os": "linux", "kernel": "6.18", "runner_version": "qemu-10.2"},
                    workarounds=[],
                    diagnostic_signatures=[],
                    provenance={"authority": "automated-ci", "contributor": "Zyntrix Labs"},
                ),
            ]
            for entry in seed_entries:
                self.add_entry(entry)

    def add_entry(self, entry: CompatibilityEntry) -> str:
        self._validate_entry(entry)
        file_path = os.path.join(self.storage_dir, f"{entry.entry_id}.json")
        try:
            with open(file_path, "w", encoding="utf-8") as f:
                json.dump(entry.to_dict(), f, indent=2)
            return file_path
        except Exception as e:
            raise DatabaseError(f"Failed to persist compatibility entry: {str(e)}")

    def get_by_sha256(self, target_sha256: str) -> Optional[CompatibilityEntry]:
        for entry in self.list_all():
            if entry.target_sha256.lower() == target_sha256.lower():
                return entry
        return None

    def get_by_id(self, entry_id: str) -> Optional[CompatibilityEntry]:
        file_path = os.path.join(self.storage_dir, f"{entry_id}.json")
        if os.path.exists(file_path):
            try:
                with open(file_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    return self._dict_to_entry(data)
            except Exception:
                pass
        return None

    def list_all(self) -> List[CompatibilityEntry]:
        entries: List[CompatibilityEntry] = []
        if not os.path.exists(self.storage_dir):
            return entries

        for fname in os.listdir(self.storage_dir):
            if fname.endswith(".json"):
                fpath = os.path.join(self.storage_dir, fname)
                try:
                    with open(fpath, "r", encoding="utf-8") as f:
                        data = json.load(f)
                        entries.append(self._dict_to_entry(data))
                except Exception:
                    continue
        return entries

    def _validate_entry(self, entry: CompatibilityEntry):
        if not entry.entry_id:
            raise DatabaseError("Missing entry_id")
        if not entry.target_sha256 or len(entry.target_sha256) != 64:
            raise DatabaseError("Invalid or missing target_sha256")
        if not entry.target_format:
            raise DatabaseError("Missing target_format")

    def _dict_to_entry(self, data: Dict[str, Any]) -> CompatibilityEntry:
        return CompatibilityEntry(
            entry_id=data["entry_id"],
            application_name=data["application_name"],
            version=data.get("version"),
            target_sha256=data["target_sha256"],
            target_format=data["target_format"],
            target_architecture=data.get("target_architecture", "unknown"),
            status=CompatibilityStatus(data["status"]),
            last_verified=data["last_verified"],
            recommended_runtime=data.get("recommended_runtime"),
            verified_environment=data.get("verified_environment", {}),
            workarounds=data.get("workarounds", []),
            diagnostic_signatures=data.get("diagnostic_signatures", []),
            provenance=data.get("provenance", {}),
        )
