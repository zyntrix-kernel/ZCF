"""Unit tests for ZCF Live Process Task Manager & Wine System Tools."""

from __future__ import annotations

import os
import shutil
import tempfile
import unittest

from zcf.runtimes.tasks import PrefixTaskManager


class TestPrefixTasks(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.prefix_dir = os.path.join(self.temp_dir, "prefix")
        os.makedirs(self.prefix_dir, exist_ok=True)
        self.tm = PrefixTaskManager()

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_list_prefix_processes_empty(self):
        procs = self.tm.list_prefix_processes(self.prefix_dir)
        self.assertIsInstance(procs, list)

    def test_reset_prefix_locks(self):
        # Create stale lock files
        lock1 = os.path.join(self.prefix_dir, ".update-timestamp")
        lock2 = os.path.join(self.prefix_dir, ".wine-lock")
        with open(lock1, "w") as f:
            f.write("stale_timestamp\n")
        with open(lock2, "w") as f:
            f.write("stale_lock\n")

        self.assertTrue(os.path.exists(lock1))
        self.assertTrue(os.path.exists(lock2))

        removed = self.tm.reset_prefix_locks(self.prefix_dir)
        self.assertIn(".update-timestamp", removed)
        self.assertIn(".wine-lock", removed)
        self.assertFalse(os.path.exists(lock1))
        self.assertFalse(os.path.exists(lock2))

    def test_kill_prefix_processes_clears_locks(self):
        lock = os.path.join(self.prefix_dir, ".update-timestamp")
        with open(lock, "w") as f:
            f.write("stale\n")

        res = self.tm.kill_prefix_processes(self.prefix_dir)
        self.assertEqual(res.get("status"), "cleared")
        self.assertFalse(os.path.exists(lock))

    def test_launch_wine_tool_validation(self):
        with self.assertRaises(ValueError):
            self.tm.launch_wine_tool(self.prefix_dir, "unsupported_utility_name")
