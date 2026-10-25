"""
Unit tests for Wine Prefix Lifecycle, Metadata Integrity, and Safe Cleanup.
Covers regression safety against accidental user-data deletion, missing/corrupt metadata handling,
active process locks, dry-run state isolation, and path traversal guards.
"""

import json
import os
import shutil
import tempfile
import time
import unittest
from unittest.mock import patch

from zcf.core.models import (
    ApplicationDescription,
    Architecture,
    BinaryFormat,
    Subsystem,
    WorkloadType,
)
from zcf.runtimes.prefix_manager import PrefixMetadata, WinePrefixManager
from zcf.runtimes.wine import WineAdapter


class TestPrefixLifecycle(unittest.TestCase):

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.mgr = WinePrefixManager(base_dir=self.temp_dir)

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_record_usage_and_list_prefixes(self):
        prefix_path = os.path.join(self.temp_dir, "app1_prefix")
        os.makedirs(prefix_path, exist_ok=True)
        with open(os.path.join(prefix_path, "system.reg"), "w") as f:
            f.write("WINE REGISTRY Version 2\n")

        self.mgr.record_usage(
            prefix_path=prefix_path,
            app_name="Test App",
            app_sha256="1234567890abcdef" * 4,
            is_persistent=True,
            architecture="win64",
        )

        prefixes = self.mgr.list_prefixes()
        self.assertEqual(len(prefixes), 1)
        p = prefixes[0]
        self.assertEqual(p.app_name, "Test App")
        self.assertEqual(p.architecture, "win64")
        self.assertTrue(p.is_persistent)
        self.assertTrue(p.size_bytes > 0)
        self.assertTrue(p.metadata_valid)

    def test_stale_prefix_without_metadata_is_preserved(self):
        """Prefixes missing prefix_meta.json must NEVER be deleted automatically."""
        untracked = os.path.join(self.temp_dir, "untracked_prefix")
        os.makedirs(untracked, exist_ok=True)
        with open(os.path.join(untracked, "important_savegame.dat"), "w") as f:
            f.write("Level 99 Boss Save")

        # Set modification time to 100 days ago
        old_time = time.time() - (100 * 86400)
        os.utime(untracked, (old_time, old_time))

        # Check preview
        preview = self.mgr.preview_cleanup(max_age_days=14, include_disposable_only=True)
        cand_paths = [c["prefix_path"] for c in preview["candidates"]]
        self.assertNotIn(untracked, cand_paths)
        self.assertIn("untracked_prefix", preview["skipped_unverified_metadata"])

        # Attempt actual cleanup
        cleaned = self.mgr.cleanup_stale_prefixes(max_age_days=14)
        self.assertEqual(cleaned, 0)
        self.assertTrue(os.path.exists(untracked))
        self.assertTrue(os.path.exists(os.path.join(untracked, "important_savegame.dat")))

    def test_stale_prefix_with_corrupt_metadata_is_preserved(self):
        """Corrupt or non-JSON metadata must result in preservation of user data."""
        corrupt = os.path.join(self.temp_dir, "corrupt_prefix")
        os.makedirs(corrupt, exist_ok=True)
        meta_file = os.path.join(corrupt, "prefix_meta.json")
        with open(meta_file, "w") as f:
            f.write("{broken_json: null, invalid,,,")

        old_time = time.time() - (100 * 86400)
        os.utime(corrupt, (old_time, old_time))

        preview = self.mgr.preview_cleanup(max_age_days=14, include_disposable_only=True)
        cand_paths = [c["prefix_path"] for c in preview["candidates"]]
        self.assertNotIn(corrupt, cand_paths)

        # Direct cleanup call must also fail safely
        success = self.mgr.cleanup_prefix(corrupt, max_age_days=14, include_disposable_only=True)
        self.assertFalse(success)
        self.assertTrue(os.path.exists(corrupt))

    def test_persistent_prefix_is_preserved(self):
        """Persistent prefixes must be protected from cleanup."""
        p_path = os.path.join(self.temp_dir, "persistent_app")
        os.makedirs(p_path, exist_ok=True)
        self.mgr.record_usage(p_path, "Persistent App", "a" * 64, is_persistent=True)

        old_time = time.time() - (100 * 86400)
        os.utime(p_path, (old_time, old_time))

        preview = self.mgr.preview_cleanup(max_age_days=14, include_disposable_only=True)
        cand_paths = [c["prefix_path"] for c in preview["candidates"]]
        self.assertNotIn(p_path, cand_paths)
        self.assertIn("persistent_app", preview["skipped_persistent"])

        cleaned = self.mgr.cleanup_stale_prefixes(max_age_days=14)
        self.assertEqual(cleaned, 0)
        self.assertTrue(os.path.exists(p_path))

    def test_explicitly_disposable_inactive_stale_prefix_can_be_cleaned(self):
        """Only explicitly disposable, stale, and unlocked prefixes can be cleaned."""
        p_path = os.path.join(self.temp_dir, "disposable_app")
        os.makedirs(p_path, exist_ok=True)
        self.mgr.record_usage(p_path, "Temporary App", "b" * 64, is_persistent=False)

        old_time = time.time() - (100 * 86400)
        os.utime(p_path, (old_time, old_time))
        # Also ensure last_used_at in JSON is old
        meta_file = os.path.join(p_path, "prefix_meta.json")
        with open(meta_file, "r") as f:
            data = json.load(f)
        data["last_used_at"] = "2020-01-01T00:00:00Z"
        with open(meta_file, "w") as f:
            json.dump(data, f)

        preview = self.mgr.preview_cleanup(max_age_days=14, include_disposable_only=True)
        cand_paths = [c["prefix_path"] for c in preview["candidates"]]
        self.assertIn(p_path, cand_paths)

        cleaned = self.mgr.cleanup_stale_prefixes(max_age_days=14)
        self.assertEqual(cleaned, 1)
        self.assertFalse(os.path.exists(p_path))

    def test_active_prefix_is_preserved(self):
        """Active prefix with locked state must not be cleaned even if stale and disposable."""
        p_path = os.path.join(self.temp_dir, "locked_app")
        os.makedirs(p_path, exist_ok=True)
        self.mgr.record_usage(p_path, "Locked App", "c" * 64, is_persistent=False)

        old_time = time.time() - (100 * 86400)
        os.utime(p_path, (old_time, old_time))

        with patch.object(self.mgr, "is_prefix_in_use", return_value=True):
            preview = self.mgr.preview_cleanup(max_age_days=14, include_disposable_only=True)
            cand_paths = [c["prefix_path"] for c in preview["candidates"]]
            self.assertNotIn(p_path, cand_paths)
            self.assertIn("locked_app", preview["skipped_locked"])

            success = self.mgr.cleanup_prefix(p_path, max_age_days=14, include_disposable_only=True)
            self.assertFalse(success)
            self.assertTrue(os.path.exists(p_path))

    def test_usage_metadata_updates_correctly(self):
        """Recording usage multiple times updates last_used_at while preserving created_at and components."""
        p_path = os.path.join(self.temp_dir, "app_meta_test")
        os.makedirs(p_path, exist_ok=True)

        self.mgr.record_usage(p_path, "App First Run", "d" * 64, is_persistent=True)
        meta_file = os.path.join(p_path, "prefix_meta.json")
        with open(meta_file, "r") as f:
            meta1 = json.load(f)
        created1 = meta1["created_at"]
        last1 = meta1["last_used_at"]

        # Simulate component installation
        meta1["installed_components"] = ["vcrun2022"]
        with open(meta_file, "w") as f:
            json.dump(meta1, f)

        time.sleep(0.01)
        self.mgr.record_usage(p_path, "App Second Run", "d" * 64, is_persistent=True)

        with open(meta_file, "r") as f:
            meta2 = json.load(f)

        self.assertEqual(meta2["created_at"], created1)
        self.assertIn("vcrun2022", meta2["installed_components"])
        self.assertEqual(meta2["app_name"], "App Second Run")

    def test_dry_run_creates_no_unexpected_persistent_state(self):
        """Dry-run execution preparation must not create prefix directories or write metadata."""
        adapter = WineAdapter(prefix_manager=self.mgr)
        app = ApplicationDescription(
            file_name="dry_run_test.exe",
            artifact_path=os.path.join(self.temp_dir, "dry_run_test.exe"),
            byte_size=1024,
            sha256="e" * 64,
            format=BinaryFormat.PE,
            architecture=Architecture.X86_64,
            subsystem=Subsystem.GUI,
            workload_type=WorkloadType.DESKTOP_GUI,
        )

        expected_prefix = self.mgr.get_prefix_path(app.sha256)
        self.assertFalse(os.path.exists(expected_prefix))

        context = adapter.prepare_environment(app, config={"dry_run": True})
        self.assertEqual(context["prefix_path"], expected_prefix)
        # Prefix path must NOT exist on disk after dry run!
        self.assertFalse(os.path.exists(expected_prefix))

    def test_cleanup_remains_restricted_to_configured_prefix_root(self):
        """Cleanup cannot delete files or directories outside base_dir via relative path or symlink."""
        outside_dir = tempfile.mkdtemp()
        try:
            sensitive_file = os.path.join(outside_dir, "do_not_delete.txt")
            with open(sensitive_file, "w") as f:
                f.write("Important")

            # Try deleting path outside base_dir
            res = self.mgr.cleanup_prefix(outside_dir, force_explicit=True)
            self.assertFalse(res)
            self.assertTrue(os.path.exists(sensitive_file))

            # Try traversal path
            traversal_path = os.path.join(self.temp_dir, "..", os.path.basename(outside_dir))
            res = self.mgr.cleanup_prefix(traversal_path, force_explicit=True)
            self.assertFalse(res)
            self.assertTrue(os.path.exists(sensitive_file))

            # Try symlink inside base_dir pointing to outside_dir
            symlink_path = os.path.join(self.temp_dir, "symlink_prefix")
            try:
                os.symlink(outside_dir, symlink_path)
                res = self.mgr.cleanup_prefix(symlink_path, force_explicit=True)
                self.assertFalse(res)
                self.assertTrue(os.path.exists(sensitive_file))
            except (OSError, NotImplementedError):
                pass
        finally:
            shutil.rmtree(outside_dir, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
