"""
Unit tests for ZCF Security Controller.
"""

import unittest

from zcf.core.exceptions import SecurityViolationError
from zcf.security.controller import SecurityController


class TestSecurityController(unittest.TestCase):
    def setUp(self):
        self.security = SecurityController()

    def test_command_injection_detection(self):
        with self.assertRaises(SecurityViolationError):
            self.security.validate_execution_safety(__file__, args=["--flag", "val; rm -rf /"])

        with self.assertRaises(SecurityViolationError):
            self.security.validate_execution_safety(__file__, args=["arg1 && echo pwned"])

    def test_nonexistent_path(self):
        with self.assertRaises(SecurityViolationError):
            self.security.validate_execution_safety("/nonexistent/file/path")

    def test_env_sanitization(self):
        dirty_env = {
            "PATH": "/usr/bin",
            "AWS_SECRET_ACCESS_KEY": "supersecret",
            "GITHUB_TOKEN": "ghp_12345",
            "APP_CONFIG": "production",
            "RANDOM_VAR": "keep_or_drop",
        }
        # Default minimized_desktop mode
        clean_min = self.security.sanitize_env_vars(dirty_env, mode="minimized_desktop")
        self.assertIn("PATH", clean_min)
        self.assertIn("APP_CONFIG", clean_min)
        self.assertNotIn("AWS_SECRET_ACCESS_KEY", clean_min)
        self.assertNotIn("GITHUB_TOKEN", clean_min)
        self.assertNotIn("RANDOM_VAR", clean_min)

        # Strict allowlist mode
        clean_strict = self.security.sanitize_env_vars(dirty_env, mode="strict_allowlist")
        self.assertIn("PATH", clean_strict)
        self.assertNotIn("APP_CONFIG", clean_strict)
        self.assertNotIn("RANDOM_VAR", clean_strict)

        # Filter secrets only mode
        clean_filter = self.security.sanitize_env_vars(dirty_env, mode="filter_secrets")
        self.assertIn("PATH", clean_filter)
        self.assertIn("APP_CONFIG", clean_filter)
        self.assertIn("RANDOM_VAR", clean_filter)
        self.assertNotIn("GITHUB_TOKEN", clean_filter)

        # Invalid mode
        with self.assertRaises(ValueError):
            self.security.sanitize_env_vars(dirty_env, mode="invalid_mode")

    def test_default_network_isolation_across_all_workloads(self):
        """All workloads default to network isolation (fail-closed) unless explicitly permitted."""
        from zcf.core.models import (
            ApplicationDescription,
            Architecture,
            BinaryFormat,
            Subsystem,
            WorkloadType,
        )

        for wl_type in [WorkloadType.DESKTOP_GUI, WorkloadType.GAME, WorkloadType.INSTALLER, WorkloadType.CLI_TOOL]:
            app = ApplicationDescription(
                artifact_path=__file__,
                file_name="test_app",
                sha256="a" * 64,
                byte_size=1024,
                format=BinaryFormat.PE,
                architecture=Architecture.X86_64,
                subsystem=Subsystem.GUI,
                workload_type=wl_type,
            )
            # Default (allow_network omitted/None) must be isolated
            pol_default = self.security.build_execution_policy(app)
            self.assertTrue(pol_default.isolate_network)
            self.assertEqual(pol_default.network_mode, "isolated")

            # Explicit allow_network=False must be isolated
            pol_isolated = self.security.build_execution_policy(app, allow_network=False)
            self.assertTrue(pol_isolated.isolate_network)
            self.assertEqual(pol_isolated.network_mode, "isolated")

            # Explicit allow_network=True permits network
            pol_net = self.security.build_execution_policy(app, allow_network=True)
            self.assertFalse(pol_net.isolate_network)
            self.assertEqual(pol_net.network_mode, "bridged_host")

    def test_workload_aware_timeouts(self):
        """Interactive workloads unconstrained by default; bounded workloads have sensible deadlines."""
        from zcf.core.models import (
            ApplicationDescription,
            Architecture,
            BinaryFormat,
            Subsystem,
            WorkloadType,
        )

        app_gui = ApplicationDescription(
            artifact_path=__file__,
            file_name="test_gui",
            sha256="a" * 64,
            byte_size=1024,
            format=BinaryFormat.PE,
            architecture=Architecture.X86_64,
            subsystem=Subsystem.GUI,
            workload_type=WorkloadType.DESKTOP_GUI,
        )
        pol_gui = self.security.build_execution_policy(app_gui)
        self.assertIsNone(pol_gui.default_timeout_seconds)  # Interactive: unlimited default
        self.assertIsNone(pol_gui.max_timeout_seconds)

        app_installer = ApplicationDescription(
            artifact_path=__file__,
            file_name="setup.exe",
            sha256="a" * 64,
            byte_size=1024,
            format=BinaryFormat.PE,
            architecture=Architecture.X86_64,
            subsystem=Subsystem.GUI,
            workload_type=WorkloadType.INSTALLER,
        )
        pol_inst = self.security.build_execution_policy(app_installer)
        self.assertEqual(pol_inst.default_timeout_seconds, 600)
        self.assertEqual(pol_inst.max_timeout_seconds, 3600)

        app_cli = ApplicationDescription(
            artifact_path=__file__,
            file_name="tool.exe",
            sha256="a" * 64,
            byte_size=1024,
            format=BinaryFormat.PE,
            architecture=Architecture.X86_64,
            subsystem=Subsystem.CONSOLE,
            workload_type=WorkloadType.CLI_TOOL,
        )
        pol_cli = self.security.build_execution_policy(app_cli)
        self.assertEqual(pol_cli.default_timeout_seconds, 120)
        self.assertEqual(pol_cli.max_timeout_seconds, 1800)


if __name__ == "__main__":
    unittest.main()
