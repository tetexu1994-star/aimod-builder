"""Synthetic regression suite: plan generation and hook synthesis across 16 scenarios."""
from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from agmod.codegen import generate_hook_from_evidence, generate_hook_template
from agmod.log_repair import diagnose_runtime_error
from agmod.planning import plan_mod

BENCHMARK_CASES = [
    # --- Unity (BepInEx / Harmony) ---
    {
        "id": "unity-infinite-gold",
        "engine": "unity",
        "markers": ["Game_Data/Managed/Assembly-CSharp.dll"],
        "request": "给主角增加 999999 金币并支持配置文件调整",
        "customizations": {"amount": 999999},
        "target_class": "PlayerEconomy",
        "target_method": "AddGold",
        "params": [{"type": "int", "name": "amount"}],
    },
    {
        "id": "unity-infinite-durability",
        "engine": "unity",
        "markers": ["Game_Data/Managed/Assembly-CSharp.dll"],
        "request": "武器装备无限耐久度，攻击与格挡时不消耗耐久",
        "customizations": {"consume": False},
        "target_class": "ItemDurability",
        "target_method": "ConsumeDurability",
        "params": [{"type": "float", "name": "loss"}],
    },
    {
        "id": "unity-movement-speed",
        "engine": "unity",
        "markers": ["Game_Data/Managed/Assembly-CSharp.dll"],
        "request": "Increase player move speed by 2.5x and double jump height",
        "customizations": {"speed_multiplier": 2.5},
        "target_class": "PlayerMovement",
        "target_method": "GetBaseSpeed",
        "params": [],
    },
    {
        "id": "unity-vacuum-pickup",
        "engine": "unity",
        "markers": ["Game_Data/Managed/Assembly-CSharp.dll"],
        "request": "掉落物自动吸附到玩家背包，拾取距离扩大 10 倍",
        "customizations": {"range": 50.0},
        "target_class": "ItemDropManager",
        "target_method": "CheckPickupRange",
        "params": [{"type": "float", "name": "distance"}],
    },
    # --- Unreal Engine (UE4SS / Lua) ---
    {
        "id": "unreal-broom-unlock",
        "engine": "unreal",
        "markers": ["MyGame.uproject", "Content/Paks/game.pak"],
        "request": "解除飞天扫帚飞行高度限制并提升最大飞行速度",
        "customizations": {"max_height": 99999.0, "speed": 2.0},
        "target_class": "BroomFlightComponent",
        "target_method": "UpdateFlightLimits",
        "params": [{"type": "float", "name": "max_altitude"}],
    },
    {
        "id": "unreal-healthbar-overlay",
        "engine": "unreal",
        "markers": ["Content/Paks/chunk0.pak"],
        "request": "在所有敌人头顶显示实时血量数值与状态栏",
        "customizations": {"show_numbers": True},
        "target_class": "EnemyUIController",
        "target_method": "RenderEnemyBar",
        "params": [{"type": "int", "name": "current_hp"}, {"type": "int", "name": "max_hp"}],
    },
    {
        "id": "unreal-god-mode",
        "engine": "unreal",
        "markers": ["Content/Paks/Paks.pak"],
        "request": "主角无敌模式，受到任意伤害时不扣减生命值",
        "customizations": {"invulnerable": True},
        "target_class": "HealthComponent",
        "target_method": "TakeDamage",
        "params": [{"type": "float", "name": "damage"}],
    },
    {
        "id": "unreal-free-camera",
        "engine": "unreal",
        "markers": ["Game.uproject"],
        "request": "Unlock free camera mode and disable photo mode boundaries",
        "customizations": {"unlimited_range": True},
        "target_class": "CameraManager",
        "target_method": "ClampCameraBounds",
        "params": [],
    },
    # --- Capcom RE Engine (REFramework / Lua) ---
    {
        "id": "reengine-monster-hp-dps",
        "engine": "re-engine",
        "markers": ["re_chunk_000.pak", "MonsterHunterRise.exe"],
        "request": "按 F1 打开 UI，实时显示大型怪物当前剩余血量与全队 DPS",
        "customizations": {"ui_toggle_key": "F1"},
        "target_class": "EnemyCharacter",
        "target_method": "CalcDamage",
        "params": [{"type": "int", "name": "damage"}],
    },
    {
        "id": "reengine-infinite-wirebug",
        "engine": "re-engine",
        "markers": ["re_chunk_000.pak", "MonsterHunterWilds.exe"],
        "request": "无限翔虫与无限耐力，使用铁虫丝技不进入冷却",
        "customizations": {"wirebug_count": 3},
        "target_class": "PlayerWirebugManager",
        "target_method": "ConsumeWirebug",
        "params": [{"type": "int", "name": "cost"}],
    },
    {
        "id": "reengine-infinite-ammo",
        "engine": "re-engine",
        "markers": ["re_chunk_000.pak", "re4.exe"],
        "request": "Resident Evil 4 infinite ammo and laser sight overlay",
        "customizations": {"infinite_ammo": True},
        "target_class": "WeaponGun",
        "target_method": "ConsumeBullet",
        "params": [],
    },
    {
        "id": "reengine-instant-reload",
        "engine": "re-engine",
        "markers": ["re_chunk_000.pak", "re8.exe"],
        "request": "武器瞬间完成装填，跳过漫长装弹动画",
        "customizations": {"instant": True},
        "target_class": "WeaponReloadController",
        "target_method": "StartReloadAnimation",
        "params": [],
    },
    # --- Godot Engine (GodotModLoader / GDScript) ---
    {
        "id": "godot-brotato-starter-mats",
        "engine": "godot",
        "markers": ["brotato.pck"],
        "request": "土豆兄弟开局获得 10000 材料，拾取磁铁范围扩大 5 倍",
        "customizations": {"initial_materials": 10000, "pickup_range": 5.0},
        "target_class": "PlayerRunData",
        "target_method": "InitRun",
        "params": [{"type": "int", "name": "gold"}],
    },
    {
        "id": "godot-auto-aim-fire",
        "engine": "godot",
        "markers": ["game.pck"],
        "request": "所有武器自动索敌并自动瞄准开火，取消射程盲区",
        "customizations": {"auto_aim": True},
        "target_class": "WeaponNode",
        "target_method": "ShootAtNearestEnemy",
        "params": [],
    },
    {
        "id": "godot-inventory-boost",
        "engine": "godot",
        "markers": ["game.godot"],
        "request": "Double the player inventory slots and disable item weight limit",
        "customizations": {"slots": 60, "weight_limit": False},
        "target_class": "InventorySystem",
        "target_method": "CanAddItem",
        "params": [{"type": "object", "name": "item"}],
    },
    {
        "id": "godot-infinite-items",
        "engine": "godot",
        "markers": ["buckshot.pck"],
        "request": "恶魔轮盘赌道具无限次使用，跳过对方回合",
        "customizations": {"infinite_items": True},
        "target_class": "TableManager",
        "target_method": "ConsumeItem",
        "params": [{"type": "int", "name": "item_id"}],
    },
]


