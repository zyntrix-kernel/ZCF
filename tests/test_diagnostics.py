"""
Unit tests for ZCF Diagnostic Engine.
"""

import unittest

from zcf.diagnostics.analyzer import DiagnosticEngine


class TestDiagnosticEngine(unittest.TestCase):
    def setUp(self):
        self.engine = DiagnosticEngine()

    def test_missing_shared_library(self):
        log = "error while loading shared libraries: libcrypto.so.3: cannot open shared object file: No such file"
        events = self.engine.analyze_log(log)

        self.assertEqual(len(events), 1)
        self.assertEqual(events[0].signature, "missing_shared_library")
        self.assertIn("libcrypto.so.3", events[0].root_cause)
        self.assertGreaterEqual(events[0].confidence, 0.90)

    def test_wine_missing_dll(self):
        log = "err:module:import_dll Library VCRUNTIME140.dll not found"
        events = self.engine.analyze_log(log)

        self.assertEqual(len(events), 1)
        self.assertEqual(events[0].signature, "wine_dll_not_found")
        self.assertIn("VCRUNTIME140.dll", events[0].root_cause)

    def test_missing_display(self):
        log = "Gtk-WARNING **: cannot open display: :0"
        events = self.engine.analyze_log(log)

        self.assertEqual(len(events), 1)
        self.assertEqual(events[0].signature, "missing_display")
        self.assertIn("xvfb-run", events[0].remediation)

    def test_exec_format_error(self):
        log = "bash: ./arm_binary: cannot execute binary file: Exec format error"
        events = self.engine.analyze_log(log)

        self.assertEqual(len(events), 1)
        self.assertEqual(events[0].signature, "exec_format_error")


if __name__ == "__main__":
    unittest.main()
