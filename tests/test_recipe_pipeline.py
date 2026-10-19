"""Unit tests for Mod Recipe export/import and ComfyUI-style pipeline DAG flow."""
from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from agmod import recipe
from agmod.ui import server


class TestRecipePipeline(unittest.TestCase):
    def test_export_and_validate_recipe(self):
        rec = recipe.export_recipe(
            mod_id="speed_boost",
            mod_name="急速奔跑 (Speed Boost)",
            game_dir="/fake/game",
            engine_id="unity",
            summary="移动速度翻倍",
            hook_target="PlayerController:Move",
            params={"multiplier": 2.0},
            rea_insight={"boundary_scope": {"safe_min": 1.0, "safe_max": 5.0}},
            healed_by="heuristic",
        )
        self.assertEqual(rec["format"], "aimod-recipe-v1")
        self.assertEqual(rec["recipe_name"], "急速奔跑 (Speed Boost)")
        self.assertEqual(rec["params"]["multiplier"], 2.0)
        self.assertEqual(rec["boundary_guard"]["safe_min"], 1.0)

        # Validate
        valid, err, val_data = recipe.validate_recipe(rec)
        self.assertTrue(valid)
        self.assertEqual(err, "")
        self.assertEqual(val_data["recipe_id"], "speed_boost")

    def test_validate_invalid_recipe(self):
        valid, err, _ = recipe.validate_recipe("not a dict")
        self.assertFalse(valid)
        self.assertIn("valid JSON object", err)

        valid, err, _ = recipe.validate_recipe({"format": "unknown-v99"})
        self.assertFalse(valid)
        self.assertIn("Unsupported recipe format", err)

        valid, err, _ = recipe.validate_recipe({"format": "aimod-recipe-v1", "params": "not a dict"})
        self.assertFalse(valid)

    def test_validate_recipe_rejects_unsafe_recipe_id(self):
        valid, err, _ = recipe.validate_recipe({
            "format": "aimod-recipe-v1",
            "recipe_name": "bad",
            "recipe_id": "../../evil",
        })
        self.assertFalse(valid)
        self.assertIn("recipe_id", err)

    def test_validate_recipe_rejects_bad_param_types(self):
        valid, err, _ = recipe.validate_recipe({
            "format": "aimod-recipe-v1",
            "recipe_name": "bad",
            "params": {"nested": {"a": 1}},
        })
        self.assertFalse(valid)
        self.assertIn("bool/int/float/str", err)

    @mock.patch("agmod.ui.server._auto_deploy_mod")
    def test_handle_recipe_import(self, mock_deploy):
        mock_deploy.return_value = {
            "success": True,
            "message": "deployed",
            "compiled": True,
            "healed_by": "",
            "installed_path": "/fake/plugins",
        }
        handler = server.ModUIRequestHandler.__new__(server.ModUIRequestHandler)
        rec = {
            "format": "aimod-recipe-v1",
            "recipe_id": "test_recipe",
            "recipe_name": "测试配方",
            "summary": "一键测试",
            "hook_target": "Test:Update",
            "params": {"speed": 3.0, "god_mode": True},
        }

        with tempfile.TemporaryDirectory() as tmp_dir:
            status, res = handler._handle_recipe_import({"game_dir": tmp_dir, "recipe": rec})
            self.assertEqual(status, 200)
            self.assertTrue(res["success"])
            self.assertEqual(res["data"]["action"]["mod_id"], "test_recipe")
            self.assertEqual(len(res["data"]["action"]["tuning_params"]), 2)

    def test_handle_recipe_export(self):
        handler = server.ModUIRequestHandler.__new__(server.ModUIRequestHandler)
        with tempfile.TemporaryDirectory() as tmp_dir:
            status, res = handler._handle_recipe_export({
                "game_dir": tmp_dir,
                "mod_id": "exported_mod",
                "mod_name": "导出测试",
                "summary": "配方测试",
                "hook_target": "Main:Tick",
                "params": {"count": 10},
            })
            self.assertEqual(status, 200)
            self.assertTrue(res["success"])
            self.assertEqual(res["data"]["recipe_name"], "导出测试")


if __name__ == "__main__":
    unittest.main()