class TestBenchmarkEvaluation(unittest.TestCase):
    def test_evidence_codegen_preserves_target_provenance(self):
        result = generate_hook_from_evidence({
            "engine": "unity",
            "target": {
                "namespace": "Game.Player",
                "class_name": "Controller",
                "method_name": "AddGold",
                "signature": "System.Void AddGold(System.Int32)",
                "overload_key": "AddGold(int)",
                "is_static": False,
                "return_type": "void",
                "parameters": [{"type": "int", "name": "amount"}],
            },
            "evidence": {"source": "rea_fast_search", "confidence": 0.91},
        })
        self.assertTrue(result["validation"]["valid"])
        self.assertIn("Game.Player", result["code"])
        self.assertIn("Controller __instance", result["code"])
        self.assertIn("int amount", result["code"])
        self.assertEqual(result["target"]["signature"], "System.Void AddGold(System.Int32)")
        self.assertEqual(result["evidence"]["source"], "rea_fast_search")

    def test_unity_static_method_omits_instance_and_keeps_params(self):
        result = generate_hook_from_evidence({
            "engine": "unity",
            "target": {
                "class_name": "GlobalScore",
                "method_name": "AddScore",
                "is_static": True,
                "parameters": [{"type": "int", "name": "points"}],
            },
        })
        self.assertTrue(result["validation"]["valid"])
        self.assertNotIn("__instance", result["code"])
        self.assertIn("int points", result["code"])


    def test_plan_generation_all_16_cases(self):
        """Verify plan_mod generates complete ModSpec, MODDING_PLAN, and engine project across all 16 cases."""
        for case in BENCHMARK_CASES:
            with self.subTest(case_id=case["id"]):
                with tempfile.TemporaryDirectory() as game_dir, tempfile.TemporaryDirectory() as proj_dir:
                    # Setup markers
                    for m in case["markers"]:
                        p = os.path.join(game_dir, m)
                        os.makedirs(os.path.dirname(p), exist_ok=True)
                        open(p, "w").close()

                    res = plan_mod(
                        game_dir=game_dir,
                        request=case["request"],
                        project_dir=proj_dir,
                        customizations=case.get("customizations"),
                    )

                    self.assertIn("id", res)
                    self.assertIn("engine", res)
                    self.assertEqual(res["engine"]["id"], case["engine"])

                    # Verify mod-spec.json
                    spec_file = os.path.join(proj_dir, "mod-spec.json")
                    self.assertTrue(os.path.isfile(spec_file))
                    with open(spec_file, "r", encoding="utf-8") as f:
                        spec = json.load(f)
                    self.assertEqual(spec["engine"]["id"], case["engine"])
                    self.assertTrue(spec["name"])
                    self.assertEqual(spec["customizations"], case.get("customizations", {}))

                    # Verify MODDING_PLAN.md and request.md
                    self.assertTrue(os.path.isfile(os.path.join(proj_dir, "MODDING_PLAN.md")))
                    self.assertTrue(os.path.isfile(os.path.join(proj_dir, "request.md")))

    def test_codegen_synthesis_all_16_cases(self):
        """Verify generate_hook_template emits valid snippets for each case's target method and params."""
        for case in BENCHMARK_CASES:
            with self.subTest(case_id=case["id"]):
                hook_res = generate_hook_template(
                    engine=case["engine"],
                    class_name=case["target_class"],
                    method_name=case["target_method"],
                    hook_type="prefix",
                    parameters=case["params"],
                )
                self.assertIn("code", hook_res)
                self.assertIn(case["target_class"], hook_res["code"])
                self.assertIn(case["target_method"], hook_res["code"])

    def test_runtime_log_diagnosis(self):
        """Verify diagnose_runtime_error correctly parses stack traces from all 4 frameworks."""
        # 1. UE4SS Lua Error
        ue4ss_log = "[2026-10-14 10:00:00] [LuaError] C:/Games/Game/Binaries/Win64/ue4ss/Mods/MyMod/scripts/main.lua:42: attempt to index a nil value (field 'Health')"
        d1 = diagnose_runtime_error(ue4ss_log)
        self.assertTrue(d1["has_error"])
        self.assertEqual(d1["issues"][0]["framework"], "UE4SS")
        self.assertEqual(d1["issues"][0]["line"], 42)

        # 2. REFramework Error
        ref_log = '[10:00:00.123] [REFramework] Sol: runtime error: [string "autorun/my_mod.lua"]:25: attempt to call a nil value'
        d2 = diagnose_runtime_error(ref_log)
        self.assertTrue(d2["has_error"])
        self.assertEqual(d2["issues"][0]["framework"], "REFramework")
        self.assertEqual(d2["issues"][0]["line"], 25)

        # 3. BepInEx Error
        bep_log = """[Error  : Unity Log] System.NullReferenceException: Object reference not set to an instance of an object
  at MyMod.Plugin.Prefix (PlayerController __instance) in C:\\Mod\\Plugin.cs:line 30"""
        d3 = diagnose_runtime_error(bep_log)
        self.assertTrue(d3["has_error"])
        self.assertEqual(d3["issues"][0]["framework"], "BepInEx")
        self.assertEqual(d3["issues"][0]["line"], 30)

        # 4. Godot Error
        godot_log = """SCRIPT ERROR: Invalid get index 'materials' (on base: 'Nil').
          at: _ready (res://mods-unpacked/Author-Mod/mod_main.gd:15)"""
        d4 = diagnose_runtime_error(godot_log)
        self.assertTrue(d4["has_error"])
        self.assertEqual(d4["issues"][0]["framework"], "GodotModLoader")
        self.assertEqual(d4["issues"][0]["line"], 15)


if __name__ == "__main__":
    unittest.main(verbosity=2)
