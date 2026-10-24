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

        imported = fresh_sync.import_bundle(res_path)
        self.assertGreaterEqual(imported, 1)


if __name__ == "__main__":
    unittest.main()
