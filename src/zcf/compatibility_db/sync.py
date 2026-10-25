"""
Compatibility Knowledge Base Synchronization and Evidence Bundle Manager.
Handles atomic import, export, and merge of compatibility profiles across distributed Linux nodes.
"""

from __future__ import annotations

import json
import os
import tarfile
from typing import Any, Dict, List, Optional

from zcf.compatibility_db.database import CompatibilityDatabase
from zcf.core.exceptions import DatabaseError
from zcf.core.models import (
    CompatibilityEntry,
    CompatibilityStatus,
    EvidenceStatus,
    ProvenanceTier,
)


class CompatibilitySyncManager:
    """Exports and imports verified compatibility knowledge bundles."""

    def __init__(self, db: Optional[CompatibilityDatabase] = None):
        self.db = db or CompatibilityDatabase()

    def export_bundle(self, output_path: str) -> str:
        """Exports all local database entries into a portable JSON evidence bundle."""
        entries = self.db.list_all()
        bundle_data = {
            "bundle_version": "1.0",
            "entry_count": len(entries),
            "license": "CC-BY-4.0",
            "entries": [e.to_dict() for e in entries],
        }

        os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
        try:
            with open(output_path, "w", encoding="utf-8") as f:
                json.dump(bundle_data, f, indent=2)
            return os.path.abspath(output_path)
        except Exception as e:
            raise DatabaseError(f"Failed to export evidence bundle: {str(e)}")

    def import_bundle(
        self,
        bundle_path: str,
        overwrite_older: bool = True,
        trust_external_provenance: bool = False,
    ) -> int:
        """Imports an evidence bundle, merging records with conflict resolution and provenance verification."""
        if not os.path.exists(bundle_path):
            raise DatabaseError(f"Bundle file not found: {bundle_path}")

        try:
            with open(bundle_path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception as e:
            raise DatabaseError(f"Invalid JSON in bundle: {str(e)}")

        raw_entries = data.get("entries", [])
        imported_count = 0

        for r_entry in raw_entries:
            try:
                entry = self.db._dict_to_entry(r_entry)

                # Validate entry ID safety
                if not entry.entry_id:
                    continue

                # Downgrade unverified third-party claims of maintainer verification unless explicitly trusted
                if not trust_external_provenance and entry.provenance_tier == ProvenanceTier.MAINTAINER_VERIFIED:
                    entry.provenance_tier = ProvenanceTier.COMMUNITY_UNTESTED
                    entry.evidence_status = EvidenceStatus.COMMUNITY_REPORTED

                existing = self.db.get_by_id(entry.entry_id)
                if not existing or (overwrite_older and entry.last_verified >= existing.last_verified):
                    self.db.add_entry(entry)
                    imported_count += 1
            except Exception:
                continue

        return imported_count
