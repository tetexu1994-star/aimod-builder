"""Tests for new features: AOB Pattern Scanner, ScanSession, Unreal Adapter, and Inspector."""
from __future__ import annotations

import os
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from agmod.adapters.unreal import UnrealAdapter
from agmod.inspector import inspect_feature
from agmod.memory import ScanSession
from agmod.pattern import Pattern, create_pattern
from agmod.registry import adapters, detect_engine


class TestPatternScanner(unittest.TestCase):
    def test_exact_pattern(self):
        pat = Pattern("48 89 5C 24 08")
        buf = b"\x90\x90\x48\x89\x5C\x24\x08\xC3"
        self.assertEqual(pat.find_first(buf), 2)

    def test_wildcard_pattern(self):
        pat = Pattern("48 89 ?? 24 ?? 57")
        buf = b"\x00\x11\x48\x89\x5C\x24\x10\x57\x48\x83"
        self.assertEqual(pat.find_first(buf), 2)
        self.assertEqual(pat.find_all(buf), [2])

    def test_multiple_occurrences(self):
        pat = Pattern("AA ?? BB")
        buf = b"\xAA\x01\xBB\xCC\xAA\x02\xBB"
        self.assertEqual(pat.find_all(buf), [0, 4])

    def test_create_pattern_helper(self):
        data = b"\x48\x8B\x05\x12\x34\x56\x78"
        pat_str = create_pattern(data, mask="xxx????")
        self.assertEqual(pat_str, "48 8B 05 ?? ?? ?? ??")


