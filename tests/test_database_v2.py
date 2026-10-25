"""
Unit tests for Compatibility Database v2 Schema, Provenance Tiers, and Query Capabilities.
"""

import os
import shutil
import tempfile
import unittest

from zcf.compatibility_db.database import CompatibilityDatabase
from zcf.core.models import (
    ApplicationDescription,
    Architecture,
    BinaryFormat,
    CompatibilityStatus,
    EnvironmentReport,
    EvidenceStatus,
    ProvenanceTier,
    Subsystem,
)


class TestDatabaseV2(unittest.TestCase):

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.db = CompatibilityDatabase(storage_dir=self.temp_dir)

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_advanced_query_filtering(self):
        # Default seeded entries include notepad, 7zip, ftl, etc.
        wine_entries = self.db.query(runtime="runtime.wine")
        self.assertTrue(len(wine_entries) >= 3)

        proton_entries = self.db.query(runtime="runtime.proton")
        self.assertEqual(len(proton_entries), 1)
        self.assertEqual(proton_entries[0].application_name, "FTL: Faster Than Light")

        arch_entries = self.db.query(arch="arm64")
        self.assertEqual(len(arch_entries), 1)

    def test_community_submission_workflow(self):
        import hashlib
        real_sha256 = hashlib.sha256(b"sample_game_payload_v2").hexdigest()
        app = ApplicationDescription(
            artifact_path="/tmp/game.exe",
            file_name="game.exe",
            sha256=real_sha256,
            byte_size=1024,
            format=BinaryFormat.PE,
            architecture=Architecture.X86_64,
            subsystem=Subsystem.GUI,
        )
        env = EnvironmentReport(
            os_name="linux",
            architecture="x86_64",
            kernel_version="6.18",
            distribution="ubuntu",
        )

        entry = self.db.submit_profile(
            app=app,
            recommended_runtime="runtime.wine",
            status=CompatibilityStatus.COMPATIBLE_WITH_WORKAROUND,
            contributor_name="community_tester",
            test_procedure="Launched game and verified audio playback.",
            env=env,
        )

        self.assertEqual(entry.provenance_tier, ProvenanceTier.COMMUNITY_UNTESTED)
        self.assertEqual(entry.evidence_status, EvidenceStatus.COMMUNITY_REPORTED)
        self.assertEqual(entry.target_sha256, real_sha256)

        # Retrieve and verify persistence
        saved = self.db.get_by_sha256(real_sha256)
        self.assertIsNotNone(saved)
        self.assertEqual(saved.application_name, "game.exe")

        # Promote/verify record with structured evidence
        structured_evidence = {
            "test_environment": {"os": "ubuntu", "kernel": "6.18", "runner_version": "wine-9.0"},
            "test_procedure": "Full headless prefix initialization and DXVK audio test",
            "test_results": {"exit_code": 0, "fps_average": 60},
        }
        verified = self.db.verify_profile(
            entry_id=entry.entry_id,
            verifier="Maintainer Bob",
            evidence_status=EvidenceStatus.VERIFIED,
            provenance_tier=ProvenanceTier.MAINTAINER_VERIFIED,
            notes="Reproduced cleanly on Ubuntu 26.04.",
            structured_evidence=structured_evidence,
        )
        self.assertTrue(verified)

        updated = self.db.get_by_id(entry.entry_id)
        self.assertEqual(updated.evidence_status, EvidenceStatus.VERIFIED)
        self.assertEqual(updated.provenance_tier, ProvenanceTier.MAINTAINER_VERIFIED)
        self.assertEqual(len(updated.verification_history), 2)


if __name__ == "__main__":
    unittest.main()
