"""
Unit tests for ZCF Environment Inspector.
"""

import unittest

from zcf.environment.inspector import EnvironmentInspector


class TestEnvironmentInspector(unittest.TestCase):
    def setUp(self):
        self.inspector = EnvironmentInspector()

    def test_inspect_environment(self):
        report = self.inspector.inspect()

        self.assertIn(report.os_name, ("windows", "linux", "darwin"))
        self.assertIn(report.architecture, ("x86_64", "arm64", "i386"))
        self.assertGreater(report.logical_cores, 0)
        self.assertGreater(report.total_memory_mb, 0)
        self.assertGreater(len(report.available_runtimes), 0)

        # Ensure native runtime is always present
        runtime_ids = [r.runtime_id for r in report.available_runtimes]
        self.assertIn("runtime.native", runtime_ids)
        self.assertIn("runtime.wine", runtime_ids)
        self.assertIn("runtime.qemu-user", runtime_ids)


if __name__ == "__main__":
    unittest.main()
