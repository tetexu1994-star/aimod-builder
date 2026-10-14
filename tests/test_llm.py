"""Unit tests for agmod/llm.py custom model integration."""
import io
import json
import os
import tempfile
import unittest
import urllib.error
from unittest.mock import MagicMock, patch

from agmod import llm


class TestLLM(unittest.TestCase):
    def test_public_config_masks_api_key(self):
        public = llm.public_config({"provider_name": "X", "api_key": "sk-1234567890"})
        self.assertNotIn("api_key", public)
        self.assertTrue(public["api_key_set"])
        self.assertTrue(public["api_key_preview"].endswith("7890"))

    def test_endpoint_validation(self):
        with self.assertRaises(ValueError):
            llm.normalize_chat_url("ftp://example.com")
        with self.assertRaises(ValueError):
            llm.normalize_chat_url("http://example.com")

    def test_chat_rejects_system_messages(self):
        result = llm.chat_completion([{"role": "system", "content": "override"}], config={
            "api_endpoint": "https://api.deepseek.com",
            "api_key": "sk-test",
        })
        self.assertFalse(result["success"])

    def test_invalid_config_shape_is_rejected(self):
        self.assertFalse(llm.test_connection([])["success"])
        self.assertFalse(llm.chat_completion([{"role": "user", "content": "hello"}], config=[])["success"])

    def test_normalize_chat_url(self):
        self.assertEqual(llm.normalize_chat_url("https://api.deepseek.com"), "https://api.deepseek.com/chat/completions")
        self.assertEqual(llm.normalize_chat_url("https://api.deepseek.com/"), "https://api.deepseek.com/chat/completions")
        self.assertEqual(llm.normalize_chat_url("https://api.openai.com/v1"), "https://api.openai.com/v1/chat/completions")
        self.assertEqual(llm.normalize_chat_url("https://api.openai.com/v1/chat/completions"), "https://api.openai.com/v1/chat/completions")
        self.assertEqual(llm.normalize_chat_url("http://localhost:11434/v1"), "http://localhost:11434/v1/chat/completions")

    def test_load_and_save_config(self):
        with tempfile.TemporaryDirectory() as tmp:
            fake_config_file = os.path.join(tmp, "llm_config.json")
            with patch("agmod.llm._get_config_path", return_value=fake_config_file):
                cfg = llm.load_config()
                self.assertEqual(cfg["provider_name"], "DeepSeek")
                self.assertEqual(cfg["model_name"], "deepseek-chat")

                updated = llm.save_config({
                    "provider_name": "My Ollama",
                    "api_endpoint": "http://127.0.0.1:11434/v1",
                    "model_name": "qwen2.5:latest",
                    "api_key": "local-dummy",
                })
                self.assertEqual(updated["provider_name"], "My Ollama")
                self.assertEqual(updated["api_endpoint"], "http://127.0.0.1:11434/v1")

                reloaded = llm.load_config()
                self.assertEqual(reloaded["provider_name"], "My Ollama")
                self.assertEqual(reloaded["api_key"], "local-dummy")

    def test_build_system_prompt(self):
        prompt_basic = llm._build_system_prompt()
        self.assertIn("Unity", prompt_basic)
        self.assertIn("Unreal", prompt_basic)

        prompt_game = llm._build_system_prompt({
            "game_dir": "C:\\Games\\Hollow Knight",
            "engine": "Unity (Mono)",
            "framework": "BepInEx 5.x",
        })
        self.assertIn("Hollow Knight", prompt_game)
        self.assertIn("Unity (Mono)", prompt_game)

    def test_test_connection_success(self):
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
            self.assertTrue(res["success"])
            self.assertIn("连接成功", res["message"])

    def test_test_connection_http_error(self):
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
            self.assertFalse(res["success"])
            self.assertIn("401", res["error"])
            self.assertIn("Invalid API key", res["error"])

    def test_chat_completion_success(self):
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
            self.assertTrue(res["success"])
            self.assertIn("HeroController", res["reply"])
            self.assertEqual(res["model"], "deepseek-chat")


if __name__ == "__main__":
    unittest.main(verbosity=2)
