"""Unit tests for the agmod.ui server and REST API endpoints."""
from __future__ import annotations

import json
import os
import socket
import tempfile
import unittest
import urllib.error
import urllib.request
from unittest.mock import patch
from pathlib import Path

from agmod.ui.server import INDEX_HTML_PATH, ModUIServer, launch_ui


def _get_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


_no_proxy_opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))


def _http_get(url: str):
    req = urllib.request.Request(url)
    try:
        with _no_proxy_opener.open(req, timeout=5) as response:
            return response.getcode(), response.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read().decode("utf-8")


def _http_post(url: str, data: dict):
    payload = json.dumps(data).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with _no_proxy_opener.open(req, timeout=5) as response:
            return response.getcode(), json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        try:
            return exc.code, json.loads(exc.read().decode("utf-8"))
        except Exception:
            return exc.code, {}


class TestUIServer(unittest.TestCase):
    def test_ui_interaction_contract(self):
        html = Path(INDEX_HTML_PATH).read_text(encoding="utf-8")
        self.assertIn("button.btn:hover:not(:disabled)", html)
        self.assertIn("button.btn:disabled", html)
        self.assertIn('class="step-item', html)
        self.assertNotIn('<div class="step-item', html)
        self.assertNotIn("onclick=\"pinMod('${", html)
        self.assertIn("function escapeHtml(value)", html)
        self.assertIn("function isAnticheatBlocked(game)", html)

    @classmethod
    def setUpClass(cls):
        cls.port = _get_free_port()
        cls.server = ModUIServer(host="127.0.0.1", port=cls.port)
        cls.base_url = cls.server.start(blocking=False)

    @classmethod
    def tearDownClass(cls):
        cls.server.stop()

    def test_health_and_index(self):
        code, body = _http_get(f"{self.base_url}/api/health")
        self.assertEqual(code, 200)
        data = json.loads(body)
        self.assertTrue(data["success"])
        self.assertEqual(data["data"]["status"], "online")

        code, html = _http_get(f"{self.base_url}/")
        self.assertEqual(code, 200)
        self.assertIn("AI Mod Builder", html)
        self.assertIn("制作新 Mod", html)

    def test_doctor_endpoint(self):
        code, body = _http_get(f"{self.base_url}/api/doctor")
        self.assertEqual(code, 200)
        res = json.loads(body)
        self.assertTrue(res["success"])
        self.assertIn("details", res["data"])

    def test_detect_and_process(self):
        with tempfile.TemporaryDirectory() as tmp:
            with open(os.path.join(tmp, "UnityPlayer.dll"), "w") as f:
                f.write("dummy")

            code, res = _http_post(f"{self.base_url}/api/detect", {"game_dir": tmp})
            self.assertEqual(code, 200)
            self.assertTrue(res["success"])
            self.assertEqual(res["data"]["id"], "unity")

            code, proc_res = _http_post(f"{self.base_url}/api/process", {"game_dir": tmp})
            self.assertEqual(code, 200)
            self.assertTrue(proc_res["success"])
            self.assertIn("is_running", proc_res["data"])

    def test_codegen_endpoints(self):
        code, res = _http_post(f"{self.base_url}/api/codegen/template", {
            "engine": "unity",
            "class_name": "HeroController",
            "method_name": "TakeDamage",
            "hook_type": "prefix",
            "return_type": "void",
            "parameters": [{"name": "damage", "type": "int", "by_ref": False}],
        })
        self.assertEqual(code, 200)
        self.assertTrue(res["success"])
        self.assertIn("[HarmonyPatch", res["data"]["code"])
        self.assertTrue(res["data"]["validation"]["valid"])

        evidence = {
            "engine": "unreal",
            "target_symbol": "APawn.AddMovementInput",
            "class_name": "APawn",
            "method_name": "AddMovementInput",
            "hook_type": "prefix",
            "provenance": "test",
            "confidence": 0.95,
            "parameters": [{"name": "WorldDirection", "type": "FVector"}],
        }
        code, ev_res = _http_post(f"{self.base_url}/api/codegen/evidence", {"evidence": evidence})
        self.assertEqual(code, 200)
        self.assertTrue(ev_res["success"])
        self.assertIn("RegisterHook", ev_res["data"]["code"])
        self.assertTrue(ev_res["data"]["validation"]["valid"])

    def test_log_diagnose(self):
        log_sample = """
System.NullReferenceException: Object reference not set to an instance of an object
  at HeroController.TakeDamage (System.Int32 damage) in D:\\Games\\Game\\Plugin.cs:line 45
"""
        code, res = _http_post(f"{self.base_url}/api/logs/diagnose", {"log_text": log_sample})
        self.assertEqual(code, 200)
        self.assertTrue(res["success"])
        self.assertTrue(res["data"]["has_error"])
        self.assertGreater(len(res["data"]["issues"]), 0)
        self.assertTrue(
            "NullReferenceException" in res["data"]["issues"][0]["suggestion"]
            or "null" in res["data"]["issues"][0]["suggestion"]
        )

    def test_mods_and_saves(self):
        with tempfile.TemporaryDirectory() as tmp:
            code, m_res = _http_post(f"{self.base_url}/api/mods/list", {"game_dir": tmp})
            self.assertEqual(code, 200)
            self.assertTrue(m_res["success"])
            self.assertEqual(m_res["data"], [])

            code, c_res = _http_post(f"{self.base_url}/api/mods/conflicts", {
                "game_dir": tmp,
                "incoming_files": ["mod.dll"],
            })
            self.assertEqual(code, 200)
            self.assertTrue(c_res["success"])
            self.assertFalse(c_res["data"]["has_conflicts"])

            saves_dir = os.path.join(tmp, "saves")
            os.makedirs(saves_dir, exist_ok=True)
            with open(os.path.join(saves_dir, "slot1.sav"), "w") as f:
                f.write("save data")

            code, s_res = _http_post(f"{self.base_url}/api/saves/create", {
                "game_dir": tmp,
                "label": "ui_test",
            })
            self.assertEqual(code, 200)
            self.assertTrue(s_res["success"])
            self.assertIn("backup_id", s_res["data"])

            code, l_res = _http_post(f"{self.base_url}/api/saves/list", {"game_dir": tmp})
            self.assertEqual(code, 200)
            self.assertTrue(l_res["success"])
            self.assertIsInstance(l_res["data"], list)
            self.assertGreaterEqual(len(l_res["data"]), 1)

    def test_plan_endpoint(self):
        with tempfile.TemporaryDirectory() as tmp:
            with open(os.path.join(tmp, "UnityPlayer.dll"), "w") as f:
                f.write("dummy")
            code, res = _http_post(f"{self.base_url}/api/plan", {
                "game_dir": tmp,
                "request": "add 99999 gold",
                "project_dir": os.path.join(tmp, "proj"),
            })
            self.assertEqual(code, 200)
            self.assertTrue(res["success"])
            self.assertEqual(res["data"]["engine"]["id"], "unity")

    def test_install_preview_endpoint(self):
        with tempfile.TemporaryDirectory() as tmp_game, tempfile.TemporaryDirectory() as tmp_source:
            Path(tmp_game, "UnityPlayer.dll").write_text("dummy", encoding="utf-8")
            core = Path(tmp_game, "BepInEx", "core")
            core.mkdir(parents=True)
            (core / "BepInEx.dll").write_bytes(b"")
            Path(tmp_game, "BepInEx", "version.txt").write_text("5.4.23.0", encoding="utf-8")
            source = Path(tmp_source, "Demo.dll")
            source.write_bytes(b"demo")
            code, res = _http_post(f"{self.base_url}/api/install/preview", {
                "game_dir": tmp_game,
                "mod_id": "demo-mod",
                "engine_id": "unity",
                "files": [{"source": str(source), "target": "BepInEx/plugins/Demo.dll"}],
            })
            self.assertEqual(code, 200)
            self.assertTrue(res["success"])
            self.assertTrue(res["data"]["ready"])
            self.assertEqual(res["data"]["summary"]["add"], 1)

    def test_logs_read_endpoint(self):
        with tempfile.TemporaryDirectory() as tmp:
            log_dir = os.path.join(tmp, "BepInEx")
            os.makedirs(log_dir, exist_ok=True)
            with open(os.path.join(log_dir, "LogOutput.log"), "w") as f:
                f.write("[Info] hello\n")
            code, res = _http_post(f"{self.base_url}/api/logs/read", {"game_dir": tmp})
            self.assertEqual(code, 200)
            self.assertTrue(res["success"])
            self.assertTrue(res["data"]["found"])

    def test_cors_safe_origin(self):
        req = urllib.request.Request(f"{self.base_url}/api/health", headers={"Origin": "http://localhost:8765"})
        with _no_proxy_opener.open(req, timeout=5) as response:
            self.assertEqual(response.getcode(), 200)
            self.assertEqual(response.headers.get("Access-Control-Allow-Origin"), "http://localhost:8765")

    def test_cors_reject_unauthorized_origin(self):
        req = urllib.request.Request(f"{self.base_url}/api/health", headers={"Origin": "https://malicious-site.com"})
        try:
            with _no_proxy_opener.open(req, timeout=5) as response:
                self.assertEqual(response.getcode(), 403)
        except urllib.error.HTTPError as e:
            self.assertEqual(e.code, 403)

    def test_llm_endpoints(self):
        with tempfile.TemporaryDirectory() as tmp:
            config_path = os.path.join(tmp, "llm_config.json")
            with patch.dict(os.environ, {"AGMOD_LLM_CONFIG_PATH": config_path}):
                code, body = _http_get(f"{self.base_url}/api/llm/config")
                self.assertEqual(code, 200)
                res = json.loads(body)
                self.assertTrue(res["success"])
                self.assertIn("config", res["data"])
                self.assertNotIn("api_key", res["data"]["config"])
                self.assertIn("presets", res["data"])

                code, save_res = _http_post(f"{self.base_url}/api/llm/config", {
                    "provider_name": "TestProvider",
                    "api_endpoint": "https://api.deepseek.com",
                    "model_name": "deepseek-chat",
                })
                self.assertEqual(code, 200)
                self.assertTrue(save_res["success"])
                self.assertEqual(save_res["data"]["provider_name"], "TestProvider")
                self.assertNotIn("api_key", save_res["data"])

    def test_games_and_mod_copilot(self):
        # 1. Test /api/games/scan
        code, body = _http_get(f"{self.base_url}/api/games/scan")
        self.assertEqual(code, 200)
        res = json.loads(body)
        self.assertTrue(res["success"])
        self.assertIsInstance(res["data"], list)

        # 2. Test /api/mod/interact
        with tempfile.TemporaryDirectory() as tmp_game:
            # create mock game exe
            with open(os.path.join(tmp_game, "game.exe"), "w") as f:
                f.write("mock")

            code, mod_res = _http_post(f"{self.base_url}/api/mod/interact", {
                "game_dir": tmp_game,
                "prompt": "角色移动速度增加 100%"
            })
            self.assertEqual(code, 200)
            self.assertTrue(mod_res["success"])
            self.assertIn("reply", mod_res["data"])
            self.assertIsNotNone(mod_res["data"]["action"])
            self.assertEqual(mod_res["data"]["action"]["mod_id"], "speed_boost")

            # 3. Test /api/mod/pin
            code, pin_res = _http_post(f"{self.base_url}/api/mod/pin", {
                "game_dir": tmp_game,
                "mod_id": "speed_boost",
                "mod_name": "急速奔跑",
                "summary": "角色移动速度提升 100%",
                "params": {"multiplier": 2.0}
            })
            self.assertEqual(code, 200)
            self.assertTrue(pin_res["success"])
            self.assertTrue(os.path.exists(pin_res["data"]["path"]))

    def test_anticheat_api_blocking(self):
        with tempfile.TemporaryDirectory() as protected_game:
            os.makedirs(os.path.join(protected_game, "EasyAntiCheat"))
            # 1. /api/mod/interact must return 403 Forbidden
            code, res = _http_post(f"{self.base_url}/api/mod/interact", {
                "game_dir": protected_game,
                "prompt": "无敌"
            })
            self.assertEqual(code, 403)
            self.assertFalse(res["success"])
            self.assertTrue(res.get("blocked_by_anticheat"))

            # 2. /api/mod/pin must return 403 Forbidden
            code, pin_res = _http_post(f"{self.base_url}/api/mod/pin", {
                "game_dir": protected_game,
                "mod_id": "cheat_mod",
                "mod_name": "作弊模组",
                "summary": "测试",
                "params": {}
            })
            self.assertEqual(code, 403)
            self.assertFalse(pin_res["success"])

    def test_ue5_iostore_uses_pak_capability_boundary(self):
        with tempfile.TemporaryDirectory() as game:
            Path(game, "Game.uproject").write_text("{}", encoding="utf-8")
            paks = Path(game, "Game", "Content", "Paks")
            paks.mkdir(parents=True)
            (paks / "global.utoc").write_bytes(b"")
            code, res = _http_post(f"{self.base_url}/api/mod/interact", {"game_dir": game, "prompt": "增加金币"})
            self.assertEqual(code, 200)
            self.assertIsNone(res["data"]["action"])
            self.assertEqual(res["data"]["capability_boundary"], "ue5-iostore-pak-only")

            code, pin_res = _http_post(f"{self.base_url}/api/mod/pin", {
                "game_dir": game,
                "mod_id": "bad-hook",
                "mod_name": "Bad Hook",
                "summary": "test",
                "params": {},
                "hook_target": "ACharacter:TakeDamage",
            })
            self.assertEqual(code, 409)
            self.assertFalse(pin_res["success"])

    def test_rea_overview_and_require_api_key(self):
        with tempfile.TemporaryDirectory() as game:
            # Create dummy Unity game structure
            managed = os.path.join(game, "Raft_Data", "Managed")
            os.makedirs(managed, exist_ok=True)
            open(os.path.join(managed, "Assembly-CSharp.dll"), "w").close()
            open(os.path.join(game, "Raft.exe"), "w").close()

            # 1. /api/rea/overview returns rich architecture info
            code, res = _http_post(f"{self.base_url}/api/rea/overview", {"game_dir": game})
            self.assertEqual(code, 200)
            self.assertTrue(res["success"])
            self.assertEqual(res["data"]["engine_id"], "unity")
            self.assertEqual(res["data"]["primary_exe"], "Raft.exe")
            self.assertIn("discovered_symbols", res["data"])
            self.assertIn("safety_guards", res["data"])

            # 2. When LLM is not configured and user asks freeform question "你这个调了啥？"
            with patch("agmod.llm.load_config", return_value={"api_key": "", "api_endpoint": "https://api.openai.com/v1"}):
                code, interact_res = _http_post(f"{self.base_url}/api/mod/interact", {
                    "game_dir": game,
                    "prompt": "你这个调了啥？"
                })
                self.assertEqual(code, 200)
                self.assertTrue(interact_res["success"])
                self.assertFalse(interact_res["data"]["has_llm"])
                self.assertTrue(interact_res["data"]["require_api_key"])
                self.assertIsNone(interact_res["data"]["action"])
                self.assertIn("尚未配置大模型 API Key", interact_res["data"]["reply"])

    def test_mod_interact_auto_deploys_and_tunes_params(self):
        with tempfile.TemporaryDirectory() as game:
            managed = os.path.join(game, "Raft_Data", "Managed")
            os.makedirs(managed, exist_ok=True)
            open(os.path.join(managed, "Assembly-CSharp.dll"), "w").close()
            open(os.path.join(game, "Raft.exe"), "w").close()

            # 1. Mod interact auto deploys files to game dir
            code, res = _http_post(f"{self.base_url}/api/mod/interact", {
                "game_dir": game,
                "prompt": "角色移动速度增加 100%"
            })
            self.assertEqual(code, 200)
            self.assertTrue(res["success"])
            action = res["data"]["action"]
            self.assertIsNotNone(action)
            self.assertEqual(action["mod_id"], "speed_boost")
            self.assertTrue(action.get("auto_deployed"))
            # Verify file was written to disk
            plugin_dir = os.path.join(game, "BepInEx", "plugins", "speed_boost")
            self.assertTrue(os.path.exists(plugin_dir))
            self.assertTrue(os.path.exists(os.path.join(plugin_dir, "mod.json")))

            # 2. Test /api/mod/tune updates param in real-time
            code, tune_res = _http_post(f"{self.base_url}/api/mod/tune", {
                "game_dir": game,
                "mod_id": "speed_boost",
                "param_id": "multiplier",
                "value": 3.5,
                "hook_target": "PlayerController.Movement"
            })
            self.assertEqual(code, 200)
            self.assertTrue(tune_res["success"])
            self.assertEqual(tune_res["data"]["value"], 3.5)
            self.assertTrue(tune_res["data"]["file_synced"])

            # Verify on-disk file was updated
            with open(os.path.join(plugin_dir, "mod.json"), "r", encoding="utf-8") as f:
                saved_manifest = json.load(f)
            self.assertEqual(saved_manifest["params"]["multiplier"], 3.5)

    def test_manual_dragging_inquiry_clarification(self):
        with tempfile.TemporaryDirectory() as game:
            managed = os.path.join(game, "Raft_Data", "Managed")
            os.makedirs(managed, exist_ok=True)
            open(os.path.join(managed, "Assembly-CSharp.dll"), "w").close()
            open(os.path.join(game, "Raft.exe"), "w").close()

            code, res = _http_post(f"{self.base_url}/api/mod/interact", {
                "game_dir": game,
                "prompt": "需要我手动放进去？"
            })
            self.assertEqual(code, 200)
            self.assertTrue(res["success"])
            self.assertIn("完全不需要手动放进去", res["data"]["reply"])
            self.assertIn("全自动", res["data"]["reply"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
