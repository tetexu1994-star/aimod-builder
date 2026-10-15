"""Game process discovery and runtime lock detection.

Detects running game executables belonging to a given game directory, warning
the agent before applying file modifications that could fail due to file locks
(e.g., Windows ERROR_ACCESS_DENIED / Errno 13).
"""
from __future__ import annotations

import csv
import io
import os
import subprocess
import sys
import time

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
    "vc_redist.x64.exe",
    "vc_redist.x86.exe",
}


def find_primary_executable_path(game_dir: str) -> str | None:
    """Find the full absolute path of the primary game executable.

    Prioritizes:
    1. Root executable matching directory name (e.g. PBZero.exe)
    2. Any executable directly in the root directory (level 0 launcher)
    3. Nested Shipping executable (e.g. */Binaries/Win64/*-Shipping.exe)
    4. Any executable inside a Binaries/Win64/ folder
    5. First valid executable found anywhere in game_dir
    """
    if not os.path.isdir(game_dir):
        return None

    game_dir_abs = os.path.abspath(game_dir)
    dir_name = os.path.basename(os.path.normpath(game_dir)).lower()

    # 1 & 2: Root level executables
    root_exes = []
    try:
        for fn in os.listdir(game_dir_abs):
            p = os.path.join(game_dir_abs, fn)
            if os.path.isfile(p):
                low = fn.lower()
                if low.endswith(".exe") and low not in _IGNORED_EXES:
                    root_exes.append(p)
                elif sys.platform != "win32" and not low.endswith((".dll", ".so", ".dylib", ".txt", ".json", ".pck", ".pak")):
                    if os.access(p, os.X_OK):
                        root_exes.append(p)
    except OSError:
        pass

    if root_exes:
        for p in root_exes:
            fn_low = os.path.basename(p).lower()
            if fn_low == f"{dir_name}.exe" or fn_low.startswith(dir_name):
                return p
        return root_exes[0]

    # 3, 4, 5: Nested executables (common in Unreal Engine / AAA titles)
    shippings = []
    win64_exes = []
    all_exes = []

    for root, _, files in os.walk(game_dir_abs):
        for fn in files:
            low = fn.lower()
            if low.endswith(".exe") and low not in _IGNORED_EXES:
                full_p = os.path.join(root, fn)
                all_exes.append(full_p)
                if "-shipping.exe" in low:
                    shippings.append(full_p)
                elif "binaries" in root.lower() and "win64" in root.lower():
                    win64_exes.append(full_p)
            elif sys.platform != "win32" and not low.endswith((".dll", ".so", ".dylib", ".txt", ".json", ".pck", ".pak")):
                full_p = os.path.join(root, fn)
                if os.access(full_p, os.X_OK) and not os.path.isdir(full_p):
                    all_exes.append(full_p)

    if shippings:
        for p in shippings:
            if dir_name in os.path.basename(p).lower():
                return p
        return shippings[0]

    if win64_exes:
        return win64_exes[0]

    if all_exes:
        return all_exes[0]

    return None


def find_game_executables(game_dir: str) -> list[str]:
    """Find primary game executable names inside game_dir."""
    if not os.path.isdir(game_dir):
        return []
    exes = set()
    primary = find_primary_executable_path(game_dir)
    primary_name = os.path.basename(primary) if primary else None

    for root, _, files in os.walk(game_dir):
        for fn in files:
            low = fn.lower()
            if low.endswith(".exe") and low not in _IGNORED_EXES:
                exes.add(fn)
            elif sys.platform != "win32" and not low.endswith((".dll", ".so", ".dylib", ".txt", ".json", ".pck", ".pak")):
                p = os.path.join(root, fn)
                if os.access(p, os.X_OK) and not os.path.isdir(p):
                    exes.add(fn)

    res = sorted(exes)
    if primary_name and primary_name in res:
        res.remove(primary_name)
        res.insert(0, primary_name)
    return res


def _is_subpath(parent: str, child: str) -> bool:
    """Return True if child path is inside parent directory."""
    if not parent or not child:
        return False
    try:
        p = os.path.normcase(os.path.abspath(os.path.realpath(parent)))
        c = os.path.normcase(os.path.abspath(os.path.realpath(child)))
        return os.path.commonpath([p, c]) == p
    except (ValueError, OSError):
        return False