class TestUnrealAdapter(unittest.TestCase):
    def test_unreal_detection_and_scaffolding(self):
        adapter = UnrealAdapter()
        with tempfile.TemporaryDirectory() as game_dir:
            self.assertFalse(adapter.detect(game_dir))

            # Add uproject marker
            uproject_file = os.path.join(game_dir, "MyGame.uproject")
            with open(uproject_file, "w") as f:
                f.write("{}")

            self.assertTrue(adapter.detect(game_dir))
            det = detect_engine(game_dir)
            self.assertIsNotNone(det)
            self.assertEqual(det["id"], "unreal")

            # Test scaffolding
            with tempfile.TemporaryDirectory() as mod_proj:
                adapter.scaffold_mod(mod_proj, "test_mod", "Test Mod")
                self.assertTrue(os.path.isfile(os.path.join(mod_proj, "enabled.txt")))
                self.assertTrue(os.path.isfile(os.path.join(mod_proj, "mod.json")))
                lua_path = os.path.join(mod_proj, "scripts", "main.lua")
                self.assertTrue(os.path.isfile(lua_path))
                with open(lua_path, "r", encoding="utf-8") as f:
                    content = f.read()
                self.assertIn("Test Mod", content)
                self.assertIn("RegisterHook", content)

    def test_unreal_variant_detection(self):
        adapter = UnrealAdapter()
        with tempfile.TemporaryDirectory() as game_dir:
            paks = os.path.join(game_dir, "PBZero", "Content", "Paks")
            os.makedirs(paks, exist_ok=True)
            open(os.path.join(paks, "global.utoc"), "w").close()
            open(os.path.join(paks, "global.ucas"), "w").close()
            self.assertEqual(adapter._variant(game_dir), "ue5")
            self.assertEqual(detect_engine(game_dir)["variant"], "ue5")

        with tempfile.TemporaryDirectory() as game_dir:
            paks = os.path.join(game_dir, "Content", "Paks")
            os.makedirs(paks, exist_ok=True)
            open(os.path.join(paks, "game.pak"), "w").close()
            self.assertEqual(adapter._variant(game_dir), "ue4")
            self.assertEqual(detect_engine(game_dir)["variant"], "ue4")

    def test_unreal_pak_mod_scaffold_and_install(self):
        adapter = UnrealAdapter()
        with tempfile.TemporaryDirectory() as mod_proj:
            adapter.scaffold_pak_mod(mod_proj, "pbz_override", "PBZ Override")
            self.assertTrue(os.path.isfile(os.path.join(mod_proj, "mod.json")))
            self.assertTrue(os.path.isdir(os.path.join(mod_proj, "override")))
            self.assertTrue(os.path.isfile(os.path.join(mod_proj, "README.md")))

        with tempfile.TemporaryDirectory() as game_dir, tempfile.TemporaryDirectory() as mod_proj:
            adapter.scaffold_pak_mod(mod_proj, "pbz_override", "PBZ Override")
            dist = os.path.join(mod_proj, "dist")
            os.makedirs(dist, exist_ok=True)
            with open(os.path.join(dist, "pbz_override.pak"), "w") as f:
                f.write("PAK")
            dest = adapter.install_pak_mod(mod_proj, game_dir, "pbz_override")
            self.assertTrue(os.path.isfile(os.path.join(dest, "pbz_override.pak")))

    def test_unreal_pack_pak_requires_override_files(self):
        adapter = UnrealAdapter()
        with tempfile.TemporaryDirectory() as game_dir, tempfile.TemporaryDirectory() as mod_proj:
            adapter.scaffold_pak_mod(mod_proj, "m", "M")
            with self.assertRaises(ValueError):
                adapter.pack_pak_mod(mod_proj, game_dir, "m")

    def test_unreal_pack_pak_ue4_calls_repak(self):
        adapter = UnrealAdapter()
        with tempfile.TemporaryDirectory() as game_dir, tempfile.TemporaryDirectory() as mod_proj:
            paks = os.path.join(game_dir, "Content", "Paks")
            os.makedirs(paks, exist_ok=True)
            open(os.path.join(paks, "game.pak"), "w").close()
            adapter.scaffold_pak_mod(mod_proj, "m", "M")
            open(os.path.join(mod_proj, "override", "x.ini"), "w").close()
            with mock.patch("agmod.repak.pack_override", return_value="/fake/m.pak") as pack:
                out = adapter.pack_pak_mod(mod_proj, game_dir, "m")
            pack.assert_called_once()
            self.assertEqual(out, "/fake/m.pak")

    def test_unreal_pack_pak_ue5_calls_repak(self):
        adapter = UnrealAdapter()
        with tempfile.TemporaryDirectory() as game_dir, tempfile.TemporaryDirectory() as mod_proj:
            paks = os.path.join(game_dir, "PBZero", "Content", "Paks")
            os.makedirs(paks, exist_ok=True)
            open(os.path.join(paks, "global.utoc"), "w").close()
            adapter.scaffold_pak_mod(mod_proj, "m", "M")
            open(os.path.join(mod_proj, "override", "x.ini"), "w").close()
            with mock.patch("agmod.repak.pack_override", return_value="/fake/m.pak") as pack:
                out = adapter.pack_pak_mod(mod_proj, game_dir, "m")
            pack.assert_called_once()
            self.assertEqual(out, "/fake/m.pak")

    def test_unreal_pack_uses_P_suffix_and_compression(self):
        adapter = UnrealAdapter()
        with tempfile.TemporaryDirectory() as game_dir, tempfile.TemporaryDirectory() as mod_proj:
            paks = os.path.join(game_dir, "PBZero", "Content", "Paks")
            os.makedirs(paks, exist_ok=True)
            open(os.path.join(paks, "global.utoc"), "w").close()
            adapter.scaffold_pak_mod(mod_proj, "m", "M")
            open(os.path.join(mod_proj, "override", "x.ini"), "w").close()
            with mock.patch("agmod.repak.pack_override", return_value="X") as pack:
                adapter.pack_pak_mod(mod_proj, game_dir, "m")
            self.assertEqual(os.path.basename(pack.call_args[0][1]), "m_P.pak")
            self.assertEqual(pack.call_args[1].get("compression"), "gzip")

    def test_unreal_extract_repack_iostore_calls_retoc(self):
        adapter = UnrealAdapter()
        with tempfile.TemporaryDirectory() as game_dir:
            paks = os.path.join(game_dir, "PBZero", "Content", "Paks")
            os.makedirs(paks, exist_ok=True)
            with mock.patch("agmod.retoc.to_legacy", return_value="/out") as tl:
                adapter.extract_iostore(game_dir, "/out")
            tl.assert_called_once()
            with mock.patch("agmod.retoc.to_zen", return_value="/x.utoc") as tz:
                adapter.repack_iostore("/in", "/x.utoc")
            tz.assert_called_once()

    def test_unreal_list_paks_and_configs(self):
        adapter = UnrealAdapter()
        with tempfile.TemporaryDirectory() as game_dir:
            paks = os.path.join(game_dir, "PBZero", "Content", "Paks")
            os.makedirs(paks, exist_ok=True)
            open(os.path.join(paks, "global.utoc"), "w").close()
            open(os.path.join(paks, "extra.pak"), "w").close()

            configs = os.path.join(game_dir, "Saved", "Config", "Windows")
            os.makedirs(configs, exist_ok=True)
            open(os.path.join(configs, "GameUserSettings.ini"), "w").close()

            paks_list = adapter.list_paks(game_dir)
            self.assertIn("PBZero/Content/Paks/global.utoc", paks_list)
            self.assertIn("PBZero/Content/Paks/extra.pak", paks_list)

            configs_list = adapter.list_configs(game_dir)
            self.assertIn("Saved/Config/Windows/GameUserSettings.ini", configs_list)

    def test_gameprofiles_recommendations(self):
        from agmod import gameprofiles
        rec = gameprofiles.get_recommendations("X", {"id": "unreal", "variant": "ue5"})
        self.assertEqual(rec["profile_key"], "unreal-ue5")
        self.assertTrue(rec["capabilities"]["pak_override"])
        self.assertEqual(rec["capabilities"]["hook"], "limited (UE4SS 对 UE5 不稳定)")

        rec = gameprofiles.get_recommendations("X", {"id": "unity"})
        self.assertEqual(rec["profile_key"], "unity")
        self.assertTrue(rec["capabilities"]["memory_edit"])

        rec = gameprofiles.get_recommendations("黑神话悟空", {"id": "unreal", "variant": "ue5"})
        self.assertIsNotNone(rec["game_note"])

    def test_bepinex_verify_plugin(self):
        from agmod import bepinex
        with tempfile.TemporaryDirectory() as game_dir:
            plugins = os.path.join(game_dir, "BepInEx", "plugins")
            os.makedirs(plugins, exist_ok=True)
            # 无 DLL → 未安装
            res = bepinex.verify_plugin(game_dir, "mymod")
            self.assertFalse(res["installed"])
            self.assertFalse(res["effective"])

            # 有 DLL 但无日志 → installed 但未加载
            with open(os.path.join(plugins, "mymod.dll"), "w") as f:
                f.write("dll")
            res = bepinex.verify_plugin(game_dir, "mymod")
            self.assertTrue(res["installed"])
            self.assertFalse(res["log_loaded"])

            # 加日志 → 已加载生效
            with open(os.path.join(game_dir, "BepInEx", "LogOutput.log"), "w") as f:
                f.write("[Info : BepInEx] Loading [mymod 1.0.0]")
            res = bepinex.verify_plugin(game_dir, "mymod")
            self.assertTrue(res["log_loaded"])
            self.assertTrue(res["effective"])


