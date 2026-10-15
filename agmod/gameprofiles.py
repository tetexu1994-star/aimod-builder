"""Per-engine and per-game mod recommendation profiles + capability boundaries.

Gives the agent a reliable "what can I actually do with THIS game" answer
instead of a one-size-fits-all template, and lets game-specific knowledge
accumulate over time (add entries to GAME_NOTES as they are verified).
"""
from __future__ import annotations

import os

# Engine-level profiles: grounded in how each engine actually mods, not guesses.
ENGINE_PROFILES = {
    "unreal-ue5": {
        "summary": "UE5 (IoStore)。改配置/资源走 pak 覆盖；改逻辑难。",
        "capabilities": {
            "config_edit": True,
            "pak_override": True,
            "memory_edit": True,
            "structure_recovery": "manual (FModel / CUE4Parse)",
            "hook": "limited (UE4SS 对 UE5 不稳定)",
        },
        "recommendations": [
            {"title": "改画质/性能/按键", "route": "config", "difficulty": "简单",
             "how": "用 list_unreal_configs 找 Saved/Config/Windows/ 下的 GameUserSettings.ini / Input.ini，改完走 ini/pak 覆盖"},
            {"title": "改数值/换资源", "route": "pak", "difficulty": "中等",
             "how": "FModel/CUE4Parse 解包 .utoc/.ucas 定位资源 → 修改 → build_unreal_pak_mod 打 loose .pak → 确认游戏支持 ~mods 后安装"},
            {"title": "临时改内存数值", "route": "memory", "difficulty": "中等",
             "how": "scan_start/scan_next 扫描目标数值 → write_memory（重启失效）"},
            {"title": "改逻辑/加功能/Hook", "route": "hook", "difficulty": "难",
             "how": "UE5 上 UE4SS 不稳定，需 C++ 插件；等结构恢复能力就绪后再攻"},
        ],
    },
    "unreal-ue4": {
        "summary": "UE4。UE4SS Lua 稳定可用，pak 覆盖也可。",
        "capabilities": {
            "config_edit": True,
            "pak_override": True,
            "memory_edit": True,
            "structure_recovery": "UE4SS dumper / FModel",
            "hook": "UE4SS Lua (稳定)",
        },
        "recommendations": [
            {"title": "改逻辑/Hook", "route": "ue4ss", "difficulty": "中等",
             "how": "scaffold_ue4ss_mod 生成 Lua Hook → install_ue4ss_mod"},
            {"title": "改数值/换资源", "route": "pak", "difficulty": "中等",
             "how": "UnrealPak 打包覆盖 → install_unreal_pak_mod"},
            {"title": "改配置", "route": "config", "difficulty": "简单", "how": "改 .ini"},
        ],
    },
    "unity": {
        "summary": "Unity。BepInEx Harmony patch 做持久 mod，内存改值做临时。",
        "capabilities": {
            "config_edit": False,
            "pak_override": False,
            "memory_edit": True,
            "structure_recovery": "ilspycmd (Mono) / Il2CppDumper (IL2CPP) / rea managed-members",
            "hook": "BepInEx Harmony (稳定)",
        },
        "recommendations": [
            {"title": "改字段/加功能（持久）", "route": "bepinex", "difficulty": "中等",
             "how": "dump_structures 找字段 → scaffold_mod 生成 Harmony patch → build_mod"},
            {"title": "临时改值", "route": "memory", "difficulty": "简单",
             "how": "scan_start/scan_next 扫描 → write_memory"},
        ],
    },
    "dotnet-xna": {
        "summary": ".NET/XNA/FNA (泰拉瑞亚/星露谷)。托管程序集，反编译即得结构。",
        "capabilities": {
            "config_edit": False,
            "pak_override": False,
            "memory_edit": True,
            "structure_recovery": "ilspycmd / rea managed-members (开箱即用)",
            "hook": "tModLoader / SMAPI",
        },
        "recommendations": [
            {"title": "做 Mod（持久）", "route": "loader", "difficulty": "中等",
             "how": "Terraria 用 scaffold_tmod_mod；星露谷用 SMAPI"},
            {"title": "临时改值", "route": "memory", "difficulty": "简单", "how": "scan_start/write_memory"},
        ],
    },
    "default": {
        "summary": "其它引擎。可靠的是内存改值 + rea 逆向。",
        "capabilities": {
            "config_edit": False,
            "pak_override": False,
            "memory_edit": True,
            "structure_recovery": "rea (Ghidra/IDA，需本地装反编译器)",
            "hook": "未覆盖",
        },
        "recommendations": [
            {"title": "临时改值", "route": "memory", "difficulty": "简单",
             "how": "scan_start/scan_next 扫描 → write_memory"},
            {"title": "逆向分析", "route": "rea", "difficulty": "难",
             "how": "rea_disassemble / rea_call_graph 分析函数（需 Ghidra/IDA）"},
        ],
    },
}

# Game-specific notes: verified engine facts only, accumulate over time.
GAME_NOTES = {
    "黑神话悟空": {"engine": "unreal", "variant": "ue5", "note": "UE5 IoStore，改配置优先 .ini，改资源走 pak 覆盖"},
    "空洞骑士": {"engine": "unity", "variant": "mono", "note": "Unity Mono，Assembly-CSharp.dll 可直接反编译找字段"},
    "幻兽帕鲁": {"engine": "unreal", "variant": "ue5", "note": "UE5，pak 覆盖 + .ini 配置"},
    "生化危机4": {"engine": "re-engine", "note": "RE Engine，REFramework + Fluffy 装 pak mod"},
    "土豆兄弟": {"engine": "godot", "note": "Godot，GDScript / pck 覆盖"},
}


def _profile_key(engine_id: str, variant: str | None) -> str:
    if engine_id == "unreal":
        return f"unreal-{variant or 'ue4'}"
    if engine_id == "unity":
        return "unity"
    if engine_id == "dotnet-xna":
        return "dotnet-xna"
    return "default"


def get_recommendations(game_dir: str, engine_info: dict | None) -> dict:
    engine_id = (engine_info or {}).get("id", "")
    variant = (engine_info or {}).get("variant", "")
    key = _profile_key(engine_id, variant)
    profile = ENGINE_PROFILES.get(key, ENGINE_PROFILES["default"])

    game_name = os.path.basename(os.path.normpath(game_dir))
    note = None
    for name, data in GAME_NOTES.items():
        if name in game_name:
            note = data
            break

    return {
        "engine": engine_info,
        "profile_key": key,
        "summary": profile["summary"],
        "capabilities": profile["capabilities"],
        "recommendations": profile["recommendations"],
        "game_note": note,
    }
