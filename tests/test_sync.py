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
from zcf.core.models import CompatibilityEntry, CompatibilityStatus


class TestCompatibilitySync(unittest.TestCase):
    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        self.db = CompatibilityDatabase(storage_dir=os.path.join(self.test_dir, "db"))
        self.sync = CompatibilitySyncManager(self.db)

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

        # Import into fresh database
        fresh_db_dir = os.path.join(self.test_dir, "fresh_db")
        fresh_db = CompatibilityDatabase(storage_dir=fresh_db_dir)
        fresh_sync = CompatibilitySyncManager(fresh_db)

        imported = fresh_sync.import_bundle(res_path, trust_external_provenance=False)
        self.assertGreaterEqual(imported, 1)

        # Verify untrusted external entries are safely downgraded from maintainer verified
        notepad_entry = fresh_db.get_by_id("zcf_entry_notepad_pe")
        self.assertIsNotNone(notepad_entry)
        self.assertEqual(notepad_entry.provenance_tier.value, "community_untested")
        self.assertEqual(notepad_entry.evidence_status.value, "community_reported")

        # Now test with trust_external_provenance=True
        trusted_db_dir = os.path.join(self.test_dir, "trusted_db")
        trusted_db = CompatibilityDatabase(storage_dir=trusted_db_dir)
        trusted_sync = CompatibilitySyncManager(trusted_db)
        trusted_sync.import_bundle(res_path, trust_external_provenance=True)
        trusted_entry = trusted_db.get_by_id("zcf_entry_notepad_pe")
        self.assertIsNotNone(trusted_entry)
        self.assertEqual(trusted_entry.provenance_tier.value, "maintainer_verified")


if __name__ == "__main__":
    unittest.main()
