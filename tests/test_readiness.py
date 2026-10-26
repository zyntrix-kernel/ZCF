"""
Tests for Pre-Flight System Readiness Audit and 'zcf doctor' command.
Verifies hardware, kernel, and compatibility subsystem evaluation and grading.
"""

from __future__ import annotations

import io
import json
import unittest
from contextlib import redirect_stdout
from unittest.mock import patch

from zcf.cli.main import main
from zcf.environment.inspector import EnvironmentInspector


class TestSystemReadiness(unittest.TestCase):
    def setUp(self):
        self.inspector = EnvironmentInspector()

    def test_readiness_audit_structure(self):
        """Verifies get_readiness_audit returns score, grade, summary, and checks."""
        audit = self.inspector.get_readiness_audit()
        self.assertIn("score", audit)
        self.assertIn("grade", audit)
        self.assertIn("summary", audit)
        self.assertIn("checks", audit)

        self.assertIsInstance(audit["score"], int)
        self.assertGreaterEqual(audit["score"], 0)
        self.assertLessEqual(audit["score"], 100)
        self.assertIn(audit["grade"], ("OPTIMAL", "GOOD", "DEGRADED", "MINIMAL"))

    def test_all_seven_readiness_checks_present(self):
        """Verifies all 7 pre-flight checks are evaluated."""
        audit = self.inspector.get_readiness_audit()
        check_ids = {c["id"] for c in audit["checks"]}
        expected_ids = {
            "vulkan_driver",
            "sync_limits",
            "multiarch_support",
            "bubblewrap_isolation",
            "dri_gpu_acceleration",
            "binfmt_registration",
            "headless_display_support",
        }
        self.assertEqual(check_ids, expected_ids)

        for c in audit["checks"]:
            self.assertIn(c["status"], ("PASS", "WARN", "FAIL"))
            self.assertGreater(c["max_points"], 0)
            self.assertGreaterEqual(c["score_points"], 0)
            self.assertLessEqual(c["score_points"], c["max_points"])
            self.assertTrue(len(c["details"]) > 0)

    def test_cli_doctor_text_output(self):
        """Verifies 'zcf doctor' prints the formatted pre-flight audit report."""
        buf = io.StringIO()
        with redirect_stdout(buf):
            try:
                main(["doctor"])
            except SystemExit as e:
                # May exit 0 on healthy, 1 on < 45
                pass

        output = buf.getvalue()
        self.assertIn("SYSTEM DOCTOR", output)
        self.assertIn("System Readiness Index", output)
        self.assertIn("PRE-FLIGHT SUBSYSTEM READINESS AUDIT", output)
        self.assertIn("Vulkan 1.3 Driver", output)

    def test_cli_doctor_json_output(self):
        """Verifies 'zcf doctor --json' outputs valid parseable JSON."""
        buf = io.StringIO()
        with redirect_stdout(buf):
            try:
                main(["doctor", "--json"])
            except SystemExit:
                pass

        data = json.loads(buf.getvalue())
        self.assertIn("score", data)
        self.assertIn("grade", data)
        self.assertIn("checks", data)
        self.assertEqual(len(data["checks"]), 7)


if __name__ == "__main__":
    unittest.main()