def _get_running_processes_tasklist(known_exes_lower: set[str]) -> list[dict]:
    """Native Windows fallback using tasklist command (zero dependency)."""
    hits = []
    creationflags = 0
    if sys.platform == "win32":
        creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000)

    try:
        proc = subprocess.run(
            ["tasklist", "/FO", "CSV", "/NH"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="gbk",
            errors="ignore",
            creationflags=creationflags,
            timeout=3,
        )
        if proc.returncode != 0:
            return []

        reader = csv.reader(io.StringIO(proc.stdout))
        for row in reader:
            if len(row) >= 2:
                name = row[0].strip()
                if name.lower() in known_exes_lower:
                    try:
                        pid = int(row[1].strip())
                    except ValueError:
                        continue
                    hits.append({
                        "pid": pid,
                        "name": name,
                        "exe": "",
                    })
    except Exception:
        pass
    return hits


def _get_running_processes_ps(known_exes_lower: set[str]) -> list[dict]:
    """Native POSIX fallback using ps command (zero dependency)."""
    hits = []
    try:
        proc = subprocess.run(
            ["ps", "-eo", "pid,comm"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=3,
        )
        if proc.returncode != 0:
            return []
        for line in proc.stdout.splitlines():
            parts = line.strip().split(None, 1)
            if len(parts) == 2:
                pid_str, comm = parts
                comm_base = os.path.basename(comm).lower()
                if comm_base in known_exes_lower:
                    try:
                        pid = int(pid_str)
                    except ValueError:
                        continue
                    hits.append({
                        "pid": pid,
                        "name": comm,
                        "exe": "",
                    })
    except Exception:
        pass
    return hits


def get_running_game_processes(game_dir: str) -> list[dict]:
    """Return active processes whose executable path or name matches game_dir."""
    if not game_dir or not os.path.isdir(game_dir):
        return []

    game_dir_abs = os.path.realpath(game_dir)
    found_exes = find_game_executables(game_dir)
    known_exes_lower = {e.lower() for e in found_exes}

    # Also include the folder name itself as possible binary name (e.g. Raft -> raft.exe)
    base_name = os.path.basename(os.path.normpath(game_dir)).lower()
    if base_name:
        known_exes_lower.add(base_name)
        known_exes_lower.add(f"{base_name}.exe")

    hits = []
    seen_pids = set()

    # Step 1: Use psutil if available
    if psutil is not None:
        try:
            for proc in psutil.process_iter(["pid", "name", "exe", "cwd"]):
                try:
                    info = proc.info
                    pid = info.get("pid")
                    if pid is None or pid in seen_pids:
                        continue

                    p_name = info.get("name") or ""
                    p_name_low = p_name.lower()
                    p_exe = info.get("exe") or ""
                    cwd = info.get("cwd") or ""

                    matched = False

                    # Check 1: Executable path is inside game directory
                    if p_exe and _is_subpath(game_dir_abs, p_exe):
                        matched = True
                    # Check 2: Working directory is inside game directory
                    elif cwd and _is_subpath(game_dir_abs, cwd):
                        matched = True
                    # Check 3: Process name matches known game executables
                    elif p_name_low and p_name_low in known_exes_lower:
                        matched = True

                    if matched:
                        seen_pids.add(pid)
                        hits.append({
                            "pid": pid,
                            "name": p_name or p_name_low,
                            "exe": p_exe or "",
                        })
                except (psutil.NoSuchProcess, psutil.ZombieProcess):
                    continue
                except psutil.AccessDenied:
                    # Windows access denied on exe/cwd: fall back to name check
                    try:
                        p_name = proc.name()
                        if p_name and p_name.lower() in known_exes_lower:
                            pid = proc.pid
                            if pid not in seen_pids:
                                seen_pids.add(pid)
                                hits.append({
                                    "pid": pid,
                                    "name": p_name,
                                    "exe": "",
                                })
                    except Exception:
                        pass
        except Exception:
            pass

    # Step 2: If psutil is absent or found 0 hits, fall back to native OS commands
    if not hits:
        fallback_hits = []
        if sys.platform == "win32":
            fallback_hits = _get_running_processes_tasklist(known_exes_lower)
        else:
            fallback_hits = _get_running_processes_ps(known_exes_lower)

        for h in fallback_hits:
            if h["pid"] not in seen_pids:
                seen_pids.add(h["pid"])
                hits.append(h)

    return hits


def is_game_running(game_dir: str) -> tuple[bool, list[dict]]:
    """Check if any game process from `game_dir` is currently active."""
    procs = get_running_game_processes(game_dir)
    return len(procs) > 0, procs


def check_game_status(game_dir: str) -> dict:
    """Check game executable status: detected binaries, whether any game process is running, and lock risk."""
    game_dir_abs = os.path.abspath(game_dir) if game_dir else ""
    exes = find_game_executables(game_dir_abs) if game_dir_abs else []
    running, running_procs = is_game_running(game_dir_abs) if game_dir_abs else (False, [])
    return {
        "game_dir": game_dir_abs,
        "executables": exes,
        "is_running": running,
        "running_processes": running_procs,
        "processes": running_procs,
        "lock_warning": "Game is currently running! File operations (install/update/uninstall) may fail due to file locks." if running else None,
    }
