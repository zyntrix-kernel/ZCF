"""
Tests for ZCF Desktop User Experience, Dialogs, and Application Integrator.
"""

import os
import tempfile
import unittest
from unittest.mock import MagicMock, patch

from zcf.desktop.integrator import DesktopIntegrator
from zcf.desktop.ui import DesktopUI


class TestDesktopUX(unittest.TestCase):

    def setUp(self):
        os.environ["ZCF_NON_INTERACTIVE"] = "1"

    def tearDown(self):
        os.environ.pop("ZCF_NON_INTERACTIVE", None)

    def test_desktop_ui_initialization(self):
        ui = DesktopUI()
        self.assertIsInstance(ui.is_gui_available(), bool)

    def test_desktop_ui_fallback_safety(self):
        ui = DesktopUI()
        res = ui.prompt_confirmation("Title", "Message")
        self.assertIsInstance(res, bool)
        ui.show_info("Title", "Message")
        ui.show_error("Title", "Message")

    @patch("shutil.which")
    def test_desktop_ui_prompt_install(self, mock_which):
        mock_which.return_value = "/usr/bin/zenity"
        ui = DesktopUI()
        ui.has_display = False  # Headless test
        res = ui.prompt_install_missing_runtime("TestApp.exe", "Wine", "sudo apt install wine64")
        self.assertFalse(res)

    def test_desktop_integrator(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            integrator = DesktopIntegrator(applications_dir=temp_dir)
            test_pe = os.path.abspath("fixtures/synthetic/valid_pe32plus.exe")
            desktop_file = integrator.integrate(test_pe, custom_name="Test Tool")

            self.assertTrue(os.path.isfile(desktop_file))
            with open(desktop_file, "r", encoding="utf-8") as f:
                content = f.read()

            self.assertIn("[Desktop Entry]", content)
            self.assertIn("Name=Test Tool", content)
            self.assertIn("zcf run", content)
            self.assertIn("application-x-executable", content)

    def test_desktop_escape_exec_path_special_characters(self):
        """Verifies proper Freedesktop specification escaping for %, $, quotes, and backslashes."""
        raw_path = '/opt/Games/My 100% $Game/bin/app"name".exe'
        escaped = DesktopIntegrator.escape_exec_path(raw_path)
        self.assertTrue(escaped.startswith('"'))
        self.assertTrue(escaped.endswith('"'))
        self.assertIn("100%%", escaped)
        self.assertIn(r"\$Game", escaped)
        self.assertIn(r'\"name\"', escaped)

    def test_desktop_escape_exec_path_rejects_control_characters(self):
        """Rejects paths containing newlines or control characters with ValueError."""
        with self.assertRaises(ValueError):
            DesktopIntegrator.escape_exec_path("/opt/app\nmalicious")

        with self.assertRaises(ValueError):
            DesktopIntegrator.escape_exec_path("/opt/app\rmalicious")

        with self.assertRaises(ValueError):
            DesktopIntegrator.escape_exec_path("/opt/app\x00malicious")

    def test_desktop_escape_string_rejects_newlines(self):
        with self.assertRaises(ValueError):
            DesktopIntegrator.escape_desktop_string("App\nExec=malware")

    def test_desktop_integrate_rejects_invalid_path(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            integrator = DesktopIntegrator(applications_dir=temp_dir)
            with self.assertRaises(ValueError):
                integrator.integrate("/tmp/test\napp.exe")


if __name__ == "__main__":
    unittest.main()
