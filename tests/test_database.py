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


if __name__ == "__main__":
    unittest.main()
