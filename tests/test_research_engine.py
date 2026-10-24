"""
Unit tests for ZCF Compatibility Research Engine.
"""

import os
import shutil
import tempfile
import unittest

from zcf.compatibility_db.database import CompatibilityDatabase
from zcf.research.engine import CompatibilityResearchEngine


class TestResearchEngine(unittest.TestCase):
    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        self.db = CompatibilityDatabase(storage_dir=os.path.join(self.test_dir, "db"))
        self.engine = CompatibilityResearchEngine(db=self.db)
        self.fixtures_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "fixtures", "synthetic"))

    def tearDown(self):
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_investigate_missing_dll(self):
        pe_path = os.path.join(self.fixtures_dir, "valid_pe32plus.exe")
        log_sample = "err:module:import_dll Library D3DX9_43.dll not found\n"

        case = self.engine.investigate(pe_path, log_sample)
        self.assertTrue(case.case_id.startswith("case_"))
        self.assertEqual(case.outcome_status, "resolved_with_workaround")
        self.assertEqual(len(case.hypotheses), 1)
        self.assertEqual(len(case.verified_workarounds), 1)

        # Check entry published to DB
        saved_entry = self.db.get_by_sha256(case.target_sha256)
        self.assertIsNotNone(saved_entry)


if __name__ == "__main__":
    unittest.main()
