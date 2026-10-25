"""
Unit tests for Execution Lifecycle Orchestration and Desktop Integration Escaping.
"""

import os
import shutil
import tempfile
import unittest
from unittest.mock import MagicMock, patch

from zcf.core.exceptions import PlanningError, SecurityViolationError
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

        # Test newline stripping for header injection prevention
        malicious_name = "Super App\nExec=/tmp/malware.sh\nTerminal=true\r\nIcon=hack"
        sanitized = DesktopIntegrator.sanitize_desktop_value(malicious_name)
        self.assertNotIn("\n", sanitized)
        self.assertNotIn("\r", sanitized)
        self.assertIn("Super App", sanitized)

    def test_desktop_integration_and_unintegration(self):
        test_exe = os.path.abspath("fixtures/synthetic/valid_pe32plus.exe")
        desktop_file = self.integrator.integrate(test_exe, custom_name="Test Game App\nInjectedKey=evil")
        self.assertTrue(os.path.exists(desktop_file))

        with open(desktop_file, "r", encoding="utf-8") as f:
            content = f.read()
            self.assertIn("Name=Test Game App InjectedKey=evil", content)
            self.assertNotIn("Name=Test Game App\nInjectedKey=evil", content)
            self.assertIn("Exec=zcf run", content)
            self.assertIn("X-ZCF-Artifact=", content)

        # Verify listing
        integrated = self.integrator.list_integrated_apps()
        self.assertTrue(any("Test Game App" in item["name"] for item in integrated))

        # Reversible unintegration
        removed = self.integrator.unintegrate(test_exe)
        self.assertTrue(removed)
        self.assertFalse(os.path.exists(desktop_file))

    def test_orchestrator_execute_lifecycle_native(self):
        script_file = os.path.join(self.temp_dir, "test_native_exec.py")
        with open(script_file, "w", encoding="utf-8") as f:
            f.write('print("ZCF Native Lifecycle Execution Successful")\n')

        res = self.orchestrator.execute_lifecycle(
            artifact_path=script_file,
            use_sandbox=False,
            timeout=10,
        )
        self.assertIsNotNone(res)
        self.assertTrue(res.success)
        self.assertEqual(res.exit_code, 0)
        self.assertEqual(res.effective_runtime, "runtime.native")
        self.assertIn("ZCF Native Lifecycle Execution Successful", res.stdout)
        self.assertIsNotNone(res.effective_security_policy)

    @patch("zcf.execution.runner.EnvironmentInspector.inspect")
    @patch("zcf.runtimes.wine.WineAdapter.is_available", return_value=True)
    def test_orchestrator_execute_lifecycle_wine_dry_run(self, mock_wine_avail, mock_env):
        mock_env.return_value = EnvironmentReport(
            os_name="linux",
            architecture="x86_64",
            kernel_version="6.18",
            available_runtimes=[
                RuntimeInfo(runtime_id="runtime.wine", name="Wine Compatibility Layer", installed=True, version="wine-9.0"),
            ],
        )
        test_pe = os.path.abspath("fixtures/synthetic/valid_pe32plus.exe")
        res = self.orchestrator.execute_lifecycle(
            artifact_path=test_pe,
            use_sandbox=False,
            dry_run=True,
            timeout=10,
        )
        self.assertIsNotNone(res)
        self.assertTrue(res.success)
        self.assertEqual(res.exit_code, 0)
        self.assertEqual(res.effective_runtime, "runtime.wine")
        self.assertIn("[Dry Run]", res.stdout)

    @patch("zcf.execution.runner.EnvironmentInspector.inspect")
    @patch("zcf.runtimes.wine.WineAdapter.is_available", return_value=False)
    def test_orchestrator_execute_lifecycle_wine_missing_runtime_fails(self, mock_wine_avail, mock_env):
        mock_env.return_value = EnvironmentReport(
            os_name="linux",
            architecture="x86_64",
            kernel_version="6.18",
            available_runtimes=[],
        )
        test_pe = os.path.abspath("fixtures/synthetic/valid_pe32plus.exe")
        with self.assertRaises(PlanningError) as ctx:
            self.orchestrator.execute_lifecycle(
                artifact_path=test_pe,
                use_sandbox=False,
                dry_run=True,
                auto_install=False,
                timeout=10,
            )
        self.assertIn("is not installed", str(ctx.exception))

    @patch("zcf.execution.runner.SandboxManager.is_sandbox_available", return_value=False)
    def test_orchestrator_sandbox_fail_closed(self, mock_sb_avail):
        script_file = os.path.join(self.temp_dir, "test_fail_closed.py")
        with open(script_file, "w", encoding="utf-8") as f:
            f.write('print("Should not run unconfined")\n')

        # use_sandbox=True and allow_unconfined=False MUST raise SecurityViolationError
        with self.assertRaises(SecurityViolationError):
            self.orchestrator.execute_lifecycle(
                artifact_path=script_file,
                use_sandbox=True,
                allow_unconfined=False,
                timeout=10,
            )

        # With allow_unconfined=True, it proceeds with recorded warning
        res = self.orchestrator.execute_lifecycle(
            artifact_path=script_file,
            use_sandbox=True,
            allow_unconfined=True,
            timeout=10,
        )
        self.assertTrue(res.success)
        self.assertTrue(any("unconfined" in w for w in res.security_warnings))

    def test_orchestrator_deadline_timeout(self):
        hang_script = os.path.join(self.temp_dir, "hang_process.py")
        with open(hang_script, "w", encoding="utf-8") as f:
            f.write('import time, sys\nsys.stdout.write("Running...\\n")\nsys.stdout.flush()\ntime.sleep(60)\n')

        res = self.orchestrator.execute_lifecycle(
            artifact_path=hang_script,
            use_sandbox=False,
            timeout=1,
        )
        self.assertEqual(res.exit_code, 124)
        self.assertFalse(res.success)
        self.assertIn("timed out", res.stdout)

    def test_orchestrator_continuous_output_timeout(self):
        """Continuous output spam must not starve the deadline check."""
        spam_script = os.path.join(self.temp_dir, "spam_process.py")
        with open(spam_script, "w", encoding="utf-8") as f:
            f.write(
                'import sys, time\n'
                'while True:\n'
                '    sys.stdout.write("Spamming rapid stdout output line\\n")\n'
                '    sys.stdout.flush()\n'
            )

        res = self.orchestrator.execute_lifecycle(
            artifact_path=spam_script,
            use_sandbox=False,
            timeout=1,
        )
        self.assertEqual(res.exit_code, 124)
        self.assertFalse(res.success)
        self.assertIn("timed out", res.stdout)

    def test_orchestrator_output_truncation_bounded(self):
        """Massive stdout floods must be capped at 512 KB to prevent memory exhaustion."""
        flood_script = os.path.join(self.temp_dir, "flood_process.py")
        with open(flood_script, "w", encoding="utf-8") as f:
            f.write(
                'import sys\n'
                'line = "A" * 200 + "\\n"\n'
                'for _ in range(4000):\n'
                '    sys.stdout.write(line)\n'
                'sys.stdout.flush()\n'
            )

        res = self.orchestrator.execute_lifecycle(
            artifact_path=flood_script,
            use_sandbox=False,
            timeout=10,
        )
        self.assertEqual(res.exit_code, 0)
        self.assertTrue(res.success)
        # Capture buffer capped at 512KB + warning notice
        self.assertLessEqual(len(res.stdout), 550 * 1024)
        self.assertIn("Process output exceeded 512 KB", res.stdout)

    @patch("zcf.execution.display.VirtualDisplayManager.is_supported", return_value=True)
    @patch("zcf.execution.display.VirtualDisplayManager.start")
    @patch("zcf.execution.display.VirtualDisplayManager.stop")
    def test_display_cleanup_on_exception(self, mock_stop, mock_start, mock_supported):
        """Virtual display must be stopped safely even if execution raises an exception."""
        mock_start.return_value = {"DISPLAY": ":99"}
        script_file = os.path.join(self.temp_dir, "test_err.py")
        with open(script_file, "w", encoding="utf-8") as f:
            f.write('print("test")\n')

        with patch("zcf.security.controller.SecurityController.sanitize_env_vars", side_effect=RuntimeError("env error")):
            with self.assertRaises(RuntimeError):
                self.orchestrator.execute_lifecycle(
                    artifact_path=script_file,
                    use_sandbox=False,
                    force_headless=True,
                )

        mock_stop.assert_called_once()


if __name__ == "__main__":
    unittest.main()
