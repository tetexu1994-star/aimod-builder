"""Game-specific prerequisite mod loader and framework detection.

Detects specialized mod ecosystems (tModLoader for Terraria, SMAPI for Stardew Valley,
REFramework for RE Engine, UE4SS for Unreal, BepInEx/MelonLoader for Unity, CET for Cyberpunk, etc.)
and reports their installation status, loader executables, and targeted mod directories.
"""
from __future__ import annotations

import os
from typing import Any, Dict, Optional


def detect_game_framework(game_dir: str) -> Dict[str, Any]:
    """Inspect game directory and detect specialized prerequisite mod loaders."""
    if not game_dir or not os.path.isdir(game_dir):
        return {
            "game_type": "unknown",
            "framework_name": "未知",
            "status": "unknown",
            "installed": False,
            "guidance": "",
        }

    game_dir = os.path.normpath(game_dir)
    files = set()
    dirs = set()
    try:
        for entry in os.scandir(game_dir):
            if entry.is_file():
                files.add(entry.name.lower())
            elif entry.is_dir():
                dirs.add(entry.name.lower())
    except OSError:
        pass

    # 1. Terraria (泰拉瑞亚)
    if "terraria.exe" in files or "relogic.native.dll" in files:
        # Check tModLoader
        tmod_in_dir = "tmodloader.dll" in files or "tmodloader.exe" in files or "modloader" in dirs
        # Check sibling tModLoader folder (Steam separate tool)
        tmod_sibling = os.path.isdir(os.path.join(os.path.dirname(game_dir), "tModLoader"))
        # Check BepInEx / Doorstop native injection
        bepinex_in_dir = (
            "bepinex" in dirs
            and ("winhttp.dll" in files or "doorstop_config.ini" in files or ".doorstop_version" in files)
        )

        if tmod_in_dir or tmod_sibling:
            tmod_path = game_dir if tmod_in_dir else os.path.join(os.path.dirname(game_dir), "tModLoader")
            return {
                "game_type": "terraria",
                "game_name": "泰拉瑞亚 (Terraria)",
                "framework_id": "tmodloader",
                "framework_name": "tModLoader",
                "status": "installed",
                "installed": True,
                "mode": "official_loader",
                "loader_exe": "tModLoader.exe" if "tmodloader.exe" in files else "",
                "framework_path": tmod_path,
                "mods_dir": os.path.join(tmod_path, "Mods") if os.path.isdir(os.path.join(tmod_path, "Mods")) else os.path.join(game_dir, "ModLoader", "Mods"),
                "summary": "已检测到官方 tModLoader 模组前置生态，支持标准 .tmod 与 C# Mod 架构。",
                "guidance": "游戏将通过 tModLoader 启动并加载 Mod；可在游戏内 Mod 管理菜单中直接启用与禁用。",
            }
        elif bepinex_in_dir:
            return {
                "game_type": "terraria",
                "game_name": "泰拉瑞亚 (Terraria)",
                "framework_id": "bepinex_doorstop",
                "framework_name": "BepInEx 5 (原版底层注入)",
                "status": "installed",
                "installed": True,
                "mode": "native_injection",
                "framework_path": os.path.join(game_dir, "BepInEx"),
                "mods_dir": os.path.join(game_dir, "BepInEx", "plugins"),
                "summary": "已在原版客户端中挂载 BepInEx / Doorstop 底层注入钩子，无需安装 tModLoader 即可开箱即用。",
                "guidance": "AI Mod Builder 已直接在原版客户端注入运行时钩子，自动编译原生 C# DLL 插件，启动 Terraria.exe 即可直接生效。",
            }
        else:
            return {
                "game_type": "terraria",
                "game_name": "泰拉瑞亚 (Terraria)",
                "framework_id": "tmodloader",
                "framework_name": "tModLoader (推荐) / BepInEx 注入",
                "status": "missing",
                "installed": False,
                "mode": "none",
                "steam_appid": "1281930",
                "steam_url": "steam://install/1281930",
                "summary": "检测到当前为纯净原版泰拉瑞亚客户端，尚未配置 Mod 前置生态。",
                "guidance": (
                    "【推荐方案】在 Steam 搜索并一键安装「tModLoader」（AppID: 1281930，完全免费）；\n"
                    "【独立方案】也可由本工具直接一键注入轻量级 BepInEx 前置，直接在原版中体验 Mod。"
                ),
            }

    # 2. Stardew Valley (星露谷物语)
    if "stardew valley.exe" in files or "stardewvalley.exe" in files or "stardew valley.dll" in files:
        has_smapi = "stardewmoddingapi.exe" in files or "smapi-internal" in dirs
        if has_smapi:
            return {
                "game_type": "stardew_valley",
                "game_name": "星露谷物语 (Stardew Valley)",
                "framework_id": "smapi",
                "framework_name": "SMAPI (Stardew Modding API)",
                "status": "installed",
                "installed": True,
                "mode": "official_loader",
                "loader_exe": "StardewModdingAPI.exe",
                "framework_path": game_dir,
                "mods_dir": os.path.join(game_dir, "Mods"),
                "summary": "已检测到星露谷官方唯一核心前置 SMAPI，生态完整。",
                "guidance": "所有生成的 Mod 插件将自动写入游戏 Mods/ 目录；请通过 StardewModdingAPI.exe 启动游戏载入模组。",
            }
        else:
            return {
                "game_type": "stardew_valley",
                "game_name": "星露谷物语 (Stardew Valley)",
                "framework_id": "smapi",
                "framework_name": "SMAPI",
                "status": "missing",
                "installed": False,
                "mode": "none",
                "download_url": "https://smapi.io",
                "summary": "⚠️ 当前为原版星露谷物语，尚未安装核心前置 SMAPI！原版游戏无法直接加载任何 Mod。",
                "guidance": (
                    "星露谷物语的所有 Mod 均依赖 SMAPI 前置。\n"
                    "👉 请前往官方网站 https://smapi.io 下载安装 SMAPI；安装完成后启动 StardewModdingAPI.exe，"
                    "AI Mod Builder 编写的代码将自动写入 Mods/ 目录。"
                ),
            }

    # 3. Cyberpunk 2077 (赛博朋克 2077)
    if "cyberpunk2077.exe" in files or "cyberpunk 2077" in game_dir.lower():
        has_cet = os.path.isfile(os.path.join(game_dir, "bin", "x64", "plugins", "cyber_engine_tweaks.asi"))
        has_redmod = os.path.isfile(os.path.join(game_dir, "tools", "redmod", "bin", "redmod.exe"))
        if has_cet or has_redmod:
            fw_names = []
            if has_cet: fw_names.append("Cyber Engine Tweaks (CET)")
            if has_redmod: fw_names.append("REDmod")
            return {
                "game_type": "cyberpunk2077",
                "game_name": "赛博朋克 2077 (Cyberpunk 2077)",
                "framework_id": "cyberpunk_mods",
                "framework_name": " + ".join(fw_names),
                "status": "installed",
                "installed": True,
                "summary": "已检测到赛博朋克 2077 核心脚本/前置环境。",
                "guidance": "支持 Lua 脚本注入及 REDmod 资产打包覆盖。",
            }
        else:
            return {
                "game_type": "cyberpunk2077",
                "game_name": "赛博朋克 2077 (Cyberpunk 2077)",
                "framework_id": "cet_redmod",
                "framework_name": "CET / REDmod",
                "status": "missing",
                "installed": False,
                "guidance": "建议在 Nexus Mods 安装 Cyber Engine Tweaks (CET) 或通过 Steam/GOG 安装官方免费 REDmod DLC 前置。",
            }

    # 4. Slay the Spire (杀戮尖塔)
    if "desktop-1.0.jar" in files or "slaythespire.exe" in files:
        has_mts = "modthespire.jar" in files or os.path.isdir(os.path.join(game_dir, "mods"))
        if has_mts:
            return {
                "game_type": "slay_the_spire",
                "game_name": "杀戮尖塔 (Slay the Spire)",
                "framework_id": "modthespire",
                "framework_name": "ModTheSpire",
                "status": "installed",
                "installed": True,
                "summary": "已检测到 ModTheSpire 模组加载器。",
                "guidance": "可通过 Steam 创意工坊或 ModTheSpire.jar 直接载入卡牌与机制 Mod。",
            }
        else:
            return {
                "game_type": "slay_the_spire",
                "game_name": "杀戮尖塔 (Slay the Spire)",
                "framework_id": "modthespire",
                "framework_name": "ModTheSpire",
                "status": "missing",
                "installed": False,
                "guidance": "推荐直接在 Steam 创意工坊一键订阅「ModTheSpire」和「BaseMod」前置。",
            }

    # 5. RE Engine (生化危机 / 怪物猎人)
    if "dinput8.dll" in files and ("reframework" in dirs or "reframework.dll" in files):
        return {
            "game_type": "re_engine",
            "framework_id": "reframework",
            "framework_name": "REFramework",
            "status": "installed",
            "installed": True,
            "mods_dir": os.path.join(game_dir, "reframework", "autorun"),
            "summary": "已检测到卡普空 RE 引擎专用前置 REFramework。",
            "guidance": "支持 Lua 脚本热重载与游戏内 ImGui 实时菜单调试。",
        }

    # 6. Unity Games (通用 Unity: BepInEx / MelonLoader)
    has_bepinex = "bepinex" in dirs and os.path.isfile(os.path.join(game_dir, "BepInEx", "core", "BepInEx.dll")) or os.path.isfile(os.path.join(game_dir, "BepInEx", "core", "BepInEx.Core.dll"))
    has_melon = "melonloader" in dirs and os.path.isfile(os.path.join(game_dir, "MelonLoader", "MelonLoader.dll"))
    if has_bepinex:
        return {
            "game_type": "unity",
            "framework_id": "bepinex",
            "framework_name": "BepInEx 5",
            "status": "installed",
            "installed": True,
            "mods_dir": os.path.join(game_dir, "BepInEx", "plugins"),
            "summary": "已检测到 Unity 通用插件前置 BepInEx 5 (Harmony)。",
            "guidance": "插件编译为 DLL 写入 BepInEx/plugins/，支持热调参和配置文件动态同步。",
        }
    if has_melon:
        return {
            "game_type": "unity",
            "framework_id": "melonloader",
            "framework_name": "MelonLoader",
            "status": "installed",
            "installed": True,
            "mods_dir": os.path.join(game_dir, "Mods"),
            "summary": "已检测到 MelonLoader 模组前置。",
            "guidance": "支持 Unity Mono / IL2CPP 双架构模组载入。",
        }

    # 7. Unreal Engine (UE4SS / loose pak)
    has_ue4ss = (
        "ue4ss" in dirs
        or "dwmapi.dll" in files
        or os.path.isdir(os.path.join(game_dir, "Binaries", "Win64", "ue4ss"))
    )
    if has_ue4ss:
        return {
            "game_type": "unreal",
            "framework_id": "ue4ss",
            "framework_name": "UE4SS (Unreal Scripting System)",
            "status": "installed",
            "installed": True,
            "summary": "已检测到虚幻引擎专用脚本系统 UE4SS。",
            "guidance": "支持 Lua 脚本反射调用 UObject 与蓝图函数。",
        }

    # Generic fallback
    return {
        "game_type": "generic",
        "framework_name": "原生执行",
        "status": "optional",
        "installed": True,
        "summary": "标准游戏目录，使用引擎原生 Hook 或内存引擎。",
        "guidance": "可直接制作 Mod，工具将自动选择适合该引擎的最优加载方案。",
    }
