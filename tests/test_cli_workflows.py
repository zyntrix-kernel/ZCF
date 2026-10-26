"""
Unit tests for ZCF CLI workflows and command dispatching.
Tests integrate, service, db verify/delete, and test recording.
"""

from __future__ import annotations

import io
import os
import shutil
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from unittest.mock import patch

from zcf.cli.main import main
from zcf.compatibility_db.database import CompatibilityDatabase
from zcf.core.models import CompatibilityEntry, CompatibilityStatus, EvidenceStatus, ProvenanceTier
from zcf.runtimes.prefix_manager import WinePrefixManager


class TestCLIWorkflows(unittest.TestCase):
    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        self.db_dir = os.path.join(self.test_dir, "db")
        self.app_dir = os.path.join(self.test_dir, "apps")
        self.prefix_dir = os.path.join(self.test_dir, "prefixes")
        os.makedirs(self.db_dir, exist_ok=True)
        os.makedirs(self.app_dir, exist_ok=True)
        os.makedirs(self.prefix_dir, exist_ok=True)

        self.fixtures_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "fixtures", "synthetic"))
        self.pe_fixture = os.path.join(self.fixtures_dir, "valid_pe32plus.exe")

    def tearDown(self):
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_cli_integrate_list_and_remove(self):
        """Verifies 'zcf integrate' CLI commands for adding, listing, and removing desktop launchers."""
        buf = io.StringIO()
        with patch("zcf.desktop.integrator.DesktopIntegrator.integrate") as mock_int, \
             patch("zcf.desktop.integrator.DesktopIntegrator.list_integrated_apps") as mock_list, \
             patch("zcf.desktop.integrator.DesktopIntegrator.unintegrate") as mock_unint:

            mock_int.return_value = "/tmp/test.desktop"
            mock_list.return_value = [{"name": "Sample", "file_name": "test.desktop", "artifact_path": "/tmp/sample.exe"}]
            mock_unint.return_value = True

            # 1. Integrate
            with redirect_stdout(buf):
                main(["integrate", self.pe_fixture, "--name", "Sample Tool"])
            self.assertIn("Successfully integrated", buf.getvalue())

            # 2. List
            buf = io.StringIO()
            with redirect_stdout(buf):
                main(["integrate", "--list"])
            self.assertIn("Desktop Integrated Applications", buf.getvalue())
            self.assertIn("Sample", buf.getvalue())

            # 3. Remove
            buf = io.StringIO()
            with redirect_stdout(buf):
                main(["integrate", "--remove", self.pe_fixture])
            self.assertIn("Successfully unintegrated", buf.getvalue())

    def test_cli_service_list_prefixes_and_cleanup(self):
        """Verifies 'zcf service list-prefixes' and cleanup commands."""
        buf = io.StringIO()
        with patch.object(WinePrefixManager, "list_prefixes", return_value=[]), \
             patch.object(WinePrefixManager, "cleanup_stale_prefixes", return_value=0):

            with redirect_stdout(buf):
                main(["service", "list-prefixes"])
            self.assertIn("ZCF Managed Prefixes", buf.getvalue())

            buf = io.StringIO()
            with redirect_stdout(buf):
                main(["service", "cleanup-prefixes", "--max-age-days", "14"])
            self.assertIn("Cleaned 0 stale prefix directories", buf.getvalue())

    def test_cli_db_verify_and_delete(self):
        """Verifies 'zcf db verify' and 'zcf db delete' actions."""
        import hashlib
        db = CompatibilityDatabase(storage_dir=self.db_dir)
        real_sha = hashlib.sha256(b"unique_cli_binary_bytes_for_testing").hexdigest()
        entry = CompatibilityEntry(
            entry_id="cli_test_entry",
            application_name="CLI App",
            target_sha256=real_sha,
            target_format="pe",
            target_architecture="x86_64",
            status=CompatibilityStatus.UNTESTED,
            last_verified="2026-10-25T00:00:00Z",
            recommended_runtime="runtime.wine",
            provenance_tier=ProvenanceTier.COMMUNITY_UNTESTED,
            evidence_status=EvidenceStatus.COMMUNITY_REPORTED,
        )
        db.add_entry(entry)

        with patch("zcf.cli.main.CompatibilityDatabase", return_value=db):
            # Verify action
            buf = io.StringIO()
            with redirect_stdout(buf):
                main(["db", "verify", "--id", "cli_test_entry", "--verifier", "Auditor", "--tier", "maintainer_verified", "--evidence-status", "verified", "--notes", "Audit pass"])
            self.assertIn("Successfully verified and promoted profile", buf.getvalue())

            # Delete action
            buf = io.StringIO()
            with redirect_stdout(buf):
                main(["db", "delete", "--id", "cli_test_entry"])
            self.assertIn("Successfully deleted profile", buf.getvalue())
            self.assertIsNone(db.get_by_id("cli_test_entry"))

    def test_cli_test_with_record(self):
        """Verifies 'zcf test' records outcome into local database when --record is specified."""
        db = CompatibilityDatabase(storage_dir=self.db_dir)
        with patch("zcf.cli.main.CompatibilityDatabase", return_value=db):
            buf = io.StringIO()
            with redirect_stdout(buf):
                main(["test", self.pe_fixture, "--dry-run", "--record", "--contributor", "Test Lead"])
            out = buf.getvalue()
            self.assertIn("ZCF Execution Test", out)
            self.assertIn("[Database] Test outcome recorded", out)

            # Honest provenance verification: dry-run must NOT record verified compatible
            from zcf.inspector.inspector import ApplicationInspector
            app = ApplicationInspector().inspect(self.pe_fixture)
            entry = db.get_by_sha256(app.sha256)
            self.assertIsNotNone(entry)
            self.assertEqual(entry.status, CompatibilityStatus.UNTESTED)
            self.assertEqual(entry.evidence_status, EvidenceStatus.UNTESTED)
            self.assertIn("Dry-run", entry.test_procedure)

    def test_cli_test_live_execution_script(self):
        """Verifies 'zcf test' live execution on a runnable script fixture."""
        script_fixture = os.path.join(self.fixtures_dir, "valid_script.sh")
        if not os.path.exists(script_fixture):
            self.skipTest("Script fixture missing")
        db = CompatibilityDatabase(storage_dir=self.db_dir)
        with patch("zcf.cli.main.CompatibilityDatabase", return_value=db):
            buf = io.StringIO()
            with redirect_stdout(buf):
                main(["test", script_fixture, "--dry-run", "--record", "--contributor", "Script Tester"])
            out = buf.getvalue()
            self.assertIn("ZCF Execution Test", out)
            self.assertIn("[Database] Test outcome recorded", out)

    def test_cli_test_blocked_hard_incompatibility(self):
        """Verifies 'zcf test' cleanly blocks and exits with code 2 for unsupported binaries."""
        corrupted_fixture = os.path.join(self.fixtures_dir, "corrupted.bin")
        if not os.path.exists(corrupted_fixture):
            self.skipTest("Corrupted fixture missing")
        db = CompatibilityDatabase(storage_dir=self.db_dir)
        with patch("zcf.cli.main.CompatibilityDatabase", return_value=db):
            buf = io.StringIO()
            err_buf = io.StringIO()
            with redirect_stdout(buf), redirect_stderr(err_buf):
                with self.assertRaises(SystemExit) as ctx:
                    main(["test", corrupted_fixture, "--record"])
            self.assertEqual(ctx.exception.code, 2)
            self.assertIn("Execution Blocked", err_buf.getvalue())

    def test_cli_history_workflow(self):
        """Verifies 'zcf history' command for listing, inspecting, and clearing runs."""
        from zcf.execution.history import ExecutionHistoryManager
        hist_dir = os.path.join(self.test_dir, "history")
        hist_mgr = ExecutionHistoryManager(storage_dir=hist_dir)

        # Record a run
        rec = hist_mgr.record_run(
            artifact_path=self.pe_fixture,
            artifact_sha256="4"*64,
            application_name="sample.exe",
            target_format="pe",
            target_architecture="x86_64",
            runtime_id="runtime.wine",
            runtime_name="Wine",
            execution_mode="translation",
            dry_run=True,
            success=True,
            exit_code=0,
            execution_time_seconds=0.05,
            sandbox_active=False,
            network_isolated=True,
            stdout="Sample stdout",
        )

        with patch("zcf.execution.history.ExecutionHistoryManager", return_value=hist_mgr):
            # 1. List history
            buf = io.StringIO()
            with redirect_stdout(buf):
                main(["history"])
            out = buf.getvalue()
            self.assertIn("Execution Test History", out)
            self.assertIn("sample.exe", out)
            self.assertIn(rec.run_id, out)

            # 2. Inspect specific run
            buf = io.StringIO()
            with redirect_stdout(buf):
                main(["history", rec.run_id])
            out = buf.getvalue()
            self.assertIn("Execution Run Record", out)
            self.assertIn("sample.exe", out)
            self.assertIn("Sample stdout", out)

            # 3. Clear history
            buf = io.StringIO()
            with redirect_stdout(buf):
                main(["history", "--clear"])
            self.assertIn("Cleared 1 execution run log(s)", buf.getvalue())

    def test_cli_runners_workflows(self):
        """Verifies 'zcf runners list' and 'zcf runners available' commands."""
        buf = io.StringIO()
        with redirect_stdout(buf):
            main(["runners", "list"])
        self.assertIn("Discovered Compatibility Runners", buf.getvalue())

        buf = io.StringIO()
        with redirect_stdout(buf):
            main(["runners", "available", "--limit", "2"])
        self.assertIn("Available Upstream Runners", buf.getvalue())

    def test_cli_snapshot_workflows(self):
        """Verifies 'zcf snapshot create' and 'zcf snapshot list' commands."""
        prefix = os.path.join(self.test_dir, "snap_prefix")
        os.makedirs(prefix, exist_ok=True)
        with open(os.path.join(prefix, "system.reg"), "w") as f:
            f.write("[Software\\\\Wine]\n")

        buf = io.StringIO()
        with redirect_stdout(buf):
            main(["snapshot", "create", prefix, "--label", "Test CLI Snap"])
        self.assertIn("Successfully created snapshot", buf.getvalue())

        buf = io.StringIO()
        with redirect_stdout(buf):
            main(["snapshot", "list", prefix])
        self.assertIn("Time-Machine Snapshots for", buf.getvalue())
        self.assertIn("Test CLI Snap", buf.getvalue())

    def test_cli_vault_workflows(self):
        """Verifies 'zcf vault list' command."""
        buf = io.StringIO()
        with redirect_stdout(buf):
            main(["vault", "list"])
        self.assertIn("Save Game Vault Backups", buf.getvalue())

    def test_cli_taskmgr_workflows(self):
        """Verifies 'zcf taskmgr list' and 'zcf taskmgr reset-locks' commands."""
        buf = io.StringIO()
        with redirect_stdout(buf):
            main(["taskmgr", "list"])
        self.assertIn("Active Prefix Processes", buf.getvalue())

        prefix = os.path.join(self.test_dir, "lock_prefix")
        os.makedirs(prefix, exist_ok=True)
        with open(os.path.join(prefix, ".update-timestamp"), "w") as f:
            f.write("test")

        buf = io.StringIO()
        with redirect_stdout(buf):
            main(["taskmgr", "reset-locks", prefix])
        self.assertIn("Cleared 1 locks", buf.getvalue())

    def test_cli_prescribe_workflows(self):
        """Verifies 'zcf prescribe generate' command."""
        log_file = os.path.join(self.test_dir, "crash.log")
        with open(log_file, "w") as f:
            f.write("err:module:import_dll Library d3dx9_43.dll not found\n")

        buf = io.StringIO()
        with redirect_stdout(buf):
            main(["prescribe", "generate", log_file, "--app", "Doom.exe"])
        out = buf.getvalue()
        self.assertIn("Autonomous Healing Prescription", out)
        self.assertIn("d3dx9", out)

    def test_cli_components_workflows(self):
        """Verifies 'zcf components list' and 'zcf components overrides' commands."""
        buf = io.StringIO()
        with redirect_stdout(buf):
            main(["components", "list"])
        out = buf.getvalue()
        self.assertIn("Available Windows Components", out)
        self.assertIn("vcrun2022", out)
        self.assertIn("dxvk", out)

        prefix = os.path.join(self.test_dir, "comp_prefix")
        os.makedirs(prefix, exist_ok=True)
        buf = io.StringIO()
        with redirect_stdout(buf):
            main(["components", "overrides", prefix, "--set", "d3d11", "native,builtin"])
        out = buf.getvalue()
        self.assertIn("Configured DLL override for 'd3d11'", out)

        buf = io.StringIO()
        with redirect_stdout(buf):
            main(["components", "overrides", prefix, "--json"])
        self.assertIn("d3d11", buf.getvalue())

    def test_cli_completions_workflows(self):
        """Verifies 'zcf completions bash/zsh/fish' commands."""
        for shell in ("bash", "zsh", "fish"):
            buf = io.StringIO()
            with redirect_stdout(buf):
                main(["completions", shell])
            out = buf.getvalue()
            self.assertIn("zcf", out)
            self.assertIn("runners", out)
            self.assertIn("vault", out)



if __name__ == "__main__":
    unittest.main()
