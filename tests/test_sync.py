"""
Unit tests for ZCF Knowledge Base Sync and Evidence Bundling.
"""

import json
import os
import shutil
import tempfile
import unittest

from zcf.compatibility_db.database import CompatibilityDatabase
from zcf.compatibility_db.sync import CompatibilitySyncManager
from zcf.core.models import (
    CompatibilityEntry,
    CompatibilityStatus,
    EvidenceStatus,
    ProvenanceTier,
)


class TestCompatibilitySync(unittest.TestCase):
    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        self.db = CompatibilityDatabase(storage_dir=os.path.join(self.test_dir, "db"))
        self.sync = CompatibilitySyncManager(self.db)
        # Add a legitimate maintainer_verified record with a real non-placeholder hash
        self.db.add_entry(
            CompatibilityEntry(
                entry_id="legit_verified_pkg",
                application_name="Legit App",
                target_sha256="7c5b6a4d3e2f109876543210abcdef0123456789abcdef0123456789abcdef01",
                target_format="pe",
                target_architecture="x86_64",
                status=CompatibilityStatus.VERIFIED_COMPATIBLE,
                last_verified="2026-10-25T00:00:00Z",
                recommended_runtime="runtime.wine",
                provenance_tier=ProvenanceTier.MAINTAINER_VERIFIED,
                evidence_status=EvidenceStatus.VERIFIED,
            )
        )

    def tearDown(self):
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_export_and_import_bundle(self):
        export_file = os.path.join(self.test_dir, "test_bundle.json")
        res_path = self.sync.export_bundle(export_file)

        self.assertTrue(os.path.exists(res_path))
        with open(res_path, "r", encoding="utf-8") as f:
            data = json.load(f)
            self.assertEqual(data["bundle_version"], "1.0")
            self.assertGreater(data["entry_count"], 0)

        # Import into fresh database with trust_external_provenance=False
        fresh_db_dir = os.path.join(self.test_dir, "fresh_db")
        fresh_db = CompatibilityDatabase(storage_dir=fresh_db_dir)
        fresh_sync = CompatibilitySyncManager(fresh_db)

        imported = fresh_sync.import_bundle(res_path, trust_external_provenance=False)
        self.assertGreaterEqual(imported, 1)

        # Verify untrusted external entries are safely downgraded from maintainer verified
        downgraded_entry = fresh_db.get_by_id("legit_verified_pkg")
        self.assertIsNotNone(downgraded_entry)
        self.assertEqual(downgraded_entry.provenance_tier.value, "community_untested")
        self.assertEqual(downgraded_entry.evidence_status.value, "community_reported")

        # Now test with trust_external_provenance=True
        trusted_db_dir = os.path.join(self.test_dir, "trusted_db")
        trusted_db = CompatibilityDatabase(storage_dir=trusted_db_dir)
        trusted_sync = CompatibilitySyncManager(trusted_db)
        trusted_sync.import_bundle(res_path, trust_external_provenance=True)
        trusted_entry = trusted_db.get_by_id("legit_verified_pkg")
        self.assertIsNotNone(trusted_entry)
        self.assertEqual(trusted_entry.provenance_tier.value, "maintainer_verified")
        self.assertEqual(trusted_entry.evidence_status.value, "verified")

    def test_import_malformed_entry_fails_and_rolls_back(self):
        """Atomic rollback ensures one malformed record does not partially apply."""
        from zcf.core.exceptions import DatabaseError

        fresh_db_dir = os.path.join(self.test_dir, "rollback_db")
        fresh_db = CompatibilityDatabase(storage_dir=fresh_db_dir)
        fresh_sync = CompatibilitySyncManager(fresh_db)

        # Bundle with 1 valid entry followed by 1 invalid entry (path traversal)
        malformed_bundle = {
            "bundle_version": "1.0",
            "entry_count": 2,
            "entries": [
                {
                    "entry_id": "valid_import_record",
                    "application_name": "Valid App",
                    "target_sha256": "a" * 64,
                    "target_format": "pe",
                    "target_architecture": "x86_64",
                    "status": "untested",
                    "last_verified": "2026-10-25T00:00:00Z",
                    "recommended_runtime": "runtime.wine",
                },
                {
                    "entry_id": "../../etc/evil_import",
                    "application_name": "Evil App",
                    "target_sha256": "b" * 64,
                    "target_format": "pe",
                    "target_architecture": "x86_64",
                    "status": "untested",
                    "last_verified": "2026-10-25T00:00:00Z",
                },
            ],
        }
        bundle_path = os.path.join(self.test_dir, "malformed_bundle.json")
        with open(bundle_path, "w", encoding="utf-8") as f:
            json.dump(malformed_bundle, f)

        with self.assertRaises(DatabaseError):
            fresh_sync.import_bundle(bundle_path)

        # Atomic rollback verification: valid_import_record must NOT have been saved!
        self.assertIsNone(fresh_db.get_by_id("valid_import_record"))

    def test_import_entry_count_mismatch_fails(self):
        """Discrepancies between declared count and actual entries must be rejected."""
        from zcf.core.exceptions import DatabaseError

        mismatch_bundle = {
            "bundle_version": "1.0",
            "entry_count": 5,
            "entries": [
                {
                    "entry_id": "single_entry",
                    "application_name": "Single App",
                    "target_sha256": "c" * 64,
                    "target_format": "pe",
                    "target_architecture": "x86_64",
                    "status": "untested",
                    "last_verified": "2026-10-25T00:00:00Z",
                }
            ],
        }
        bundle_path = os.path.join(self.test_dir, "mismatch_bundle.json")
        with open(bundle_path, "w", encoding="utf-8") as f:
            json.dump(mismatch_bundle, f)

        with self.assertRaises(DatabaseError):
            self.sync.import_bundle(bundle_path)

    def test_import_forged_placeholder_hash_always_downgraded(self):
        """Even with trust_external_provenance=True, placeholder hashes are never trusted."""
        forged_bundle = {
            "bundle_version": "1.0",
            "entry_count": 1,
            "entries": [
                {
                    "entry_id": "forged_app",
                    "application_name": "Forged App",
                    "target_sha256": "8b3a72d1194e8c5671234908ef1234567890abcdef1234567890abcdef123456",
                    "target_format": "pe",
                    "target_architecture": "x86_64",
                    "status": "verified_compatible",
                    "provenance_tier": "maintainer_verified",
                    "evidence_status": "verified",
                    "last_verified": "2026-10-25T00:00:00Z",
                }
            ],
        }
        bundle_path = os.path.join(self.test_dir, "forged_bundle.json")
        with open(bundle_path, "w", encoding="utf-8") as f:
            json.dump(forged_bundle, f)

        fresh_db_dir = os.path.join(self.test_dir, "forged_test_db")
        fresh_db = CompatibilityDatabase(storage_dir=fresh_db_dir)
        fresh_sync = CompatibilitySyncManager(fresh_db)

        # Even with trust_external_provenance=True
        fresh_sync.import_bundle(bundle_path, trust_external_provenance=True)
        imported = fresh_db.get_by_id("forged_app")
        self.assertIsNotNone(imported)
        self.assertEqual(imported.provenance_tier.value, "community_untested")
        self.assertEqual(imported.evidence_status.value, "community_reported")


if __name__ == "__main__":
    unittest.main()
