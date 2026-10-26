"""
Unit tests for ZCF Execution History and Run Comparison.
Verifies record persistence, querying, side-by-side comparison, and cleanup.
"""

from __future__ import annotations

import os
import shutil
import tempfile
import unittest

from zcf.execution.history import ExecutionHistoryManager, ExecutionRecord


class TestExecutionHistory(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.mgr = ExecutionHistoryManager(storage_dir=self.temp_dir)

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_record_and_retrieve_run(self):
        rec = self.mgr.record_run(
            artifact_path="/tmp/test_app.exe",
            artifact_sha256="1111222233334444555566667777888899990000aaaabbbbccccddddeeeeffff",
            application_name="test_app.exe",
            target_format="pe",
            target_architecture="x86_64",
            runtime_id="runtime.wine",
            runtime_name="Wine Compatibility Layer",
            execution_mode="translation",
            dry_run=False,
            success=True,
            exit_code=0,
            execution_time_seconds=0.4521,
            sandbox_active=True,
            network_isolated=True,
            command=["bwrap", "--ro-bind", "/", "/", "wine", "test_app.exe"],
            stdout="Application launched successfully.\n",
            stderr="",
            diagnostics=[],
            environment={"os": "linux", "arch": "x86_64"},
        )

        self.assertTrue(rec.run_id.startswith("run_"))
        self.assertEqual(rec.application_name, "test_app.exe")

        fetched = self.mgr.get_run(rec.run_id)
        self.assertIsNotNone(fetched)
        self.assertEqual(fetched["run_id"], rec.run_id)
        self.assertEqual(fetched["exit_code"], 0)
        self.assertTrue(fetched["success"])
        self.assertTrue(fetched["sandbox_active"])
        self.assertIn("Application launched", fetched["stdout"])

    def test_list_and_filter_runs(self):
        sha_a = "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
        sha_b = "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"

        rec1 = self.mgr.record_run(
            artifact_path="/tmp/a.exe",
            artifact_sha256=sha_a,
            application_name="a.exe",
            target_format="pe",
            target_architecture="x86_64",
            runtime_id="runtime.wine",
            runtime_name="Wine",
            execution_mode="translation",
            dry_run=True,
            success=True,
            exit_code=0,
            execution_time_seconds=0.01,
            sandbox_active=False,
            network_isolated=True,
        )

        rec2 = self.mgr.record_run(
            artifact_path="/tmp/b.exe",
            artifact_sha256=sha_b,
            application_name="b.exe",
            target_format="pe",
            target_architecture="x86_64",
            runtime_id="runtime.proton",
            runtime_name="Proton",
            execution_mode="translation",
            dry_run=False,
            success=False,
            exit_code=1,
            execution_time_seconds=1.25,
            sandbox_active=True,
            network_isolated=False,
        )

        all_runs = self.mgr.list_runs()
        self.assertEqual(len(all_runs), 2)

        filtered_a = self.mgr.list_runs(sha256=sha_a)
        self.assertEqual(len(filtered_a), 1)
        self.assertEqual(filtered_a[0]["run_id"], rec1.run_id)

        filtered_b = self.mgr.list_runs(sha256=sha_b)
        self.assertEqual(len(filtered_b), 1)
        self.assertEqual(filtered_b[0]["run_id"], rec2.run_id)

    def test_delete_and_clear_runs(self):
        rec1 = self.mgr.record_run(
            artifact_path="/tmp/a.exe",
            artifact_sha256="1234567890abcdef1234567890abcdef1234567890abcdef1234567890abcdef",
            application_name="a.exe",
            target_format="pe",
            target_architecture="x86_64",
            runtime_id="runtime.wine",
            runtime_name="Wine",
            execution_mode="translation",
            dry_run=False,
            success=True,
            exit_code=0,
            execution_time_seconds=0.1,
            sandbox_active=True,
            network_isolated=True,
        )

        self.assertTrue(self.mgr.delete_run(rec1.run_id))
        self.assertIsNone(self.mgr.get_run(rec1.run_id))

        # Record two more and clear all
        self.mgr.record_run("/tmp/1.exe", "1"*64, "1.exe", "pe", "x86_64", "runtime.wine", "Wine", "trans", False, True, 0, 0.1, True, True)
        self.mgr.record_run("/tmp/2.exe", "2"*64, "2.exe", "pe", "x86_64", "runtime.wine", "Wine", "trans", False, True, 0, 0.1, True, True)
        self.assertEqual(len(self.mgr.list_runs()), 2)

        cleared = self.mgr.clear_runs()
        self.assertEqual(cleared, 2)
        self.assertEqual(len(self.mgr.list_runs()), 0)

    def test_compare_runs(self):
        rec1 = self.mgr.record_run(
            artifact_path="/tmp/game.exe",
            artifact_sha256="3333333333333333333333333333333333333333333333333333333333333333",
            application_name="game.exe",
            target_format="pe",
            target_architecture="x86_64",
            runtime_id="runtime.wine",
            runtime_name="Wine Compatibility Layer",
            execution_mode="translation",
            dry_run=False,
            success=False,
            exit_code=1,
            execution_time_seconds=1.5,
            sandbox_active=True,
            network_isolated=True,
        )

        rec2 = self.mgr.record_run(
            artifact_path="/tmp/game.exe",
            artifact_sha256="3333333333333333333333333333333333333333333333333333333333333333",
            application_name="game.exe",
            target_format="pe",
            target_architecture="x86_64",
            runtime_id="runtime.proton",
            runtime_name="Proton Compatibility Runner",
            execution_mode="translation",
            dry_run=False,
            success=True,
            exit_code=0,
            execution_time_seconds=1.1,
            sandbox_active=True,
            network_isolated=True,
        )

        diff = self.mgr.compare_runs(rec1.run_id, rec2.run_id)
        self.assertEqual(diff["run_a"]["runtime"], "Wine Compatibility Layer")
        self.assertEqual(diff["run_b"]["runtime"], "Proton Compatibility Runner")
        self.assertTrue(diff["differences"]["runtime_changed"])
        self.assertTrue(diff["differences"]["exit_code_changed"])
        self.assertTrue(diff["differences"]["outcome_improved"])
        self.assertAlmostEqual(diff["differences"]["execution_time_delta_seconds"], -0.4, places=2)

    def test_path_traversal_protection(self):
        with self.assertRaises(ValueError):
            self.mgr._resolve_run_path("../../../etc/passwd")

        with self.assertRaises(ValueError):
            self.mgr._resolve_run_path("run_test;rm -rf /")


if __name__ == "__main__":
    unittest.main()
