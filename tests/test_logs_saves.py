"""Unit tests for mod runtime log diagnostics and savegame snapshots."""
from __future__ import annotations

import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from agmod import logs, planning, saves


class TestLogs(unittest.TestCase):
    def test_find_and_read_logs(self):
        with tempfile.TemporaryDirectory() as game_dir:
            # 1. No logs initially
            res = logs.read_mod_logs(game_dir)
            self.assertFalse(res["found"])

            # 2. Create a dummy BepInEx log
            bep_dir = os.path.join(game_dir, "BepInEx")
            os.makedirs(bep_dir, exist_ok=True)
            log_file = os.path.join(bep_dir, "LogOutput.log")
            with open(log_file, "w", encoding="utf-8") as f:
                f.write("[Info   :   BepInEx] Loading plugins...\n")
                f.write("[Error  :   Harmony] Patch failed for Player.AddGold: MethodNotFoundException\n")
                f.write("[Error  :   Unity] NullReferenceException: Object reference not set to an instance\n")

            res = logs.read_mod_logs(game_dir, tail_lines=10)
            self.assertTrue(res["found"])
            self.assertTrue(res["has_errors"])
            self.assertIn("Harmony patch failed", " ".join(res["diagnostics"]))
            self.assertIn("NullReferenceException", " ".join(res["diagnostics"]))


class TestSaves(unittest.TestCase):
    def test_backup_and_restore_cycle(self):
        with tempfile.TemporaryDirectory() as game_dir, tempfile.TemporaryDirectory() as cache_dir:
            # 1. Create a dummy save directory
            save_dir = os.path.join(game_dir, "saves")
            os.makedirs(save_dir, exist_ok=True)
            save_file = os.path.join(save_dir, "slot1.dat")
            with open(save_file, "w", encoding="utf-8") as f:
                f.write("PLAYER_GOLD=500;LEVEL=10")

            # 2. Detect
            detected = saves.detect_save_dirs(game_dir)
            self.assertEqual(len(detected), 1)

            # 3. Create backup
            res = saves.create_save_backup(game_dir, tag="test-run", cache_root=cache_dir)
            self.assertTrue(res["success"])
            self.assertEqual(res["files_count"], 1)
            backup_id = res["backup_id"]

            # 4. List backups
            backups = saves.list_save_backups(game_dir, cache_root=cache_dir)
            self.assertEqual(len(backups), 1)
            self.assertEqual(backups[0]["backup_id"], backup_id)

            # 5. Modify or corrupt original save
            with open(save_file, "w", encoding="utf-8") as f:
                f.write("CORRUPTED_DATA")

            # 6. Restore backup
            restore_res = saves.restore_save_backup(game_dir, backup_id, cache_root=cache_dir)
            self.assertTrue(restore_res["success"])

            # 7. Verify restored content
            with open(save_file, "r", encoding="utf-8") as f:
                content = f.read()
            self.assertEqual(content, "PLAYER_GOLD=500;LEVEL=10")


class TestPlanningIntegration(unittest.TestCase):
    def test_plan_with_inspection_metadata(self):
        with tempfile.TemporaryDirectory() as game_dir, tempfile.TemporaryDirectory() as proj_dir:
            # Fake uproject
            with open(os.path.join(game_dir, "Game.uproject"), "w") as f:
                f.write("{}")

            spec = planning.create_mod_plan(
                game_dir=game_dir,
                request="Add 99999 gold to inventory",
                project_dir=proj_dir,
                mod_id="my-gold-mod",
                mod_name="Gold Mod",
            )
            self.assertEqual(spec["id"], "my-gold-mod")
            self.assertIn("gold", spec["request"].lower())
            self.assertIn("candidate_symbols", spec)
            self.assertIn("recommended_strategy", spec)

            # Validate generated project shape
            val = planning.validate_project(proj_dir)
            self.assertTrue(val["ok"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
