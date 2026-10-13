"""Tests for the installation journal: record, uninstall, rollback."""
from __future__ import annotations

import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from agmod import rollback


class TestRollback(unittest.TestCase):
    def test_uninstall_removes_added_and_restores_overwritten(self):
        with tempfile.TemporaryDirectory() as game_dir:
            existing = os.path.join(game_dir, "BepInEx", "plugins", "X.dll")
            os.makedirs(os.path.dirname(existing), exist_ok=True)
            with open(existing, "w") as f:
                f.write("ORIGINAL")

            backups = rollback.backup_files(game_dir, [existing])
            with open(existing, "w") as f:
                f.write("MODDED")
            newfile = os.path.join(game_dir, "BepInEx", "plugins", "Y.dll")
            with open(newfile, "w") as f:
                f.write("NEW")
            rollback.record_install(game_dir, "mymod", [newfile], backups)

            r = rollback.uninstall(game_dir, "mymod")
            self.assertIn(os.path.relpath(newfile, game_dir), r["removed"])
            self.assertFalse(os.path.exists(newfile))
            with open(existing) as f:
                self.assertEqual(f.read(), "ORIGINAL")
            self.assertEqual(rollback.list_installs(game_dir), [])

    def test_rollback_all_reverses_everything(self):
        with tempfile.TemporaryDirectory() as game_dir:
            f1 = os.path.join(game_dir, "a.dll")
            f2 = os.path.join(game_dir, "b.dll")
            with open(f1, "w") as f:
                f.write("1")
            with open(f2, "w") as f:
                f.write("2")
            rollback.record_install(game_dir, "mod1", [f1], {})
            rollback.record_install(game_dir, "mod2", [f2], {})

            rollback.rollback_all(game_dir)
            self.assertFalse(os.path.exists(f1))
            self.assertFalse(os.path.exists(f2))
            self.assertEqual(rollback.list_installs(game_dir), [])

    def test_backup_files_skips_missing(self):
        with tempfile.TemporaryDirectory() as game_dir:
            missing = os.path.join(game_dir, "does-not-exist.dll")
            self.assertEqual(rollback.backup_files(game_dir, [missing]), {})


if __name__ == "__main__":
    unittest.main(verbosity=2)
