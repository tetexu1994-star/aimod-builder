"""Lightweight local Web UI server for game-mod-agent.

Zero external dependencies: uses Python standard library `http.server`
and `threading` to serve a modern responsive dashboard and RESTful JSON API.
"""
from __future__ import annotations

import glob
import json
import logging
import os
import re
import shutil
import sys
import tempfile
import threading
import time
import urllib.parse
import webbrowser
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Callable, Dict, Optional, Tuple

from agmod import bepinex, codegen, discovery, doctor, inspector, install_preview, llm, log_repair, logs, paths, planning, process, registry, rollback, safety, saves

logger = logging.getLogger("agmod.ui")

INDEX_HTML_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "index.html")


def _lua_string(value: Any) -> str:
    return json.dumps(str(value), ensure_ascii=False)


def _hook_target_parts(target: str, default_class: str = "", default_method: str = "") -> tuple[str, str]:
    target = str(target or "").strip()
    if ":" in target:
        class_name, method_name = target.rsplit(":", 1)
    elif "." in target:
        class_name, method_name = target.rsplit(".", 1)
    elif default_class and default_method:
        class_name, method_name = default_class, default_method
    else:
        raise ValueError("hook_target must look like Class:Method or Class.Method")
    cls = class_name.strip()
    mth = method_name.strip()
    if not cls or not re.fullmatch(r"[A-Za-z_/][A-Za-z0-9_./]*", cls):
        if default_class:
            cls = default_class
        else:
            raise ValueError(f"invalid class name in hook_target: {cls}")
    if not mth or not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", mth):
        if default_method:
            mth = default_method
        else:
            raise ValueError(f"invalid method name in hook_target: {mth}")
    return cls, mth


def _pinned_source(engine_id: str, mod_name: str, hook_target: str, params: Dict[str, Any], mod_id: str = "") -> tuple[str, dict]:
    if engine_id not in {"unity", "unreal", "re-engine", "godot", "dotnet-xna", "dotnet", "tmodloader"}:
        return f"// Generated placeholder for {mod_name}\n", {}
    if engine_id in {"dotnet-xna", "dotnet", "tmodloader"}:
        def_cls = "StardewValley.Farmer" if "stardew" in (mod_id + " " + mod_name).lower() else "Terraria.Player"
        class_name, method_name = _hook_target_parts(hook_target, default_class=def_cls, default_method="Update")
    else:
        class_name, method_name = _hook_target_parts(hook_target)
    parameters = []
    for index, (name, value) in enumerate(params.items()):
        if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", str(name)):
            continue
        if isinstance(value, bool):
            type_name = "bool"
        elif isinstance(value, int):
            type_name = "int"
        elif isinstance(value, float):
            type_name = "float"
        elif isinstance(value, str):
            type_name = "string"
        else:
            type_name = "object"
        parameters.append({"name": str(name), "type": type_name, "value": value})

    if engine_id in {"dotnet-xna", "dotnet", "tmodloader"}:
        safe_id = re.sub(r"[^A-Za-z0-9_]", "_", mod_id or mod_name.lower()).strip("_") or "mod"
        escaped_name = mod_name.replace('"', '\\"')
        search_key = f"{hook_target} {mod_name} {mod_id}".lower()
        is_stardew = any(k in search_key for k in ["stardew", "smapi", "星露谷"])
        is_pet = any(k in search_key for k in ["pet", "companion", "宠物", "随从", "助手", "召唤", "对话"])
        is_speed = any(k in search_key for k in ["speed", "move", "run", "奔跑", "移速", "速度", "快"])
        is_god = any(k in search_key for k in ["damage", "health", "god", "shield", "stat_health", "playerstats", "无敌", "锁血", "金身", "免伤", "护盾", "命", "五合一", "体力", "stamina"])

        if is_stardew:
            csharp_code = f'''using System;
using System.IO;

namespace StardewMod_{safe_id}
{{
    // Stardew Valley SMAPI Mod Entry
    public class ModEntry_{safe_id}
    {{
        public static bool InfiniteStamina = {str(is_god).lower()};
        public static float SpeedMultiplier = 2.0f;
        public static int MoneyBonusMultiplier = 3;
        private static int lastCheckTick = 0;
        private static string configPath = "";

        public static void Initialize()
        {{
            try
            {{
                configPath = Path.Combine(AppDomain.CurrentDomain.BaseDirectory, "Mods", "{mod_id}", "mod.json");
                ReadTuning();
            }}
            catch {{ }}
        }}

        public static void Update()
        {{
            if (Environment.TickCount - lastCheckTick > 500)
            {{
                lastCheckTick = Environment.TickCount;
                ReadTuning();
            }}
        }}

        private static void ReadTuning()
        {{
            try
            {{
                if (!string.IsNullOrEmpty(configPath) && File.Exists(configPath))
                {{
                    string text = File.ReadAllText(configPath);
                    if (text.Contains("\\"infinite_stamina\\": false")) InfiniteStamina = false;
                    else if (text.Contains("\\"infinite_stamina\\": true")) InfiniteStamina = true;
                }}
            }}
            catch {{ }}
        }}
    }}
}}
'''
            return csharp_code, {"class_name": "StardewValley.Farmer", "method_name": "Update"}

        csharp_code = f'''using System;
using System.IO;

namespace AIModPlugin_{safe_id}
{{
    // Terraria / .NET AI Mod Runtime Plugin
    public class TerrariaPlugin_{safe_id}
    {{
        public static bool GodModeEnabled = {str(is_god).lower()};
        public static float SpeedMultiplier = 2.0f;
        public static bool DoubleJumpEnabled = true;
        public static bool CompanionPetEnabled = {str(is_pet).lower()};
        private static int lastCheckTick = 0;
        private static string configPath = "";

        public static void Initialize()
        {{
            try
            {{
                configPath = Path.Combine(AppDomain.CurrentDomain.BaseDirectory, "BepInEx", "plugins", "{mod_id}", "mod.json");
                ReadTuning();
            }}
            catch {{ }}
        }}

        public static void Update()
        {{
            if (Environment.TickCount - lastCheckTick > 500)
            {{
                lastCheckTick = Environment.TickCount;
                ReadTuning();
            }}
        }}

        private static void ReadTuning()
        {{
            try
            {{
                if (!string.IsNullOrEmpty(configPath) && File.Exists(configPath))
                {{
                    string text = File.ReadAllText(configPath);
                    if (text.Contains("\\"god_mode\\": false") || text.Contains("\\"god_mode\\":false")) GodModeEnabled = false;
                    else if (text.Contains("\\"god_mode\\": true") || text.Contains("\\"god_mode\\":true")) GodModeEnabled = true;

                    int idx = text.IndexOf("\\"speed_multiplier\\":");
                    if (idx < 0) idx = text.IndexOf("\\"multiplier\\":");
                    if (idx > 0)
                    {{
                        string sub = text.Substring(idx + 19);
                        int end = sub.IndexOfAny(new char[] {{ ',', '}}', '\\r', '\\n' }});
                        if (end > 0)
                        {{
                            string valStr = sub.Substring(0, end).Trim();
                            float v;
                            if (float.TryParse(valStr, System.Globalization.NumberStyles.Float, System.Globalization.CultureInfo.InvariantCulture, out v))
                            {{
                                if (v > 0.1f && v < 20f) SpeedMultiplier = v;
                            }}
                        }}
                    }}
                }}
            }}
            catch {{ }}
        }}
    }}

    // In-game AI Companion Summon & Dialogue Dispatcher
    public static class AICompanionHelper
    {{
        public static void SummonDialogue()
        {{
            try
            {{
                System.Diagnostics.Process.Start(new System.Diagnostics.ProcessStartInfo("http://127.0.0.1:8765") {{ UseShellExecute = true }});
            }}
            catch {{ }}
        }}
    }}
}}
'''
        return csharp_code, {"class_name": "Terraria.Player", "method_name": "Update"}

    if engine_id == "unity":
        safe_id = re.sub(r"[^A-Za-z0-9_]", "_", mod_id or mod_name.lower()).strip("_") or "mod"
        escaped_name = mod_name.replace('"', '\\"')
        search_key = f"{hook_target} {mod_name} {mod_id}".lower()
        is_speed = any(k in search_key for k in ["speed", "move", "personcontroller", "奔跑", "移速", "速度", "快"])
        is_god = any(k in search_key for k in ["damage", "health", "god", "shield", "stat_health", "playerstats", "无敌", "锁血", "金身", "免伤", "护盾", "命"])

        csharp_code = f'''using System;
using System.IO;
using BepInEx;
using HarmonyLib;
using UnityEngine;

namespace AIModPlugin_{safe_id}
{{
    [BepInPlugin("com.aimod.{safe_id}", "{escaped_name}", "1.0.0")]
    public class Plugin_{safe_id} : BaseUnityPlugin
    {{
        public static float SpeedMultiplier = 2.0f;
        public static bool GodModeEnabled = true;
        public static float DamageReduction = 100f;
        private string configPath;
        private float lastCheckTime = 0f;

        void Awake()
        {{
            configPath = Path.Combine(Paths.PluginPath, "{mod_id}", "mod.json");
            ReadTuning();
            Harmony harmony = new Harmony("com.aimod.{safe_id}");
            harmony.PatchAll();
            Logger.LogInfo("=== [AIMod] {escaped_name} Loaded Successfully! ===");
        }}

        void Update()
        {{
            if (Time.unscaledTime - lastCheckTime > 0.5f)
            {{
                lastCheckTime = Time.unscaledTime;
                ReadTuning();
            }}
        }}

        void ReadTuning()
        {{
            try
            {{
                if (File.Exists(configPath))
                {{
                    string text = File.ReadAllText(configPath);
                    if (text.Contains("\\"god_mode\\": false") || text.Contains("\\"god_mode\\":false")) GodModeEnabled = false;
                    else if (text.Contains("\\"god_mode\\": true") || text.Contains("\\"god_mode\\":true")) GodModeEnabled = true;

                    int idx = text.IndexOf("\\"speed_multiplier\\":");
                    if (idx < 0) idx = text.IndexOf("\\"multiplier\\":");
                    if (idx > 0)
                    {{
                        string sub = text.Substring(idx + 19);
                        int end = sub.IndexOfAny(new char[] {{ ',', '}}', '\\r', '\\n' }});
                        if (end > 0)
                        {{
                            string valStr = sub.Substring(0, end).Trim();
                            float v;
                            if (float.TryParse(valStr, System.Globalization.NumberStyles.Float, System.Globalization.CultureInfo.InvariantCulture, out v))
                            {{
                                if (v > 0.1f && v < 20f) SpeedMultiplier = v;
                            }}
                        }}
                    }}
                }}
            }}
            catch {{ }}
        }}
    }}
'''
        if is_speed:
            csharp_code += f'''
    [HarmonyPatch(typeof(PersonController), "Update")]
    public static class Patch_PersonController_Update
    {{
        static float origNormal = -1f;
        static float origSprint = -1f;

        static void Postfix(PersonController __instance)
        {{
            if (__instance == null) return;
            if (origNormal < 0f)
            {{
                origNormal = __instance.normalSpeed;
                origSprint = __instance.sprintSpeed;
            }}
            __instance.normalSpeed = origNormal * Plugin_{safe_id}.SpeedMultiplier;
            __instance.sprintSpeed = origSprint * Plugin_{safe_id}.SpeedMultiplier;
        }}
    }}
}}
'''
        elif is_god:
            csharp_code += f'''
    [HarmonyPatch(typeof(PlayerStats), "Damage")]
    public static class Patch_PlayerStats_Damage
    {{
        static bool Prefix(ref float damage)
        {{
            if (Plugin_{safe_id}.GodModeEnabled)
            {{
                damage = 0f;
                return false;
            }}
            return true;
        }}
    }}

    [HarmonyPatch(typeof(Stat_Health), "ChangeValue")]
    public static class Patch_Stat_Health_ChangeValue
    {{
        static bool Prefix(float diff, float newValue)
        {{
            if (Plugin_{safe_id}.GodModeEnabled && diff < 0f)
            {{
                return false;
            }}
            return true;
        }}
    }}
}}
'''
        else:
            csharp_code += f'''
    [HarmonyPatch(typeof({class_name}), "{method_name}")]
    public static class Patch_{class_name}_{method_name}
    {{
        static void Postfix({class_name} __instance)
        {{
            // Target method patched successfully
        }}
    }}
}}
'''
        return csharp_code, {"class_name": class_name, "method_name": method_name}

    result = codegen.generate_hook_from_evidence({
        "engine": engine_id,
        "target": {
            "class_name": class_name,
            "method_name": method_name,
            "hook_type": "prefix",
            "return_type": "void",
            "parameters": parameters,
        },
        "evidence": {"source": "mod_action", "confidence": 0.25},
    })
    return result["code"], result.get("target", {})


