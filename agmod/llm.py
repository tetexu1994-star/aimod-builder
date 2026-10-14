"""LLM integration module for AI Mod Builder.

Zero external dependencies: uses Python standard library `urllib.request`,
`json`, and `ssl` to communicate with any OpenAI-compatible Chat Completions API
(DeepSeek, OpenAI, Qwen, Moonshot/Kimi, Zhipu, SiliconFlow, Ollama, etc.).
"""
from __future__ import annotations

import json
import logging
import os
import ssl
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger("agmod.llm")

DEFAULT_CONFIG: Dict[str, Any] = {
    "provider_name": "DeepSeek",
    "note": "官方默认",
    "website_url": "https://platform.deepseek.com",
    "api_protocol": "OpenAI Chat Completions",
    "api_endpoint": "https://api.deepseek.com",
    "api_key": "",
    "model_name": "deepseek-chat",
    "temperature": 0.7,
    "max_tokens": 2048,
}

PRESETS: Dict[str, Dict[str, Any]] = {
    "deepseek": {
        "provider_name": "DeepSeek",
        "note": "高性价比推理与代码能力",
        "website_url": "https://platform.deepseek.com",
        "api_protocol": "OpenAI Chat Completions",
        "api_endpoint": "https://api.deepseek.com",
        "model_name": "deepseek-chat",
        "temperature": 0.7,
    },
    "openai": {
        "provider_name": "OpenAI",
        "note": "GPT-4o 官方接口",
        "website_url": "https://platform.openai.com",
        "api_protocol": "OpenAI Chat Completions",
        "api_endpoint": "https://api.openai.com/v1",
        "model_name": "gpt-4o",
        "temperature": 0.7,
    },
    "qwen": {
        "provider_name": "通义千问 (DashScope)",
        "note": "阿里云通义千问兼容接口",
        "website_url": "https://dashscope.console.aliyun.com",
        "api_protocol": "OpenAI Chat Completions",
        "api_endpoint": "https://dashscope.aliyuncs.com/compatible-mode/v1",
        "model_name": "qwen-plus",
        "temperature": 0.7,
    },
    "moonshot": {
        "provider_name": "月之暗面 (Kimi)",
        "note": "长上下文对话",
        "website_url": "https://platform.moonshot.cn",
        "api_protocol": "OpenAI Chat Completions",
        "api_endpoint": "https://api.moonshot.cn/v1",
        "model_name": "moonshot-v1-8k",
        "temperature": 0.7,
    },
    "siliconflow": {
        "provider_name": "硅基流动 (SiliconFlow)",
        "note": "支持 DeepSeek-V3 / R1 等高速模型",
        "website_url": "https://cloud.siliconflow.cn",
        "api_protocol": "OpenAI Chat Completions",
        "api_endpoint": "https://api.siliconflow.cn/v1",
        "model_name": "deepseek-ai/DeepSeek-V3",
        "temperature": 0.7,
    },
    "ollama": {
        "provider_name": "Ollama (本地模型)",
        "note": "本地免联网运行 (如 Qwen2.5 / Llama3)",
        "website_url": "https://ollama.com",
        "api_protocol": "OpenAI Chat Completions",
        "api_endpoint": "http://localhost:11434/v1",
        "model_name": "qwen2.5:latest",
        "temperature": 0.7,
    },
}


def _get_config_path() -> str:
    home_dir = os.path.expanduser("~")
    target_dir = os.path.join(home_dir, ".agmod")
    try:
        os.makedirs(target_dir, exist_ok=True)
        return os.path.join(target_dir, "llm_config.json")
    except Exception:
        fallback_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "mods")
        os.makedirs(fallback_dir, exist_ok=True)
        return os.path.join(fallback_dir, ".llm_config.json")


def load_config() -> Dict[str, Any]:
    """Load persisted LLM configuration or return default."""
    config_path = _get_config_path()
    if os.path.exists(config_path):
        try:
            with open(config_path, "r", encoding="utf-8") as f:
                saved = json.load(f)
            merged = dict(DEFAULT_CONFIG)
            merged.update(saved)
            return merged
        except Exception as e:
            logger.warning("Failed to read llm_config.json: %s", e)
    return dict(DEFAULT_CONFIG)


def save_config(new_config: Dict[str, Any]) -> Dict[str, Any]:
    """Validate and persist LLM configuration."""
    current = load_config()
    for k in (
        "provider_name",
        "note",
        "website_url",
        "api_protocol",
        "api_endpoint",
        "api_key",
        "model_name",
        "temperature",
        "max_tokens",
    ):
        if k in new_config:
            current[k] = new_config[k]

    config_path = _get_config_path()
    try:
        with open(config_path, "w", encoding="utf-8") as f:
            json.dump(current, f, ensure_ascii=False, indent=2)
        try:
            os.chmod(config_path, 0o600)
        except Exception:
            pass
    except Exception as e:
        raise IOError(f"Failed to write config file: {e}")
    return current


def normalize_chat_url(endpoint: str) -> str:
    """Normalize user input base_url into full chat/completions URL."""
    url = endpoint.strip().rstrip("/")
    if url.endswith("/chat/completions"):
        return url
    if url.endswith("/v1"):
        return f"{url}/chat/completions"
    if "api.deepseek.com" in url:
        return f"{url}/chat/completions"
    return f"{url}/v1/chat/completions"