class TestScanSessionLogic(unittest.TestCase):
    def test_session_filtering(self):
        sess = ScanSession(pid=1234, kind="int32")
        sess.candidates = [0x1000, 0x2000, 0x3000]
        sess.last_value = 100
        sess.round = 1

        # Mock memory reading in next_scan
        import agmod.memory as mem
        orig_read = mem.read_value
        try:
            # Suppose 0x1000 is now 80, 0x2000 is still 100, 0x3000 is 50
            mem.read_value = lambda h, addr, kind: {0x1000: 80, 0x2000: 100, 0x3000: 50}.get(addr, 0)
            
            # Next scan for exact 80
            survivors = sess.next_scan(handle=0, new_value=80, scan_type="exact")
            self.assertEqual(survivors, 1)
            self.assertEqual(sess.candidates, [0x1000])
            self.assertEqual(sess.round, 2)
        finally:
            mem.read_value = orig_read


class TestInspector(unittest.TestCase):
    def test_inspect_unreal(self):
        with tempfile.TemporaryDirectory() as game_dir:
            with open(os.path.join(game_dir, "Game.uproject"), "w") as f:
                f.write("{}")
            res = inspect_feature(game_dir, "gold")
            self.assertTrue(res["success"])
            self.assertEqual(res["engine"]["id"], "unreal")
            self.assertIn("ue4ss", res["recommended_strategy"]["persistent_mod"].lower())

    def test_analyze_reverse_engineering_context(self):
        from agmod.inspector import analyze_reverse_engineering_context
        with tempfile.TemporaryDirectory() as game_dir:
            # Unreal project
            with open(os.path.join(game_dir, "PBZero.uproject"), "w") as f:
                f.write("{}")

            # Test movement speed prompt
            res = analyze_reverse_engineering_context(game_dir, "移动速度翻倍并开启两倍移速")
            self.assertEqual(res["category"], "movement_speed")
            self.assertIn("UCharacterMovementComponent:SetMaxWalkSpeed", res["matched_symbols"])
            self.assertTrue(res["boundary_scope"]["safe_min"] > 0)
            self.assertTrue(len(res["exception_guards"]) > 0)
            self.assertIn("ue4ss", res["implementation_strategy"].lower())

            # Test defense / godmode prompt
            res_def = analyze_reverse_engineering_context(game_dir, "无敌不死，免疫一切伤害")
            self.assertEqual(res_def["category"], "combat_defense")
            self.assertIn("ACharacter:TakeDamage", res_def["matched_symbols"])
            self.assertIn("伤害", res_def["boundary_scope"]["param_label"])
            self.assertTrue(len(res_def["exception_guards"]) > 0)

    def test_analyze_reverse_engineering_unity_mono(self):
        from agmod.inspector import analyze_reverse_engineering_context
        with tempfile.TemporaryDirectory() as game_dir:
            managed_dir = os.path.join(game_dir, "MyGame_Data", "Managed")
            os.makedirs(managed_dir)
            open(os.path.join(managed_dir, "Assembly-CSharp.dll"), "wb").close()

            res = analyze_reverse_engineering_context(game_dir, "主角移动速度增加 100%")
            self.assertEqual(res["category"], "movement_speed")
            self.assertEqual(res["engine_id"], "unity")
            self.assertIn("Assembly-CSharp.dll", res["target_binary"])
            self.assertIn("Harmony", res["implementation_strategy"])
            guards_text = " ".join(res["exception_guards"])
            self.assertIn("FixedUpdate", guards_text)
            self.assertIn("UnityEngine.Object", guards_text)

    def test_analyze_reverse_engineering_unity_il2cpp(self):
        from agmod.inspector import analyze_reverse_engineering_context
        with tempfile.TemporaryDirectory() as game_dir:
            meta_dir = os.path.join(game_dir, "Game_Data", "il2cpp_data", "Metadata")
            os.makedirs(meta_dir)
            open(os.path.join(meta_dir, "global-metadata.dat"), "wb").close()
            open(os.path.join(game_dir, "GameAssembly.dll"), "wb").close()

            res = analyze_reverse_engineering_context(game_dir, "受到伤害减免 100% 刀枪不入")
            self.assertEqual(res["category"], "combat_defense")
            self.assertEqual(res["engine_id"], "unity")
            self.assertIn("IL2CPP", res["target_binary"])
            self.assertIn("Cpp2IL", res["implementation_strategy"])
            guards_text = " ".join(res["exception_guards"])
            self.assertIn("IL2CPP", guards_text)

    def test_analyze_reverse_engineering_terraria_dotnet(self):
        from agmod.inspector import analyze_reverse_engineering_context
        with tempfile.TemporaryDirectory() as game_dir:
            open(os.path.join(game_dir, "Terraria.exe"), "wb").close()

            res = analyze_reverse_engineering_context(game_dir, "主角移动速度加倍")
            self.assertEqual(res["category"], "movement_speed")
            self.assertEqual(res["engine_id"], "dotnet-xna")
            self.assertEqual(res["target_binary"], "Terraria.exe")
            self.assertIn("Terraria.Player.moveSpeed", res["matched_symbols"])
            guards_text = " ".join(res["exception_guards"])
            self.assertIn("严禁引入 UnityEngine", guards_text)

    def test_analyze_reverse_engineering_stardew_dotnet(self):
        from agmod.inspector import analyze_reverse_engineering_context
        with tempfile.TemporaryDirectory() as game_dir:
            open(os.path.join(game_dir, "Stardew Valley.exe"), "wb").close()

            res = analyze_reverse_engineering_context(game_dir, "主角速度翻倍跑得快")
            self.assertEqual(res["category"], "movement_speed")
            self.assertEqual(res["engine_id"], "dotnet-xna")
            self.assertEqual(res["target_binary"], "Stardew Valley.exe")
            self.assertIn("StardewValley.Farmer.speed", res["matched_symbols"])
            guards_text = " ".join(res["exception_guards"])
            self.assertIn("禁止使用 UnityEngine", guards_text)



