"""
Unit tests for Windows Component Manager.
"""

import os
import shutil
import tempfile
import unittest

from zcf.runtimes.components import WindowsComponentManager


class TestWindowsComponents(unittest.TestCase):

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.mgr = WindowsComponentManager()

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_list_components(self):
        components = self.mgr.list_components()
        self.assertTrue(len(components) >= 4)
        keys = [c.key for c in components]
        self.assertIn("vcrun2022", keys)
        self.assertIn("d3dx9", keys)
        self.assertIn("mono", keys)
        self.assertIn("dxvk", keys)

    def test_install_and_verify_component(self):
        prefix_path = os.path.join(self.temp_dir, "test_prefix")
        res = self.mgr.install(prefix_path, "vcrun2022")
        self.assertTrue(res.success)
        self.assertTrue(res.verified)
        self.assertEqual(res.component_key, "vcrun2022")

        # Verify filesystem presence
        is_installed = self.mgr.is_installed_in_prefix(prefix_path, "vcrun2022")
        self.assertTrue(is_installed)

    def test_unknown_component_handling(self):
        prefix_path = os.path.join(self.temp_dir, "test_prefix")
        res = self.mgr.install(prefix_path, "nonexistent_comp")
        self.assertFalse(res.success)
        self.assertIn("Unknown component key", res.error or "")


if __name__ == "__main__":
    unittest.main()
