"""Game process discovery and runtime lock detection.

Detects running game executables belonging to a given game directory, warning
the agent before applying file modifications that could fail due to file locks
(e.g., Windows ERROR_ACCESS_DENIED / Errno 13).
"""
from __future__ import annotations

import os
import sys

try:
    import psutil
except ImportError:  # pragma: no cover
    psutil = None

_IGNORED_EXES = {
    "unitycrashhandler32.exe",
    "unitycrashhandler64.exe",
    "crashreportclient.exe",
    "unins000.exe",
    "unins001.exe",
    "uninstall.exe",
    "vcredist_x64.exe",
    "vcredist_x86.exe",
    "dxwebsetup.exe",
}


def find_game_executables(game_dir: str) -> list[str]:
    """Find primary game executable names inside game_dir."""
    if not os.path.isdir(game_dir):
        return []
    exes = set()
    for root, _, files in os.walk(game_dir):
        for fn in files:
            low = fn.lower()
            if low.endswith(".exe") and low not in _IGNORED_EXES:
                exes.add(fn)
            elif sys.platform != "win32" and not low.endswith((".dll", ".so", ".dylib", ".txt", ".json", ".pck", ".pak")):
                p = os.path.join(root, fn)
                if os.access(p, os.X_OK) and not os.path.isdir(p):
                    exes.add(fn)
    return sorted(exes)


def get_running_game_processes(game_dir: str) -> list[dict]:
    """Return active processes whose executable path or name matches game_dir."""
    if psutil is None:
        return []
    game_dir_abs = os.path.abspath(game_dir)
    target_exes = {e.lower() for e in find_game_executables(game_dir)}

    hits = []
    for proc in psutil.process_iter(["pid", "name", "exe"]):
        try:
            info = proc.info
            p_name = (info.get("name") or "").lower()
            p_exe = info.get("exe") or ""
            p_exe_abs = os.path.abspath(p_exe) if p_exe else ""

            matched = False
            # Check 1: Exe is inside game directory
            if p_exe_abs and p_exe_abs.startswith(game_dir_abs + os.sep):
                matched = True
            # Check 2: Process name matches one of the detected game executables
            elif target_exes and p_name in target_exes:
                matched = True

            if matched:
                hits.append({
                    "pid": info["pid"],
                    "name": info.get("name") or p_name,
                    "exe": p_exe or "",
                })
        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
            continue

    return hits


def is_game_running(game_dir: str) -> tuple[bool, list[dict]]:
    """Check if any game process from `game_dir` is currently active."""
    procs = get_running_game_processes(game_dir)
    return len(procs) > 0, procs
