"""
Unit tests for Wine Prefix Lifecycle, Metadata, and Safe Cleanup.
"""

import os
import shutil
import tempfile
import unittest

from zcf.runtimes.prefix_manager import WinePrefixManager


class TestPrefixLifecycle(unittest.TestCase):

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.mgr = WinePrefixManager(base_dir=self.temp_dir)

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_record_usage_and_list_prefixes(self):
        prefix_path = os.path.join(self.temp_dir, "app1_prefix")
        os.makedirs(prefix_path, exist_ok=True)
        # Create dummy file to give it size
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

    def test_preview_cleanup_respects_persistence(self):
        # Create persistent prefix
        p1 = os.path.join(self.temp_dir, "p1")
        os.makedirs(p1, exist_ok=True)
        self.mgr.record_usage(p1, "Persistent App", "a" * 64, is_persistent=True)

        # Create disposable prefix
        p2 = os.path.join(self.temp_dir, "p2")
        os.makedirs(p2, exist_ok=True)
        self.mgr.record_usage(p2, "Disposable App", "b" * 64, is_persistent=False)

        # Force older mtime on p2
        os.utime(p2, (1000, 1000))

        preview = self.mgr.preview_cleanup(max_age_days=1, include_disposable_only=True)
        cand_paths = [c["prefix_path"] for c in preview["candidates"]]
        self.assertIn(p2, cand_paths)
        self.assertNotIn(p1, cand_paths)
        self.assertIn("p1", preview["skipped_persistent"])


if __name__ == "__main__":
    unittest.main()
