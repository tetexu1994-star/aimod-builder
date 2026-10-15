"""Safety guardrails enforced in code, not just in the agent prompt.

Refuses to attach/scan/write to known anti-cheat processes, and can list active
anti-cheat services so the agent can warn the user before doing anything.
"""
from __future__ import annotations

import os
import re
import sys
from typing import Any

try:
    import psutil
except ImportError:  # pragma: no cover
    psutil = None

# Known anti-cheat service executables and drivers
BLOCKED = {
    "easyanticheat.exe",
    "easyanticheat_eos.exe",
    "easyanticheat_setup.exe",
    "beservice.exe",
    "beservice_x64.exe",
    "battleye.exe",
    "vgc.exe",                 # Riot Vanguard
    "vgtray.exe",
    "faceitservice.exe",
    "faceitclient.exe",
    "mrac.exe",                # Mail.ru / Warface Anti-Cheat
    "equ8.exe",
    "fisecurityservice.exe",
    "nprotect game monitor.exe",
    "gamemon.des",             # GameGuard
    "gamemon64.des",
    "xigncode.exe",
    "xcs.xem",                 # XIGNCODE3
    "ace-base.sys",            # Tencent Anti-Cheat Expert
    "anticheatexpert.exe",
    "mhyprot2.sys",            # HoYoverse Anti-Cheat
    "hoop.sys",
    "punkbuster.exe",
    "pbsvc.exe",
    "ricochet.sys",
}

# Subfolder names inside game directory indicating anti-cheat presence
ANTICHEAT_DIR_NAMES = {
    "easyanticheat": "EasyAntiCheat",
    "battleye": "BattlEye",
    "gameguard": "nProtect GameGuard",
    "xigncode": "XIGNCODE3",
    "xigncode3": "XIGNCODE3",
    "anticheatexpert": "Tencent AntiCheatExpert",
    "ace-base": "Tencent AntiCheatExpert",
    "equ8": "EQU8 Anti-Cheat",
    "mrac": "MRAC Anti-Cheat",
}

# Specific files indicating anti-cheat presence
ANTICHEAT_FILE_PATTERNS = {
    "easyanticheat_x64.dll": "EasyAntiCheat",
    "easyanticheat_x86.dll": "EasyAntiCheat",
    "easyanticheat.dll": "EasyAntiCheat",
    "easyanticheat_eos.exe": "EasyAntiCheat",
    "easyanticheat_setup.exe": "EasyAntiCheat",
    "start_protected_game.exe": "EasyAntiCheat (Protected Launcher)",
    "beservice.exe": "BattlEye",
    "beservice_x64.exe": "BattlEye",
    "beclient_x64.dll": "BattlEye",
    "beclient.dll": "BattlEye",
    "bedaisy.sys": "BattlEye",
    "vgc.exe": "Riot Vanguard",
    "vgk.sys": "Riot Vanguard",
    "gamemon.des": "nProtect GameGuard",
    "x3.xem": "XIGNCODE3",
}

# Known competitive online titles that strictly enforce server-side anti-cheat
BLOCKED_GAME_NAMES = {
    "apex legends",
    "pubg: battlegrounds",
    "pubg",
    "valorant",
    "counter-strike 2",
    "cs2",
    "dead by daylight",
    "rainbow six siege",
    "destiny 2",
    "naraka: bladepoint",
    "naraka bladepoint",
    "genshin impact",
    "honkai: star rail",
    "zenless zone zero",
    "the finals",
    "fortnite",
}


def is_blocked_name(name: str) -> bool:
    return name.strip().lower() in BLOCKED


