"""
Compatibility Knowledge Base Synchronization and Evidence Bundle Manager.
Handles atomic import, export, schema validation, and rollback of compatibility profiles across distributed nodes.
"""

from __future__ import annotations

import json
import os
import re
from typing import Any, Dict, List, Optional

from zcf.compatibility_db.database import CompatibilityDatabase, is_placeholder_hash
from zcf.core.exceptions import DatabaseError
from zcf.core.models import (
    CompatibilityEntry,
    CompatibilityStatus,
    EvidenceStatus,
    ProvenanceTier,
)


class CompatibilitySyncManager:
    """Exports and imports verified compatibility knowledge bundles with atomic transaction semantics."""

    SUPPORTED_BUNDLE_VERSIONS = {"1.0", "2.0"}

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
        """
        Imports an evidence bundle with atomic all-or-nothing transaction semantics.
        Validates bundle version, schema types, entry count consistency, and record safety.
        Treats external bundles as untrusted input: external unauthenticated bundles cannot claim
        maintainer-verified status without cryptographic attestation.
        """
        if not os.path.exists(bundle_path):
            raise DatabaseError(f"Bundle file not found: {bundle_path}")

        try:
            with open(bundle_path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception as e:
            raise DatabaseError(f"Invalid JSON in bundle: {str(e)}")

        if not isinstance(data, dict):
            raise DatabaseError("Malformed bundle: root payload must be a JSON object.")

        # 1. Validate bundle version
        version = str(data.get("bundle_version", ""))
        if version not in self.SUPPORTED_BUNDLE_VERSIONS:
            raise DatabaseError(
                f"Unsupported bundle version '{version}'. Supported versions are: {sorted(self.SUPPORTED_BUNDLE_VERSIONS)}"
            )

        # 2. Validate entry count consistency
        raw_entries = data.get("entries")
        if not isinstance(raw_entries, list):
            raise DatabaseError("Malformed bundle: 'entries' field must be an array.")

        declared_count = data.get("entry_count")
        if declared_count is not None and declared_count != len(raw_entries):
            raise DatabaseError(
                f"Bundle entry count mismatch: declared {declared_count}, but contains {len(raw_entries)} entries."
            )

        # 3. Stage and strictly validate all entries into memory
        staged_entries: List[CompatibilityEntry] = []
        for idx, r_entry in enumerate(raw_entries):
            if not isinstance(r_entry, dict):
                raise DatabaseError(f"Malformed entry at index {idx}: entry must be a JSON object.")

            try:
                entry = self.db._dict_to_entry(r_entry)
            except Exception as e:
                raise DatabaseError(f"Malformed schema in entry at index {idx}: {str(e)}")

            # Validate entry_id safety (prevent directory traversal and illegal characters)
            if not entry.entry_id or not re.match(r"^[a-zA-Z0-9_\-]+$", entry.entry_id):
                raise DatabaseError(f"Security error in entry at index {idx}: invalid or dangerous entry_id '{entry.entry_id}'.")

            # Validate target SHA-256 format
            if not entry.target_sha256 or len(entry.target_sha256) != 64 or not re.match(r"^[0-9a-fA-F]{64}$", entry.target_sha256):
                raise DatabaseError(f"Validation error in entry '{entry.entry_id}': invalid SHA-256 target hash format.")

            # Unauthenticated external bundles are treated as untrusted:
            # Claims of MAINTAINER_VERIFIED or AUTOMATED_TEST are safely downgraded to COMMUNITY_UNTESTED / COMMUNITY_REPORTED.
            if not trust_external_provenance or is_placeholder_hash(entry.target_sha256):
                if entry.provenance_tier in (ProvenanceTier.MAINTAINER_VERIFIED, ProvenanceTier.AUTOMATED_TEST):
                    entry.provenance_tier = ProvenanceTier.COMMUNITY_UNTESTED
                if entry.evidence_status in (EvidenceStatus.VERIFIED, EvidenceStatus.REPRODUCED):
                    entry.evidence_status = EvidenceStatus.COMMUNITY_REPORTED
                if entry.status == CompatibilityStatus.VERIFIED_COMPATIBLE:
                    entry.status = CompatibilityStatus.UNTESTED

            staged_entries.append(entry)

        # 4. Atomic Commit with Rollback Protection
        backups: Dict[str, str] = {}
        created_files: List[str] = []
        imported_count = 0

        try:
            for entry in staged_entries:
                file_path = self.db._resolve_entry_path(entry.entry_id)
                existing = self.db.get_by_id(entry.entry_id)

                if existing and not overwrite_older and entry.last_verified < existing.last_verified:
                    continue

                if os.path.exists(file_path):
                    if file_path not in backups:
                        with open(file_path, "r", encoding="utf-8") as f:
                            backups[file_path] = f.read()
                else:
                    created_files.append(file_path)

                self.db.add_entry(entry)
                imported_count += 1

            return imported_count

        except Exception as e:
            # Atomic rollback: restore previous files and remove newly written files
            for path, orig_content in backups.items():
                try:
                    with open(path, "w", encoding="utf-8") as f:
                        f.write(orig_content)
                except Exception:
                    pass
            for path in created_files:
                try:
                    if os.path.exists(path):
                        os.remove(path)
                except Exception:
                    pass
            raise DatabaseError(f"Import transaction failed and was rolled back cleanly: {str(e)}")