class TestProcessDiscovery(unittest.TestCase):
    def test_find_game_executables(self):
        from agmod.process import find_game_executables, is_game_running
        with tempfile.TemporaryDirectory() as game_dir:
            open(os.path.join(game_dir, "Game.exe"), "w").close()
            open(os.path.join(game_dir, "UnityCrashHandler64.exe"), "w").close()
            open(os.path.join(game_dir, "unins000.exe"), "w").close()

            exes = find_game_executables(game_dir)
            self.assertIn("Game.exe", exes)
            self.assertNotIn("UnityCrashHandler64.exe", exes)
            self.assertNotIn("unins000.exe", exes)

            running, procs = is_game_running(game_dir)
            self.assertIsInstance(running, bool)
            self.assertIsInstance(procs, list)

    def test_is_subpath_and_status(self):
        from agmod.process import _is_subpath, check_game_status
        with tempfile.TemporaryDirectory() as game_dir:
            sub = os.path.join(game_dir, "bin", "Game.exe")
            outside = os.path.join(tempfile.gettempdir(), "other.exe")
            self.assertTrue(_is_subpath(game_dir, sub))
            self.assertFalse(_is_subpath(game_dir, outside))

            status = check_game_status(game_dir)
            self.assertIn("is_running", status)
            self.assertIn("running_processes", status)
            self.assertIn("processes", status)
            self.assertIsInstance(status["processes"], list)

    def test_find_primary_executable_path(self):
        from agmod.process import find_primary_executable_path, find_game_executables
        with tempfile.TemporaryDirectory() as game_dir:
            # 1. Root exe matching dir name
            exe_root = os.path.join(game_dir, "Game.exe")
            open(exe_root, "w").close()
            p = find_primary_executable_path(game_dir)
            self.assertEqual(p, exe_root)

        with tempfile.TemporaryDirectory() as game_dir:
            # 2. Nested Unreal Engine Win64 Shipping exe
            win64 = os.path.join(game_dir, "PBZero", "Binaries", "Win64")
            os.makedirs(win64, exist_ok=True)
            shipping_exe = os.path.join(win64, "PBZero-Win64-Shipping.exe")
            open(shipping_exe, "w").close()
            p = find_primary_executable_path(game_dir)
            self.assertEqual(p, shipping_exe)

            exes = find_game_executables(game_dir)
            self.assertEqual(exes[0], "PBZero-Win64-Shipping.exe")

        with tempfile.TemporaryDirectory() as game_dir:
            # A root launcher must not outrank the actual nested Shipping binary.
            launcher = os.path.join(game_dir, "Launcher.exe")
            open(launcher, "w").close()
            win64 = os.path.join(game_dir, "Game", "Binaries", "Win64")
            os.makedirs(win64, exist_ok=True)
            shipping_exe = os.path.join(win64, "Game-Win64-Shipping.exe")
            open(shipping_exe, "w").close()
            self.assertEqual(find_primary_executable_path(game_dir), shipping_exe)

    def test_unreal_iostore_detect(self):
        from agmod.adapters.unreal import UnrealAdapter
        adapter = UnrealAdapter()
        with tempfile.TemporaryDirectory() as game_dir:
            paks = os.path.join(game_dir, "PBZero", "Content", "Paks")
            os.makedirs(paks, exist_ok=True)
            open(os.path.join(paks, "global.utoc"), "w").close()
            open(os.path.join(paks, "global.ucas"), "w").close()
            self.assertTrue(adapter.detect(game_dir))


