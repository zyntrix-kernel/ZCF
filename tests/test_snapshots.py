"""Unit tests for ZCF Prefix Time-Machine Snapshots & Rollback Engine."""

from __future__ import annotations

import json
import os
import shutil
import tempfile
import unittest

from zcf.runtimes.snapshots import PrefixSnapshotManager, auto_pre_component_snapshot


class TestPrefixSnapshots(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.prefix_dir = os.path.join(self.temp_dir, "test_prefix")
        os.makedirs(self.prefix_dir, exist_ok=True)

        # Create mock prefix files
        self.system_reg = os.path.join(self.prefix_dir, "system.reg")
        self.user_reg = os.path.join(self.prefix_dir, "user.reg")
        self.meta_file = os.path.join(self.prefix_dir, "prefix_meta.json")

        with open(self.system_reg, "w") as f:
            f.write("[Software\\\\Wine]\n\"Version\"=\"1.0\"\n")
        with open(self.user_reg, "w") as f:
            f.write("[Software\\\\App]\n\"Installed\"=\"true\"\n")
        with open(self.meta_file, "w") as f:
            json.dump({"architecture": "win64", "dll_overrides": {}}, f)

        self.mgr = PrefixSnapshotManager(default_retention=5)

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_create_and_list_snapshots(self):
        snap1 = self.mgr.create_snapshot(self.prefix_dir, label="Initial State")
        self.assertTrue(snap1.id.startswith("snap_"))
        self.assertEqual(snap1.label, "Initial State")
        self.assertIn("system.reg", snap1.files_preserved)
        self.assertIn("user.reg", snap1.files_preserved)
        self.assertGreater(snap1.size_bytes, 0)

        # List snapshots
        snaps = self.mgr.list_snapshots(self.prefix_dir)
        self.assertEqual(len(snaps), 1)
        self.assertEqual(snaps[0].id, snap1.id)

    def test_restore_snapshot(self):
        # Create baseline snapshot
        snap = self.mgr.create_snapshot(self.prefix_dir, label="Pre-Modification")

        # Mutate prefix files (simulating breaking component install or registry edit)
        with open(self.system_reg, "w") as f:
            f.write("[Software\\\\Corrupted]\n\"Broken\"=\"true\"\n")
        with open(self.meta_file, "w") as f:
            json.dump({"architecture": "win64", "dll_overrides": {"d3d11": "disabled"}}, f)

        # Verify mutation occurred
        with open(self.system_reg, "r") as f:
            self.assertIn("Corrupted", f.read())

        # Roll back to snapshot
        restored = self.mgr.restore_snapshot(self.prefix_dir, snap.id)
        self.assertTrue(restored)

        # Verify registry reverted to baseline
        with open(self.system_reg, "r") as f:
            content = f.read()
            self.assertIn("Software\\\\Wine", content)
            self.assertNotIn("Corrupted", content)

        with open(self.meta_file, "r") as f:
            meta = json.load(f)
            self.assertEqual(meta.get("dll_overrides"), {})

    def test_delete_snapshot(self):
        snap = self.mgr.create_snapshot(self.prefix_dir, label="Temporary")
        self.assertEqual(len(self.mgr.list_snapshots(self.prefix_dir)), 1)

        deleted = self.mgr.delete_snapshot(self.prefix_dir, snap.id)
        self.assertTrue(deleted)
        self.assertEqual(len(self.mgr.list_snapshots(self.prefix_dir)), 0)

    def test_auto_pre_component_snapshot_helper(self):
        snap = auto_pre_component_snapshot(self.prefix_dir, "vcrun2022")
        self.assertIsNotNone(snap)
        self.assertEqual(snap.trigger, "auto_pre_component")
        self.assertIn("vcrun2022", snap.label)
