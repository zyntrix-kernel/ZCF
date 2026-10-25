"""
Unit tests for ZCF Sandbox Manager.
"""

import unittest
from unittest.mock import patch

from zcf.core.exceptions import SecurityViolationError
from zcf.security.sandbox import SandboxManager, SandboxPolicy


class TestSandboxManager(unittest.TestCase):
    def setUp(self):
        self.mgr = SandboxManager()

    def test_sandbox_policy_wrapping_with_bwrap(self):
        base_cmd = ["/bin/echo", "hello"]
        policy = SandboxPolicy(
            isolate_network=True,
            read_only_root=True,
            read_only_app=True,
            bind_mounts=["/run", "/tmp/valid_prefix"],
            ro_bind_mounts=["/tmp/.X11-unix"],
        )

        with patch.object(self.mgr, "has_bwrap", True), patch.object(self.mgr, "bwrap_bin", "/usr/bin/bwrap"):
            wrapped = self.mgr.wrap_command(base_cmd, "/tmp", policy)
            self.assertGreaterEqual(len(wrapped), len(base_cmd))
            self.assertEqual(wrapped[0], "/usr/bin/bwrap")
            self.assertIn("--unshare-net", wrapped)
            self.assertIn("--ro-bind", wrapped)
            # Ensure working dir is mounted read-only
            ro_idx = [i for i, v in enumerate(wrapped) if v == "--ro-bind"]
            self.assertTrue(any(wrapped[i + 1] == "/tmp" for i in ro_idx))
            # Critical: Ensure /run is NEVER mounted writable
            bind_idx = [i for i, v in enumerate(wrapped) if v == "--bind"]
            self.assertFalse(any(wrapped[i + 1] == "/run" for i in bind_idx))

    def test_sandbox_fail_closed_when_bwrap_missing(self):
        base_cmd = ["/bin/echo", "hello"]
        policy = SandboxPolicy()

        with patch.object(self.mgr, "has_bwrap", False), patch.object(self.mgr, "bwrap_bin", None):
            # Default allow_unconfined=False MUST raise SecurityViolationError
            with self.assertRaises(SecurityViolationError):
                self.mgr.wrap_command(base_cmd, "/tmp", policy, allow_unconfined=False)

            # Explicit allow_unconfined=True returns original command
            unconfined = self.mgr.wrap_command(base_cmd, "/tmp", policy, allow_unconfined=True)
            self.assertEqual(unconfined, base_cmd)

    def test_sandbox_status_report(self):
        status = self.mgr.get_sandbox_status()
        self.assertIn("backend", status)
        self.assertIn("available", status)
        self.assertIn("resource_enforcement", status)


if __name__ == "__main__":
    unittest.main()
