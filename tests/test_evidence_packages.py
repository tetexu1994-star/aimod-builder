from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from agmod import codegen, evidence, packages, symbols
from agmod.manifest import ModManifest
from agmod.pack import package_mod, validate_package
from agmod.planning import create_mod_plan, validate_project


class TestSymbolEvidence(unittest.TestCase):
    def test_ue4ss_dump_is_observed_evidence(self):
        with tempfile.TemporaryDirectory() as game:
            dump = Path(game, "ue4ss", "Mods", "Example", "symbols.txt")
            dump.parent.mkdir(parents=True)
            dump.write_text("ACharacter:TakeDamage(float amount)\n", encoding="utf-8")
            result = symbols.collect_symbol_evidence(game, "unreal", "TakeDamage")
            self.assertEqual(result["status"], "observed")
            self.assertEqual(result["candidates"][0]["source"], "ue4ss_dump")
            self.assertEqual(result["candidates"][0]["status"], "observed")
            self.assertIn("TakeDamage", result["candidates"][0]["symbol"])
            self.assertEqual(result["candidates"][0]["hook_target"]["method_name"], "TakeDamage")

    def test_reframework_dump_is_observed_evidence(self):
        with tempfile.TemporaryDirectory() as game:
            dump = Path(game, "reframework", "sdk.txt")
            dump.parent.mkdir(parents=True)
            dump.write_text("sdk.hook('app.PlayerManager', 'update')\n", encoding="utf-8")
            result = symbols.collect_symbol_evidence(game, "re-engine", "PlayerManager")
            self.assertEqual(result["status"], "observed")
            self.assertEqual(result["candidates"][0]["source"], "reframework_dump")
            self.assertIn("PlayerManager", result["candidates"][0]["symbol"])

    def test_rea_managed_search_is_observed_evidence(self):
        with tempfile.TemporaryDirectory() as game:
            managed = Path(game, "Game_Data", "Managed")
            managed.mkdir(parents=True)
            (managed / "Assembly-CSharp.dll").write_bytes(b"")
            with mock.patch.object(symbols.rea, "fast_search_members", return_value=["PlayerInventory.AddGold"]):
                result = symbols.collect_symbol_evidence(game, "unity", "AddGold")
            self.assertEqual(result["status"], "observed")
            self.assertEqual(result["candidates"][0]["source"], "rea_fast_search")
            self.assertEqual(result["candidates"][0]["status"], "observed")

    def test_cpp2il_dump_preserves_normalized_target(self):
        with tempfile.TemporaryDirectory() as game:
            dump = Path(game, "GameAssembly.il2cpp-dump", "dump.cs")
            dump.parent.mkdir(parents=True)
            dump.write_text("System.Void Game.Player.Controller::AddGold(System.Int32 amount)\n", encoding="utf-8")
            result = symbols.collect_symbol_evidence(game, "unity", "AddGold")
            self.assertEqual(result["candidates"][0]["source"], "cpp2il_dump")
            self.assertEqual(result["candidates"][0]["hook_target"]["full_class_name"], "Game.Player.Controller")

    def test_symbol_shapes_normalize_to_hook_targets(self):
        unreal = evidence.normalize_hook_target("ACharacter:TakeDamage(float amount)", "unreal", source="ue4ss_dump")
        self.assertEqual(unreal["class_name"], "ACharacter")
        self.assertEqual(unreal["method_name"], "TakeDamage")
        self.assertEqual(unreal["parameters"][0]["name"], "amount")
        ref = evidence.normalize_hook_target("sdk.hook('app.PlayerManager', 'update')", "re-engine", source="reframework_dump")
        self.assertEqual(ref["full_class_name"], "app.PlayerManager")
        self.assertEqual(ref["method_name"], "update")
        cpp2il = evidence.normalize_hook_target("Game.Player::AddGold(int32 amount)", "unity", source="cpp2il_dump")
        self.assertEqual(cpp2il["full_class_name"], "Game.Player")
        self.assertEqual(cpp2il["method_name"], "AddGold")
        rea_signature = evidence.normalize_hook_target("System.Void Game.Player.Controller::AddGold(System.Int32 amount)", "unity", source="rea_fast_search")
        self.assertEqual(rea_signature["full_class_name"], "Game.Player.Controller")
        self.assertEqual(rea_signature["method_name"], "AddGold")
        generated = codegen.generate_hook_from_evidence(rea_signature)
        self.assertTrue(generated["validation"]["valid"])
        self.assertEqual(generated["evidence"]["status"], "observed")
        self.assertFalse(generated["evidence"]["verified"])


