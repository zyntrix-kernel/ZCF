"""
Unit tests for Execution Lifecycle Orchestration and Desktop Integration Escaping.
"""

import os
import shutil
import tempfile
import unittest
from unittest.mock import MagicMock, patch

from zcf.core.models import (
    ApplicationDescription,
    Architecture,
    BinaryFormat,
    CompatibilityPlan,
    EnvironmentReport,
    ExecutionMode,
    RuntimeInfo,
    Subsystem,
    WorkloadType,
)
from zcf.desktop.integrator import DesktopIntegrator
from zcf.execution.runner import ExecutionOrchestrator


class TestOrchestratorLifecycle(unittest.TestCase):

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.orchestrator = ExecutionOrchestrator(prefix_root=self.temp_dir)
        self.integrator = DesktopIntegrator(applications_dir=self.temp_dir)

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_desktop_integrator_escaping(self):
        # Test escaping for spaces, quotes, and percent signs
        test_path = "/opt/Games/My Super Game%20/bin/game\"quoted\".exe"
        escaped = DesktopIntegrator.escape_exec_path(test_path)
        self.assertTrue(escaped.startswith('"'))
        self.assertTrue(escaped.endswith('"'))
        self.assertIn("%%20", escaped)
        self.assertIn('\\"quoted\\"', escaped)

    def test_desktop_integration_and_unintegration(self):
        test_exe = os.path.abspath("fixtures/synthetic/valid_pe32plus.exe")
        desktop_file = self.integrator.integrate(test_exe, custom_name="Test Game App")
        self.assertTrue(os.path.exists(desktop_file))

        with open(desktop_file, "r", encoding="utf-8") as f:
            content = f.read()
            self.assertIn("Name=Test Game App", content)
            self.assertIn("Exec=zcf run", content)
            self.assertIn("X-ZCF-Artifact=", content)

        # Verify listing
        integrated = self.integrator.list_integrated_apps()
        self.assertTrue(any(item["name"] == "Test Game App" for item in integrated))

        # Reversible unintegration
        removed = self.integrator.unintegrate(test_exe)
        self.assertTrue(removed)
        self.assertFalse(os.path.exists(desktop_file))

    @patch("zcf.execution.runner.EnvironmentInspector.inspect")
    def test_orchestrator_execute_lifecycle_native(self, mock_env_inspect):
        mock_env_inspect.return_value = EnvironmentReport(
            os_name="windows" if os.name == "nt" else "linux",
            architecture="x86_64",
            kernel_version="6.18",
            available_runtimes=[
                RuntimeInfo(runtime_id="runtime.native", name="Native Host Runtime", installed=True),
            ],
        )

        test_pe = os.path.abspath("fixtures/synthetic/valid_pe32plus.exe")
        # In dry run mode / mock run, verify lifecycle result
        res = self.orchestrator.execute_lifecycle(
            artifact_path=test_pe,
            use_sandbox=False,
            timeout=10,
        )
        self.assertIsNotNone(res)
        self.assertIsNotNone(res.effective_runtime)
        self.assertIsNotNone(res.effective_security_policy)
        self.assertTrue(len(res.permitted_writable_paths) >= 1)


if __name__ == "__main__":
    unittest.main()
