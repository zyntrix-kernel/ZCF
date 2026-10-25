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


if __name__ == "__main__":
    unittest.main()
