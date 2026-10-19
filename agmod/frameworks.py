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
                "framework_name": "tModLoader (官方模组前置)",
                "status": "missing",
                "installed": False,
                "mode": "official_steam_loader",
                "steam_appid": "1281930",
                "steam_url": "steam://rungameid/1281930",
                "summary": "泰拉瑞亚官方模组依赖 tModLoader 运行环境（本工具已默认设为官方启动通道）。",
                "guidance": (
                    "点击【启动游戏】本工具将默认通过 Steam 直接唤起官方 tModLoader 并自动装载模组，用户无需手动下载任何必备 Mod 或前置补丁！"
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

    # 8. Bethesda Creation Engine (上古卷轴5: 天际 / 辐射4 / 辐射:新维加斯 / 星空)
    is_bethesda = (
        any(k in files for k in ["skyrimse.exe", "skyrim.exe", "skyrimvr.exe", "fallout4.exe", "fallout4vr.exe", "falloutnv.exe", "starfield.exe", "tesv.exe"])
        or any(fn.endswith((".esm", ".esp", ".esl")) for fn in files)
    )
    if is_bethesda:
        has_skse = (
            any(k in files for k in ["skse64_loader.exe", "f4se_loader.exe", "sfse_loader.exe", "nvse_loader.exe"])
            or os.path.isdir(os.path.join(game_dir, "Data", "SKSE"))
            or os.path.isdir(os.path.join(game_dir, "Data", "F4SE"))
        )
        se_name = "SKSE64" if "skyrimse.exe" in files else ("F4SE" if "fallout4.exe" in files else ("SFSE" if "starfield.exe" in files else "Script Extender"))
        if has_skse:
            return {
                "game_type": "bethesda",
                "game_name": "B社开放世界 (上古卷轴 / 辐射 / 星空)",
                "framework_id": "script_extender",
                "framework_name": f"{se_name} (Script Extender)",
                "status": "installed",
                "installed": True,
                "mods_dir": os.path.join(game_dir, "Data"),
                "summary": f"已检测到 {se_name} 脚本扩展器，支持深度内存钩子与 Papyrus 脚本扩展。",
                "guidance": f"Mod 插件文件放置于 Data/ 目录；请通过对应 {se_name} 加载器启动游戏。",
            }
        else:
            return {
                "game_type": "bethesda",
                "game_name": "B社开放世界 (上古卷轴 / 辐射 / 星空)",
                "framework_id": "script_extender",
                "framework_name": se_name,
                "status": "missing",
                "installed": False,
                "download_url": "https://silverlock.org",
                "summary": f"检测到 B社游戏环境，暂未安装核心脚本扩展器 {se_name}。",
                "guidance": f"推荐前往 https://silverlock.org 下载安装 {se_name}，绝大部分复杂机制 Mod 均以此为基础。",
            }

    # 9. Baldur's Gate 3 (博德之门3) & 神界原罪2
    is_bg3 = "bg3.exe" in files or "bg3_dx11.exe" in files or "eocapp.exe" in files
    if is_bg3:
        has_bg3se = os.path.isfile(os.path.join(game_dir, "bin", "DWrite.dll")) or "dwrite.dll" in files
        if has_bg3se:
            return {
                "game_type": "baldurs_gate_3",
                "game_name": "博德之门3 (Baldur's Gate 3)",
                "framework_id": "bg3se",
                "framework_name": "BG3 Script Extender (Norbyte)",
                "status": "installed",
                "installed": True,
                "summary": "已检测到 Norbyte BG3 Script Extender (DWrite.dll)，生态完整。",
                "guidance": "支持扩展控制台命令、OSIRIS 逻辑钩子及深入 Lua 脚本交互。",
            }
        else:
            return {
                "game_type": "baldurs_gate_3",
                "game_name": "博德之门3 (Baldur's Gate 3)",
                "framework_id": "bg3se",
                "framework_name": "BG3 Script Extender / 官方 Patch 7",
                "status": "missing",
                "installed": False,
                "download_url": "https://github.com/Norbyte/bg3se/releases",
                "summary": "检测到博德之门3客户端，当前暂未安装 Norbyte BG3 Script Extender。",
                "guidance": "推荐安装 Norbyte Script Extender (解压 DWrite.dll 至 bin 目录)，绝大部分职业、法术与 UI 模组均需此依赖。",
            }

    # 10. FromSoftware (艾尔登法环 / 只狼 / 魂系列 / 装甲核心6)
    is_fromsoft = any(k in files for k in ["eldenring.exe", "sekiro.exe", "darksoulsiii.exe", "darksoulsii.exe", "darksouls.exe", "armoredcore6.exe"])
    if is_fromsoft:
        has_modengine = "modengine2_launcher.exe" in files or "modengine2" in dirs or "launchmod_eldenring.bat" in files
        has_seamless = "ersc.dll" in files
        if has_modengine or has_seamless:
            names = []
            if has_modengine: names.append("Mod Engine 2")
            if has_seamless: names.append("Seamless Co-op")
            return {
                "game_type": "fromsoftware",
                "game_name": "FromSoftware (艾尔登法环 / 魂系列)",
                "framework_id": "modengine2",
                "framework_name": " + ".join(names),
                "status": "installed",
                "installed": True,
                "mods_dir": os.path.join(game_dir, "mod"),
                "summary": "已检测到 FromSoftware 无损文件劫持前置 (Mod Engine 2 / 无缝联机)。",
                "guidance": "Mod 资产文件放置于 mod/ 目录；自动绕过反作弊启动独立沙箱。",
            }
        else:
            return {
                "game_type": "fromsoftware",
                "game_name": "FromSoftware (艾尔登法环 / 魂系列)",
                "framework_id": "modengine2",
                "framework_name": "Mod Engine 2",
                "status": "missing",
                "installed": False,
                "download_url": "https://github.com/soulsmods/ModEngine2/releases",
                "summary": "检测到 FromSoftware 原版客户端，推荐配置 Mod Engine 2 前置沙箱。",
                "guidance": "推荐使用 Mod Engine 2（直接将解包的 modengine2 放入游戏根目录），实现免解包非破坏性 Mod 载入。",
            }

    # 11. The Witcher 3: Wild Hunt (巫师3：狂猎)
    is_witcher3 = "witcher3.exe" in files or os.path.isfile(os.path.join(game_dir, "bin", "x64", "witcher3.exe")) or os.path.isfile(os.path.join(game_dir, "bin", "x64_dx12", "witcher3.exe"))
    if is_witcher3:
        has_mods_dir = "mods" in dirs or os.path.isdir(os.path.join(game_dir, "Mods"))
        return {
            "game_type": "witcher3",
            "game_name": "巫师3：狂猎 (The Witcher 3)",
            "framework_id": "witcher3_mods",
            "framework_name": "REDengine 3 (Mods 架构)",
            "status": "installed",
            "installed": True,
            "mods_dir": os.path.join(game_dir, "Mods"),
            "summary": "已就绪：巫师3 标准 Mods / DLC 扩展架构。",
            "guidance": "Mod 文件夹以 mod* 格式写入 Mods/ 目录；如遇脚本冲突建议使用 Script Merger 自动合并。",
        }

    # 12. Mount & Blade II: Bannerlord (骑马与砍杀2：霸主)
    is_bannerlord = "bannerlord.exe" in files or "taleworlds.mountandblade.launcher.exe" in files or "modules" in dirs
    if is_bannerlord:
        has_harmony = os.path.isdir(os.path.join(game_dir, "Modules", "Bannerlord.Harmony"))
        if has_harmony:
            return {
                "game_type": "bannerlord",
                "game_name": "骑马与砍杀2：霸主 (Bannerlord)",
                "framework_id": "bannerlord_harmony",
                "framework_name": "Harmony + ButterLib (骑砍2核心前置)",
                "status": "installed",
                "installed": True,
                "mods_dir": os.path.join(game_dir, "Modules"),
                "summary": "已检测到骑马与砍杀2 核心前置架构 (Bannerlord.Harmony)。",
                "guidance": "Mod 按照独立 Module 写入 Modules/ 目录，并在启动器中勾选启用。",
            }
        else:
            return {
                "game_type": "bannerlord",
                "game_name": "骑马与砍杀2：霸主 (Bannerlord)",
                "framework_id": "bannerlord_harmony",
                "framework_name": "Bannerlord.Harmony / ButterLib",
                "status": "missing",
                "installed": False,
                "download_url": "https://www.nexusmods.com/mountandblade2bannerlord/mods/2006",
                "summary": "检测到骑马与砍杀2客户端，尚未安装 Harmony 基础前置。",
                "guidance": "骑砍2 绝大多数进阶 Mod 依赖 Harmony、ButterLib 与 UIExtenderEx；可在 Nexus Mods 订阅安装。",
            }

    # 13. Rockstar RAGE (GTA V / 荒野大镖客2)
    is_rockstar = "gta5.exe" in files or "rdr2.exe" in files
    if is_rockstar:
        has_sh = "scripthookv.dll" in files or "scripthookrdr2.dll" in files or "dinput8.dll" in files
        sh_name = "Script Hook V" if "gta5.exe" in files else "Script Hook RDR2"
        if has_sh:
            return {
                "game_type": "rockstar_rage",
                "game_name": "R星沙盒 (GTA 5 / 荒野大镖客2)",
                "framework_id": "scripthook",
                "framework_name": f"{sh_name} + dinput8",
                "status": "installed",
                "installed": True,
                "summary": f"已检测到 {sh_name} 原生插件载入钩子。",
                "guidance": "支持 .asi 插件及 scripts/ 目录脚本动态加载。",
            }
        else:
            return {
                "game_type": "rockstar_rage",
                "game_name": "R星沙盒 (GTA 5 / 荒野大镖客2)",
                "framework_id": "scripthook",
                "framework_name": sh_name,
                "status": "missing",
                "installed": False,
                "summary": f"检测到 R星游戏客户端，暂未挂载 {sh_name} 前置。",
                "guidance": f"建议下载安装 {sh_name} 及 dinput8.dll，方可在单机模式中加载自制 .asi 或脚本 Mod。",
            }

    # 14. Monster Hunter: World (怪物猎人：世界)
    is_mhw = "monsterhunterworld.exe" in files or "chunkg0.bin" in files
    if is_mhw:
        has_loader = "dinput8.dll" in files and "nativepc" in dirs
        if has_loader:
            return {
                "game_type": "mhw",
                "game_name": "怪物猎人：世界 (Monster Hunter: World)",
                "framework_id": "strackers_loader",
                "framework_name": "Stracker's Loader (nativePC)",
                "status": "installed",
                "installed": True,
                "mods_dir": os.path.join(game_dir, "nativePC"),
                "summary": "已检测到 Stracker's Loader 前置，nativePC 资产覆盖已就绪。",
                "guidance": "Mod 资源直接放入 nativePC/ 目录即可免解包覆盖生效。",
            }
        else:
            return {
                "game_type": "mhw",
                "game_name": "怪物猎人：世界 (Monster Hunter: World)",
                "framework_id": "strackers_loader",
                "framework_name": "Stracker's Loader",
                "status": "missing",
                "installed": False,
                "download_url": "https://www.nexusmods.com/monsterhunterworld/mods/1982",
                "summary": "检测到怪物猎人世界客户端，尚未安装 Stracker's Loader 前置补丁。",
                "guidance": "推荐前往 Nexus Mods 下载 Stracker's Loader，以启用 nativePC 文件免解包读取支持。",
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

