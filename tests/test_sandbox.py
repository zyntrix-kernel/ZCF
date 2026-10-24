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
        policy = SandboxPolicy(isolate_network=True, read_only_root=True)

        wrapped = self.mgr.wrap_command(base_cmd, "/tmp", policy)
        self.assertGreaterEqual(len(wrapped), len(base_cmd))

        if self.mgr.has_bwrap:
            self.assertIn("--unshare-net", wrapped)
            self.assertIn("--ro-bind", wrapped)
        else:
            self.assertEqual(wrapped, base_cmd)


if __name__ == "__main__":
    unittest.main()
