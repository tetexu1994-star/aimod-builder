"""Game library auto-discovery and launcher module.

Discovers games from Steam installations (across all drive letters and library folders),
identifies game engines, detects running state, and provides safe one-click launching
with pre-launch savegame protection.
"""
from __future__ import annotations

import logging
import os
import re
import subprocess
import sys
from typing import Any, Dict, List, Optional, Set

from agmod import frameworks, process, registry, safety, saves

logger = logging.getLogger("agmod.discovery")

try:
    import winreg
except ImportError:
    winreg = None  # Non-Windows fallback


def get_steam_roots() -> List[str]:
    """Find all Steam installation root directories on the host."""
    roots: List[str] = []
    seen_cases: Set[str] = set()

    def add_root(p: str):
        if not p:
            return
        norm = os.path.normpath(p)
        if not os.path.isdir(norm):
            return
        key = os.path.normcase(os.path.realpath(norm))
        if key not in seen_cases:
            seen_cases.add(key)
            roots.append(norm)

    # 1. Windows Registry detection
    if winreg is not None:
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Valve\Steam") as key:
                val, _ = winreg.QueryValueEx(key, "SteamPath")
                add_root(val)
        except OSError:
            pass

        try:
            with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\WOW6432Node\Valve\Steam") as key:
                val, _ = winreg.QueryValueEx(key, "InstallPath")
                add_root(val)
        except OSError:
            pass

    # 2. Known standard paths
    candidates = [
        r"C:\Program Files (x86)\Steam",
        r"C:\Program Files\Steam",
        r"D:\steam",
        r"E:\steam",
        r"F:\steam",
        r"D:\SteamLibrary",
        r"E:\SteamLibrary",
        r"F:\SteamLibrary",
        # Mac
        os.path.expanduser("~/Library/Application Support/Steam"),
        # Linux
        os.path.expanduser("~/.steam/steam"),
        os.path.expanduser("~/.local/share/Steam"),
    ]

    for p in candidates:
        add_root(p)

    return sorted(roots)


def find_all_steam_libraries() -> List[str]:
    """Find all Steam library folders (from all drive partitions) via libraryfolders.vdf."""
    lib_folders: List[str] = []
    seen_cases: Set[str] = set()
    roots = get_steam_roots()

    for root in roots:
        key = os.path.normcase(os.path.realpath(root))
        if key not in seen_cases:
            seen_cases.add(key)
            lib_folders.append(root)

        vdf_path = os.path.join(root, "steamapps", "libraryfolders.vdf")
        if not os.path.isfile(vdf_path):
            continue

        try:
            with open(vdf_path, "r", encoding="utf-8", errors="ignore") as f:
                content = f.read()

            # Steam VDF format: "path" "D:\\SteamLibrary"
            for match in re.finditer(r'"path"\s+"([^"]+)"', content):
                raw_path = match.group(1).replace(r"\\", os.sep)
                norm_p = os.path.normpath(raw_path)
                if os.path.isdir(norm_p):
                    k = os.path.normcase(os.path.realpath(norm_p))
                    if k not in seen_cases:
                        seen_cases.add(k)
                        lib_folders.append(norm_p)
        except Exception:
            pass

    return sorted(lib_folders)


def _parse_acf_manifest(acf_path: str) -> Optional[Dict[str, str]]:
    """Parse a single Steam appmanifest_<appid>.acf file."""
    try:
        with open(acf_path, "r", encoding="utf-8", errors="ignore") as f:
            content = f.read()

        appid_m = re.search(r'"appid"\s+"(\d+)"', content)
        name_m = re.search(r'"name"\s+"([^"]+)"', content)
        installdir_m = re.search(r'"installdir"\s+"([^"]+)"', content)

        if appid_m and installdir_m:
            return {
                "appid": appid_m.group(1).strip(),
                "name": name_m.group(1).strip() if name_m else installdir_m.group(1).strip(),
                "installdir": installdir_m.group(1).strip(),
            }
    except Exception:
        pass
    return None


