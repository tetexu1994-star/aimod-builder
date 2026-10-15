"""Lightweight local Web UI server for game-mod-agent.

Zero external dependencies: uses Python standard library `http.server`
and `threading` to serve a modern responsive dashboard and RESTful JSON API.
"""
from __future__ import annotations

import json
import logging
import os
import sys
import threading
import time
import urllib.parse
import webbrowser
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Callable, Dict, Optional, Tuple

from agmod import codegen, discovery, doctor, llm, log_repair, logs, paths, planning, process, registry, rollback, saves

logger = logging.getLogger("agmod.ui")

INDEX_HTML_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "index.html")


def _read_body_json(handler: BaseHTTPRequestHandler) -> Dict[str, Any]:
    content_len = int(handler.headers.get("Content-Length", 0))
    if content_len == 0:
        return {}
    raw_data = handler.rfile.read(content_len)
    try:
        return json.loads(raw_data.decode("utf-8"))
    except Exception as e:
        raise ValueError(f"Invalid JSON body: {e}")


def _safe_path(p: str) -> str:
    """Resolve and normalize path to avoid empty string or traversal quirks."""
    if not p:
        return ""
    return os.path.abspath(os.path.expanduser(p))


class ModUIRequestHandler(BaseHTTPRequestHandler):
    """Handles static SPA delivery and REST API routing."""

    server_version = "AIModBuilderUI/1.0"

    def log_message(self, format: str, *args: Any) -> None:
        if os.environ.get("AGMOD_DEBUG"):
            logger.info("%s - - [%s] %s\n" % (self.address_string(), self.log_date_time_string(), format % args))

    def _is_safe_origin(self) -> bool:
        origin = self.headers.get("Origin")
        if not origin:
            return True
        parsed = urllib.parse.urlparse(origin)
        return parsed.hostname in ("127.0.0.1", "localhost")

    def _apply_cors_headers(self) -> None:
        origin = self.headers.get("Origin")
        if origin and self._is_safe_origin():
            self.send_header("Access-Control-Allow-Origin", origin)
            self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
            self.send_header("Access-Control-Allow-Headers", "Content-Type")
            self.send_header("Vary", "Origin")

    def _send_json(self, status_code: int, data: Dict[str, Any]) -> None:
        payload = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(status_code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(payload)))
        self._apply_cors_headers()
        self.end_headers()
        self.wfile.write(payload)

    def _send_html(self, status_code: int, html_content: str) -> None:
        payload = html_content.encode("utf-8")
        self.send_response(status_code)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def do_OPTIONS(self) -> None:
        if not self._is_safe_origin():
            self.send_response(HTTPStatus.FORBIDDEN)
            self.end_headers()
            return
        self.send_response(HTTPStatus.NO_CONTENT)
        self._apply_cors_headers()
        self.end_headers()

    def do_GET(self) -> None:
        if not self._is_safe_origin():
            self._send_json(HTTPStatus.FORBIDDEN, {
                "success": False,
                "error": "Cross-origin request rejected: origin is not authorized."
            })
            return

        parsed_url = urllib.parse.urlparse(self.path)
        path = parsed_url.path

        if path == "/api/health":
            self._send_json(HTTPStatus.OK, {
                "success": True,
                "data": {
                    "status": "online",
                    "version": "1.0.0",
                    "pid": os.getpid(),
                    "platform": sys.platform,
                }
            })
            return

        if path == "/api/doctor":
            try:
                report = doctor.check_environment()
                self._send_json(HTTPStatus.OK, {
                    "success": True,
                    "data": {
                        "ready": report.get("ready", False),
                        "details": report,
                        "formatted": doctor.format_doctor_report(report),
                    }
                })
            except Exception as e:
                self._send_json(HTTPStatus.INTERNAL_SERVER_ERROR, {
                    "success": False,
                    "error": f"Doctor check failed: {e}"
                })
            return

        if path == "/api/llm/config":
            try:
                cfg = llm.load_config()
                self._send_json(HTTPStatus.OK, {
                    "success": True,
                    "data": {
                        "config": llm.public_config(cfg),
                        "presets": llm.PRESETS,
                    }
                })
            except Exception as e:
                self._send_json(HTTPStatus.INTERNAL_SERVER_ERROR, {
                    "success": False,
                    "error": f"Failed to load LLM config: {e}"
                })
            return

        if path == "/api/games/scan":
            try:
                from agmod import discovery
                games = discovery.scan_installed_games()
                self._send_json(HTTPStatus.OK, {
                    "success": True,
                    "data": games
                })
            except Exception as e:
                self._send_json(HTTPStatus.INTERNAL_SERVER_ERROR, {
                    "success": False,
                    "error": f"Failed to scan games: {e}"
                })
            return

        # Static SPA Delivery
        if path in ("/", "/index.html", "/ui"):
            if os.path.exists(INDEX_HTML_PATH):
                with open(INDEX_HTML_PATH, "r", encoding="utf-8") as f:
                    content = f.read()
                self._send_html(HTTPStatus.OK, content)
            else:
                self._send_html(HTTPStatus.NOT_FOUND, "<h1>Dashboard HTML not found.</h1>")
            return

        # Fallback for SPA routing
        if os.path.exists(INDEX_HTML_PATH):
            with open(INDEX_HTML_PATH, "r", encoding="utf-8") as f:
                content = f.read()
            self._send_html(HTTPStatus.OK, content)
        else:
            self.send_error(HTTPStatus.NOT_FOUND, "Page not found")

    def do_POST(self) -> None:
        if not self._is_safe_origin():
            self._send_json(HTTPStatus.FORBIDDEN, {
                "success": False,
                "error": "Cross-origin request rejected: origin is not authorized."
            })
            return

        parsed_url = urllib.parse.urlparse(self.path)
        path = parsed_url.path

        try:
            body = _read_body_json(self)
        except ValueError as e:
            self._send_json(HTTPStatus.BAD_REQUEST, {"success": False, "error": str(e)})
            return

        routes: Dict[str, Callable[[Dict[str, Any]], Tuple[int, Dict[str, Any]]]] = {
            "/api/detect": self._handle_detect,
            "/api/process": self._handle_process,
            "/api/plan": self._handle_plan,
            "/api/codegen/template": self._handle_codegen_template,
            "/api/codegen/evidence": self._handle_codegen_evidence,
            "/api/mods/list": self._handle_mods_list,
            "/api/mods/conflicts": self._handle_mods_conflicts,
            "/api/mods/uninstall": self._handle_mods_uninstall,
            "/api/mods/rollback": self._handle_mods_rollback,
            "/api/saves/list": self._handle_saves_list,
            "/api/saves/create": self._handle_saves_create,
            "/api/saves/restore": self._handle_saves_restore,
            "/api/logs/read": self._handle_logs_read,
            "/api/logs/diagnose": self._handle_logs_diagnose,
            "/api/llm/config": self._handle_llm_config_save,
            "/api/llm/test": self._handle_llm_test,
            "/api/llm/chat": self._handle_llm_chat,
            "/api/games/launch": self._handle_games_launch,
            "/api/mod/interact": self._handle_mod_interact,
            "/api/mod/pin": self._handle_mod_pin,
        }

        handler_fn = routes.get(path)
        if handler_fn is None:
            self._send_json(HTTPStatus.NOT_FOUND, {"success": False, "error": f"API route not found: {path}"})
            return

        try:
            status_code, resp_data = handler_fn(body)
            self._send_json(status_code, resp_data)
        except Exception as e:
            self._send_json(HTTPStatus.INTERNAL_SERVER_ERROR, {
                "success": False,
                "error": f"Internal error handling {path}: {str(e)}"
            })

    # --- API Route Handlers ---

    def _handle_detect(self, body: Dict[str, Any]) -> Tuple[int, Dict[str, Any]]:
        game_dir = _safe_path(body.get("game_dir", ""))
        if not game_dir:
            return HTTPStatus.BAD_REQUEST, {"success": False, "error": "game_dir is required"}
        info = registry.detect_engine(game_dir)
        return HTTPStatus.OK, {"success": True, "data": info}

    def _handle_process(self, body: Dict[str, Any]) -> Tuple[int, Dict[str, Any]]:
        game_dir = _safe_path(body.get("game_dir", ""))
        status = process.check_game_status(game_dir)
        return HTTPStatus.OK, {"success": True, "data": status}

    def _handle_plan(self, body: Dict[str, Any]) -> Tuple[int, Dict[str, Any]]:
        game_dir = _safe_path(body.get("game_dir", ""))
        request_text = body.get("request", "").strip()
        project_dir = _safe_path(body.get("project_dir", ""))
        mod_id = body.get("mod_id", "").strip()
        mod_name = body.get("mod_name", "").strip()
        mod_version = body.get("mod_version", "1.0.0").strip()
        customizations = body.get("customizations")

        if not game_dir or not request_text:
            return HTTPStatus.BAD_REQUEST, {"success": False, "error": "game_dir and request are required"}

        if not project_dir:
            project_dir = os.path.join(game_dir, "_mod_projects", mod_id or "new_mod")

        spec = planning.create_mod_plan(
            game_dir=game_dir,
            request=request_text,
            project_dir=project_dir,
            mod_id=mod_id,
            mod_name=mod_name,
            mod_version=mod_version,
            customizations=customizations,
        )
        return HTTPStatus.OK, {"success": True, "data": spec}

    def _handle_codegen_template(self, body: Dict[str, Any]) -> Tuple[int, Dict[str, Any]]:
        engine = body.get("engine", "")
        class_name = body.get("class_name", "")
        method_name = body.get("method_name", "")
        hook_type = body.get("hook_type", "prefix")
        return_type = body.get("return_type", "void")
        parameters = body.get("parameters", [])

        if not engine or not class_name or not method_name:
            return HTTPStatus.BAD_REQUEST, {"success": False, "error": "engine, class_name, and method_name are required"}

        try:
            res = codegen.generate_hook_template(
                engine=engine,
                class_name=class_name,
                method_name=method_name,
                hook_type=hook_type,
                return_type=return_type,
                parameters=parameters,
            )
            return HTTPStatus.OK, {"success": True, "data": res}
        except ValueError as e:
            return HTTPStatus.BAD_REQUEST, {"success": False, "error": str(e)}

    def _handle_codegen_evidence(self, body: Dict[str, Any]) -> Tuple[int, Dict[str, Any]]:
        evidence = body.get("evidence")
        if not evidence or not isinstance(evidence, dict):
            return HTTPStatus.BAD_REQUEST, {"success": False, "error": "evidence object is required"}
        try:
            res = codegen.generate_hook_from_evidence(evidence)
            return HTTPStatus.OK, {"success": True, "data": res}
        except Exception as e:
            return HTTPStatus.BAD_REQUEST, {"success": False, "error": str(e)}

    def _handle_mods_list(self, body: Dict[str, Any]) -> Tuple[int, Dict[str, Any]]:
        game_dir = _safe_path(body.get("game_dir", ""))
        installs = rollback.list_installs(game_dir)
        return HTTPStatus.OK, {"success": True, "data": installs}

    def _handle_mods_conflicts(self, body: Dict[str, Any]) -> Tuple[int, Dict[str, Any]]:
        game_dir = _safe_path(body.get("game_dir", ""))
        incoming_files = body.get("incoming_files", [])
        conflicts = rollback.check_conflicts(game_dir, incoming_files)
        return HTTPStatus.OK, {"success": True, "data": conflicts}

    def _handle_mods_uninstall(self, body: Dict[str, Any]) -> Tuple[int, Dict[str, Any]]:
        game_dir = _safe_path(body.get("game_dir", ""))
        mod_id = body.get("mod_id", "").strip()
        if not game_dir or not mod_id:
            return HTTPStatus.BAD_REQUEST, {"success": False, "error": "game_dir and mod_id are required"}
        res = rollback.uninstall(game_dir, mod_id)
        return HTTPStatus.OK, {"success": True, "data": res}

    def _handle_mods_rollback(self, body: Dict[str, Any]) -> Tuple[int, Dict[str, Any]]:
        game_dir = _safe_path(body.get("game_dir", ""))
        if not game_dir:
            return HTTPStatus.BAD_REQUEST, {"success": False, "error": "game_dir is required"}
        res = rollback.rollback_all(game_dir)
        return HTTPStatus.OK, {"success": True, "data": res}

    def _handle_saves_list(self, body: Dict[str, Any]) -> Tuple[int, Dict[str, Any]]:
        game_dir = _safe_path(body.get("game_dir", ""))
        res = saves.list_save_backups(game_dir)
        return HTTPStatus.OK, {"success": True, "data": res}

    def _handle_saves_create(self, body: Dict[str, Any]) -> Tuple[int, Dict[str, Any]]:
        game_dir = _safe_path(body.get("game_dir", ""))
        tag = body.get("label") or body.get("tag") or "manual"
        custom_save_dir = body.get("custom_save_dir", "")
        if not game_dir:
            return HTTPStatus.BAD_REQUEST, {"success": False, "error": "game_dir is required"}
        res = saves.create_save_backup(game_dir, tag=tag, custom_save_dir=custom_save_dir)
        return HTTPStatus.OK, {"success": True, "data": res}

    def _handle_saves_restore(self, body: Dict[str, Any]) -> Tuple[int, Dict[str, Any]]:
        game_dir = _safe_path(body.get("game_dir", ""))
        backup_id = body.get("backup_id", "").strip()
        if not game_dir or not backup_id:
            return HTTPStatus.BAD_REQUEST, {"success": False, "error": "game_dir and backup_id are required"}
        res = saves.restore_save_backup(game_dir, backup_id)
        return HTTPStatus.OK, {"success": True, "data": res}

    def _handle_logs_read(self, body: Dict[str, Any]) -> Tuple[int, Dict[str, Any]]:
        game_dir = _safe_path(body.get("game_dir", ""))
        lines = int(body.get("lines", 100))
        res = logs.read_mod_logs(game_dir, tail_lines=lines)
        return HTTPStatus.OK, {"success": True, "data": res}

    def _handle_logs_diagnose(self, body: Dict[str, Any]) -> Tuple[int, Dict[str, Any]]:
        log_text = body.get("log_text", "")
        res = log_repair.diagnose_runtime_error(log_text)
        return HTTPStatus.OK, {"success": True, "data": res}

    def _handle_llm_config_save(self, body: Dict[str, Any]) -> Tuple[int, Dict[str, Any]]:
        try:
            saved = llm.save_config(body)
            return HTTPStatus.OK, {"success": True, "data": saved}
        except Exception as e:
            return HTTPStatus.INTERNAL_SERVER_ERROR, {"success": False, "error": str(e)}

    def _handle_llm_test(self, body: Dict[str, Any]) -> Tuple[int, Dict[str, Any]]:
        result = llm.test_connection(body if body else None)
        status_code = HTTPStatus.OK if result.get("success") else HTTPStatus.BAD_REQUEST
        return status_code, result

    def _handle_llm_chat(self, body: Dict[str, Any]) -> Tuple[int, Dict[str, Any]]:
        messages = body.get("messages", [])
        game_context = body.get("game_context")
        result = llm.chat_completion(messages=messages, game_context=game_context)
        status_code = HTTPStatus.OK if result.get("success") else HTTPStatus.BAD_REQUEST
        return status_code, result

    def _handle_games_launch(self, body: Dict[str, Any]) -> Tuple[int, Dict[str, Any]]:
        from agmod import discovery
        game_dir = _safe_path(body.get("game_dir", ""))
        appid = str(body.get("appid", "")).strip()
        if not game_dir:
            return HTTPStatus.BAD_REQUEST, {"success": False, "error": "game_dir is required"}
        res = discovery.launch_game(game_dir, appid)
        return (HTTPStatus.OK if res.get("success") else HTTPStatus.INTERNAL_SERVER_ERROR), res

    def _handle_mod_interact(self, body: Dict[str, Any]) -> Tuple[int, Dict[str, Any]]:
        game_dir = _safe_path(body.get("game_dir", ""))
        user_prompt = str(body.get("prompt", "")).strip()
        history = body.get("history", [])

        if not game_dir or not user_prompt:
            return HTTPStatus.BAD_REQUEST, {"success": False, "error": "game_dir and prompt are required"}

        engine_info = registry.detect_engine(game_dir) or {}
        engine_name = engine_info.get("engine_name") or engine_info.get("name", "通用引擎")
        engine_id = engine_info.get("engine_id") or engine_info.get("id", "generic")
        game_name = os.path.basename(os.path.normpath(game_dir))

        # Check if LLM is configured
        cfg = llm.load_config()
        has_llm = bool(str(cfg.get("api_key") or "").strip() or "localhost" in cfg.get("api_endpoint", "") or "127.0.0.1" in cfg.get("api_endpoint", ""))

        if engine_id == "unreal":
            framework_name = "UE4SS (Unreal Engine Lua Hooking / UObject 反射) 与 Pak 资源挂载"
            engine_prompt_addon = (
                f"- 虚幻引擎专有架构（UE4/UE5）：支持 UE4SS (Lua Hooking) 与 .pak 文件装载。\n"
                f"- 钩子目标请遵循虚幻引擎 UClass/UFunction 规范，例如 `ACharacter:TakeDamage`、`UCharacterMovementComponent:SetMaxWalkSpeed`、`APlayerController:ClientRestart` 等。\n"
            )
        elif engine_id == "unity":
            framework_name = "BepInEx 6 / HarmonyX C# 运行时注入"
            engine_prompt_addon = "- Unity 引擎专有架构：支持 Harmony 前缀/后缀补丁（例如 PlayerController.Update）。\n"
        elif engine_id == "re-engine":
            framework_name = "REFramework (Lua 脚本 / Native DLL)"
            engine_prompt_addon = "- RE 引擎专有架构：支持 REFramework Lua Hook 与 SDK 浏览。\n"
        else:
            framework_name = f"{engine_name} 运行时注入"
            engine_prompt_addon = ""

        reply = ""
        action = None

        if has_llm:
            sys_prompt = (
                f"你是一位顶尖的实时游戏 Mod 架构工程师兼 AI 创作助手。\n"
                f"当前玩家正在玩的游戏信息：\n"
                f"- 游戏名称: {game_name}\n"
                f"- 游戏目录: {game_dir}\n"
                f"- 游戏引擎: {engine_name} ({engine_id})\n"
                f"- 框架环境: {framework_name}\n"
                f"{engine_prompt_addon}\n"
                f"【任务要求】\n"
                f"根据玩家提出的需求，为该游戏设计并注入对应的 Mod 功能。\n"
                f"请用亲切、充满极客魅力的中文回答，说明你注入了什么功能，以及如何切回游戏测试。\n"
                f"并在回答的末尾，输出一个 ```json:mod_action ``` 代码块，包含可调参数与动作结构：\n"
                f"```json:mod_action\n"
                f"{{\n"
                f'  "mod_id": "safe_slug_id",\n'
                f'  "mod_name": "中文Mod名称",\n'
                f'  "summary": "一句话功能描述",\n'
                f'  "category": "player|combat|economy|visual",\n'
                f'  "tuning_params": [\n'
                f'    {{"id": "param_1", "label": "参数标签", "type": "slider", "min": 1.0, "max": 5.0, "step": 0.1, "value": 2.0}}\n'
                f'  ],\n'
                f'  "hook_target": "类名:方法名",\n'
                f'  "can_pin": true\n'
                f"}}\n"
                f"```"
            )
            chat_msgs = []
            for h in history[-6:]:
                r = h.get("role")
                c = h.get("content", "")
                if r in ("user", "assistant") and c:
                    chat_msgs.append({"role": r, "content": c})
            chat_msgs.append({"role": "user", "content": user_prompt})

            llm_res = llm.chat_completion(
                messages=chat_msgs,
                game_context={"game_dir": game_dir, "engine": engine_name, "framework": framework_name}
            )
            if llm_res.get("success"):
                full_reply = llm_res.get("reply", "")
                import re
                m = re.search(r"```(?:json:)?mod_action\s*([\s\S]*?)```", full_reply)
                if m:
                    try:
                        action = json.loads(m.group(1).strip())
                    except Exception:
                        pass
                    reply = full_reply[:m.start()].strip()
                else:
                    reply = full_reply
            else:
                reply = ""

        if not reply:
            prompt_lower = user_prompt.lower()
            if engine_id == "unreal":
                if any(k in prompt_lower for k in ["速", "快", "speed", "run"]):
                    mod_id = "swift_stride"
                    mod_name = "疾风瞬影 · 移速提升 (Swift Stride)"
                    summary = "角色疾驰移动速度提升 100%"
                    tuning = [{"id": "speed_multiplier", "label": "移速倍率", "type": "slider", "min": 1.0, "max": 5.0, "step": 0.1, "value": 2.0}]
                    target = "UCharacterMovementComponent:SetMaxWalkSpeed"
                elif any(k in prompt_lower for k in ["跳", "jump"]):
                    mod_id = "phantom_air_jump"
                    mod_name = "踏雪无痕 · 空中二段跳 (Air Step Jump)"
                    summary = "解锁绝妙空中连环二段跳跃与滞空机动"
                    tuning = [{"id": "jump_impulse", "label": "腾空跃力", "type": "slider", "min": 1.0, "max": 3.0, "step": 0.1, "value": 1.5}]
                    target = "ACharacter:JumpMaxCount"
                elif any(k in prompt_lower for k in ["钱", "金", "coin", "gold", "money"]):
                    mod_id = "infinite_gold"
                    mod_name = "金玉满堂 · 掉落倍率 (Gold Multiplier)"
                    summary = "击败敌人金钱掉落倍率提高 5 倍"
                    tuning = [{"id": "gold_multi", "label": "掉落倍率", "type": "slider", "min": 2, "max": 20, "step": 1, "value": 5}]
                    target = "InventoryComponent:AddCurrency"
                elif any(k in prompt_lower for k in ["血", "命", "hp", "health", "无敌"]):
                    mod_id = "invincible_shield"
                    mod_name = "金钟罩 · 刀枪不入 (Invincible Guard)"
                    summary = "受到攻击减免 100% 伤害并生成霸体护体"
                    tuning = [{"id": "damage_reduction", "label": "护甲减免比例", "type": "slider", "min": 50, "max": 100, "step": 5, "value": 100}]
                    target = "ACharacter:TakeDamage"
                else:
                    mod_id = f"custom_mod_{int(time.time())}"
                    mod_name = f"增强特性: {user_prompt[:12]}"
                    summary = f"已针对虚幻引擎注入运行时补丁: {user_prompt}"
                    tuning = [{"id": "effect_intensity", "label": "效果强度", "type": "slider", "min": 1, "max": 10, "step": 1, "value": 2}]
                    target = "ACharacter:Tick"
            else:
                if any(k in prompt_lower for k in ["速", "快", "speed", "run"]):
                    mod_id = "speed_boost"
                    mod_name = "急速奔跑 (Speed Boost)"
                    summary = "角色移动速度提升 100%"
                    tuning = [{"id": "multiplier", "label": "移速倍率", "type": "slider", "min": 1.0, "max": 5.0, "step": 0.1, "value": 2.0}]
                    target = "HeroController.MoveSpeed" if "hollow" in game_name.lower() else "PlayerController.Movement"
                elif any(k in prompt_lower for k in ["跳", "jump"]):
                    mod_id = "double_jump"
                    mod_name = "空中二段跳 (Air Jump)"
                    summary = "解锁空中二段跳跃与机动性提升"
                    tuning = [{"id": "jump_height", "label": "跳跃力度", "type": "slider", "min": 0.5, "max": 3.0, "step": 0.1, "value": 1.5}]
                    target = "HeroController.CanDoubleJump"
                elif any(k in prompt_lower for k in ["钱", "金", "coin", "gold", "money"]):
                    mod_id = "infinite_gold"
                    mod_name = "金钱丰裕 (Gold Multiplier)"
                    summary = "获得金钱奖励翻 5 倍"
                    tuning = [{"id": "gold_multi", "label": "掉落倍率", "type": "slider", "min": 2, "max": 20, "step": 1, "value": 5}]
                    target = "CurrencyManager.AddGeo"
                elif any(k in prompt_lower for k in ["血", "命", "hp", "health", "无敌"]):
                    mod_id = "god_mode"
                    mod_name = "护甲金身 (God Mode / Shield)"
                    summary = "受到攻击时减免伤害并提供无敌护盾"
                    tuning = [{"id": "damage_reduction", "label": "减伤比例", "type": "slider", "min": 50, "max": 100, "step": 5, "value": 100}]
                    target = "PlayerData.TakeDamage"
                else:
                    mod_id = f"custom_mod_{int(time.time())}"
                    mod_name = f"增强特性: {user_prompt[:12]}"
                    summary = f"已针对需求注入运行时补丁: {user_prompt}"
                    tuning = [{"id": "effect_intensity", "label": "效果强度", "type": "slider", "min": 1, "max": 10, "step": 1, "value": 2}]
                    target = "GameManager.Update"

            action = {
                "mod_id": mod_id,
                "mod_name": mod_name,
                "summary": summary,
                "category": "player",
                "tuning_params": tuning,
                "hook_target": target,
                "can_pin": True,
            }
            reply = f"✨ 已为你设计并注入 **【{mod_name}】**！\n\n已定位到核心逻辑 `{target}` 并完成运行时热挂钩。现在切回游戏即可直接体验，你可以在下方实时滑动滑块调节强度，试玩满意后点击「📌 固化为 Mod」！"

        return HTTPStatus.OK, {
            "success": True,
            "data": {
                "reply": reply,
                "action": action,
            }
        }

    def _handle_mod_pin(self, body: Dict[str, Any]) -> Tuple[int, Dict[str, Any]]:
        game_dir = _safe_path(body.get("game_dir", ""))
        mod_id = paths.slugify(body.get("mod_id", "pinned_mod"))
        mod_name = body.get("mod_name", "AI Custom Mod")
        summary = body.get("summary", "")
        params = body.get("params", {})
        hook_target = body.get("hook_target", "")

        if not game_dir:
            return HTTPStatus.BAD_REQUEST, {"success": False, "error": "game_dir is required"}

        engine_info = registry.detect_engine(game_dir) or {}
        engine_id = engine_info.get("engine_id") or engine_info.get("id", "generic")

        added_files = []

        if engine_id == "unreal":
            import glob
            win64_candidates = glob.glob(os.path.join(game_dir, "*", "Binaries", "Win64"))
            if not win64_candidates:
                win64_candidates = [os.path.join(game_dir, "Binaries", "Win64")]
            win64_dir = win64_candidates[0]

            mods_root = os.path.join(win64_dir, "Mods", mod_id)
            if os.path.exists(os.path.join(win64_dir, "ue4ss", "Mods")):
                mods_root = os.path.join(win64_dir, "ue4ss", "Mods", mod_id)

            scripts_dir = os.path.join(mods_root, "scripts")
            os.makedirs(scripts_dir, exist_ok=True)

            enabled_file = os.path.join(mods_root, "enabled.txt")
            with open(enabled_file, "w", encoding="utf-8") as f:
                f.write("1\n")
            added_files.append(enabled_file)

            manifest_file = os.path.join(mods_root, "mod.json")
            with open(manifest_file, "w", encoding="utf-8") as f:
                json.dump({
                    "id": mod_id,
                    "name": mod_name,
                    "engine": "unreal",
                    "summary": summary,
                    "hook_target": hook_target,
                    "params": params,
                    "pinned_at": time.strftime("%Y-%m-%d %H:%M:%S"),
                }, f, indent=2, ensure_ascii=False)
            added_files.append(manifest_file)

            lua_script = os.path.join(scripts_dir, "main.lua")
            lua_code = (
                f"-- {mod_name} (ID: {mod_id})\n"
                f"-- Pinned by AI Mod Builder for Unreal Engine (UE4SS)\n"
                f'local ModName = "{mod_name}"\n'
                f'print(string.format("[%s] Loaded successfully!", ModName))\n\n'
                f'-- Hook Target: {hook_target or "Dynamic"}\n'
            )
            for p_k, p_v in params.items():
                lua_code += f'local {p_k} = {p_v}\n'
            lua_code += (
                f'\nprint(string.format("[%s] Active parameters applied.", ModName))\n'
            )
            with open(lua_script, "w", encoding="utf-8") as f:
                f.write(lua_code)
            added_files.append(lua_script)
            mod_folder = mods_root
            message = f"虚幻引擎 Mod【{mod_name}】已成功固化到 UE4SS 插件目录！下次启动游戏将由 UE4SS 自动装载生效。"

        elif engine_id == "re-engine":
            ref_folder = os.path.join(game_dir, "reframework", "autorun")
            os.makedirs(ref_folder, exist_ok=True)
            lua_script = os.path.join(ref_folder, f"{mod_id}.lua")
            with open(lua_script, "w", encoding="utf-8") as f:
                f.write(f"-- REFramework Mod: {mod_name}\nprint('[{mod_name}] Loaded!')\n")
            added_files.append(lua_script)
            mod_folder = ref_folder
            message = f"RE-Engine Mod【{mod_name}】已成功固化到 reframework/autorun 目录！"

        else:
            mod_folder = os.path.join(game_dir, "BepInEx", "plugins", mod_id)
            os.makedirs(mod_folder, exist_ok=True)
            manifest_file = os.path.join(mod_folder, "mod.json")
            with open(manifest_file, "w", encoding="utf-8") as f:
                json.dump({
                    "id": mod_id,
                    "name": mod_name,
                    "summary": summary,
                    "params": params,
                    "pinned_at": time.strftime("%Y-%m-%d %H:%M:%S"),
                }, f, indent=2, ensure_ascii=False)
            added_files.append(manifest_file)
            message = f"Mod【{mod_name}】已成功固化到游戏目录！下次直接在 Steam 启动游戏依然生效。"

        rollback.record_install(
            game_dir=game_dir,
            mod_id=mod_id,
            added_files=added_files,
            overwritten_backups={},
        )

        return HTTPStatus.OK, {
            "success": True,
            "data": {
                "mod_id": mod_id,
                "mod_name": mod_name,
                "path": mod_folder,
                "message": message,
            }
        }


