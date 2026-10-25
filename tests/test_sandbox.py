"""
Unit tests for ZCF Sandbox Manager.
"""

import unittest

from zcf.security.sandbox import SandboxManager, SandboxPolicy


class TestSandboxManager(unittest.TestCase):
    def setUp(self):
        self.mgr = SandboxManager()

    def test_sandbox_policy_wrapping(self):
        base_cmd = ["/bin/echo", "hello"]
        policy = SandboxPolicy(
            isolate_network=True,
            read_only_root=True,
            read_only_app=True,
            bind_mounts=["/run", "/tmp/valid_prefix"],
            ro_bind_mounts=["/tmp/.X11-unix"],
        )

        wrapped = self.mgr.wrap_command(base_cmd, "/tmp", policy)
        self.assertGreaterEqual(len(wrapped), len(base_cmd))

        if self.mgr.has_bwrap:
            self.assertIn("--unshare-net", wrapped)
            self.assertIn("--ro-bind", wrapped)
            # Ensure working dir is mounted read-only
            ro_idx = [i for i, v in enumerate(wrapped) if v == "--ro-bind"]
            self.assertTrue(any(wrapped[i + 1] == "/tmp" for i in ro_idx))
            # Critical: Ensure /run is NEVER mounted writable
            bind_idx = [i for i, v in enumerate(wrapped) if v == "--bind"]
            self.assertFalse(any(wrapped[i + 1] == "/run" for i in bind_idx))
        else:
            self.assertEqual(wrapped, base_cmd)


if __name__ == "__main__":
    unittest.main()
