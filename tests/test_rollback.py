"""Tests for the installation journal: record, uninstall, rollback."""
from __future__ import annotations

import os
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from agmod import rollback


class TestRollback(unittest.TestCase):
    def test_game_journals_are_isolated_by_absolute_path(self):
        with tempfile.TemporaryDirectory() as cache, tempfile.TemporaryDirectory() as one, tempfile.TemporaryDirectory() as two:
            game_one = os.path.join(one, "Game")
            game_two = os.path.join(two, "Game")
            os.makedirs(game_one)
            os.makedirs(game_two)
            mod_file = os.path.join(game_one, "mod.dll")
            with open(mod_file, "w") as f:
                f.write("x")
            with mock.patch.object(rollback, "CACHE_ROOT", cache):
                rollback.record_install(game_one, "mod-a", [mod_file], {})
                self.assertEqual(len(rollback.list_installs(game_one)), 1)
                self.assertEqual(rollback.list_installs(game_two), [])

    def test_uninstall_preserves_user_modified_files(self):
        with tempfile.TemporaryDirectory() as game_dir:
            mod_file = os.path.join(game_dir, "Mods", "mod.lua")
            os.makedirs(os.path.dirname(mod_file))
            with open(mod_file, "w") as f:
                f.write("installed")
            rollback.record_install(game_dir, "mod", [mod_file], {})
            with open(mod_file, "w") as f:
                f.write("user changed this")
            result = rollback.uninstall(game_dir, "mod")
            self.assertFalse(result["success"])
            self.assertTrue(os.path.isfile(mod_file))
            self.assertEqual(len(rollback.list_installs(game_dir)), 1)

    def test_install_files_rolls_back_partial_copy(self):
        import shutil

        with tempfile.TemporaryDirectory() as game_dir, tempfile.TemporaryDirectory() as src_dir:
            src_a = os.path.join(src_dir, "a.lua")
            src_b = os.path.join(src_dir, "b.lua")
            with open(src_a, "w") as f:
                f.write("a")
            with open(src_b, "w") as f:
                f.write("b")
            dest_a = os.path.join(game_dir, "mods", "a.lua")
            dest_b = os.path.join(game_dir, "mods", "b.lua")
            real_copy = shutil.copy2

            def failing_copy(src, dest, *args, **kwargs):
                if os.path.basename(dest) == "b.lua":
                    raise OSError("simulated copy failure")
                return real_copy(src, dest, *args, **kwargs)

            with mock.patch.object(rollback.shutil, "copy2", side_effect=failing_copy):
                with self.assertRaises(OSError):
                    rollback.install_files(game_dir, "partial", [(src_a, dest_a), (src_b, dest_b)])
            self.assertFalse(os.path.exists(dest_a))
            self.assertEqual(rollback.list_installs(game_dir), [])

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

    def test_prune_empty_dirs_and_keep_protected(self):
        with tempfile.TemporaryDirectory() as game_dir:
            # Subdir structure
            nested_file = os.path.join(game_dir, "Mods", "DeepMod", "scripts", "main.lua")
            os.makedirs(os.path.dirname(nested_file), exist_ok=True)
            with open(nested_file, "w") as f:
                f.write("print('hi')")

            rollback.record_install(game_dir, "deepmod", [nested_file], {})
            r = rollback.uninstall(game_dir, "deepmod")
            self.assertTrue(r["success"])
            # The mod file and subdirectories should be gone
            self.assertFalse(os.path.exists(nested_file))
            self.assertFalse(os.path.exists(os.path.join(game_dir, "Mods", "DeepMod")))
            # But the protected folder "Mods" must still exist!
            self.assertTrue(os.path.isdir(os.path.join(game_dir, "Mods")))

    def test_check_conflicts_detects_ownership(self):
        with tempfile.TemporaryDirectory() as game_dir:
            f1 = os.path.join(game_dir, "BepInEx", "plugins", "ModA.dll")
            os.makedirs(os.path.dirname(f1), exist_ok=True)
            with open(f1, "w") as f:
                f.write("A")
            rollback.record_install(game_dir, "ModA", [f1], {})

            # Check conflict for ModA.dll and a new file
            res = rollback.check_conflicts(game_dir, ["BepInEx/plugins/ModA.dll", "BepInEx/plugins/ModB.dll"])
            self.assertTrue(res["has_conflicts"])
            self.assertEqual(res["conflict_count"], 1)
            self.assertEqual(res["conflicts"][0]["path"], "BepInEx/plugins/ModA.dll")
            self.assertEqual(res["conflicts"][0]["installed_by"], "ModA")

    def test_uninstall_not_found(self):
        with tempfile.TemporaryDirectory() as game_dir:
            res = rollback.uninstall(game_dir, "nonexistent")
            self.assertFalse(res["success"])
            self.assertIn("no install record found", res["error"])

    def test_reengine_scaffold_install_and_uninstall(self):
        from agmod.adapters.reengine import ReEngineAdapter
        adapter = ReEngineAdapter()

        with tempfile.TemporaryDirectory() as proj_dir, tempfile.TemporaryDirectory() as game_dir:
            adapter.scaffold_mod(proj_dir, "dps-meter", "DPS Meter", "1.0.0", "Tester")
            self.assertTrue(os.path.isfile(os.path.join(proj_dir, "autorun", "dps-meter.lua")))
            self.assertTrue(os.path.isfile(os.path.join(proj_dir, "mod.json")))

            dest = adapter.install_mod(proj_dir, game_dir)
            installed_lua = os.path.join(dest, "dps-meter.lua")
            self.assertTrue(os.path.isfile(installed_lua))

            # Verify recorded in rollback journal
            installs = rollback.list_installs(game_dir)
            self.assertEqual(len(installs), 1)
            self.assertEqual(installs[0]["mod_id"], "dps-meter")

            # Uninstall
            res = rollback.uninstall(game_dir, "dps-meter")
            self.assertTrue(res["success"])
            self.assertFalse(os.path.exists(installed_lua))
            self.assertEqual(rollback.list_installs(game_dir), [])

    def test_tmodloader_install_and_uninstall(self):
        from agmod.tmodloader import scaffold_tmod_mod, install_tmod_mod

        with tempfile.TemporaryDirectory() as proj_dir, tempfile.TemporaryDirectory() as game_dir:
            scaffold_tmod_mod(proj_dir, "ItemMod", "Item Mod", "0.1.0", "Author")
            out_dir = os.path.join(proj_dir, "out")
            os.makedirs(out_dir, exist_ok=True)
            dummy_dll = os.path.join(out_dir, "ItemMod.dll")
            with open(dummy_dll, "w") as f:
                f.write("DLL_BYTES")

            r = install_tmod_mod(proj_dir, game_dir)
            self.assertTrue(r["success"])
            installed_target = os.path.join(r["destination"], "ItemMod.dll")
            self.assertTrue(os.path.isfile(installed_target))

            # Rollback
            res = rollback.uninstall(game_dir, "ItemMod")
            self.assertTrue(res["success"])
            self.assertFalse(os.path.exists(installed_target))

    def test_package_validation(self):
        from agmod.pack import package_mod, validate_package
        from agmod.adapters.reengine import ReEngineAdapter

        with tempfile.TemporaryDirectory() as proj_dir:
            adapter = ReEngineAdapter()
            adapter.scaffold_mod(proj_dir, "quick-mod", "Quick Mod", "1.0.0", "Author")
            zip_path = package_mod(proj_dir)
            self.assertTrue(os.path.isfile(zip_path))

            val = validate_package(zip_path)
            self.assertTrue(val["valid"])
            self.assertEqual(val["errors"], [])
            self.assertIn("autorun/quick-mod.lua", val["payload_files"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