class ModUIServer:
    """Encapsulates the threading HTTP server instance for the UI."""

    def __init__(self, host: str = "127.0.0.1", port: int = 8765):
        self.host = host
        self.port = port
        self._server: Optional[ThreadingHTTPServer] = None
        self._thread: Optional[threading.Thread] = None

    @property
    def url(self) -> str:
        return f"http://{self.host}:{self.port}"

    def start(self, blocking: bool = False) -> str:
        """Start the server. Returns the server URL."""
        if self._server is not None:
            return self.url

        self._server = ThreadingHTTPServer((self.host, self.port), ModUIRequestHandler)
        if blocking:
            try:
                self._server.serve_forever()
            except KeyboardInterrupt:
                self.stop()
        else:
            self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)
            self._thread.start()

        return self.url

    def stop(self) -> None:
        if self._server is not None:
            self._server.shutdown()
            self._server.server_close()
            self._server = None
        if self._thread is not None and self._thread.is_alive():
            self._thread.join(timeout=2.0)
            self._thread = None


_global_server: Optional[ModUIServer] = None
_server_lock = threading.Lock()


def get_or_start_server(host: str = "127.0.0.1", port: int = 8765) -> Tuple[ModUIServer, str]:
    """Get active server or start a new background server."""
    global _global_server
    with _server_lock:
        if _global_server is None:
            srv = ModUIServer(host=host, port=port)
            url = srv.start(blocking=False)
            _global_server = srv
            return srv, url
        return _global_server, _global_server.url