def detect_game_anticheat(game_dir: str) -> dict[str, Any]:
    """Inspect game directory for anti-cheat subsystems, protecting user accounts from bans."""
    if not game_dir or not os.path.isdir(game_dir):
        return {"has_anticheat": False, "system": "", "reason": ""}

    game_dir_abs = os.path.abspath(game_dir)
    dir_name = os.path.basename(os.path.normpath(game_dir_abs)).lower()

    def _build_res(has_ac: bool, sys_n: str, r_msg: str):
        return {
            "has_anticheat": has_ac,
            "system": sys_n,
            "anticheat_system": sys_n,
            "reason": r_msg,
            "anticheat_reason": r_msg,
        }

    # 1. Check known protected game directory names
    for blocked_title in BLOCKED_GAME_NAMES:
        if blocked_title in dir_name:
            return _build_res(
                True,
                "Online Anti-Cheat Protection",
                f"游戏 '{dir_name}' (匹配: {blocked_title}) 属于强联网反作弊竞技游戏，已自动屏蔽自定义 Mod 操作以防封号。",
            )

    # 2. Check top-level and 2-level deep files and directories
    try:
        entries = os.listdir(game_dir_abs)
    except OSError:
        entries = []

    for entry in entries:
        low = entry.lower()
        full_p = os.path.join(game_dir_abs, entry)

        # Check subdirectories
        if os.path.isdir(full_p):
            if low in ANTICHEAT_DIR_NAMES:
                sys_name = ANTICHEAT_DIR_NAMES[low]
                return _build_res(
                    True,
                    sys_name,
                    f"检测到反作弊目录 '{entry}' ({sys_name})，已自动拦截自定义 Mod 操作以保护账号安全。",
                )
            # Check 1 level inside (e.g. Game/EasyAntiCheat)
            try:
                sub_entries = os.listdir(full_p)
                for sub in sub_entries:
                    sub_low = sub.lower()
                    if sub_low in ANTICHEAT_DIR_NAMES:
                        sys_name = ANTICHEAT_DIR_NAMES[sub_low]
                        return _build_res(
                            True,
                            sys_name,
                            f"检测到反作弊模块 '{sub}' ({sys_name})，已自动拦截自定义 Mod 操作。",
                        )
                    if sub_low in ANTICHEAT_FILE_PATTERNS:
                        sys_name = ANTICHEAT_FILE_PATTERNS[sub_low]
                        return _build_res(
                            True,
                            sys_name,
                            f"检测到反作弊程序组件 '{sub}' ({sys_name})，禁止自定义 Mod 操作。",
                        )
            except OSError:
                pass

        # Check files in root
        if os.path.isfile(full_p):
            if low in ANTICHEAT_FILE_PATTERNS:
                sys_name = ANTICHEAT_FILE_PATTERNS[low]
                return _build_res(
                    True,
                    sys_name,
                    f"检测到反作弊文件 '{entry}' ({sys_name})，已自动拦截自定义 Mod 操作。",
                )

    return _build_res(False, "", "")


def process_name(pid: int) -> str:
    if psutil is None:
        return ""
    try:
        return psutil.Process(pid).name() or ""
    except Exception:
        return ""


def check_target(pid: int) -> tuple[bool, str]:
    """Return (allowed, reason), failing closed for unknown/protected targets."""
    if not isinstance(pid, int) or pid <= 0:
        return False, "pid must be a positive integer"
    if psutil is None:
        return False, "psutil is required before process memory access"
    name = process_name(pid)
    if not name:
        return False, f"process {pid} is not running or cannot be inspected"
    if is_blocked_name(name):
        return False, f"target process '{name}' is anti-cheat; refusing to touch it"
    active = active_anticheat()
    if active:
        return False, "anti-cheat service is active: " + ", ".join(active)
    return True, ""


def check_game_target(game_dir: str) -> tuple[bool, str]:
    """Refuse work on game directories that contain anti-cheat or while anti-cheat is active."""
    # 1. Check directory-level anti-cheat markers
    ac = detect_game_anticheat(game_dir)
    if ac.get("has_anticheat"):
        return False, ac.get("reason", f"检测到该游戏受 {ac.get('system', '反作弊')} 保护，禁止修改。")

    # 2. Check running anti-cheat services on the host
    active = active_anticheat()
    if active:
        return False, "检测到宿主机正运行反作弊服务: " + ", ".join(active) + "，为防封禁已自动拦截 Mod 操作。"
    return True, ""


def active_anticheat() -> list[str]:
    """Names of any currently-running known anti-cheat services."""
    out = set()
    if psutil is not None:
        for p in psutil.process_iter(["name"]):
            try:
                n = (p.info.get("name") or "").lower()
            except Exception:
                continue
            if n in BLOCKED:
                out.add(p.info["name"])
    else:
        try:
            from agmod import process
            if sys.platform == "win32":
                hits = process._get_running_processes_tasklist(BLOCKED)
                for h in hits:
                    out.add(h["name"])
            else:
                hits = process._get_running_processes_ps(BLOCKED)
                for h in hits:
                    out.add(h["name"])
        except Exception:
            pass
    return sorted(out)
