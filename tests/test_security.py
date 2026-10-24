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
        }
        clean_env = self.security.sanitize_env_vars(dirty_env)

        self.assertIn("PATH", clean_env)
        self.assertIn("APP_CONFIG", clean_env)
        self.assertNotIn("AWS_SECRET_ACCESS_KEY", clean_env)
        self.assertNotIn("GITHUB_TOKEN", clean_env)


if __name__ == "__main__":
    unittest.main()
