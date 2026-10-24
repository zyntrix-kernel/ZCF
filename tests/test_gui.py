"""
Unit tests for ZCF Graphical User Interface (Control Center).
"""

import os
import unittest
import tkinter as tk

from zcf.gui.app import ZCFControlCenter


class TestZCFGui(unittest.TestCase):

    def setUp(self):
        os.environ["ZCF_NON_INTERACTIVE"] = "1"
        try:
            self.root = tk.Tk()
            self.root.withdraw()  # Do not display window during automated testing
            self.has_tk = True
        except Exception:
            self.has_tk = False

    def tearDown(self):
        if hasattr(self, "root") and self.root:
            try:
                self.root.destroy()
            except Exception:
                pass

    def test_gui_control_center_creation(self):
        if not self.has_tk:
            self.skipTest("Tkinter display not available in this test environment")

        app = ZCFControlCenter(self.root)
        self.assertIsNotNone(app.notebook)
        self.assertEqual(len(app.notebook.tabs()), 5)

        # Verify all tabs exist
        self.assertIsNotNone(app.tab_launch)
        self.assertIsNotNone(app.tab_runtimes)
        self.assertIsNotNone(app.tab_components)
        self.assertIsNotNone(app.tab_prefixes)
        self.assertIsNotNone(app.tab_diag)

    def test_gui_inspection_update(self):
        if not self.has_tk:
            self.skipTest("Tkinter display not available")

        app = ZCFControlCenter(self.root)
        test_pe = os.path.abspath("fixtures/synthetic/valid_pe32plus.exe")
        app._inspect_and_update_ui(test_pe)

        self.assertIn("valid_pe32plus.exe", app.lbl_app_name.cget("text"))
        self.assertIn("PE", app.lbl_app_details.cget("text"))

    def test_gui_diagnose_log(self):
        if not self.has_tk:
            self.skipTest("Tkinter display not available")

        app = ZCFControlCenter(self.root)
        app.txt_log.delete("1.0", tk.END)
        app.txt_log.insert("1.0", "err:module:import_dll Library D3DX9_43.dll not found")

        app._on_diagnose_log()
        result_text = app.lbl_diag_result.cget("text")
        self.assertIn("D3DX9_43.dll", result_text)


if __name__ == "__main__":
    unittest.main()