def _build_system_prompt(game_context: Optional[Dict[str, Any]] = None) -> str:
    prompt = (
        "你是一位资深的单机 PC 游戏 Mod 制作与逆向工程专家助手。"
        "你精通各种游戏引擎的 Mod 机制，包括：\n"
        "- Unity (Mono / IL2CPP，使用 BepInEx、Harmony 切面、Hook 注入)\n"
        "- Unreal Engine (UE4 / UE5，使用 UE4SS、Lua 脚本、UObject / UFunction Hook)\n"
        "- RE-Engine (生化危机/怪物猎人/DMC5，使用 REFramework、Lua 脚本)\n"
        "- Godot (GDScript Mod、pck 覆盖打包)\n"
        "- 内存读写与 Cheat Engine 逻辑（基址偏移、AOB 特征码扫描、扫描会话过滤）\n\n"
        "回答风格要求：亲切友好、言简意赅、直接切入玩家痛点。用通俗易懂的中文提供直接可行的方案与参数建议。"
    )
    if game_context:
        game_dir = game_context.get("game_dir")
        engine = game_context.get("engine")
        framework = game_context.get("framework")
        if game_dir or engine:
            prompt += (
                f"\n\n【玩家当前选定的游戏环境上下文】\n"
                f"- 游戏目录: {game_dir or '未选定'}\n"
                f"- 探测引擎: {engine or '待探测'}\n"
                f"- Mod 框架: {framework or '待适配'}\n"
                f"请结合当前游戏引擎特点为玩家量身定制回答！"
            )
    return prompt


def test_connection(config: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Test connection with the configured provider using a minimal ping request."""
    cfg = config or load_config()
    api_endpoint = cfg.get("api_endpoint", "").strip()
    api_key = cfg.get("api_key", "").strip()
    model = cfg.get("model_name", "deepseek-chat").strip() or "deepseek-chat"

    if not api_endpoint:
        return {"success": False, "error": "API 端点 (Endpoint) 不能为空"}

    url = normalize_chat_url(api_endpoint)
    headers = {
        "Content-Type": "application/json",
        "User-Agent": "AIModBuilder/1.0",
    }
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"

    payload = {
        "model": model,
        "messages": [
            {"role": "user", "content": "hi"}
        ],
        "max_tokens": 5,
    }

    start_time = time.time()
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers=headers,
        method="POST",
    )

    context = ssl.create_default_context()
    try:
        with urllib.request.urlopen(req, timeout=15, context=context) as response:
            status = response.status
            body = response.read().decode("utf-8")
            elapsed_ms = int((time.time() - start_time) * 1000)
            res_json = json.loads(body)
            choices = res_json.get("choices", [])
            reply = choices[0].get("message", {}).get("content", "") if choices else ""
            return {
                "success": True,
                "latency_ms": elapsed_ms,
                "model": model,
                "message": f"连接成功！模型响应正常 (耗时 {elapsed_ms}ms)",
                "raw_reply": reply.strip(),
            }
    except urllib.error.HTTPError as e:
        body = ""
        try:
            body = e.read().decode("utf-8")
            err_data = json.loads(body)
            msg = err_data.get("error", {}).get("message", body)
        except Exception:
            msg = body or str(e)
        return {
            "success": False,
            "status_code": e.code,
            "error": f"HTTP {e.code}: {msg}",
        }
    except urllib.error.URLError as e:
        return {
            "success": False,
            "error": f"无法连接到端点: {e.reason}",
        }
    except Exception as e:
        return {
            "success": False,
            "error": f"连接失败: {str(e)}",
        }


def chat_completion(
    messages: List[Dict[str, str]],
    game_context: Optional[Dict[str, Any]] = None,
    config: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Execute chat completion with conversation history and game context."""
    cfg = config or load_config()
    api_endpoint = cfg.get("api_endpoint", "").strip()
    api_key = cfg.get("api_key", "").strip()
    model = cfg.get("model_name", "deepseek-chat").strip() or "deepseek-chat"
    temperature = float(cfg.get("temperature", 0.7))
    max_tokens = int(cfg.get("max_tokens", 2048))

    if not api_endpoint:
        return {"success": False, "error": "请先在「模型设置」中配置 API 端点"}

    url = normalize_chat_url(api_endpoint)
    headers = {
        "Content-Type": "application/json",
        "User-Agent": "AIModBuilder/1.0",
    }
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"

    # Prepend system prompt
    system_prompt = _build_system_prompt(game_context)
    full_messages = [{"role": "system", "content": system_prompt}]
    for m in messages:
        if m.get("content"):
            full_messages.append({"role": m.get("role", "user"), "content": m.get("content")})

    payload = {
        "model": model,
        "messages": full_messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
    }

    start_time = time.time()
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers=headers,
        method="POST",
    )

    context = ssl.create_default_context()
    try:
        with urllib.request.urlopen(req, timeout=45, context=context) as response:
            body = response.read().decode("utf-8")
            elapsed_ms = int((time.time() - start_time) * 1000)
            res_json = json.loads(body)
            choices = res_json.get("choices", [])
            if not choices:
                return {"success": False, "error": "模型返回为空 (无 choices)"}
            msg_obj = choices[0].get("message", {})
            content = msg_obj.get("content", "")
            return {
                "success": True,
                "reply": content,
                "model": res_json.get("model", model),
                "latency_ms": elapsed_ms,
                "usage": res_json.get("usage", {}),
            }
    except urllib.error.HTTPError as e:
        body = ""
        try:
            body = e.read().decode("utf-8")
            err_data = json.loads(body)
            msg = err_data.get("error", {}).get("message", body)
        except Exception:
            msg = body or str(e)
        return {
            "success": False,
            "status_code": e.code,
            "error": f"HTTP {e.code}: {msg}",
        }
    except urllib.error.URLError as e:
        return {
            "success": False,
            "error": f"网络通信失败: {e.reason}",
        }
    except Exception as e:
        return {
            "success": False,
            "error": f"调用异常: {str(e)}",
        }
