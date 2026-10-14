"""LLM integration module for AI Mod Builder.

Zero external dependencies: uses Python standard library `urllib.request`,
`json`, and `ssl` to communicate with any OpenAI-compatible Chat Completions API
(DeepSeek, OpenAI, Qwen, Moonshot/Kimi, Zhipu, SiliconFlow, Ollama, etc.).
"""
from __future__ import annotations

import json
import logging
import math
import os
import ssl
import tempfile
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
    "ccswitch": {
        "provider_name": "CC Switch (本地中转网关)",
        "note": "配合桌面的 CC Switch 本地转发，直接配置 API Key 即可连接",
        "website_url": "http://127.0.0.1:8000",
        "api_protocol": "OpenAI Chat Completions",
        "api_endpoint": "http://127.0.0.1:8000/v1",
        "model_name": "claude-3-7-sonnet",
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
    override = os.environ.get("AGMOD_LLM_CONFIG_PATH")
    if override:
        parent = os.path.dirname(os.path.abspath(override))
        os.makedirs(parent, exist_ok=True)
        return override
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
            return _validated_config(merged)
        except Exception as e:
            logger.warning("Failed to read llm_config.json: %s", e)
    return dict(DEFAULT_CONFIG)


def _validate_url(value: Any, field: str, allow_http_loopback: bool = False) -> str:
    url = str(value or "").strip()
    parsed = urllib.parse.urlsplit(url)
    if parsed.scheme not in {"https", "http"} or not parsed.hostname or parsed.username or parsed.password:
        raise ValueError(f"{field} must be an http(s) URL")
    if parsed.scheme == "http":
        if not allow_http_loopback or parsed.hostname not in {"localhost", "127.0.0.1", "::1"}:
            raise ValueError(f"{field} must use https outside localhost")
    return url


def _validated_config(config: Dict[str, Any]) -> Dict[str, Any]:
    result = dict(DEFAULT_CONFIG)
    result.update(config or {})
    result["provider_name"] = str(result.get("provider_name") or "Custom Provider")[:120]
    result["note"] = str(result.get("note") or "")[:300]
    result["website_url"] = _validate_url(result.get("website_url"), "website_url")
    result["api_endpoint"] = _validate_url(result.get("api_endpoint"), "api_endpoint", allow_http_loopback=True)
    result["api_protocol"] = str(result.get("api_protocol") or "OpenAI Chat Completions")[:120]
    result["api_key"] = str(result.get("api_key") or "")
    result["model_name"] = str(result.get("model_name") or "deepseek-chat")[:200]
    try:
        temperature = float(result.get("temperature", 0.7))
        max_tokens = int(result.get("max_tokens", 2048))
    except (TypeError, ValueError) as exc:
        raise ValueError("temperature and max_tokens must be numeric") from exc
    if not math.isfinite(temperature) or not 0 <= temperature <= 2:
        raise ValueError("temperature must be between 0 and 2")
    if not 1 <= max_tokens <= 32768:
        raise ValueError("max_tokens must be between 1 and 32768")
    result["temperature"] = temperature
    result["max_tokens"] = max_tokens
    return result


def public_config(config: Dict[str, Any]) -> Dict[str, Any]:
    """Return a browser-safe config without exposing the API key."""
    result = dict(config)
    key = str(result.pop("api_key", "") or "")
    result["api_key_set"] = bool(key)
    result["api_key_preview"] = ("*" * max(0, len(key) - 4) + key[-4:]) if key else ""
    return result


def save_config(new_config: Dict[str, Any]) -> Dict[str, Any]:
    """Validate and persist LLM configuration."""
    if not isinstance(new_config, dict):
        raise ValueError("config must be an object")
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
        if k in new_config and (k != "api_key" or str(new_config[k] or "").strip()):
            current[k] = new_config[k]

    current = _validated_config(current)
    config_path = _get_config_path()
    try:
        fd, temp_path = tempfile.mkstemp(prefix=".llm_config-", dir=os.path.dirname(config_path))
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(current, f, ensure_ascii=False, indent=2)
            f.flush()
            os.fsync(f.fileno())
        os.replace(temp_path, config_path)
        os.chmod(config_path, 0o600)
    except Exception as e:
        if 'temp_path' in locals() and os.path.exists(temp_path):
            os.unlink(temp_path)
        raise IOError(f"Failed to write config file: {e}")
    return public_config(current)


def normalize_chat_url(endpoint: str) -> str:
    """Normalize user input base_url into full chat/completions URL."""
    raw = str(endpoint or "").strip()
    parsed = urllib.parse.urlsplit(raw)
    if parsed.scheme not in {"https", "http"} or not parsed.hostname or parsed.username or parsed.password:
        raise ValueError("api_endpoint must be an http(s) URL")
    if parsed.scheme == "http" and parsed.hostname not in {"localhost", "127.0.0.1", "::1"}:
        raise ValueError("http endpoints are only allowed for localhost")
    path = parsed.path.rstrip("/")
    if not path.endswith("/chat/completions"):
        if path.endswith("/v1"):
            path += "/chat/completions"
        elif parsed.hostname == "api.deepseek.com":
            path += "/chat/completions"
        else:
            path += "/v1/chat/completions"
    return urllib.parse.urlunsplit((parsed.scheme, parsed.netloc, path, parsed.query, ""))


def _prepare_config(config: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    current = load_config()
    if config is not None and not isinstance(config, dict):
        raise ValueError("config must be an object")
    if config:
        current.update(config)
        if not str(current.get("api_key") or "").strip():
            current["api_key"] = load_config().get("api_key", "")
    return _validated_config(current)


def _validate_messages(messages: Any) -> List[Dict[str, str]]:
    if not isinstance(messages, list) or not 1 <= len(messages) <= 100:
        raise ValueError("messages must be a non-empty list of at most 100 items")
    normalized = []
    for item in messages:
        if not isinstance(item, dict) or item.get("role") not in {"user", "assistant"}:
            raise ValueError("message roles must be user or assistant")
        content = item.get("content")
        if not isinstance(content, str) or not content.strip() or len(content) > 32000:
            raise ValueError("message content must be a non-empty string up to 32000 characters")
        normalized.append({"role": item["role"], "content": content})
    return normalized


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
    try:
        cfg = _prepare_config(config)
    except ValueError as e:
        return {"success": False, "error": str(e)}
    api_endpoint = cfg.get("api_endpoint", "").strip()
    api_key = cfg.get("api_key", "").strip()
    model = cfg.get("model_name", "deepseek-chat").strip() or "deepseek-chat"

    if not api_endpoint:
        return {"success": False, "error": "API 端点 (Endpoint) 不能为空"}

    try:
        url = normalize_chat_url(api_endpoint)
    except ValueError as e:
        return {"success": False, "error": str(e)}
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
    try:
        cfg = _prepare_config(config)
        messages = _validate_messages(messages)
        if game_context is not None and not isinstance(game_context, dict):
            raise ValueError("game_context must be an object")
    except ValueError as e:
        return {"success": False, "error": str(e)}
    api_endpoint = cfg.get("api_endpoint", "").strip()
    api_key = cfg.get("api_key", "").strip()
    model = cfg.get("model_name", "deepseek-chat").strip() or "deepseek-chat"
    temperature = float(cfg.get("temperature", 0.7))
    max_tokens = int(cfg.get("max_tokens", 2048))

    if not api_endpoint:
        return {"success": False, "error": "请先在「模型设置」中配置 API 端点"}

    try:
        url = normalize_chat_url(api_endpoint)
    except ValueError as e:
        return {"success": False, "error": str(e)}
    headers = {
        "Content-Type": "application/json",
        "User-Agent": "AIModBuilder/1.0",
    }
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"

    # Prepend system prompt
    system_prompt = _build_system_prompt(game_context)
    full_messages = [{"role": "system", "content": system_prompt}]
    full_messages.extend(messages)

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