def scan_installed_games(extra_dirs: Optional[List[str]] = None) -> List[Dict[str, Any]]:
    """Auto-discover all installed games on the host."""
    games: List[Dict[str, Any]] = []
    seen_dirs: Set[str] = set()

    # 1. Scan Steam Libraries
    steam_libs = find_all_steam_libraries()
    for lib in steam_libs:
        steamapps = os.path.join(lib, "steamapps")
        if not os.path.isdir(steamapps):
            continue

        # 1a. From appmanifest_*.acf
        try:
            entries = os.listdir(steamapps)
        except OSError:
            entries = []

        for fn in entries:
            if fn.startswith("appmanifest_") and fn.endswith(".acf"):
                acf_file = os.path.join(steamapps, fn)
                info = _parse_acf_manifest(acf_file)
                if not info:
                    continue

                game_dir = os.path.normpath(os.path.join(steamapps, "common", info["installdir"]))
                if not os.path.isdir(game_dir):
                    continue

                norm_key = game_dir.lower()
                if norm_key in seen_dirs:
                    continue
                seen_dirs.add(norm_key)

                appid = info["appid"]
                engine_info = registry.detect_engine(game_dir) or {}
                is_running, procs = process.is_game_running(game_dir)
                exes = process.find_game_executables(game_dir)
                ac_info = safety.detect_game_anticheat(game_dir)
                ac_allowed, ac_reason = safety.check_game_target(game_dir)

                games.append({
                    "id": f"steam_{appid}",
                    "name": info["name"],
                    "source": "steam",
                    "appid": appid,
                    "game_dir": game_dir,
                    "cover_url": f"https://cdn.akamai.steamstatic.com/steam/apps/{appid}/header.jpg",
                    "engine": engine_info.get("id") or engine_info.get("engine_id", "generic"),
                    "engine_name": engine_info.get("name") or engine_info.get("engine_name", "通用引擎"),
                    "adapter_ready": engine_info.get("adapter_ready", False) or bool(engine_info.get("id")),
                    "framework": frameworks.detect_game_framework(game_dir),
                    "is_running": is_running,
                    "running_pid": procs[0]["pid"] if procs else None,
                    "executables": exes,
                    "has_anticheat": ac_info.get("has_anticheat", False),
                    "anticheat_blocked": not ac_allowed,
                    "anticheat_system": ac_info.get("system", ""),
                    "anticheat_reason": ac_reason or ac_info.get("reason", ""),
                })

        # 1b. Fallback: scan common folder directly for games without active acf
        common_dir = os.path.join(steamapps, "common")
        if os.path.isdir(common_dir):
            try:
                subs = os.listdir(common_dir)
            except OSError:
                subs = []

            for sub in subs:
                sub_dir = os.path.normpath(os.path.join(common_dir, sub))
                if not os.path.isdir(sub_dir):
                    continue
                # Ignore Steamworks common redistributables
                if sub.lower() in {"steamworks shared", "steam controller configs"}:
                    continue

                norm_key = sub_dir.lower()
                if norm_key in seen_dirs:
                    continue
                seen_dirs.add(norm_key)

                exes = process.find_game_executables(sub_dir)
                if not exes:
                    continue

                engine_info = registry.detect_engine(sub_dir) or {}
                is_running, procs = process.is_game_running(sub_dir)
                ac_info = safety.detect_game_anticheat(sub_dir)
                ac_allowed, ac_reason = safety.check_game_target(sub_dir)

                games.append({
                    "id": f"folder_{sub}",
                    "name": sub,
                    "source": "steam_common",
                    "appid": "",
                    "game_dir": sub_dir,
                    "cover_url": "",
                    "engine": engine_info.get("id") or engine_info.get("engine_id", "generic"),
                    "engine_name": engine_info.get("name") or engine_info.get("engine_name", "通用引擎"),
                    "adapter_ready": engine_info.get("adapter_ready", False) or bool(engine_info.get("id")),
                    "framework": frameworks.detect_game_framework(sub_dir),
                    "is_running": is_running,
                    "running_pid": procs[0]["pid"] if procs else None,
                    "executables": exes,
                    "has_anticheat": ac_info.get("has_anticheat", False),
                    "anticheat_blocked": not ac_allowed,
                    "anticheat_system": ac_info.get("system", ""),
                    "anticheat_reason": ac_reason or ac_info.get("reason", ""),
                })

    # 2. Extra custom directories
    if extra_dirs:
        for ed in extra_dirs:
            if not os.path.isdir(ed):
                continue
            norm_key = os.path.normpath(ed).lower()
            if norm_key in seen_dirs:
                continue
            seen_dirs.add(norm_key)

            exes = process.find_game_executables(ed)
            engine_info = registry.detect_engine(ed) or {}
            is_running, procs = process.is_game_running(ed)
            base_name = os.path.basename(os.path.normpath(ed))
            ac_info = safety.detect_game_anticheat(ed)
            ac_allowed, ac_reason = safety.check_game_target(ed)

            games.append({
                "id": f"custom_{base_name}",
                "name": base_name,
                "source": "custom",
                "appid": "",
                "game_dir": os.path.normpath(ed),
                "cover_url": "",
                "engine": engine_info.get("id") or engine_info.get("engine_id", "generic"),
                "engine_name": engine_info.get("name") or engine_info.get("engine_name", "通用引擎"),
                "adapter_ready": engine_info.get("adapter_ready", False) or bool(engine_info.get("id")),
                "framework": frameworks.detect_game_framework(ed),
                "is_running": is_running,
                "running_pid": procs[0]["pid"] if procs else None,
                "executables": exes,
                "has_anticheat": ac_info.get("has_anticheat", False),
                "anticheat_blocked": not ac_allowed,
                "anticheat_system": ac_info.get("system", ""),
                "anticheat_reason": ac_reason or ac_info.get("reason", ""),
            })

    # Sort running games first, then by name
    games.sort(key=lambda g: (0 if g["is_running"] else 1, g["name"].lower()))
    return games


