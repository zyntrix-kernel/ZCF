"""
Unit tests for ZCF Compatibility Database.
"""

import os
import shutil
import tempfile
import unittest

from zcf.compatibility_db.database import CompatibilityDatabase
from zcf.core.exceptions import DatabaseError
from zcf.core.models import CompatibilityEntry, CompatibilityStatus


class TestCompatibilityDatabase(unittest.TestCase):
    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        self.db = CompatibilityDatabase(storage_dir=self.test_dir)

    def tearDown(self):
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_database_crud(self):
        entry = CompatibilityEntry(
            entry_id="test_app_1",
            application_name="Test Application",
            target_sha256="1234567890abcdef" * 4,
            target_format="pe",
            target_architecture="x86_64",
            status=CompatibilityStatus.VERIFIED_COMPATIBLE,
            last_verified="2026-10-24T00:00:00Z",
            recommended_runtime="runtime.wine",
        )

        saved_path = self.db.add_entry(entry)
        self.assertTrue(os.path.exists(saved_path))

        fetched = self.db.get_by_id("test_app_1")
        self.assertIsNotNone(fetched)
        self.assertEqual(fetched.application_name, "Test Application")

        by_hash = self.db.get_by_sha256("1234567890abcdef" * 4)
        self.assertIsNotNone(by_hash)
        self.assertEqual(by_hash.entry_id, "test_app_1")

    def test_invalid_entry_validation(self):
        invalid_entry = CompatibilityEntry(
            entry_id="",  # Missing entry_id
            application_name="Bad App",
            target_sha256="short",  # Bad hash length
            target_format="pe",
            target_architecture="x86_64",
            status=CompatibilityStatus.UNTESTED,
            last_verified="2026-10-24T00:00:00Z",
        )

        with self.assertRaises(DatabaseError):
            self.db.add_entry(invalid_entry)

    def test_entry_id_path_traversal_prevention(self):
        traversal_entry = CompatibilityEntry(
            entry_id="../../etc/evil",
            application_name="Traversal App",
            target_sha256="1234567890abcdef" * 4,
            target_format="pe",
            target_architecture="x86_64",
            status=CompatibilityStatus.UNTESTED,
            last_verified="2026-10-24T00:00:00Z",
        )

        with self.assertRaises(DatabaseError):
            self.db.add_entry(traversal_entry)

        # Non-matching entry_id should return None safely from get_by_id without raising
        self.assertIsNone(self.db.get_by_id("../../etc/evil"))

    def test_placeholder_seeds_are_downgraded_to_untested(self):
        """Placeholder seed profiles must NOT claim maintainer verification."""
        npp = self.db.get_by_id("zcf_entry_notepadplusplus")
        self.assertIsNotNone(npp)
        self.assertEqual(npp.provenance_tier.value, "community_untested")
        self.assertEqual(npp.evidence_status.value, "community_reported")

        ftl = self.db.get_by_id("zcf_entry_ftl_proton")
        self.assertIsNotNone(ftl)
        self.assertEqual(ftl.provenance_tier.value, "community_untested")
        self.assertEqual(ftl.evidence_status.value, "community_reported")

        fdroid = self.db.get_by_id("zcf_entry_fdroid_waydroid")
        self.assertIsNotNone(fdroid)
        self.assertEqual(fdroid.provenance_tier.value, "community_untested")

    def test_genuine_fixture_seeds_are_verified(self):
        """Entries based on actual fixture bytes retain verified automated-test status while untested headers are honest."""
        pe_fix = self.db.get_by_id("zcf_fixture_pe32plus")
        self.assertIsNotNone(pe_fix)
        self.assertEqual(pe_fix.provenance_tier.value, "automated_test")
        self.assertEqual(pe_fix.evidence_status.value, "verified")

        arm_fix = self.db.get_by_id("zcf_fixture_elf64_aarch64")
        self.assertIsNotNone(arm_fix)
        self.assertEqual(arm_fix.provenance_tier.value, "automated_test")
        self.assertEqual(arm_fix.status.value, "untested")

        # Unsupported claims about real applications must be downgraded to untested
        notepad = self.db.get_by_id("zcf_entry_notepad_pe")
        self.assertIsNotNone(notepad)
        self.assertEqual(notepad.provenance_tier.value, "community_untested")
        self.assertEqual(notepad.status.value, "untested")

    def test_database_migration_v3_downgrades_existing_legacy_db(self):
        """Existing persisted database with placeholder hashes claiming verification is safely migrated."""
        import json
        legacy_dir = tempfile.mkdtemp()
        try:
            # Write unmigrated legacy entry with placeholder hash claiming maintainer verification
            legacy_entry = {
                "entry_id": "legacy_fake_app",
                "application_name": "Legacy Fake App",
                "target_sha256": "8b3a72d1194e8c5671234908ef1234567890abcdef1234567890abcdef123456",
                "target_format": "pe",
                "target_architecture": "x86_64",
                "status": "verified_compatible",
                "last_verified": "2026-01-01T00:00:00Z",
                "recommended_runtime": "runtime.wine",
                "provenance_tier": "maintainer_verified",
                "evidence_status": "verified",
            }
            with open(os.path.join(legacy_dir, "legacy_fake_app.json"), "w") as f:
                json.dump(legacy_entry, f)

            # Also write a legitimate user entry with a real hash
            user_entry = {
                "entry_id": "user_custom_app",
                "application_name": "User Custom App",
                "target_sha256": "3a4b5c6d7e8f0123456789abcdef0123456789abcdef0123456789abcdef0123",
                "target_format": "pe",
                "target_architecture": "x86_64",
                "status": "verified_compatible",
                "last_verified": "2026-01-01T00:00:00Z",
                "recommended_runtime": "runtime.wine",
                "provenance_tier": "maintainer_verified",
                "evidence_status": "verified",
            }
            with open(os.path.join(legacy_dir, "user_custom_app.json"), "w") as f:
                json.dump(user_entry, f)

            # Initializing db runs migration
            migrated_db = CompatibilityDatabase(storage_dir=legacy_dir)

            # Fake app must be downgraded
            migrated_fake = migrated_db.get_by_id("legacy_fake_app")
            self.assertEqual(migrated_fake.provenance_tier.value, "community_untested")
            self.assertEqual(migrated_fake.evidence_status.value, "community_reported")

            # User custom app must be preserved intact
            migrated_user = migrated_db.get_by_id("user_custom_app")
            self.assertEqual(migrated_user.provenance_tier.value, "maintainer_verified")
            self.assertEqual(migrated_user.evidence_status.value, "verified")

            # Check db_meta.json
            with open(os.path.join(legacy_dir, "db_meta.json")) as f:
                meta = json.load(f)
            self.assertEqual(meta["migration_version"], 3)
            self.assertEqual(meta["status"], "completed")
        finally:
            shutil.rmtree(legacy_dir, ignore_errors=True)

    def test_database_migration_failure_visibility(self):
        """If a corrupted entry file fails during migration, migration failure is recorded and db_meta reflects status."""
        import json
        corrupt_dir = tempfile.mkdtemp()
        try:
            with open(os.path.join(corrupt_dir, "corrupt_entry.json"), "w") as f:
                f.write("{invalid_json: true")

            # Initializing db attempts migration
            corrupt_db = CompatibilityDatabase(storage_dir=corrupt_dir)
            with open(os.path.join(corrupt_dir, "db_meta.json")) as f:
                meta = json.load(f)
            self.assertEqual(meta["status"], "failed")
            self.assertTrue(len(meta["errors"]) > 0)
        finally:
            shutil.rmtree(corrupt_dir, ignore_errors=True)

    def test_verify_profile_requires_structured_evidence(self):
        """Promotion requires structured evidence and rejects placeholder hashes."""
        import hashlib
        real_sha = hashlib.sha256(b"structured_test_bin").hexdigest()
        entry = CompatibilityEntry(
            entry_id="test_struct_app",
            application_name="Structured App",
            target_sha256=real_sha,
            target_format="pe",
            target_architecture="x86_64",
            status=CompatibilityStatus.UNTESTED,
            last_verified="2026-10-24T00:00:00Z",
        )
        self.db.add_entry(entry)

        # Missing structured evidence must fail
        with self.assertRaises(DatabaseError):
            self.db.verify_profile(
                entry_id="test_struct_app",
                verifier="Lead Tester",
                structured_evidence=None,
            )

        # Incomplete structured evidence must fail
        with self.assertRaises(DatabaseError):
            self.db.verify_profile(
                entry_id="test_struct_app",
                verifier="Lead Tester",
                structured_evidence={"test_environment": {}},
            )

        # Valid structured evidence succeeds
        res = self.db.verify_profile(
            entry_id="test_struct_app",
            verifier="Lead Tester",
            structured_evidence={
                "test_environment": {"os": "linux", "runner_version": "wine-9.0"},
                "test_procedure": "Launched binary, verified exit code 0",
                "test_results": {"exit_code": 0},
            },
        )
        self.assertTrue(res)
        updated = self.db.get_by_id("test_struct_app")
        self.assertEqual(updated.evidence_status.value, "verified")
        self.assertEqual(updated.provenance_tier.value, "maintainer_verified")

    def test_verify_profile_contradictory_combinations_and_sha_mismatch(self):
        """Contradictory status/tier combinations and artifact hash mismatches are rejected."""
        import hashlib
        from zcf.core.models import EvidenceStatus, ProvenanceTier
        real_sha = hashlib.sha256(b"another_test_bin").hexdigest()
        entry = CompatibilityEntry(
            entry_id="test_mismatch_app",
            application_name="Mismatch App",
            target_sha256=real_sha,
            target_format="pe",
            target_architecture="x86_64",
            status=CompatibilityStatus.UNTESTED,
            last_verified="2026-10-24T00:00:00Z",
        )
        self.db.add_entry(entry)

        # Contradictory: MAINTAINER_VERIFIED tier with COMMUNITY_REPORTED evidence_status
        with self.assertRaises(DatabaseError):
            self.db.verify_profile(
                entry_id="test_mismatch_app",
                verifier="Lead Tester",
                provenance_tier=ProvenanceTier.MAINTAINER_VERIFIED,
                evidence_status=EvidenceStatus.COMMUNITY_REPORTED,
                structured_evidence={
                    "test_environment": {"os": "linux"},
                    "test_procedure": "procedure",
                    "test_result": {"exit_code": 0, "success": True},
                },
            )

        # Contradictory: COMMUNITY_UNTESTED tier claiming VERIFIED evidence_status
        with self.assertRaises(DatabaseError):
            self.db.verify_profile(
                entry_id="test_mismatch_app",
                verifier="Lead Tester",
                provenance_tier=ProvenanceTier.COMMUNITY_UNTESTED,
                evidence_status=EvidenceStatus.VERIFIED,
                structured_evidence={
                    "test_environment": {"os": "linux"},
                    "test_procedure": "procedure",
                    "test_result": {"exit_code": 0, "success": True},
                },
            )

        # Hash mismatch: structured_evidence has wrong artifact_sha256
        with self.assertRaises(DatabaseError):
            self.db.verify_profile(
                entry_id="test_mismatch_app",
                verifier="Lead Tester",
                provenance_tier=ProvenanceTier.MAINTAINER_VERIFIED,
                evidence_status=EvidenceStatus.VERIFIED,
                structured_evidence={
                    "test_environment": {"os": "linux"},
                    "test_procedure": "procedure",
                    "test_result": {"exit_code": 0, "success": True},
                    "artifact_sha256": "0" * 64,
                },
            )


if __name__ == "__main__":
    unittest.main()
