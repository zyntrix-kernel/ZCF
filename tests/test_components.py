"""
Unit tests for Windows Component Manager.
Verifies real component definitions, genuine verification logic,
and safe handling when dependencies are missing without fake stubs.
"""

import json
import os
import shutil
import tempfile
import unittest
from unittest.mock import MagicMock, patch

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

        # Check each component definition has valid verification files
        for comp in components:
            self.assertTrue(len(comp.verification_files) > 0)
            self.assertTrue(bool(comp.winetricks_verb))

    @patch("shutil.which", return_value=None)
    def test_install_missing_winetricks_fails_safely(self, mock_which):
        # When winetricks is missing and non-interactive, must fail honestly without creating stubs
        prefix_path = os.path.join(self.temp_dir, "test_prefix")
        with patch.dict(os.environ, {"ZCF_NON_INTERACTIVE": "1"}):
            res = self.mgr.install(prefix_path, "vcrun2022")

        self.assertFalse(res.success)
        self.assertFalse(res.verified)
        self.assertEqual(res.assurance_level, "NONE")
        self.assertIn("Winetricks is required", res.error or "")

        # Crucial: verify NO fake stubs were created on disk
        sys32 = os.path.join(prefix_path, "drive_c", "windows", "system32")
        if os.path.exists(sys32):
            self.assertEqual(len(os.listdir(sys32)), 0)

    @patch("shutil.which", return_value="/usr/bin/winetricks")
    @patch("subprocess.Popen")
    def test_install_and_verify_component_success(self, mock_popen, mock_which):
        prefix_path = os.path.join(self.temp_dir, "test_prefix")
        sys32 = os.path.join(prefix_path, "drive_c", "windows", "system32")
        os.makedirs(sys32, exist_ok=True)

        # Simulate winetricks placing all required DLLs for vcrun2022
        def side_effect(*args, **kwargs):
            for dll_name in ("vcruntime140.dll", "msvcp140.dll"):
                with open(os.path.join(sys32, dll_name), "wb") as f:
                    f.write(b"REAL_DLL_PAYLOAD_FROM_INSTALLER")
            mock_proc = MagicMock()
            mock_proc.stdout = ["Executing cabextract...", "Installing visual c++ runtime..."]
            mock_proc.wait.return_value = 0
            mock_proc.poll.return_value = 0
            return mock_proc

        mock_popen.side_effect = side_effect

        res = self.mgr.install(prefix_path, "vcrun2022")
        self.assertTrue(res.success)
        self.assertTrue(res.verified)
        self.assertEqual(res.assurance_level, "FILESYSTEM_SIGNATURE_PRESENCE")
        self.assertEqual(res.component_key, "vcrun2022")

        # Verify filesystem presence
        is_installed = self.mgr.is_installed_in_prefix(prefix_path, "vcrun2022")
        self.assertTrue(is_installed)

        # Verify recorded metadata
        meta_file = os.path.join(prefix_path, "prefix_meta.json")
        self.assertTrue(os.path.exists(meta_file))
        with open(meta_file, "r", encoding="utf-8") as f:
            data = json.load(f)
            self.assertIn("vcrun2022", data.get("installed_components", []))

    def test_partial_dll_verification_fails(self):
        """Verifies that if only 1 of 2 required DLLs exists, verification returns False."""
        prefix_path = os.path.join(self.temp_dir, "test_prefix")
        sys32 = os.path.join(prefix_path, "drive_c", "windows", "system32")
        os.makedirs(sys32, exist_ok=True)

        # Only create vcruntime140.dll, omit msvcp140.dll
        with open(os.path.join(sys32, "vcruntime140.dll"), "wb") as f:
            f.write(b"PARTIAL_DLL")

        is_installed = self.mgr.is_installed_in_prefix(prefix_path, "vcrun2022")
        self.assertFalse(is_installed)

    def test_metadata_alone_does_not_verify(self):
        """Metadata is history, not proof of disk presence. Missing DLLs must fail verification."""
        prefix_path = os.path.join(self.temp_dir, "test_prefix")
        os.makedirs(prefix_path, exist_ok=True)

        # Write prefix_meta.json claiming vcrun2022 is installed
        meta_file = os.path.join(prefix_path, "prefix_meta.json")
        with open(meta_file, "w", encoding="utf-8") as f:
            json.dump({"installed_components": ["vcrun2022"]}, f)

        # DLLs are absent
        is_installed = self.mgr.is_installed_in_prefix(prefix_path, "vcrun2022")
        self.assertFalse(is_installed)

    @patch("shutil.which", return_value="/usr/bin/winetricks")
    @patch("subprocess.Popen")
    def test_install_failure_cleans_metadata(self, mock_popen, mock_which):
        """If install or verification fails, metadata must not claim component is installed."""
        prefix_path = os.path.join(self.temp_dir, "test_prefix")
        os.makedirs(prefix_path, exist_ok=True)

        meta_file = os.path.join(prefix_path, "prefix_meta.json")
        with open(meta_file, "w", encoding="utf-8") as f:
            json.dump({"installed_components": ["vcrun2022", "mono"]}, f)

        mock_proc = MagicMock()
        mock_proc.stdout = ["Error downloading package"]
        mock_proc.wait.return_value = 1
        mock_proc.poll.return_value = 1
        mock_popen.return_value = mock_proc

        res = self.mgr.install(prefix_path, "vcrun2022")
        self.assertFalse(res.success)
        self.assertFalse(res.verified)

        with open(meta_file, "r", encoding="utf-8") as f:
            data = json.load(f)
            self.assertNotIn("vcrun2022", data.get("installed_components", []))
            self.assertIn("mono", data.get("installed_components", []))

    @patch("shutil.which", return_value="/usr/bin/winetricks")
    @patch("subprocess.Popen")
    def test_install_nonzero_exit_fails(self, mock_popen, mock_which):
        prefix_path = os.path.join(self.temp_dir, "test_prefix")
        mock_proc = MagicMock()
        mock_proc.stdout = ["Error: checksum mismatch in download"]
        mock_proc.wait.return_value = 1
        mock_proc.poll.return_value = 1
        mock_popen.return_value = mock_proc

        res = self.mgr.install(prefix_path, "vcrun2022")
        self.assertFalse(res.success)
        self.assertFalse(res.verified)
        self.assertIn("failed with exit code 1", res.error or "")

    @patch("shutil.which", return_value="/usr/bin/winetricks")
    @patch("subprocess.Popen")
    def test_install_missing_dll_verification_fails(self, mock_popen, mock_which):
        prefix_path = os.path.join(self.temp_dir, "test_prefix")
        mock_proc = MagicMock()
        mock_proc.stdout = ["Success message but DLL not extracted"]
        mock_proc.wait.return_value = 0
        mock_proc.poll.return_value = 0
        mock_popen.return_value = mock_proc

        # Process exited 0 but DLL was not placed
        res = self.mgr.install(prefix_path, "vcrun2022")
        self.assertFalse(res.success)
        self.assertFalse(res.verified)
        self.assertIn("Verification failed", res.error or "")

    @patch("shutil.which", return_value="/usr/bin/winetricks")
    @patch("subprocess.Popen")
    def test_install_timeout_terminates_process(self, mock_popen, mock_which):
        """Simulates a hanging winetricks process; installer must time out and clean up."""
        prefix_path = os.path.join(self.temp_dir, "test_prefix")
        mock_proc = MagicMock()
        mock_proc.pid = 99999
        mock_proc.poll.return_value = None  # Never finishes
        mock_proc.stdout = MagicMock()
        mock_proc.stdout.readline.return_value = "working...\n"
        mock_popen.return_value = mock_proc

        res = self.mgr.install(prefix_path, "vcrun2022", timeout=0.1)
        self.assertFalse(res.success)
        self.assertFalse(res.verified)
        self.assertIn("timed out after 0.1 seconds", res.error or "")

    def test_unknown_component_handling(self):
        prefix_path = os.path.join(self.temp_dir, "test_prefix")
        res = self.mgr.install(prefix_path, "nonexistent_comp")
        self.assertFalse(res.success)
        self.assertIn("Unknown component key", res.error or "")


if __name__ == "__main__":
    unittest.main()