class TestPackagePlanning(unittest.TestCase):
    def test_package_spec_resolves_loader_and_declares_layers(self):
        with tempfile.TemporaryDirectory() as game:
            Path(game, "Game.uproject").write_text("{}", encoding="utf-8")
            spec = packages.build_package_spec(game, "unreal", "better-loot", "Better Loot", "1.2.0", {"drop_rate": 2})
            self.assertEqual(spec["dependency_plan"]["dependencies"][0]["id"], "UE4SS/UE4SS")
            self.assertEqual(spec["dependency_plan"]["dependencies"][0]["status"], "missing")
            self.assertIn("config", spec["artifact_groups"])
            self.assertIn("localization", spec["artifact_groups"])
            self.assertEqual(spec["dependency_plan"]["manifest_dependencies"], ["UE4SS-UE4SS-3.0.1"])

    def test_unknown_engine_does_not_invent_a_loader_dependency(self):
        spec = packages.build_package_spec("", "future-engine", "future-mod", "Future Mod", "1.0.0")
        self.assertEqual(spec["dependencies"], [])
        self.assertEqual(spec["dependency_profile_status"], "unverified")

    def test_materialized_layout_is_valid_and_plan_writes_package_spec(self):
        with tempfile.TemporaryDirectory() as game, tempfile.TemporaryDirectory() as project:
            Path(game, "Game.uproject").write_text("{}", encoding="utf-8")
            spec = create_mod_plan(game, "增加金币", project, mod_id="gold-plus", mod_name="Gold Plus")
            self.assertTrue(Path(project, "package-spec.json").is_file())
            self.assertTrue(Path(project, "config", "default.json").is_file())
            self.assertTrue(Path(project, "localization", "en-US.json").is_file())
            self.assertIn("dependency_plan", spec)
            self.assertTrue(validate_project(project)["ok"])
            package_spec = json.loads(Path(project, "package-spec.json").read_text(encoding="utf-8"))
            self.assertTrue(packages.validate_package_spec(project, package_spec)["ok"])

    def test_plan_uses_observed_local_dump_symbols(self):
        with tempfile.TemporaryDirectory() as game, tempfile.TemporaryDirectory() as project:
            Path(game, "Game.uproject").write_text("{}", encoding="utf-8")
            dump = Path(game, "ue4ss", "symbols.txt")
            dump.parent.mkdir(parents=True)
            dump.write_text("UInventoryComponent:AddGold(int amount)\n", encoding="utf-8")
            spec = create_mod_plan(game, "增加金币", project, mod_id="gold-plus", mod_name="Gold Plus")
            self.assertIn("UInventoryComponent:AddGold", spec["candidate_symbols"])

    def test_package_validation_reports_missing_artifact(self):
        with tempfile.TemporaryDirectory() as project:
            ModManifest(id="x", name="X", version="1.0.0", engine="unreal").save(os.path.join(project, "mod.json"))
            spec = packages.build_package_spec(project, "unreal", "x", "X", "1.0.0")
            Path(project, "package-spec.json").write_text(json.dumps(spec), encoding="utf-8")
            result = packages.validate_package_spec(project, spec)
            self.assertFalse(result["ok"])
            self.assertTrue(any("missing package artifact" in error for error in result["errors"]))

    def test_distribution_includes_dependency_and_artifact_layers(self):
        with tempfile.TemporaryDirectory() as game, tempfile.TemporaryDirectory() as project:
            Path(game, "Game.uproject").write_text("{}", encoding="utf-8")
            create_mod_plan(game, "增加金币", project, mod_id="gold-plus", mod_name="Gold Plus")
            package_path = package_mod(project)
            result = validate_package(package_path)
            self.assertTrue(result["valid"])
            self.assertTrue({"package-spec.json", "compatibility.json", "config/default.json", "localization/en-US.json", "docs/INSTALL.md"}.issubset(set(result["payload_files"])))


if __name__ == "__main__":
    unittest.main(verbosity=2)
