"""Unit tests for agmod/llm.py custom model integration."""
import io
import json
import os
import urllib.error
from unittest.mock import MagicMock, patch

import pytest
from agmod import llm


def test_normalize_chat_url():
    assert llm.normalize_chat_url("https://api.deepseek.com") == "https://api.deepseek.com/chat/completions"
    assert llm.normalize_chat_url("https://api.deepseek.com/") == "https://api.deepseek.com/chat/completions"
    assert llm.normalize_chat_url("https://api.openai.com/v1") == "https://api.openai.com/v1/chat/completions"
    assert llm.normalize_chat_url("https://api.openai.com/v1/chat/completions") == "https://api.openai.com/v1/chat/completions"
    assert llm.normalize_chat_url("http://localhost:11434/v1") == "http://localhost:11434/v1/chat/completions"


def test_load_and_save_config(tmp_path):
    fake_config_file = str(tmp_path / "llm_config.json")
    with patch("agmod.llm._get_config_path", return_value=fake_config_file):
        cfg = llm.load_config()
        assert cfg["provider_name"] == "DeepSeek"
        assert cfg["model_name"] == "deepseek-chat"

        updated = llm.save_config({
            "provider_name": "My Ollama",
            "api_endpoint": "http://127.0.0.1:11434/v1",
            "model_name": "qwen2.5:latest",
            "api_key": "local-dummy",
        })
        assert updated["provider_name"] == "My Ollama"
        assert updated["api_endpoint"] == "http://127.0.0.1:11434/v1"

        reloaded = llm.load_config()
        assert reloaded["provider_name"] == "My Ollama"
        assert reloaded["api_key"] == "local-dummy"


def test_build_system_prompt():
    prompt_basic = llm._build_system_prompt()
    assert "Unity" in prompt_basic
    assert "Unreal" in prompt_basic

    prompt_game = llm._build_system_prompt({
        "game_dir": "C:\\Games\\Hollow Knight",
        "engine": "Unity (Mono)",
        "framework": "BepInEx 5.x",
    })
    assert "Hollow Knight" in prompt_game
    assert "Unity (Mono)" in prompt_game


def test_test_connection_success():
    mock_resp = MagicMock()
    mock_resp.status = 200
    mock_resp.read.return_value = json.dumps({
        "choices": [{"message": {"content": "pong"}}]
    }).encode("utf-8")
    mock_resp.__enter__.return_value = mock_resp

    with patch("urllib.request.urlopen", return_value=mock_resp):
        res = llm.test_connection({
            "api_endpoint": "https://api.deepseek.com",
            "api_key": "sk-123456",
            "model_name": "deepseek-chat",
        })
        assert res["success"] is True
        assert "连接成功" in res["message"]


def test_test_connection_http_error():
    err = urllib.error.HTTPError(
        url="https://api.deepseek.com/chat/completions",
        code=401,
        msg="Unauthorized",
        hdrs={},
        fp=io.BytesIO(b'{"error": {"message": "Invalid API key"}}'),
    )
    with patch("urllib.request.urlopen", side_effect=err):
        res = llm.test_connection({
            "api_endpoint": "https://api.deepseek.com",
            "api_key": "wrong-key",
            "model_name": "deepseek-chat",
        })
        assert res["success"] is False
        assert "401" in res["error"]
        assert "Invalid API key" in res["error"]


def test_chat_completion_success():
    mock_resp = MagicMock()
    mock_resp.status = 200
    mock_resp.read.return_value = json.dumps({
        "model": "deepseek-chat",
        "choices": [{"message": {"role": "assistant", "content": "可以通过修改 HeroController 类的 MOVE_SPEED 字段实现加速。"}}],
        "usage": {"total_tokens": 42},
    }).encode("utf-8")
    mock_resp.__enter__.return_value = mock_resp

    with patch("urllib.request.urlopen", return_value=mock_resp):
        res = llm.chat_completion(
            messages=[{"role": "user", "content": "怎么改空洞骑士移速？"}],
            game_context={"game_dir": "C:\\HollowKnight", "engine": "Unity"},
            config={"api_endpoint": "https://api.deepseek.com", "api_key": "sk-test", "model_name": "deepseek-chat"},
        )
        assert res["success"] is True
        assert "HeroController" in res["reply"]
        assert res["model"] == "deepseek-chat"