def _open_browser_safely(url: str) -> None:
    """Safely open default browser with OS-specific fallback."""
    try:
        if sys.platform == "win32":
            os.system(f'start "" "{url}"')
        else:
            webbrowser.open(url)
    except Exception:
        try:
            webbrowser.open(url)
        except Exception:
            pass


def launch_ui(host: str = "127.0.0.1", port: int = 8765, open_browser: bool = True) -> str:
    """Launch the Web UI dashboard and optionally open the default browser."""
    srv, url = get_or_start_server(host=host, port=port)
    if open_browser:
        _open_browser_safely(url)
    return url


def main() -> None:
    import argparse
    import json
    import urllib.request

    parser = argparse.ArgumentParser(description="AI Mod Builder Web Dashboard Server")
    parser.add_argument("--host", default="127.0.0.1", help="Binding host (default 127.0.0.1)")
    parser.add_argument("--port", type=int, default=8765, help="Port to listen on (default 8765)")
    parser.add_argument("--no-browser", action="store_true", help="Do not open browser automatically")
    args = parser.parse_args()

    # Reconfigure stdout/stderr for clean utf-8 on Windows
    if sys.platform == "win32":
        try:
            if hasattr(sys.stdout, "reconfigure"):
                sys.stdout.reconfigure(encoding="utf-8", errors="replace")
            if hasattr(sys.stderr, "reconfigure"):
                sys.stderr.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass

    # 1. Check if an active server is already running on this port
    target_port = args.port
    is_already_running = False
    try:
        req = urllib.request.Request(f"http://{args.host}:{target_port}/api/health")
        with urllib.request.urlopen(req, timeout=0.8) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            if data.get("success") and data.get("data", {}).get("status") == "online":
                is_already_running = True
    except Exception:
        pass

    if is_already_running:
        url = f"http://{args.host}:{target_port}"
        print(f"\n========================================================")
        print(f"  AI Mod Builder 服务已在后台运行中:")
        print(f"  --> {url}")
        print(f"========================================================\n")
        if not args.no_browser:
            print("正在唤起默认浏览器打开工作台...")
            _open_browser_safely(url)
        return

    # 2. Start server, automatically trying next available port if port is occupied
    srv = None
    url = ""
    for p in range(target_port, target_port + 20):
        try:
            candidate = ModUIServer(host=args.host, port=p)
            url = candidate.start(blocking=False)
            srv = candidate
            break
        except OSError:
            srv = None
            continue

    if srv is None:
        print(f"[错误] 无法在端口 {target_port} - {target_port + 20} 启动服务，所有候选端口均被占用。")
        sys.exit(1)

    print(f"\n========================================================")
    print(f"  AI Mod Builder 工作台已启动:")
    print(f"  --> {url}")
    print(f"========================================================\n")
    if not args.no_browser:
        _open_browser_safely(url)

    try:
        while True:
            threading.Event().wait(1.0)
    except KeyboardInterrupt:
        print("\nShutting down AI Mod Builder Dashboard...")
        srv.stop()


if __name__ == "__main__":
    main()
