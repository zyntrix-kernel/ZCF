"""
Unit tests for ZCF Automated Remediator.
"""

import unittest

from zcf.core.models import (
    ApplicationDescription,
    Architecture,
    BinaryFormat,
    EnvironmentReport,
    Subsystem,
)
from zcf.diagnostics.analyzer import DiagnosticEvent
from zcf.diagnostics.remediator import AutomatedRemediator


class TestAutomatedRemediator(unittest.TestCase):
    def setUp(self):
        self.remediator = AutomatedRemediator()
        self.app = ApplicationDescription(
            artifact_path="/tmp/game.exe",
            file_name="game.exe",
            sha256="e" * 64,
            byte_size=10000,
            format=BinaryFormat.PE,
            architecture=Architecture.X86_64,
            subsystem=Subsystem.GUI,
        )
        self.env = EnvironmentReport(
            os_name="linux",
            distribution="ubuntu",
            architecture="x86_64",
            kernel_version="6.18",
        )

    def test_synthesize_remediation(self):
        events = [
            DiagnosticEvent(
                signature="missing_shared_library",
                severity="error",
                matched_text="error while loading shared libraries: libvulkan.so.1: cannot open shared object file",
                root_cause="Missing Linux shared library dependency: 'libvulkan.so.1'",
                remediation="Install libvulkan",
                confidence=0.98,
            ),
            DiagnosticEvent(
                signature="missing_display",
                severity="error",
                matched_text="cannot open display: :0",
                root_cause="Display unavailable",
                remediation="Run with xvfb-run",
                confidence=0.95,
            ),
        ]

        plan = self.remediator.synthesize(self.app, self.env, events)
        self.assertTrue(plan.can_auto_remediate)
        self.assertEqual(plan.wrapper_prefix, "xvfb-run -a")
        self.assertGreater(len(plan.package_install_commands), 0)
        self.assertIn("apt", plan.package_install_commands[0])


if __name__ == "__main__":
    unittest.main()