class TestGodotAdapter(unittest.TestCase):
    def test_godot_lifecycle(self):
        from agmod.adapters.godot import GodotAdapter
        from agmod import rollback
        from agmod.pack import package_mod, validate_package

        adapter = GodotAdapter()
        with tempfile.TemporaryDirectory() as game_dir:
            open(os.path.join(game_dir, "brotato.pck"), "w").close()
            self.assertTrue(adapter.detect(game_dir))
            det = detect_engine(game_dir)
            self.assertEqual(det["id"], "godot")

            with tempfile.TemporaryDirectory() as proj_dir:
                adapter.scaffold_mod(proj_dir, "auto-pickup", "Auto Pickup", "0.2.0", "Dev")
                self.assertTrue(os.path.isfile(os.path.join(proj_dir, "mod_main.gd")))
                self.assertTrue(os.path.isfile(os.path.join(proj_dir, "mod.json")))

                dest = adapter.install_mod(proj_dir, game_dir)
                self.assertTrue(os.path.isdir(dest))
                self.assertTrue(os.path.isfile(os.path.join(dest, "mod_main.gd")))

                # Verify install journal
                installs = rollback.list_installs(game_dir)
                self.assertEqual(len(installs), 1)
                self.assertEqual(installs[0]["mod_id"], "auto-pickup")

                # Test packaging
                zip_path = package_mod(proj_dir)
                self.assertTrue(os.path.isfile(zip_path))
                val = validate_package(zip_path)
                self.assertTrue(val["valid"])
                self.assertIn("mod_main.gd", val["payload_files"])

                # Test uninstall
                res = rollback.uninstall(game_dir, "auto-pickup")
                self.assertTrue(res["success"])
                self.assertFalse(os.path.exists(dest))
                self.assertEqual(rollback.list_installs(game_dir), [])

    def test_detection_requires_real_engine_marker(self):
        from agmod.adapters.godot import GodotAdapter
        from agmod.adapters.reengine import ReEngineAdapter
        with tempfile.TemporaryDirectory() as d:
            os.mkdir(os.path.join(d, "mods-unpacked"))
            with open(os.path.join(d, "dinput8.dll"), "wb") as f:
                f.write(b"")
            self.assertFalse(GodotAdapter().detect(d))
            self.assertFalse(ReEngineAdapter().detect(d))


