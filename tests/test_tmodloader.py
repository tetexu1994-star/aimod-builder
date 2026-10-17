from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from agmod import tmodloader
from agmod.pack import package_mod, validate_package
from agmod.ui.server import _auto_deploy_mod, _pinned_source


class TestTModLoaderWorkflow(unittest.TestCase):
    def test_scaffold_uses_official_tmlmod_targets(self):
        with tempfile.TemporaryDirectory() as project:
            tmodloader.scaffold_tmod_mod(project, "gold-plus", "Gold Plus", "1.0.0", "Tester")
            csproj = Path(project, "gold-plus.csproj").read_text(encoding="utf-8")
            self.assertIn("tMLMod.targets", csproj)
            self.assertNotIn("<TargetFramework>net6.0", csproj)
            self.assertTrue(Path(project, "docs", "BUILD.md").is_file())
            self.assertFalse(Path(project, "lib").exists())

    def test_generated_source_is_real_modplayer(self):
        source, _ = _pinned_source(
            "tmodloader", "Gold Plus", "Terraria.Player:PostUpdate",
            {"god_mode": True, "speed_multiplier": 3.0}, "gold_plus"
        )
        self.assertIn("class GoldPlusMod : Mod", source)
        self.assertIn("class GoldPlusPlayer : ModPlayer", source)
        self.assertIn("PostUpdateRunSpeeds", source)
        self.assertIn("SpeedMultiplier = 3.0f", source)

    def test_build_requires_and_returns_tmod_archive(self):
        with tempfile.TemporaryDirectory() as project, tempfile.TemporaryDirectory() as tml:
            Path(tml, "tModLoader.dll").write_bytes(b"")
            Path(tml, "tMLMod.targets").write_text("<Project />", encoding="utf-8")
            tmodloader.scaffold_tmod_mod(project, "gold-plus", "Gold Plus", "1.0.0", "Tester")

            def build_side_effect(command, **kwargs):
                output_dir = Path(command[command.index("-o") + 1])
                output_dir.mkdir(parents=True, exist_ok=True)
                mods = Path(tml, "ModLoader", "Mods")
                mods.mkdir(parents=True, exist_ok=True)
                (mods / "gold-plus.tmod").write_bytes(b"TMOD")
                return mock.Mock(returncode=0, stdout="", stderr="")

            with mock.patch.object(tmodloader.subprocess, "run", side_effect=build_side_effect):
                out_dir = tmodloader.build_tmod_mod(project, tml)
            self.assertTrue(Path(out_dir, "gold-plus.tmod").is_file())

    def test_auto_deploy_uses_tmodloader_package(self):
        with tempfile.TemporaryDirectory() as game:
            Path(game, "tModLoader.exe").write_bytes(b"")
            Path(game, "tModLoader.dll").write_bytes(b"")
            Path(game, "tMLMod.targets").write_text("<Project />", encoding="utf-8")
            Path(game, "ModLoader").mkdir()

            def fake_build(project_dir, game_dir):
                out = Path(project_dir, "out")
                out.mkdir(parents=True, exist_ok=True)
                (out / "demo.tmod").write_bytes(b"TMOD")
                return str(out)

            with mock.patch("agmod.registry.detect_engine", return_value={"id": "dotnet-xna", "engine_id": "dotnet-xna"}), mock.patch(
                "agmod.tmodloader.build_tmod_mod", side_effect=fake_build
            ):
                result = _auto_deploy_mod(game, "demo", "Demo", "test", "Terraria.Player:PostUpdate", {"god_mode": True})
            self.assertTrue(result["success"], result)
            self.assertTrue(Path(game, "ModLoader", "Mods", "demo.tmod").is_file())
            self.assertFalse(Path(game, "BepInEx").exists())

    def test_verify_tmod_mod_requires_archive_and_load_log(self):
        with tempfile.TemporaryDirectory() as game:
            mods = Path(game, "ModLoader", "Mods")
            mods.mkdir(parents=True)
            self.assertFalse(tmodloader.verify_tmod_mod(game, "demo")["installed"])
            (mods / "demo.tmod").write_bytes(b"TMOD")
            result = tmodloader.verify_tmod_mod(game, "demo")
            self.assertTrue(result["installed"])
            self.assertFalse(result["effective"])
            logs = Path(game, "ModLoader", "Logs")
            logs.mkdir(parents=True)
            (logs / "tModLoader.log").write_text("Adding Mod: demo\nMod loaded: demo\n", encoding="utf-8")
            self.assertTrue(tmodloader.verify_tmod_mod(game, "demo")["effective"])

    def test_distribution_package_contains_tmod_artifact(self):
        with tempfile.TemporaryDirectory() as project:
            tmodloader.scaffold_tmod_mod(project, "demo", "Demo", "1.0.0", "Tester")
            out = Path(project, "out")
            out.mkdir()
            (out / "demo.tmod").write_bytes(b"TMOD")
            package_path = package_mod(project)
            result = validate_package(package_path)
            self.assertTrue(result["valid"])
            self.assertIn("dist/demo.tmod", result["payload_files"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
