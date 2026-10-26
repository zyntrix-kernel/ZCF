"""Unit tests for ZCF Universal Game Save Vault."""

from __future__ import annotations

import os
import shutil
import tempfile
import unittest

from zcf.runtimes.vault import GameSaveVault


class TestGameSaveVault(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.vault_dir = os.path.join(self.temp_dir, "vault")
        self.prefix_dir = os.path.join(self.temp_dir, "prefix1")

        # Create mock Windows save structure inside prefix1
        # drive_c/users/steamuser/AppData/Local/MyGame/savedata.bin
        self.save_folder = os.path.join(
            self.prefix_dir, "drive_c", "users", "steamuser", "AppData", "Local", "CyberGame"
        )
        os.makedirs(self.save_folder, exist_ok=True)
        self.save_file = os.path.join(self.save_folder, "slot1.sav")
        with open(self.save_file, "w") as f:
            f.write("PLAYER_LEVEL=50;COINS=99999\n")

        self.vault = GameSaveVault(vault_dir=self.vault_dir)

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_discover_save_locations(self):
        saves = self.vault.discover_save_locations(self.prefix_dir)
        self.assertEqual(len(saves), 1)
        self.assertEqual(saves[0].folder_name, "CyberGame")
        self.assertEqual(saves[0].category, "appdata_local")
        self.assertEqual(saves[0].files_count, 1)

    def test_backup_and_list_saves(self):
        entry = self.vault.backup_save(self.prefix_dir, "CyberGame", notes="Level 50 save before boss")
        self.assertTrue(entry.vault_id.startswith("vault_cybergame_"))
        self.assertEqual(entry.app_name, "CyberGame")
        self.assertTrue(os.path.isfile(entry.archive_path))
        self.assertGreater(entry.size_bytes, 0)
        self.assertEqual(len(entry.sha256), 64)

        backups = self.vault.list_backups(app_name_filter="CyberGame")
        self.assertEqual(len(backups), 1)
        self.assertEqual(backups[0].vault_id, entry.vault_id)

    def test_restore_save_to_new_prefix(self):
        # 1. Take backup from prefix1
        entry = self.vault.backup_save(self.prefix_dir, "CyberGame")

        # 2. Create fresh prefix2 with clean drive_c
        prefix2_dir = os.path.join(self.temp_dir, "prefix2")
        os.makedirs(os.path.join(prefix2_dir, "drive_c"), exist_ok=True)

        # 3. Restore into prefix2
        restored = self.vault.restore_save(entry.vault_id, prefix2_dir)
        self.assertTrue(restored)

        # 4. Verify save file restored exactly
        restored_file = os.path.join(
            prefix2_dir, "drive_c", "users", "steamuser", "AppData", "Local", "CyberGame", "slot1.sav"
        )
        self.assertTrue(os.path.isfile(restored_file))
        with open(restored_file, "r") as f:
            self.assertIn("PLAYER_LEVEL=50", f.read())

    def test_delete_backup(self):
        entry = self.vault.backup_save(self.prefix_dir, "CyberGame")
        self.assertEqual(len(self.vault.list_backups()), 1)

        deleted = self.vault.delete_backup(entry.vault_id)
        self.assertTrue(deleted)
        self.assertEqual(len(self.vault.list_backups()), 0)
        self.assertFalse(os.path.exists(entry.archive_path))