def launch_game(game_dir: str, appid: str = "") -> Dict[str, Any]:
    """Launch game with auto-save backup protection."""
    game_dir = os.path.normpath(game_dir)
    if not os.path.isdir(game_dir):
        return {"success": False, "error": f"Game directory not found: {game_dir}"}
    allowed, reason = safety.check_game_target(game_dir)
    if not allowed:
        return {"success": False, "error": reason}

    # 1. Pre-launch safety savegame backup
    try:
        saves.create_backup(game_dir, reason="AIMod_PreLaunch_Safety_Backup")
    except Exception:
        pass

    # 2. Framework-aware launch routing (fully generic across all game frameworks)
    fw = frameworks.detect_game_framework(game_dir)
    effective_appid = str(appid or "").strip()
    fw_name = fw.get("framework_name", "游戏")
    companion_appid = str(fw.get("steam_appid", "")).strip()

    # If framework specifies an official Steam companion tool (e.g. tModLoader AppID 1281930),
    # prioritize it when launching through Steam so mods load by default
    if companion_appid:
        effective_appid = companion_appid

    # Locate candidate loader executable in game_dir or framework_path or sibling directory
    loader_exe = None
    loader_candidates = list(fw.get("loader_candidates") or [])
    if fw.get("loader_exe") and fw["loader_exe"] not in loader_candidates:
        loader_candidates.insert(0, fw["loader_exe"])

    search_dirs = [game_dir]
    fw_path = fw.get("framework_path")
    if fw_path and os.path.isdir(fw_path) and os.path.abspath(fw_path) != os.path.abspath(game_dir):
        search_dirs.append(fw_path)
    parent_dir = os.path.dirname(os.path.abspath(game_dir))
    for sub in (fw.get("sibling_folders") or []):
        cand_dir = os.path.join(parent_dir, sub)
        if os.path.isdir(cand_dir):
            search_dirs.append(cand_dir)

    for cand_name in loader_candidates:
        if not cand_name:
            continue
        for sdir in search_dirs:
            p = os.path.join(sdir, cand_name)
            if os.path.isfile(p):
                loader_exe = p
                break
        if loader_exe:
            break

    # Prioritize Steam URI protocol for Steam games to ensure Steam DRM and overlay initialize cleanly
    if effective_appid and str(effective_appid).isdigit():
        try:
            if sys.platform == "win32":
                try:
                    os.startfile(f"steam://rungameid/{effective_appid}")
                except Exception:
                    subprocess.Popen(["cmd.exe", "/c", "start", "", f"steam://rungameid/{effective_appid}"])
            elif sys.platform == "darwin":
                subprocess.Popen(["open", f"steam://rungameid/{effective_appid}"])
            else:
                subprocess.Popen(["xdg-open", f"steam://rungameid/{effective_appid}"])

            msg = (
                f"已通过 Steam 官方客户端安全唤起官方模组前置 {fw_name} (AppID: {effective_appid})！全自动装载模组，无需手动配置。"
                if companion_appid else
                f"已通过 Steam 官方客户端安全唤起游戏 (AppID: {effective_appid})"
            )
            return {
                "success": True,
                "method": "steam_protocol",
                "appid": str(effective_appid),
                "is_companion_loader": bool(companion_appid),
                "message": msg,
            }
        except Exception as e:
            logger.warning("Steam protocol launch failed: %s, attempting direct executable launch", e)

    # 3. Direct executable launch (loader executable prioritized, else primary game executable)
    main_exe = loader_exe if loader_exe else process.find_primary_executable_path(game_dir)
    if main_exe and os.path.isfile(main_exe):
        exe_cwd = os.path.dirname(main_exe)
        exe_name = os.path.basename(main_exe)
        try:
            if sys.platform == "win32":
                try:
                    os.startfile(main_exe, cwd=exe_cwd)
                except TypeError:
                    os.startfile(main_exe)
            else:
                subprocess.Popen([main_exe], cwd=exe_cwd)
            is_custom_loader = bool(loader_exe and main_exe == loader_exe)
            msg = f"已通过专用模组加载器启动: {exe_name}" if is_custom_loader else f"游戏主程序已安全启动: {exe_name}"
            return {
                "success": True,
                "method": "direct_executable",
                "exe": main_exe,
                "is_loader": is_custom_loader,
                "message": msg,
            }
        except Exception as e:
            logger.warning("Direct launch failed: %s", e)

    return {"success": False, "error": "未在游戏目录中找到有效的主程序或模组加载器 (.exe)"}