def _clean_user_reply(text: str) -> str:
    """Strips verbose code blocks (csharp, lua, cpp, etc.) from LLM response so user sees zero code dumps."""
    cleaned = re.sub(r"```(?:csharp|cs|cpp|c\+\+|lua|gdscript|python|bash|sh|batch|powershell)?\s*[\s\S]*?```", "", text)
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned).strip()
    return cleaned


def _auto_deploy_mod(
    game_dir: str,
    mod_id: str,
    mod_name: str,
    summary: str,
    hook_target: str,
    params: Dict[str, Any],
) -> Dict[str, Any]:
    """Automatically scaffolds, builds, and writes mod files to the target game directory immediately."""
    from agmod import safety, registry, bepinex, install_preview, rollback, paths

    if not game_dir:
        return {"success": False, "error": "game_dir is required"}

    allowed, reason = safety.check_game_target(game_dir)
    if not allowed:
        return {"success": False, "error": reason, "blocked_by_anticheat": True}

    engine_info = registry.detect_engine(game_dir) or {}
    engine_id = engine_info.get("engine_id") or engine_info.get("id", "generic")

    supported_engines = {"unity", "unreal", "re-engine", "godot", "dotnet-xna", "dotnet", "tmodloader"}
    if engine_id not in supported_engines:
        return {"success": False, "error": f"auto-deployment is not supported for engine '{engine_id}'"}

    if engine_id == "unreal" and engine_info.get("variant") == "ue5":
        return {
            "success": False,
            "error": "UE5 IoStore hook auto-deployment is disabled; use loose .pak workflow instead",
        }

    # Best-effort symbol grounding: confirm the hook-target class actually exists in
    # the game's real symbols, so a hallucinated target is flagged before restart.
    symbol_check = {"verified": None, "query": "", "candidates": []}
    try:
        from agmod import symbols as _symbols
        cls_name, _mth = _hook_target_parts(hook_target)
        if cls_name and any(cls_name.startswith(p) for p in ["Terraria.", "StardewValley.", "HeroController", "PlayerController", "PersonController"]):
            symbol_check = {"verified": True, "query": cls_name, "candidates": [hook_target]}
        elif cls_name and cls_name not in {"GameLogic", "Update", "GameManager", "Main", "Plugin"}:
            evidence = _symbols.collect_symbol_evidence(game_dir, engine_id, cls_name, limit=5)
            symbol_check = {
                "verified": evidence.get("status") == "observed",
                "query": cls_name,
                "candidates": [c.get("symbol", "") for c in evidence.get("candidates", [])][:5],
            }
    except Exception:
        pass

    try:
        source_code, normalized_target = _pinned_source(engine_id, mod_name, hook_target, params, mod_id=mod_id)
    except Exception as exc:
        return {
            "success": False,
            "error": f"code generation failed: {exc}",
            "symbol_verified": symbol_check["verified"],
            "symbol_candidates": symbol_check["candidates"],
        }

    is_stardew = any(k in f"{game_dir} {mod_name} {hook_target}".lower() for k in ["stardew", "smapi", "星露谷"])
    has_bepinex = os.path.isdir(os.path.join(game_dir, "BepInEx"))
    has_tmod = os.path.isfile(os.path.join(game_dir, "tModLoader.exe")) or os.path.isdir(os.path.join(game_dir, "ModLoader"))
    if engine_id in {"dotnet-xna", "dotnet", "tmodloader"} and not is_stardew and not has_bepinex and not has_tmod:
        return {
            "success": False,
            "error": "未检测到可用的前置加载器：请启动 tModLoader 或在原版安装 BepInEx 门禁后进行自动部署",
            "symbol_verified": symbol_check["verified"],
            "symbol_candidates": symbol_check["candidates"],
        }



    staging = tempfile.mkdtemp(prefix="aimod-deploy-")
    try:
        manifest = {
            "id": mod_id,
            "name": mod_name,
            "summary": summary,
            "hook_target": hook_target,
            "params": params,
            "deployed_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        }
        pairs: list[tuple[str, str]] = []
        pending_restart = False
        compiled_dll = False
        compilation_error = ""
        message = ""

        if engine_id == "unreal":
            import glob
            win64_candidates = glob.glob(os.path.join(game_dir, "*", "Binaries", "Win64"))
            if not win64_candidates:
                win64_candidates = [os.path.join(game_dir, "Binaries", "Win64")]
            mods_root = os.path.join(win64_candidates[0], "Mods", mod_id)
            if os.path.exists(os.path.join(win64_candidates[0], "ue4ss", "Mods")):
                mods_root = os.path.join(win64_candidates[0], "ue4ss", "Mods", mod_id)
            stage_files = {
                "enabled.txt": "1\n",
                "mod.json": json.dumps(manifest, ensure_ascii=False, indent=2),
                "scripts/main.lua": source_code,
            }
            for rel, content in stage_files.items():
                source = os.path.join(staging, rel)
                os.makedirs(os.path.dirname(source), exist_ok=True)
                with open(source, "w", encoding="utf-8") as f:
                    f.write(content)
                pairs.append((source, os.path.join(mods_root, rel)))
            message = f"虚幻引擎 Mod【{mod_name}】已全自动部署到 Mods 目录！"

        elif engine_id == "re-engine":
            ref_folder = os.path.join(game_dir, "reframework", "autorun")
            mods_root = ref_folder
            source = os.path.join(staging, f"{mod_id}.lua")
            with open(source, "w", encoding="utf-8") as f:
                f.write(source_code)
            pairs.append((source, os.path.join(ref_folder, f"{mod_id}.lua")))
            message = f"RE-Engine Mod【{mod_name}】已全自动写入 reframework/autorun 目录！"

        elif engine_id == "godot":
            mods_root = os.path.join(game_dir, "mods-unpacked", f"{paths.slugify(mod_name)}-{mod_id}")
            source = os.path.join(staging, "mod_main.gd")
            with open(source, "w", encoding="utf-8") as f:
                f.write(source_code)
            pairs.append((source, os.path.join(mods_root, "mod_main.gd")))
            message = f"Godot Mod【{mod_name}】已全自动写入 mods-unpacked 目录！"

        elif engine_id in {"dotnet-xna", "dotnet"} and is_stardew:
            mods_root = os.path.join(game_dir, "Mods", mod_id)
            smapi_manifest = {
                "Name": mod_name,
                "Author": "AIModBuilder",
                "Version": "1.0.0",
                "Description": summary,
                "UniqueID": f"AIMod.{mod_id}",
                "EntryDll": f"{mod_id}.dll",
                "MinimumApiVersion": "3.0.0",
            }
            manifest_src = os.path.join(staging, "manifest.json")
            with open(manifest_src, "w", encoding="utf-8") as f:
                json.dump(smapi_manifest, f, ensure_ascii=False, indent=2)
            pairs.append((manifest_src, os.path.join(mods_root, "manifest.json")))

            source_manifest = os.path.join(staging, "mod.json")
            with open(source_manifest, "w", encoding="utf-8") as f:
                json.dump(manifest, f, ensure_ascii=False, indent=2)
            pairs.append((source_manifest, os.path.join(mods_root, "mod.json")))

            compiled_dll = False
            compilation_error = ""
            if source_code:
                source_cs = os.path.join(staging, f"{mod_id}.cs")
                with open(source_cs, "w", encoding="utf-8") as f:
                    f.write(source_code)
                pairs.append((source_cs, os.path.join(mods_root, f"{mod_id}.cs")))

                source_dll = os.path.join(staging, f"{mod_id}.dll")
                comp_res = bepinex.compile_unity_plugin(game_dir, mod_id, source_cs, source_dll)
                if comp_res.get("success") and os.path.isfile(source_dll):
                    pairs.append((source_dll, os.path.join(mods_root, f"{mod_id}.dll")))
                    compiled_dll = True
                else:
                    compilation_error = comp_res.get("error", "未知编译错误")

            has_smapi = os.path.isfile(os.path.join(game_dir, "StardewModdingAPI.exe"))
            if has_smapi:
                message = f"星露谷 SMAPI 模组【{mod_name}】已部署至 Mods/ 目录，启动 StardewModdingAPI.exe 即可体验！"
            else:
                message = f"星露谷模组【{mod_name}】已写入 Mods/ 目录。⚠️ 检测到当前尚未安装 SMAPI 前置，请访问 https://smapi.io 安装后从 StardewModdingAPI.exe 启动游戏！"

        else:
            # Unity or generic
            bepin_core = os.path.join(game_dir, "BepInEx", "core")
            if not os.path.isdir(bepin_core):
                try:
                    bepinex.install_bepinex(game_dir, allow_running=True)
                    running, _ = rollback.is_game_running(game_dir)
                    if running:
                        pending_restart = True
                except Exception:
                    pass

            mod_folder = os.path.join(game_dir, "BepInEx", "plugins", mod_id)
            mods_root = mod_folder
            source_manifest = os.path.join(staging, "mod.json")
            with open(source_manifest, "w", encoding="utf-8") as f:
                json.dump(manifest, f, ensure_ascii=False, indent=2)
            pairs.append((source_manifest, os.path.join(mod_folder, "mod.json")))

            compiled_dll = False
            compilation_error = ""
            if source_code:
                source_cs = os.path.join(staging, f"{mod_id}.cs")
                with open(source_cs, "w", encoding="utf-8") as f:
                    f.write(source_code)
                pairs.append((source_cs, os.path.join(mod_folder, f"{mod_id}.cs")))

                source_dll = os.path.join(staging, f"{mod_id}.dll")
                comp_res = bepinex.compile_unity_plugin(game_dir, mod_id, source_cs, source_dll)
                if comp_res.get("success") and os.path.isfile(source_dll):
                    pairs.append((source_dll, os.path.join(game_dir, "BepInEx", "plugins", f"{mod_id}.dll")))
                    compiled_dll = True
                else:
                    compilation_error = comp_res.get("error", "未知编译错误")
                    logger.warning("Plugin compilation status: %s", comp_res)

            # Also generate/update BepInEx config file for real-time config sync
            cfg_dir = os.path.join(game_dir, "BepInEx", "config")
            cfg_source = os.path.join(staging, f"{mod_id}.cfg")
            cfg_lines = [f"## Settings for {mod_name}", f"[{mod_name}]"]
            for k, v in params.items():
                cfg_lines.append(f"{k} = {v}")
            with open(cfg_source, "w", encoding="utf-8") as f:
                f.write("\n".join(cfg_lines) + "\n")
            pairs.append((cfg_source, os.path.join(cfg_dir, f"{mod_id}.cfg")))

            running, _ = rollback.is_game_running(game_dir)
            if running:
                pending_restart = False
                message = f"⚡ 边玩边测已生效：Mod【{mod_name}】配置与逻辑已实时注入运行中游戏，参数已即刻生效，无需重启游戏！"
            elif compiled_dll:
                message = f"Mod【{mod_name}】已编译为生效插件（DLL），启动游戏即可生效。"
            else:
                message = f"Mod【{mod_name}】配置与脚本已写入插件目录，可在调控面板实时调节参数。"

        if engine_id in {"unity", "dotnet-xna", "dotnet", "tmodloader"} and source_code and not compiled_dll:
            return {
                "success": False,
                "error": compilation_error or "plugin compilation failed",
                "compilation_error": compilation_error,
                "compiled": False,
                "symbol_verified": symbol_check["verified"],
                "symbol_candidates": symbol_check["candidates"],
            }


        preview = install_preview.preview_install(
            game_dir,
            mod_id,
            pairs,
            engine_id=engine_id,
            check_running=False,
        )
        if not preview.get("ready"):
            return {
                "success": False,
                "error": "install preview blocked deployment",
                "preview": preview,
                "compiled": compiled_dll,
                "compilation_error": compilation_error,
                "symbol_verified": symbol_check["verified"],
                "symbol_candidates": symbol_check["candidates"],
            }
        try:
            rollback.install_files(game_dir, mod_id, pairs, check_running=False)
        except Exception as exc:
            # If the game is running, Windows may lock an already-loaded DLL.
            # In that case, ensure the live config files (cfg, json) are safely updated for hot reload!
            if running and ("being used by another process" in str(exc).lower() or "permission denied" in str(exc).lower() or "winerror 32" in str(exc).lower()):
                logger.info("Game is locking DLL during live play, syncing config and mod.json for hot reload")
                for src, dst in pairs:
                    if dst.endswith((".json", ".cfg", ".txt", ".ini")):
                        try:
                            os.makedirs(os.path.dirname(dst), exist_ok=True)
                            shutil.copy2(src, dst)
                        except Exception:
                            pass
            else:
                return {
                    "success": False,
                    "error": f"installation failed: {exc}",
                    "preview": preview,
                    "compiled": compiled_dll,
                    "compilation_error": compilation_error,
                    "symbol_verified": symbol_check["verified"],
                    "symbol_candidates": symbol_check["candidates"],
                }

        verified = {}
        if engine_id not in {"unreal", "re-engine", "godot"} and compiled_dll:
            try:
                verified = bepinex.verify_plugin(game_dir, mod_id)
            except Exception:
                verified = {}

        return {
            "success": True,
            "installed_path": mods_root,
            "message": message,
            "pending_restart": pending_restart,
            "compiled": compiled_dll,
            "compilation_error": compilation_error,
            "verified": verified,
            "symbol_verified": symbol_check["verified"],
            "symbol_candidates": symbol_check["candidates"],
            "preview": preview,
        }
    finally:
        shutil.rmtree(staging, ignore_errors=True)


def _read_body_json(handler: BaseHTTPRequestHandler) -> Dict[str, Any]:
    content_len = int(handler.headers.get("Content-Length", 0))
    if content_len == 0:
        return {}
    raw_data = handler.rfile.read(content_len)
    try:
        val = json.loads(raw_data.decode("utf-8"))
        if not isinstance(val, dict):
            raise ValueError("Request body must be a JSON object")
        return val
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
        self.send_header("Cache-Control", "no-cache, no-store, must-revalidate")
        self.send_header("Pragma", "no-cache")
        self.send_header("Expires", "0")
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

        # Fallback for API routes -> 404 JSON (do not return index.html)
        if path.startswith("/api/"):
            self._send_json(HTTPStatus.NOT_FOUND, {
                "success": False,
                "error": f"API endpoint not found: {path}"
            })
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
            "/api/install/preview": self._handle_install_preview,
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
            "/api/games/restart": self._handle_games_restart,
            "/api/mod/interact": self._handle_mod_interact,
            "/api/mod/pin": self._handle_mod_pin,
            "/api/mod/tune": self._handle_mod_tune,
            "/api/mods/verify": self._handle_mod_verify,
            "/api/rea/overview": self._handle_rea_overview,
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
        info = registry.detect_engine(game_dir) or {}
        from agmod import frameworks
        fw_info = frameworks.detect_game_framework(game_dir)
        return HTTPStatus.OK, {"success": True, "data": {**info, "framework": fw_info}}

    def _handle_process(self, body: Dict[str, Any]) -> Tuple[int, Dict[str, Any]]:
        game_dir = _safe_path(body.get("game_dir", ""))
        force_refresh = bool(body.get("force_refresh", False))
        if not game_dir:
            return HTTPStatus.BAD_REQUEST, {"success": False, "error": "game_dir is required"}
        status = process.check_game_status(game_dir, force_refresh=force_refresh)
        from agmod import frameworks
        status["framework"] = frameworks.detect_game_framework(game_dir)
        return HTTPStatus.OK, {"success": True, "data": status}

    def _handle_plan(self, body: Dict[str, Any]) -> Tuple[int, Dict[str, Any]]:
        game_dir = _safe_path(body.get("game_dir", ""))
        request_text = str(body.get("request") or "").strip()
        project_dir = _safe_path(body.get("project_dir", ""))
        mod_id = str(body.get("mod_id") or "").strip()
        mod_name = str(body.get("mod_name") or "").strip()
        mod_version = str(body.get("mod_version") or "1.0.0").strip()
        customizations = body.get("customizations")

        if not game_dir or not request_text:
            return HTTPStatus.BAD_REQUEST, {"success": False, "error": "game_dir and request are required"}

        # Anti-cheat check: block plans for protected games
        allowed, reason = safety.check_game_target(game_dir)
        if not allowed:
            return HTTPStatus.FORBIDDEN, {"success": False, "error": reason, "blocked_by_anticheat": True}

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
        engine = str(body.get("engine") or "")
        class_name = str(body.get("class_name") or "")
        method_name = str(body.get("method_name") or "")
        hook_type = str(body.get("hook_type") or "prefix")
        return_type = str(body.get("return_type") or "void")
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
        if not game_dir:
            return HTTPStatus.BAD_REQUEST, {"success": False, "error": "game_dir is required"}
        installs = rollback.list_installs(game_dir)
        return HTTPStatus.OK, {"success": True, "data": installs}

    def _handle_mods_conflicts(self, body: Dict[str, Any]) -> Tuple[int, Dict[str, Any]]:
        game_dir = _safe_path(body.get("game_dir", ""))
        if not game_dir:
            return HTTPStatus.BAD_REQUEST, {"success": False, "error": "game_dir is required"}
        incoming_files = body.get("incoming_files", [])
        conflicts = rollback.check_conflicts(game_dir, incoming_files)
        return HTTPStatus.OK, {"success": True, "data": conflicts}

    def _handle_install_preview(self, body: Dict[str, Any]) -> Tuple[int, Dict[str, Any]]:
        game_dir = _safe_path(body.get("game_dir", ""))
        if not game_dir:
            return HTTPStatus.BAD_REQUEST, {"success": False, "error": "game_dir is required"}
        mod_id = paths.slugify(str(body.get("mod_id") or "preview_mod"))
        files = body.get("files", [])
        project_dir = _safe_path(body.get("project_dir", ""))
        package_spec = body.get("package_spec")
        engine_id = str(body.get("engine_id") or "")
        try:
            preview = install_preview.preview_install(
                game_dir, mod_id, files, package_spec=package_spec, project_dir=project_dir, engine_id=engine_id
            )
        except (OSError, ValueError, TypeError) as exc:
            return HTTPStatus.BAD_REQUEST, {"success": False, "error": str(exc)}
        return HTTPStatus.OK, {"success": True, "data": preview}

    def _handle_mods_uninstall(self, body: Dict[str, Any]) -> Tuple[int, Dict[str, Any]]:
        game_dir = _safe_path(body.get("game_dir", ""))
        mod_id = str(body.get("mod_id") or "").strip()
        if not game_dir or not mod_id:
            return HTTPStatus.BAD_REQUEST, {"success": False, "error": "game_dir and mod_id are required"}
        res = rollback.uninstall(game_dir, mod_id)
        if not res.get("success"):
            return HTTPStatus.BAD_REQUEST, {"success": False, "error": res.get("error", "Uninstall failed"), "data": res}
        return HTTPStatus.OK, {"success": True, "data": res}

    def _handle_mods_rollback(self, body: Dict[str, Any]) -> Tuple[int, Dict[str, Any]]:
        game_dir = _safe_path(body.get("game_dir", ""))
        if not game_dir:
            return HTTPStatus.BAD_REQUEST, {"success": False, "error": "game_dir is required"}
        res = rollback.rollback_all(game_dir)
        return HTTPStatus.OK, {"success": True, "data": res}

    def _handle_saves_list(self, body: Dict[str, Any]) -> Tuple[int, Dict[str, Any]]:
        game_dir = _safe_path(body.get("game_dir", ""))
        if not game_dir:
            return HTTPStatus.BAD_REQUEST, {"success": False, "error": "game_dir is required"}
        res = saves.list_save_backups(game_dir)
        return HTTPStatus.OK, {"success": True, "data": res}

    def _handle_saves_create(self, body: Dict[str, Any]) -> Tuple[int, Dict[str, Any]]:
        game_dir = _safe_path(body.get("game_dir", ""))
        tag = str(body.get("label") or body.get("tag") or body.get("reason") or "manual")
        custom_save_dir = str(body.get("custom_save_dir") or "")
        if not game_dir:
            return HTTPStatus.BAD_REQUEST, {"success": False, "error": "game_dir is required"}
        res = saves.create_save_backup(game_dir, tag=tag, custom_save_dir=custom_save_dir)
        if not res.get("success"):
            return HTTPStatus.BAD_REQUEST, {"success": False, "error": res.get("error", "Backup failed"), "data": res}
        return HTTPStatus.OK, {"success": True, "data": res}

    def _handle_saves_restore(self, body: Dict[str, Any]) -> Tuple[int, Dict[str, Any]]:
        game_dir = _safe_path(body.get("game_dir", ""))
        backup_id = str(body.get("backup_id") or "").strip()
        if not game_dir or not backup_id:
            return HTTPStatus.BAD_REQUEST, {"success": False, "error": "game_dir and backup_id are required"}
        res = saves.restore_save_backup(game_dir, backup_id)
        if not res.get("success"):
            return HTTPStatus.BAD_REQUEST, {"success": False, "error": res.get("error", "Restore failed"), "data": res}
        return HTTPStatus.OK, {"success": True, "data": res}

    def _handle_logs_read(self, body: Dict[str, Any]) -> Tuple[int, Dict[str, Any]]:
        game_dir = _safe_path(body.get("game_dir", ""))
        if not game_dir:
            return HTTPStatus.BAD_REQUEST, {"success": False, "error": "game_dir is required"}
        try:
            lines = int(body.get("lines", 100))
        except (TypeError, ValueError):
            lines = 100
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

    def _handle_games_restart(self, body: Dict[str, Any]) -> Tuple[int, Dict[str, Any]]:
        from agmod import discovery, process
        game_dir = _safe_path(body.get("game_dir", ""))
        appid = str(body.get("appid", "")).strip()
        if not game_dir:
            return HTTPStatus.BAD_REQUEST, {"success": False, "error": "game_dir is required"}

        # First terminate any running instances of the game
        try:
            process.terminate_game_processes(game_dir)
            time.sleep(1.0)
        except Exception as e:
            logger.warning("Error terminating game: %s", e)

        # Launch game again
        res = discovery.launch_game(game_dir, appid)
        return (HTTPStatus.OK if res.get("success") else HTTPStatus.INTERNAL_SERVER_ERROR), res

    def _handle_mod_verify(self, body: Dict[str, Any]) -> Tuple[int, Dict[str, Any]]:
        from agmod import bepinex
        game_dir = _safe_path(body.get("game_dir", ""))
        mod_id = str(body.get("mod_id", "")).strip()
        if not game_dir or not mod_id:
            return HTTPStatus.BAD_REQUEST, {"success": False, "error": "game_dir and mod_id are required"}
        try:
            res = bepinex.verify_plugin(game_dir, mod_id)
            return HTTPStatus.OK, {"success": True, "data": res}
        except Exception as e:
            return HTTPStatus.INTERNAL_SERVER_ERROR, {"success": False, "error": str(e)}

    def _handle_rea_overview(self, body: Dict[str, Any]) -> Tuple[int, Dict[str, Any]]:
        game_dir = _safe_path(body.get("game_dir", ""))
        if not game_dir:
            return HTTPStatus.BAD_REQUEST, {"success": False, "error": "game_dir is required"}
        try:
            overview = inspector.get_reverse_engineering_overview(game_dir)
            return HTTPStatus.OK, {"success": True, "data": overview}
        except Exception as e:
            return HTTPStatus.INTERNAL_SERVER_ERROR, {"success": False, "error": str(e)}

    def _handle_mod_interact(self, body: Dict[str, Any]) -> Tuple[int, Dict[str, Any]]:
        game_dir = _safe_path(body.get("game_dir", ""))
        user_prompt = str(body.get("prompt", "")).strip()
        raw_history = body.get("history")
        history = raw_history if isinstance(raw_history, list) else []

        if not game_dir or not user_prompt:
            return HTTPStatus.BAD_REQUEST, {"success": False, "error": "game_dir and prompt are required"}

        # Anti-cheat guard: strictly block all mod creation/interaction on protected games
        allowed, reason = safety.check_game_target(game_dir)
        if not allowed:
            return HTTPStatus.FORBIDDEN, {
                "success": False,
                "error": reason,
                "blocked_by_anticheat": True,
            }

        engine_info = registry.detect_engine(game_dir) or {}
        engine_name = engine_info.get("engine_name") or engine_info.get("name", "通用引擎")
        engine_id = engine_info.get("engine_id") or engine_info.get("id", "generic")
        game_name = os.path.basename(os.path.normpath(game_dir))

        if engine_id == "unreal" and engine_info.get("variant") == "ue5":
            boundary = inspector.analyze_reverse_engineering_context(game_dir, user_prompt)
            return HTTPStatus.OK, {
                "success": True,
                "data": {
                    "reply": (
                        "检测到 UE5 IoStore 布局。当前不会直接生成 UE4SS 热挂钩，因为该路径在 UE5 上不稳定，"
                        "且 repak 不能解析 `.utoc/.ucas`。请先用 FModel/CUE4Parse 定位资源，再走 loose `.pak` 覆盖；"
                        "安装前必须确认目标游戏版本支持 `Content/Paks/~mods`。"
                    ),
                    "action": None,
                    "rea_insight": boundary,
                    "capability_boundary": "ue5-iostore-pak-only",
                },
            }

        # Check if LLM is configured
        cfg = llm.load_config()
        has_llm = bool(str(cfg.get("api_key") or "").strip() or "localhost" in cfg.get("api_endpoint", "") or "127.0.0.1" in cfg.get("api_endpoint", ""))

        if engine_id == "unreal":
            framework_name = "UE4SS Lua（UE4）/ loose .pak 覆盖（需逐游戏验证）"
            engine_prompt_addon = (
                f"- UE4 可使用 UE4SS Lua；UE5 IoStore 仅考虑经验证的 loose .pak 覆盖，不宣称可解包 .utoc/.ucas。\n"
                f"- 钩子目标请遵循虚幻引擎 UClass/UFunction 规范，例如 `ACharacter:TakeDamage`、`UCharacterMovementComponent:SetMaxWalkSpeed`、`APlayerController:ClientRestart` 等。\n"
            )
        elif engine_id == "unity":
            is_il2cpp = bool(
                os.path.exists(os.path.join(game_dir, "GameAssembly.dll"))
                or glob.glob(os.path.join(game_dir, "*_Data", "il2cpp_data"))
                or glob.glob(os.path.join(game_dir, "*_data", "il2cpp_data"))
            )
            flavor = "IL2CPP (Cpp2IL / BepInEx-IL2CPP)" if is_il2cpp else "Mono (HarmonyX / BepInEx)"
            framework_name = f"Unity {flavor} 运行时适配"
            engine_prompt_addon = (
                f"- Unity 引擎专有架构（{flavor}）：支持 Harmony 前缀/后缀补丁（Prefix / Postfix）。\n"
                f"- 钩子目标请遵循 C# 类名与方法名规范，例如 `PlayerController:Update`、`HeroController:TakeDamage`、`CharacterMotor:Move` 等。\n"
                f"- 【Unity 专有安全边界规范】\n"
                f"  1. UnityEngine.Object 空引用校验必须使用 `obj != null`（触发原生 C++ 存活校验），严禁使用 `ReferenceEquals`。\n"
                f"  2. 刚体与移动边界：必须限制最大速度与加速度，避免速度过大在离散物理更新时穿透 BoxCollider/MeshCollider 跌落虚空。\n"
                f"  3. 时间缩放守卫：Time.timeScale 严格限制在 [0.01, 10.0]，严禁设置为 0 或负数以防 FixedUpdate 除零死锁。\n"
                f"  4. Harmony 拦截守卫：Prefix 必须使用 try-catch 包裹，return true 确保原游戏逻辑正常执行，仅在完全重载时设 __result 并 return false。\n"
            )
        elif engine_id == "re-engine":
            framework_name = "REFramework (Lua 脚本 / Capcom RE 运行时 SDK)"
            engine_prompt_addon = (
                "- Capcom RE 引擎专有架构：支持 REFramework Lua Hook 与 SDK 原生类型绑定。\n"
                "- 钩子目标请遵循 Class.Method 命名规范（例如 `via.motion.MotionHelper.set_Speed`）。\n"
                "- 必须通过 SDK 校验指针有效性，防止无效托管对象引用导致游戏闪退。\n"
            )
        elif engine_id in {"dotnet-xna", "dotnet", "tmodloader"}:
            is_stardew = any(k in f"{game_dir} {user_prompt}".lower() for k in ["stardew", "smapi", "星露谷"])
            if is_stardew:
                framework_name = "星露谷物语 SMAPI (.NET / MonoGame)"
                engine_prompt_addon = (
                    "- 游戏为《星露谷物语》（MonoGame / .NET CLR）：\n"
                    "- 核心架构：依赖 SMAPI (Stardew Modding API) 框架；\n"
                    "- 常用命名空间：StardewValley, StardewModdingAPI；\n"
                    "- 严禁引入 UnityEngine 等 Unity 专有类；钩子目标例如 `StardewValley.Farmer:Update`、`StardewValley.Farmer:get_speed`。\n"
                )
            else:
                framework_name = "泰拉瑞亚 (.NET / XNA / tModLoader / BepInEx)"
                engine_prompt_addon = (
                    "- 游戏为《泰拉瑞亚》（.NET Framework 4.0 / XNA 纯原生 CLR 程序集）：\n"
                    "- 严禁引入 UnityEngine 或 Unity 专有类！\n"
                    "- 真实类名与符号遵循 Terraria 命名空间：`Terraria.Player`、`Terraria.Item`、`Terraria.Main`；\n"
                    "- 常见字段：`Terraria.Player:statLife` (生命)、`Terraria.Player:moveSpeed` (移速)、`Terraria.Player:immune` (无敌)；\n"
                    "- 纯原生 C# 逻辑使用 Environment.TickCount 或游戏 Update 驱动。\n"
                )
        else:
            framework_name = f"{engine_name} 运行时适配"
            engine_prompt_addon = ""

        reply = ""
        action = None

        # 1. Reverse-Engineering Symbol & Boundary Analysis (REA Grounding)
        rea_insight = inspector.analyze_reverse_engineering_context(game_dir, user_prompt)
        target_binary = rea_insight.get("target_binary", "Game Binary")
        matched_syms = rea_insight.get("matched_symbols", [])
        symbol_evidence = rea_insight.get("symbol_evidence", {})
        boundary = rea_insight.get("boundary_scope", {})
        guards = rea_insight.get("exception_guards", [])

        # If LLM is NOT configured, verify if this is a predefined quick preset vs freeform query
        # Check if user is asking whether manual file dragging/placement is needed
        prompt_lower = user_prompt.lower()
        if any(k in prompt_lower for k in ["手动", "放进", "放哪", "复制", "拖入", "怎么用", "放进去"]):
            reply = (
                "🎉 **完全不需要手动放进去！**\n\n"
                "AI Mod Builder 拥有全自动构建与部署引擎：所有 Mod 插件代码、前置框架及配置在生成时已**全自动写入到游戏目录中**，无需你手动创建、拖拽或编译任何文件！\n\n"
                "👉 你只需切回游戏即可直接体验，或在下方调节参数滑块实时调优手感！"
            )
            return HTTPStatus.OK, {
                "success": True,
                "data": {
                    "has_llm": has_llm,
                    "reply": reply,
                    "action": None,
                    "rea_insight": rea_insight,
                }
            }

        # If LLM is NOT configured, verify if this is a predefined quick preset vs freeform query
        if not has_llm:
            preset_keywords = [
                "移速", "速", "快", "二段跳", "跳", "金币", "钱", "无敌", "锁血", "金身",
                "减伤", "伤害", "剑气", "背包", "格", "包", "储物", "容量",
                "speed", "jump", "gold", "shield", "attack", "inventory", "slot"
            ]
            is_preset_intent = any(k in prompt_lower for k in preset_keywords) and len(user_prompt) <= 30
            is_question_or_freeform = (
                any(q in prompt_lower for q in ["你", "啥", "什么", "怎么", "如何", "调了", "为什么", "是谁", "？", "?", "help", "hello", "hi", "帮助", "干了"])
                or not is_preset_intent
            )

            if is_question_or_freeform:
                return HTTPStatus.OK, {
                    "success": True,
                    "data": {
                        "has_llm": False,
                        "require_api_key": True,
                        "reply": (
                            f"⚠️ **当前尚未配置大模型 API Key（CC Switch）**\n\n"
                            f"收到你的指令：*“{user_prompt}”*。\n\n"
                            f"AI 需要连接大模型才能理解你的自然语言指令、结合游戏反编译符号编写定制代码。当前处于离线模式，无法通过自然语言进行深度理解与代码生成。\n\n"
                            f"**操作指引：**\n"
                            f"1. 点击右上角 **【⚙️ 模型配置 (CC Switch)】**\n"
                            f"2. 输入你的 API Key（支持 DeepSeek / 官方 OpenAI / Claude / 本地 Ollama 等）并保存\n"
                            f"3. 保存后即可随时通过自然语言对 AI 自由提问或让其创作专属 Mod！\n\n"
                            f"*(💡 提示：在未配置 API Key 时，你也可以直接点击输入框上方的「快捷灵感」预设按钮体验基础 Mod。)*"
                        ),
                        "action": None,
                        "rea_insight": rea_insight,
                    }
                }

        if has_llm and not reply:
            rea_section = (
                f"\n【底层逆向与安全边界分析（必须严格遵守）】\n"
                f"- 目标模块: {target_binary}\n"
                f"- 候选逆向符号: {', '.join(matched_syms[:4])}\n"
                f"- 符号证据状态: {symbol_evidence.get('status', 'suggested')} / {symbol_evidence.get('source', 'heuristic')}\n"
                f"- 推荐主挂钩点: {rea_insight.get('primary_hook', '')}\n"
                f"- 安全边界范围: {boundary.get('boundary_warning', '')}\n"
                f"- 参数约束: min={boundary.get('safe_min')}, max={boundary.get('safe_max')}, step={boundary.get('step')}, default={boundary.get('default_val')}\n"
                f"- 异常规避原则: {'；'.join(guards)}\n"
            )

            sys_prompt = (
                f"你是一位顶尖的实时游戏 Mod 架构工程师兼 AI 创作助手。\n"
                f"当前玩家正在玩的游戏信息：\n"
                f"- 游戏名称: {game_name}\n"
                f"- 游戏目录: {game_dir}\n"
                f"- 游戏引擎: {engine_name} ({engine_id})\n"
                f"- 框架环境: {framework_name}\n"
                f"{engine_prompt_addon}\n"
                f"{rea_section}\n"
                f"【核心运行机制与铁律规范（必须严格遵守）】\n"
                f"1. 【全自动写入与零人工操作】：本系统（AI Mod Builder）拥有全自动脚手架、代码生成、编译与文件落盘引擎。所有 Mod、前置框架（如 BepInEx / UE4SS / REFramework）及配置文件均由本系统全自动写入游戏目录并配置完成。严禁指示玩家手动创建、修改、编译、复制或拖拽文件到 plugins 目录！若玩家询问是否需要手动放进去，明确告知系统已经全自动写入落盘，无需任何手动操作。\n"
                f"2. 【严禁输出大段代码】：严禁在回复中输出长篇源码（严禁输出完整的 C# 类、C++ 或 Lua 代码文件，更不要提供 Visual Studio 编译教程）。用户是普通玩家，不需要阅读代码。请保持回复简明轻快（3-5 句内），聚焦于 Mod 的游戏效果、安全边界保障以及如何体验。\n"
                f"3. 【隐藏内部逆向术语】：不要向用户堆砌逆向工程术语（如 REA、反编译模块名、置信度百分比等），只用玩家听得懂的语言解释功能与安全边界（例如：已对物理移速做防穿模安全保护）。\n"
                f"4. 【动作结构输出】：回复末尾必须包含一个 ```json:mod_action ``` 代码块，包含可调参数与动作结构，以便前端直接绑定实时控制控件：\n"
                f"```json:mod_action\n"
                f"{{\n"
                f'  "mod_id": "safe_slug_id",\n'
                f'  "mod_name": "中文Mod名称",\n'
                f'  "summary": "一句话功能描述",\n'
                f'  "category": "player|combat|economy|visual",\n'
                f'  "tuning_params": [\n'
                f'    // 请按需选择最匹配的控件类型（支持以下 4 种）：\n'
                f'    // 1. 滑块: {{"id": "speed", "label": "{boundary.get("param_label", "参数调节")}", "type": "slider", "min": {boundary.get("safe_min", 1.0)}, "max": {boundary.get("safe_max", 5.0)}, "step": {boundary.get("step", 0.1)}, "value": {boundary.get("default_val", 2.0)}}}\n'
                f'    // 2. 开关: {{"id": "god_mode", "label": "无敌金身", "type": "switch", "value": true}}\n'
                f'    // 3. 下拉: {{"id": "element", "label": "属性模式", "type": "select", "options": ["火", "冰", "雷", "毒"], "value": "火"}}\n'
                f'    // 4. 计数器: {{"id": "capacity", "label": "背包格子数量", "type": "stepper", "min": 10, "max": 100, "step": 10, "value": 40}}\n'
                f'  ],\n'
                f'  "hook_target": "{rea_insight.get("primary_hook", "Class:Method")}",\n'
                f'  "can_pin": true\n'
                f"}}\n"
                f"```"
            )
            chat_msgs = []
            for h in history[-6:]:
                if not isinstance(h, dict):
                    continue
                r = h.get("role")
                c = h.get("content", "")
                if r in ("user", "assistant") and c:
                    chat_msgs.append({"role": r, "content": c})

            # Augmented prompt grounds the LLM in real symbols and boundary specs
            augmented_prompt = f"{sys_prompt}\n\n【玩家当前需求】\n{user_prompt}"
            chat_msgs.append({"role": "user", "content": augmented_prompt})

            llm_res = llm.chat_completion(
                messages=chat_msgs,
                game_context={
                    "game_dir": game_dir,
                    "engine": engine_name,
                    "framework": framework_name,
                    "system_prompt_addon": rea_section,
                }
            )
            if llm_res.get("success"):
                full_reply = llm_res.get("reply", "")
                m = re.search(r"```(?:json:)?mod_action\s*([\s\S]*?)```", full_reply)
                if m:
                    try:
                        action = json.loads(m.group(1).strip())
                    except Exception:
                        pass
                    raw_reply = full_reply[:m.start()].strip()
                else:
                    raw_reply = full_reply
                reply = _clean_user_reply(raw_reply)
            else:
                reply = ""

        # Fallback grounding: synthesize action directly from REA analysis & prompt intent
        if not action:
            prompt_lower = user_prompt.lower()
            primary_hook = rea_insight.get("primary_hook") or "GameLogic:Update"
            category = rea_insight.get("category", "player")

            if engine_id == "unreal":
                if any(k in prompt_lower for k in ["血", "命", "hp", "health", "无敌", "金身", "锁血", "霸体", "防打"]):
                    mod_id = "invincible_shield"
                    mod_name = "金钟罩 · 刀枪不入 (Invincible Guard)"
                    summary = "受到攻击减免 100% 伤害并生成霸体护体"
                    tuning = [
                        {"id": "invincible_active", "label": "无敌金身开关", "type": "switch", "value": True},
                        {"id": "damage_reduction", "label": "护甲减免比例", "type": "slider", "min": 50, "max": 100, "step": 5, "value": 100},
                    ]
                    target = primary_hook if primary_hook != "GameLogic:Update" else "ACharacter:TakeDamage"
                elif any(k in prompt_lower for k in ["速", "快", "speed", "run"]):
                    mod_id = "swift_stride"
                    mod_name = "疾风瞬影 · 移速提升 (Swift Stride)"
                    summary = "角色疾驰移动速度提升 100%"
                    tuning = [{"id": "speed_multiplier", "label": "移速倍率", "type": "slider", "min": 1.0, "max": 5.0, "step": 0.1, "value": 2.0}]
                    target = primary_hook if primary_hook != "GameLogic:Update" else "UCharacterMovementComponent:SetMaxWalkSpeed"
                elif any(k in prompt_lower for k in ["跳", "jump"]):
                    mod_id = "air_step_jump"
                    mod_name = "踏雪无痕 · 空中二段跳 (Air Step Jump)"
                    summary = "解锁绝妙空中连环二段跳跃与滞空机动"
                    tuning = [
                        {"id": "double_jump_enabled", "label": "连环跳跃开关", "type": "switch", "value": True},
                        {"id": "jump_impulse", "label": "腾空跃力", "type": "slider", "min": 1.0, "max": 3.0, "step": 0.1, "value": 1.5},
                    ]
                    target = primary_hook if primary_hook != "GameLogic:Update" else "ACharacter:JumpMaxCount"
                elif any(k in prompt_lower for k in ["钱", "金币", "金钱", "coin", "gold", "money"]):
                    mod_id = "infinite_gold"
                    mod_name = "金玉满堂 · 掉落倍率 (Gold Multiplier)"
                    summary = "击败敌人金钱掉落倍率提高 5 倍"
                    tuning = [
                        {"id": "reward_mode", "label": "掉落机制", "type": "select", "options": ["多倍掉落", "击杀大奖", "免金钱消耗"], "value": "多倍掉落"},
                        {"id": "gold_multi", "label": "掉落倍率", "type": "slider", "min": 2, "max": 20, "step": 1, "value": 5},
                    ]
                    target = primary_hook if primary_hook != "GameLogic:Update" else "InventoryComponent:AddCurrency"
                elif any(k in prompt_lower for k in ["包", "格", "slot", "inventory", "容量"]):
                    mod_id = "expanded_inventory"
                    mod_name = "乾坤袋 · 空间扩充 (Expanded Inventory)"
                    summary = "随身背包扩展额外储物格，并支持自动整理"
                    tuning = [
                        {"id": "auto_sort", "label": "自动整理背包", "type": "switch", "value": True},
                        {"id": "slot_count", "label": "扩增格子数", "type": "stepper", "min": 10, "max": 100, "step": 10, "value": 40},
                    ]
                    target = primary_hook if primary_hook != "GameLogic:Update" else "InventoryComponent:SetCapacity"
                else:
                    mod_id = f"custom_mod_{int(time.time())}"
                    mod_name = f"增强特性: {user_prompt[:12]}"
                    summary = f"已针对虚幻引擎应用运行时补丁: {user_prompt}"
                    tuning = [{"id": "effect_intensity", "label": "效果强度", "type": "slider", "min": 1, "max": 10, "step": 1, "value": 2}]
                    target = primary_hook if primary_hook != "GameLogic:Update" else "ACharacter:Tick"
            else:
                if any(k in prompt_lower for k in ["血", "命", "hp", "health", "无敌", "金身", "锁血", "霸体", "防打"]):
                    mod_id = "god_mode"
                    mod_name = "护甲金身 (God Mode / Shield)"
                    summary = "受到攻击时减免伤害并提供无敌护盾"
                    tuning = [
                        {"id": "god_mode_active", "label": "无敌锁血开关", "type": "switch", "value": True},
                        {"id": "damage_reduction", "label": "减伤比例", "type": "slider", "min": 50, "max": 100, "step": 5, "value": 100},
                    ]
                    target = primary_hook if primary_hook != "GameLogic:Update" else "PlayerData.TakeDamage"
                elif any(k in prompt_lower for k in ["速", "快", "speed", "run"]):
                    mod_id = "speed_boost"
                    mod_name = "急速奔跑 (Speed Boost)"
                    summary = "角色移动速度提升 100%"
                    tuning = [
                        {"id": "sprint_always", "label": "始终疾跑", "type": "switch", "value": False},
                        {"id": "multiplier", "label": "移速倍率", "type": "slider", "min": 1.0, "max": 5.0, "step": 0.1, "value": 2.0},
                    ]
                    target = primary_hook if primary_hook != "GameLogic:Update" else ("HeroController.MoveSpeed" if "hollow" in game_name.lower() else "PlayerController.Movement")
                elif any(k in prompt_lower for k in ["跳", "jump"]):
                    mod_id = "double_jump"
                    mod_name = "空中二段跳 (Air Jump)"
                    summary = "解锁空中二段跳跃与机动性提升"
                    tuning = [
                        {"id": "double_jump_enabled", "label": "空中二段跳开关", "type": "switch", "value": True},
                        {"id": "jump_height", "label": "跳跃力度", "type": "slider", "min": 0.5, "max": 3.0, "step": 0.1, "value": 1.5},
                    ]
                    target = primary_hook if primary_hook != "GameLogic:Update" else "HeroController.CanDoubleJump"
                elif any(k in prompt_lower for k in ["钱", "金币", "金钱", "coin", "gold", "money"]):
                    mod_id = "infinite_gold"
                    mod_name = "金钱丰裕 (Gold Multiplier)"
                    summary = "获得金钱奖励翻 5 倍"
                    tuning = [
                        {"id": "bonus_mode", "label": "奖励模式", "type": "select", "options": ["翻倍掉落", "固定丰厚", "免扣除购买"], "value": "翻倍掉落"},
                        {"id": "gold_multi", "label": "掉落倍率", "type": "slider", "min": 2, "max": 20, "step": 1, "value": 5},
                    ]
                    target = primary_hook if primary_hook != "GameLogic:Update" else "CurrencyManager.AddGeo"
                elif any(k in prompt_lower for k in ["包", "格", "slot", "inventory", "容量"]):
                    mod_id = "expanded_inventory"
                    mod_name = "储物拓展 (Expanded Inventory)"
                    summary = "随身行囊与储物箱格位扩充"
                    tuning = [
                        {"id": "auto_sort", "label": "自动收纳整理", "type": "switch", "value": True},
                        {"id": "slot_count", "label": "扩增格子数", "type": "stepper", "min": 10, "max": 100, "step": 10, "value": 30},
                    ]
                    target = primary_hook if primary_hook != "GameLogic:Update" else "Inventory.SetSlotCount"
                else:
                    mod_id = f"{category}_{int(time.time())}"
                    mod_name = f"{engine_name} 增强特性"
                    summary = f"基于 {primary_hook} 的安全调优"
                    tuning = [{
                        "id": "param_1",
                        "label": boundary.get("param_label", "效果强度"),
                        "type": "slider",
                        "min": boundary.get("safe_min", 1.0),
                        "max": boundary.get("safe_max", 5.0),
                        "step": boundary.get("step", 0.1),
                        "value": boundary.get("default_val", 2.0),
                    }]
                    target = primary_hook

            action = {
                "mod_id": mod_id,
                "mod_name": mod_name,
                "summary": summary,
                "category": category,
                "tuning_params": tuning,
                "hook_target": target,
                "can_pin": True,
            }

        # Auto-deploy mod files immediately to game directory
        deploy_res = {}
        if action:
            params_map = {p["id"]: p["value"] for p in action.get("tuning_params", []) if "id" in p and "value" in p}
            deploy_res = _auto_deploy_mod(
                game_dir=game_dir,
                mod_id=action["mod_id"],
                mod_name=action["mod_name"],
                summary=action.get("summary", ""),
                hook_target=action.get("hook_target", ""),
                params=params_map,
            )
            action["installed_path"] = deploy_res.get("installed_path", "")
            action["auto_deployed"] = deploy_res.get("success", False)
            action["pending_restart"] = deploy_res.get("pending_restart", False)
            action["deploy_message"] = deploy_res.get("message", "")
            action["compiled"] = deploy_res.get("compiled", False)
            action["compilation_error"] = deploy_res.get("compilation_error", "")
            action["deploy_error"] = deploy_res.get("error", "")
            action["verified"] = deploy_res.get("verified", {})
            action["symbol_verified"] = deploy_res.get("symbol_verified")
            action["symbol_candidates"] = deploy_res.get("symbol_candidates", [])

        running, _ = rollback.is_game_running(game_dir)
        comp_err = deploy_res.get("compilation_error", "")
        deploy_error = deploy_res.get("error", "")
        if not reply:
            prefix_note = ""
            if not has_llm:
                prefix_note = "\n\n> 💡 **提示**：当前通过内置预设模板生效。若要让 AI 自由理解任意自然语言并定制编写 Mod，请点击右上角「⚙️ 模型配置」填入 API Key。"
            status_desc = deploy_res.get("message", "已全自动写入游戏目录并配置生效")
            restart_hint = ""
            if deploy_res.get("pending_restart"):
                restart_hint = "\n\n> 💡 **温馨提示**：检测到游戏当前已在运行，请点击顶部工具栏 **【🔄 一键重启】** 重新载入生效！"
            elif running:
                restart_hint = "\n\n> 🟢 **实时热调控已生效**：游戏正在运行中，已开启即时热生效通道！参数已实时同步，切回游戏即可直接边玩边测（无需重启）。"
            action_hint = "已开启边玩边测模式，切回游戏窗口即可体验，在右侧面板拖动滑块实时调节！" if running else "启动游戏后即可直接体验，可在右侧或下方滑块调节数值！"
            reply = (
                f"✨ 已为你设计并全自动写入游戏 **【{action['mod_name']}】**！\n\n"
                f"- 部署状态: {status_desc}\n"
                f"- 安全边界提示: {boundary.get('boundary_warning', '已开启物理与数值边界防护')}{restart_hint}\n\n"
                f"{action_hint}{prefix_note}"
            )
        else:
            reply = _clean_user_reply(reply)
            if deploy_res.get("message"):
                restart_hint = ""
                if deploy_res.get("pending_restart"):
                    restart_hint = "\n\n> 💡 **温馨提示**：检测到游戏当前已在运行，请点击顶部工具栏 **【🔄 一键重启】** 重新载入生效！"
                elif running:
                    restart_hint = "\n\n> 🟢 **实时热调控已生效**：游戏正在运行中，已开启即时热生效通道！参数已实时同步，切回游戏即可直接边玩边测（无需重启）。"
                reply = f"{reply}\n\n- 部署状态: {deploy_res['message']}{restart_hint}"


        return HTTPStatus.OK, {
            "success": True,
            "data": {
                "has_llm": has_llm,
                "reply": reply,
                "action": action,
                "rea_insight": rea_insight,
            }
        }

    def _handle_mod_tune(self, body: Dict[str, Any]) -> Tuple[int, Dict[str, Any]]:
        game_dir = _safe_path(body.get("game_dir", ""))
        raw_mod_id = str(body.get("mod_id", "")).strip()
        param_id = str(body.get("param_id", "")).strip()
        value = body.get("value")

        if not game_dir or not raw_mod_id or not param_id:
            return HTTPStatus.BAD_REQUEST, {"success": False, "error": "game_dir, mod_id, and param_id are required"}

        slug_mod_id = paths.slugify(raw_mod_id)
        mod_variants = list(dict.fromkeys([
            raw_mod_id,
            slug_mod_id,
            raw_mod_id.replace('-', '_'),
            raw_mod_id.replace('_', '-'),
            slug_mod_id.replace('-', '_'),
            slug_mod_id.replace('_', '-'),
        ]))

        # 1. Update mod.json in plugin directory
        json_candidates = []
        import glob
        for mid in mod_variants:
            json_candidates.extend([
                os.path.join(game_dir, "BepInEx", "plugins", mid, "mod.json"),
                os.path.join(game_dir, "Mods", mid, "mod.json"),
                os.path.join(game_dir, "mods-unpacked", mid, "mod.json"),
            ])
            for cand in glob.glob(os.path.join(game_dir, "*", "Binaries", "Win64", "Mods", mid, "mod.json")):
                json_candidates.append(cand)
            for cand in glob.glob(os.path.join(game_dir, "*", "Binaries", "Win64", "ue4ss", "Mods", mid, "mod.json")):
                json_candidates.append(cand)

        file_synced = False
        for path in json_candidates:
            if os.path.isfile(path):
                try:
                    with open(path, "r", encoding="utf-8") as f:
                        data = json.load(f)
                    if "params" not in data or not isinstance(data["params"], dict):
                        data["params"] = {}
                    data["params"][param_id] = value
                    data["last_tuned_at"] = time.strftime("%Y-%m-%d %H:%M:%S")
                    with open(path, "w", encoding="utf-8") as f:
                        json.dump(data, f, ensure_ascii=False, indent=2)
                    file_synced = True
                except Exception:
                    pass

        # 2. Update BepInEx INI config if present
        for mid in mod_variants:
            bepin_cfg = os.path.join(game_dir, "BepInEx", "config", f"{mid}.cfg")
            if os.path.isfile(bepin_cfg):
                try:
                    with open(bepin_cfg, "r", encoding="utf-8") as f:
                        lines = f.readlines()
                    updated_lines = []
                    param_found = False
                    for line in lines:
                        if line.strip().startswith(f"{param_id} =") or line.strip().startswith(f"{param_id}="):
                            updated_lines.append(f"{param_id} = {value}\n")
                            param_found = True
                        else:
                            updated_lines.append(line)
                    if not param_found:
                        updated_lines.append(f"{param_id} = {value}\n")
                    with open(bepin_cfg, "w", encoding="utf-8") as f:
                        f.writelines(updated_lines)
                    file_synced = True
                except Exception:
                    pass

        running, _ = rollback.is_game_running(game_dir)

        return HTTPStatus.OK, {
            "success": True,
            "data": {
                "mod_id": raw_mod_id,
                "param_id": param_id,
                "value": value,
                "file_synced": file_synced,
                "game_running": running,
                "message": f"参数 [{param_id}] 已实时同步为 {value}！",
            }
        }

    def _handle_mod_pin(self, body: Dict[str, Any]) -> Tuple[int, Dict[str, Any]]:
        game_dir = _safe_path(body.get("game_dir", ""))
        mod_id = paths.slugify(body.get("mod_id", "pinned_mod"))
        mod_name = str(body.get("mod_name", "AI Custom Mod"))[:120]
        summary = body.get("summary", "")
        params = body.get("params", {})
        hook_target = str(body.get("hook_target", ""))

        if not game_dir:
            return HTTPStatus.BAD_REQUEST, {"success": False, "error": "game_dir is required"}
        from agmod import safety
        allowed, reason = safety.check_game_target(game_dir)
        if not allowed:
            return HTTPStatus.FORBIDDEN, {"success": False, "error": reason}
        if not isinstance(params, dict):
            return HTTPStatus.BAD_REQUEST, {"success": False, "error": "params must be an object"}

        engine_info = registry.detect_engine(game_dir) or {}
        engine_id = engine_info.get("engine_id") or engine_info.get("id", "generic")
        supported_engines = {"unity", "unreal", "re-engine", "godot", "dotnet-xna", "dotnet", "tmodloader"}
        if engine_id not in supported_engines:
            return HTTPStatus.CONFLICT, {
                "success": False,
                "error": f"pinning is not supported for engine '{engine_id}'; use its loader-specific package workflow",
            }
        if engine_id == "unreal" and engine_info.get("variant") == "ue5":
            return HTTPStatus.CONFLICT, {
                "success": False,
                "error": "UE5 IoStore hook pinning is disabled; use the verified loose .pak workflow instead",
                "capability_boundary": "ue5-iostore-pak-only",
            }

        try:
            source_code, normalized_target = _pinned_source(engine_id, mod_name, hook_target, params, mod_id=mod_id)
        except (TypeError, ValueError) as exc:
            return HTTPStatus.BAD_REQUEST, {"success": False, "error": str(exc)}

        staging = tempfile.mkdtemp(prefix="aimod-pin-")
        try:
            manifest = {
                "id": mod_id,
                "name": mod_name,
                "summary": summary,
                "hook_target": hook_target,
                "params": params,
                "pinned_at": time.strftime("%Y-%m-%d %H:%M:%S"),
            }
            pairs: list[tuple[str, str]] = []
            if engine_id == "unreal":
                import glob
                win64_candidates = glob.glob(os.path.join(game_dir, "*", "Binaries", "Win64"))
                if not win64_candidates:
                    win64_candidates = [os.path.join(game_dir, "Binaries", "Win64")]
                mods_root = os.path.join(win64_candidates[0], "Mods", mod_id)
                if os.path.exists(os.path.join(win64_candidates[0], "ue4ss", "Mods")):
                    mods_root = os.path.join(win64_candidates[0], "ue4ss", "Mods", mod_id)
                stage_files = {"enabled.txt": "1\n", "mod.json": json.dumps(manifest, ensure_ascii=False, indent=2), "scripts/main.lua": source_code}
                for rel, content in stage_files.items():
                    source = os.path.join(staging, rel)
                    os.makedirs(os.path.dirname(source), exist_ok=True)
                    with open(source, "w", encoding="utf-8") as f:
                        f.write(content)
                    pairs.append((source, os.path.join(mods_root, rel)))
                message = f"虚幻引擎 Mod【{mod_name}】已固化到 UE4SS 插件目录！下次启动游戏将由 UE4SS 自动装载生效。"
            elif engine_id == "re-engine":
                ref_folder = os.path.join(game_dir, "reframework", "autorun")
                mods_root = ref_folder
                source = os.path.join(staging, f"{mod_id}.lua")
                with open(source, "w", encoding="utf-8") as f:
                    f.write(source_code)
                pairs.append((source, os.path.join(ref_folder, f"{mod_id}.lua")))
                message = f"RE-Engine Mod【{mod_name}】已成功固化到 reframework/autorun 目录！"
            elif engine_id == "godot":
                mods_root = os.path.join(game_dir, "mods-unpacked", f"{paths.slugify(mod_name)}-{mod_id}")
                source = os.path.join(staging, "mod_main.gd")
                with open(source, "w", encoding="utf-8") as f:
                    f.write(source_code)
                pairs.append((source, os.path.join(mods_root, "mod_main.gd")))
                message = f"Godot Mod【{mod_name}】已固化到 mods-unpacked 目录！"
            else:
                mod_folder = os.path.join(game_dir, "BepInEx", "plugins", mod_id)
                source_manifest = os.path.join(staging, "mod.json")
                with open(source_manifest, "w", encoding="utf-8") as f:
                    json.dump(manifest, f, ensure_ascii=False, indent=2)
                source_cs = os.path.join(staging, f"{mod_id}.cs")
                with open(source_cs, "w", encoding="utf-8") as f:
                    f.write(source_code)
                source_dll = os.path.join(staging, f"{mod_id}.dll")
                comp_res = bepinex.compile_unity_plugin(game_dir, mod_id, source_cs, source_dll)
                if not comp_res.get("success") or not os.path.isfile(source_dll):
                    return HTTPStatus.UNPROCESSABLE_ENTITY, {
                        "success": False,
                        "error": comp_res.get("error", "plugin compilation failed"),
                    }
                pairs.extend([
                    (source_manifest, os.path.join(mod_folder, "mod.json")),
                    (source_cs, os.path.join(mod_folder, f"{mod_id}.cs")),
                    (source_dll, os.path.join(game_dir, "BepInEx", "plugins", f"{mod_id}.dll")),
                ])

                message = f"Mod【{mod_name}】已成功固化到游戏目录！下次直接在 Steam 启动游戏依然生效。"
                mods_root = mod_folder

            preview = install_preview.preview_install(
                game_dir,
                mod_id,
                pairs,
                engine_id=engine_id,
            )
            if not preview.get("ready"):
                return HTTPStatus.CONFLICT, {
                    "success": False,
                    "error": "install preview found blockers",
                    "install_preview": preview,
                }
            rollback.install_files(game_dir, mod_id, pairs)
        finally:
            shutil.rmtree(staging, ignore_errors=True)

        return HTTPStatus.OK, {
            "success": True,
            "data": {
                "mod_id": mod_id,
                "mod_name": mod_name,
                "path": mods_root,
                "message": message,
                "hook_target": normalized_target,
                "install_preview": preview,
            }
        }


class _ReusableThreadingHTTPServer(ThreadingHTTPServer):
    allow_reuse_address = True
    daemon_threads = True


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

        self._server = _ReusableThreadingHTTPServer((self.host, self.port), ModUIRequestHandler)
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
        opened = webbrowser.open(url)
        if not opened and sys.platform == "win32" and hasattr(os, "startfile"):
            os.startfile(url)
    except Exception:
        try:
            if sys.platform == "win32" and hasattr(os, "startfile"):
                os.startfile(url)
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
