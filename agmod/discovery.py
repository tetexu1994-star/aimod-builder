"""Game library auto-discovery and launcher module.

Discovers games from Steam installations (across all drive letters and library folders),
identifies game engines, detects running state, and provides safe one-click launching
with pre-launch savegame protection.
"""
from __future__ import annotations

import os
import re
import subprocess
import sys
from typing import Any, Dict, List, Optional, Set

from agmod import process, registry, saves

try:
    import winreg
except ImportError:
    winreg = None  # Non-Windows fallback


def get_steam_roots() -> List[str]:
    """Find all Steam installation root directories on the host."""
    roots: Set[str] = set()

    # 1. Windows Registry detection
    if winreg is not None:
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Valve\Steam") as key:
                val, _ = winreg.QueryValueEx(key, "SteamPath")
                if val and os.path.isdir(val):
                    roots.add(os.path.normpath(val))
        except OSError:
            pass

        try:
            with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\WOW6432Node\Valve\Steam") as key:
                val, _ = winreg.QueryValueEx(key, "InstallPath")
                if val and os.path.isdir(val):
                    roots.add(os.path.normpath(val))
        except OSError:
            pass

    # 2. Known standard paths
    candidates = [
        r"D:\steam",
        r"C:\Program Files (x86)\Steam",
        r"C:\Program Files\Steam",
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
        if os.path.isdir(p):
            roots.add(os.path.normpath(p))

    return sorted(roots)


def find_all_steam_libraries() -> List[str]:
    """Find all Steam library folders (from all drive partitions) via libraryfolders.vdf."""
    lib_folders: Set[str] = set()
    roots = get_steam_roots()

    for root in roots:
        lib_folders.add(root)
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
                    lib_folders.add(norm_p)
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
                    "is_running": is_running,
                    "running_pid": procs[0]["pid"] if procs else None,
                    "executables": exes,
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
                    "is_running": is_running,
                    "running_pid": procs[0]["pid"] if procs else None,
                    "executables": exes,
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
                "is_running": is_running,
                "running_pid": procs[0]["pid"] if procs else None,
                "executables": exes,
            })

    # Sort running games first, then by name
    games.sort(key=lambda g: (0 if g["is_running"] else 1, g["name"].lower()))
    return games


def launch_game(game_dir: str, appid: str = "") -> Dict[str, Any]:
    """Launch game with auto-save backup protection."""
    game_dir = os.path.normpath(game_dir)
    if not os.path.isdir(game_dir):
        return {"success": False, "error": f"Game directory not found: {game_dir}"}

    # 1. Pre-launch safety savegame backup
    try:
        saves.create_backup(game_dir, reason="AIMod_PreLaunch_Safety_Backup")
    except Exception:
        pass

    # 2. If Steam appid is provided on Windows, try launching via Steam URI protocol
    if sys.platform == "win32" and appid and appid.isdigit():
        try:
            os.system(f'start steam://run/{appid}')
            return {
                "success": True,
                "method": "steam_protocol",
                "appid": appid,
                "message": f"Steam 启动指令已发送 (AppID: {appid})",
            }
        except Exception:
            pass

    # 3. Direct executable launch fallback
    exes = process.find_game_executables(game_dir)
    if not exes:
        return {"success": False, "error": "No game executable found in directory"}

    main_exe = os.path.join(game_dir, exes[0])
    try:
        if sys.platform == "win32":
            os.startfile(main_exe)
        else:
            subprocess.Popen([main_exe], cwd=game_dir)
        return {
            "success": True,
            "method": "direct_executable",
            "exe": main_exe,
            "message": f"游戏主程序已启动: {exes[0]}",
        }
    except Exception as e:
        return {"success": False, "error": f"Failed to launch game executable: {str(e)}"}
