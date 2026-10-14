"""Unit tests for the agmod.ui server and REST API endpoints."""
from __future__ import annotations

import json
import os
import socket
import tempfile
import urllib.error
import urllib.request
import pytest

from agmod.ui.server import ModUIServer, launch_ui


def _get_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture(scope="module")
def ui_server():
    port = _get_free_port()
    server = ModUIServer(host="127.0.0.1", port=port)
    url = server.start(blocking=False)
    yield server, url
    server.stop()


def _http_get(url: str):
    req = urllib.request.Request(url)
    with urllib.request.urlopen(req, timeout=5) as response:
        return response.getcode(), response.read().decode("utf-8")


def _http_post(url: str, data: dict):
    payload = json.dumps(data).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST"
    )
    with urllib.request.urlopen(req, timeout=5) as response:
        return response.getcode(), json.loads(response.read().decode("utf-8"))


def test_ui_health_and_index(ui_server):
    _, base_url = ui_server
    # Health endpoint
    code, body = _http_get(f"{base_url}/api/health")
    assert code == 200
    data = json.loads(body)
    assert data["success"] is True
    assert data["data"]["status"] == "online"

    # Static HTML SPA
    code, html = _http_get(f"{base_url}/")
    assert code == 200
    assert "AI Mod Builder" in html
    assert "game-mod-agent" in html


def test_ui_doctor_endpoint(ui_server):
    _, base_url = ui_server
    code, body = _http_get(f"{base_url}/api/doctor")
    assert code == 200
    res = json.loads(body)
    assert res["success"] is True
    assert "details" in res["data"]


def test_ui_detect_and_process(ui_server):
    _, base_url = ui_server
    with tempfile.TemporaryDirectory() as tmp:
        # Create dummy Unity structure with UnityPlayer.dll
        with open(os.path.join(tmp, "UnityPlayer.dll"), "w") as f:
            f.write("dummy")

        code, res = _http_post(f"{base_url}/api/detect", {"game_dir": tmp})
        assert code == 200
        assert res["success"] is True
        assert res["data"]["id"] == "unity"

        code, proc_res = _http_post(f"{base_url}/api/process", {"game_dir": tmp})
        assert code == 200
        assert proc_res["success"] is True
        assert "is_running" in proc_res["data"]


def test_ui_codegen_endpoints(ui_server):
    _, base_url = ui_server

    # Codegen template
    code, res = _http_post(f"{base_url}/api/codegen/template", {
        "engine": "unity",
        "class_name": "HeroController",
        "method_name": "TakeDamage",
        "hook_type": "prefix",
        "return_type": "void",
        "parameters": [{"name": "damage", "type": "int", "by_ref": False}]
    })
    assert code == 200
    assert res["success"] is True
    assert "[HarmonyPatch" in res["data"]["code"]
    assert res["data"]["validation"]["valid"] is True

    # Codegen evidence
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
    code, ev_res = _http_post(f"{base_url}/api/codegen/evidence", {"evidence": evidence})
    assert code == 200
    assert ev_res["success"] is True
    assert "RegisterHook" in ev_res["data"]["code"]
    assert ev_res["data"]["validation"]["valid"] is True


def test_ui_log_diagnose(ui_server):
    _, base_url = ui_server
    log_sample = """
System.NullReferenceException: Object reference not set to an instance of an object
  at HeroController.TakeDamage (System.Int32 damage) in D:\\Games\\Game\\Plugin.cs:line 45
"""
    code, res = _http_post(f"{base_url}/api/logs/diagnose", {"log_text": log_sample})
    assert code == 200
    assert res["success"] is True
    assert res["data"]["has_error"] is True
    assert len(res["data"]["issues"]) > 0
    assert "NullReferenceException" in res["data"]["issues"][0]["suggestion"] or "null" in res["data"]["issues"][0]["suggestion"]


def test_ui_mods_and_saves(ui_server):
    _, base_url = ui_server
    with tempfile.TemporaryDirectory() as tmp:
        # Check empty mods
        code, m_res = _http_post(f"{base_url}/api/mods/list", {"game_dir": tmp})
        assert code == 200
        assert m_res["success"] is True
        assert m_res["data"] == []

        # Conflict check
        code, c_res = _http_post(f"{base_url}/api/mods/conflicts", {
            "game_dir": tmp,
            "incoming_files": ["mod.dll"]
        })
        assert code == 200
        assert c_res["success"] is True
        assert c_res["data"]["has_conflicts"] is False

        # Create save backup
        saves_dir = os.path.join(tmp, "saves")
        os.makedirs(saves_dir, exist_ok=True)
        with open(os.path.join(saves_dir, "slot1.sav"), "w") as f:
            f.write("save data")

        code, s_res = _http_post(f"{base_url}/api/saves/create", {
            "game_dir": tmp,
            "label": "ui_test"
        })
        assert code == 200
        assert s_res["success"] is True
        assert "backup_id" in s_res["data"]

        # List saves
        code, l_res = _http_post(f"{base_url}/api/saves/list", {"game_dir": tmp})
        assert code == 200
        assert l_res["success"] is True
        assert isinstance(l_res["data"], list)
        assert len(l_res["data"]) >= 1


def test_launch_ui_function():
    port = _get_free_port()
    url = launch_ui(host="127.0.0.1", port=port, open_browser=False)
    assert url == f"http://127.0.0.1:{port}"