class TestAntiCheatDetection(unittest.TestCase):
    def test_detect_eac_and_battleye(self):
        from agmod import safety

        with tempfile.TemporaryDirectory() as game_dir:
            # Clean game initially
            info = safety.detect_game_anticheat(game_dir)
            self.assertFalse(info["has_anticheat"])

            # EAC folder
            os.makedirs(os.path.join(game_dir, "EasyAntiCheat"))
            info = safety.detect_game_anticheat(game_dir)
            self.assertTrue(info["has_anticheat"])
            self.assertEqual(info["anticheat_system"], "EasyAntiCheat")

            # Check check_game_target blocks it
            allowed, reason = safety.check_game_target(game_dir)
            self.assertFalse(allowed)
            self.assertIn("反作弊", reason)

        with tempfile.TemporaryDirectory() as game_dir:
            # BattlEye folder
            os.makedirs(os.path.join(game_dir, "BattlEye"))
            info = safety.detect_game_anticheat(game_dir)
            self.assertTrue(info["has_anticheat"])
            self.assertEqual(info["anticheat_system"], "BattlEye")

            allowed, reason = safety.check_game_target(game_dir)
            self.assertFalse(allowed)
            self.assertIn("反作弊", reason)

    def test_deep_anticheat_component_is_detected(self):
        from agmod import safety

        with tempfile.TemporaryDirectory() as game_dir:
            component_dir = os.path.join(game_dir, "Engine", "Binaries", "ThirdParty", "EasyAntiCheat", "Win64")
            os.makedirs(component_dir)
            open(os.path.join(component_dir, "easyanticheat_x64.dll"), "wb").close()
            info = safety.detect_game_anticheat(game_dir)
            self.assertTrue(info["has_anticheat"])
            self.assertEqual(info["anticheat_system"], "EasyAntiCheat")

    def test_anticheat_process_scan_fails_closed(self):
        from agmod import safety

        with tempfile.TemporaryDirectory() as game_dir:
            broken_psutil = mock.Mock()
            broken_psutil.process_iter.side_effect = RuntimeError("process scan unavailable")
            with mock.patch.object(safety, "psutil", broken_psutil):
                allowed, reason = safety.check_game_target(game_dir)
            self.assertFalse(allowed)
            self.assertIn("安全策略拒绝继续", reason)

    def test_detect_blocked_game_names(self):
        from agmod import safety

        with tempfile.TemporaryDirectory() as base_dir:
            apex_dir = os.path.join(base_dir, "Apex Legends")
            os.makedirs(apex_dir)
            info = safety.detect_game_anticheat(apex_dir)
            self.assertTrue(info["has_anticheat"])
            self.assertIn("apex", info["anticheat_reason"].lower())

            allowed, reason = safety.check_game_target(apex_dir)
            self.assertFalse(allowed)
            self.assertIn("反作弊", reason)

    def test_singleplayer_allowlist_skips_stale_markers(self):
        from agmod import safety

        with tempfile.TemporaryDirectory() as base_dir:
            # 白名单单机游戏带 EAC 残留目录 → detect 仍报 has_anticheat，但 check_game_target 放行
            pz = os.path.join(base_dir, "Phantom Blade Zero")
            os.makedirs(os.path.join(pz, "EasyAntiCheat"))
            info = safety.detect_game_anticheat(pz)
            self.assertTrue(info["has_anticheat"])
            self.assertEqual(info["kind"], "stale_marker")
            allowed, reason = safety.check_game_target(pz)
            self.assertTrue(allowed, reason)

            # 非白名单游戏带 EAC 残留 → 拦
            other = os.path.join(base_dir, "Some Online Game")
            os.makedirs(os.path.join(other, "EasyAntiCheat"))
            allowed2, _ = safety.check_game_target(other)
            self.assertFalse(allowed2)

    def test_allowlist_game_runtime(self):
        from agmod import safety
        safety.allowlist_game("My Solo Game")
        self.assertIn("my solo game", safety.SINGLEPLAYER_ALLOWLIST)
        self.assertTrue(safety.is_allowlisted("C:/Games/My Solo Game"))

    def test_discovery_keeps_raw_marker_but_does_not_block_allowlisted_solo_game(self):
        from agmod import discovery, safety

        with tempfile.TemporaryDirectory() as base_dir:
            game_dir = os.path.join(base_dir, "Phantom Blade Zero")
            os.makedirs(os.path.join(game_dir, "EasyAntiCheat"))
            with mock.patch.object(safety, "_active_anticheat_status", return_value=([], "")):
                with mock.patch.object(discovery, "find_all_steam_libraries", return_value=[]):
                    games = discovery.scan_installed_games(extra_dirs=[game_dir])
            target = next((g for g in games if os.path.abspath(g["game_dir"]) == os.path.abspath(game_dir)), None)
            self.assertIsNotNone(target)
            self.assertTrue(target["has_anticheat"])
            self.assertFalse(target["anticheat_blocked"])


    def test_process_fallback_without_psutil(self):
        from agmod import process

        with tempfile.TemporaryDirectory() as game_dir:
            exe_path = os.path.join(game_dir, "Raft.exe")
            open(exe_path, "w").close()

            # Mock psutil as None to test native fallback
            with mock.patch.object(process, "psutil", None):
                # Mock tasklist returning Raft.exe on Windows
                mock_csv = b'"Raft.exe","48588","Console","1","1,500,888 K"\r\n'
                mock_proc = mock.MagicMock(returncode=0, stdout=mock_csv)
                with mock.patch("subprocess.run", return_value=mock_proc):
                    with mock.patch.object(process.sys, "platform", "win32"):
                        running, procs = process.is_game_running(game_dir, force_refresh=True)
                        self.assertTrue(running)
                        self.assertEqual(len(procs), 1)
                        self.assertEqual(procs[0]["pid"], 48588)
                        self.assertEqual(procs[0]["name"], "Raft.exe")
            process.clear_process_cache()


if __name__ == "__main__":
    unittest.main(verbosity=2)

