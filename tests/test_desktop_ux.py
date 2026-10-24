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
        # Should not crash on any environment
        res = ui.prompt_confirmation("Title", "Message")
        self.assertIsInstance(res, bool)
        ui.show_info("Title", "Message")
        ui.show_error("Title", "Message")

    @patch("shutil.which")
    def test_desktop_ui_prompt_install(self, mock_which):
        mock_which.return_value = "/usr/bin/zenity"
        ui = DesktopUI()
        ui.has_display = False  # Headless test
        # Verify call succeeds without raising exceptions
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


if __name__ == "__main__":
    unittest.main()
