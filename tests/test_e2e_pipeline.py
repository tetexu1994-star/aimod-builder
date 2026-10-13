"""End-to-end integration pipeline tests: doctor, compiler repair, and full lifecycle."""
from __future__ import annotations

import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from agmod import doctor, inspector, logs, planning, repair, saves


class TestDoctor(unittest.TestCase):
    def test_environment_check(self):
        rep = doctor.check_environment()
        self.assertIn("ready", rep)
        self.assertIn("platform", rep)
        self.assertIn("checks", rep)
        self.assertTrue(len(rep["checks"]) >= 5)

        md = doctor.format_doctor_report(rep)
        self.assertIn("Environment Doctor Report", md)
        self.assertIn("Python", md)


class TestRepair(unittest.TestCase):
    def test_parse_and_diagnose_errors(self):
        sample_output = """
Microsoft (R) Build Engine version 17.0.0
Plugin.cs(12,17): error CS0246: The type or namespace name 'GameObject' could not be found (are you missing a using directive or an assembly reference?)
Plugin.cs(18,5): error CS1002: ; expected
Plugin.cs(25,1): warning CS0168: The variable 'ex' is declared but never used
"""
        diag = repair.diagnose_build_output(sample_output)
        self.assertTrue(diag["has_errors"])
        self.assertEqual(diag["error_count"], 2)
        self.assertEqual(diag["warning_count"], 1)

        # Check suggestions
        fixes = diag["suggested_fixes"]
        self.assertTrue(any("using UnityEngine;" in f for f in fixes))
        self.assertTrue(any("Semicolon missing" in f for f in fixes))

    def test_auto_heal_source(self):
        initial_source = """using BepInEx;
using HarmonyLib;

namespace MyMod
{
    public class MyPlugin : BaseUnityPlugin
    {
        void Start()
        {
            GameObject go = new GameObject();
        }
    }
}
"""
        errs = [
            repair.CompileError(
                file="Plugin.cs",
                line=10,
                column=13,
                code="CS0246",
                message="The type or namespace name 'GameObject' could not be found",
                severity="error",
            )
        ]
        healed, applied = repair.auto_heal_csharp_source(initial_source, errs)
        self.assertIn("using UnityEngine;", healed)
        self.assertEqual(len(applied), 1)
        self.assertIn("using UnityEngine;", applied[0])


class TestFullE2EPipeline(unittest.TestCase):
    def test_complete_mod_lifecycle(self):
        """Simulate the complete end-to-end flow an agent performs."""
        with tempfile.TemporaryDirectory() as game_dir, tempfile.TemporaryDirectory() as proj_dir:
            # 1. Setup mock Unreal game structure
            uproject = os.path.join(game_dir, "SandboxGame.uproject")
            with open(uproject, "w") as f:
                f.write("{}")

            save_dir = os.path.join(game_dir, "saves")
            os.makedirs(save_dir, exist_ok=True)
            with open(os.path.join(save_dir, "player.sav"), "w") as f:
                f.write("COINS=100")

            # 2. Doctor check
            doc = doctor.check_environment()
            self.assertIsNotNone(doc)

            # 3. Save backup
            bk = saves.create_save_backup(game_dir, tag="pre-flight")
            self.assertTrue(bk["success"])
            backup_id = bk["backup_id"]

            # 4. Feature inspection
            ins = inspector.inspect_feature(game_dir, "coins")
            self.assertTrue(ins["success"])
            self.assertEqual(ins["engine"]["id"], "unreal")

            # 5. Planning
            plan = planning.create_mod_plan(
                game_dir=game_dir,
                request="Set infinite coins in SandboxGame",
                project_dir=proj_dir,
                mod_id="unreal-infinite-coins",
                mod_name="Infinite Coins",
            )
            self.assertEqual(plan["status"], "planned")

            # 6. Validate project
            val = planning.validate_project(proj_dir)
            self.assertTrue(val["ok"])

            # 7. Mock logs check
            log_res = logs.read_mod_logs(game_dir)
            self.assertFalse(log_res["found"])

            # 8. Restore backup
            res = saves.restore_save_backup(game_dir, backup_id)
            self.assertTrue(res["success"])
            with open(os.path.join(save_dir, "player.sav"), "r") as f:
                self.assertEqual(f.read(), "COINS=100")


if __name__ == "__main__":
    unittest.main(verbosity=2)
