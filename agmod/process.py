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
from typing import Any

try:
    import psutil
except ImportError:  # pragma: no cover
    psutil = None

_IGNORED_EXES = {
    "unitycrashhandler32.exe",
    "unitycrashhandler64.exe",
    "crashreportclient.exe",
    "crashreport.exe",
    "crashreporter.exe",
    "unins000.exe",
    "unins001.exe",
    "uninstall.exe",
    "vcredist_x64.exe",
    "vcredist_x86.exe",
    "dxwebsetup.exe",
    "dxsetup.exe",
    "vc_redist.x64.exe",
    "vc_redist.x86.exe",
    "installer.exe",
}

def is_ignored_executable_name(fn: str) -> bool:
    low = fn.lower()
    if low in _IGNORED_EXES:
        return True
    if any(k in low for k in ("crashreport", "crashhandler", "unins00", "uninstall", "redist", "dxsetup", "patch.", "installermessage")):
        return True
    return False

_SKIP_DIR_NAMES = {
    "content", "paks", "streamingassets", "assetbundles", "assets",
    "resources", "media", "shaders", "sound", "sounds", "audio", "music",
    "video", "videos", "movies", "textures", "texture", ".git", ".svn",
    "workshop", "temp", "cache", "logs", "crashdumps"
}

_PROCESS_CACHE: dict[str, Any] = {"timestamp": 0.0, "processes": []}
_PROCESS_CACHE_TTL = 3.0  # seconds


def clear_process_cache() -> None:
    """Clear cached process list to ensure fresh process queries."""
    _PROCESS_CACHE["timestamp"] = 0.0
    _PROCESS_CACHE["processes"] = []


def _scan_dir_executables(game_dir: str) -> list[str]:
    """Fast shallow walk of game directory to locate executables, skipping heavy asset folders."""
    if not os.path.isdir(game_dir):
        return []
    game_dir_abs = os.path.abspath(game_dir)
    found_paths = []

    for root, dirs, files in os.walk(game_dir_abs, topdown=True):
        rel = os.path.relpath(root, game_dir_abs)
        if rel != ".":
            # Cap depth to 3 subfolder levels
            if rel.count(os.sep) >= 3:
                dirs.clear()
        # Prune known heavy non-executable asset subdirectories
        dirs[:] = [d for d in dirs if d.lower() not in _SKIP_DIR_NAMES]

        for fn in files:
            low = fn.lower()
            if low.endswith(".exe") and not is_ignored_executable_name(fn):
                found_paths.append(os.path.join(root, fn))
            elif sys.platform != "win32" and not low.endswith((".dll", ".so", ".dylib", ".txt", ".json", ".pck", ".pak")):
                p = os.path.join(root, fn)
                if os.access(p, os.X_OK) and not os.path.isdir(p):
                    found_paths.append(p)

    return found_paths


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
                if low.endswith(".exe") and not is_ignored_executable_name(fn):
                    root_exes.append(p)
                elif sys.platform != "win32" and not low.endswith((".dll", ".so", ".dylib", ".txt", ".json", ".pck", ".pak")):
                    if os.access(p, os.X_OK):
                        root_exes.append(p)
    except OSError:
        pass

    root_match = next(
        (p for p in root_exes if os.path.basename(p).lower() in {f"{dir_name}.exe", f"{dir_name}"}),
        None,
    )
    if root_match:
        return root_match

    # 3, 4, 5: Nested executables (common in Unreal Engine / AAA titles)
    all_exes = _scan_dir_executables(game_dir_abs)
    if not all_exes:
        return None

    shippings = []
    win64_exes = []
    for full_p in all_exes:
        low = os.path.basename(full_p).lower()
        if "-shipping.exe" in low:
            shippings.append(full_p)
        elif "binaries" in full_p.lower() and "win64" in full_p.lower():
            win64_exes.append(full_p)

    if shippings:
        for p in shippings:
            if dir_name in os.path.basename(p).lower():
                return p
        return shippings[0]

    if win64_exes:
        return win64_exes[0]

    return root_exes[0] if root_exes else all_exes[0]


def find_game_executables(game_dir: str) -> list[str]:
    """Find primary game executable names inside game_dir."""
    if not os.path.isdir(game_dir):
        return []
    exes = set()
    primary = find_primary_executable_path(game_dir)
    primary_name = os.path.basename(primary) if primary else None

    # Check root level first
    game_dir_abs = os.path.abspath(game_dir)
    try:
        for fn in os.listdir(game_dir_abs):
            low = fn.lower()
            if low.endswith(".exe") and not is_ignored_executable_name(fn):
                exes.add(fn)
            elif sys.platform != "win32" and not low.endswith((".dll", ".so", ".dylib", ".txt", ".json", ".pck", ".pak")):
                p = os.path.join(game_dir_abs, fn)
                if os.path.isfile(p) and os.access(p, os.X_OK):
                    exes.add(fn)
    except OSError:
        pass

    # If root had executables and primary is among them, avoid deep scan
    if not exes or (primary_name and primary_name not in exes):
        all_paths = _scan_dir_executables(game_dir_abs)
        for p in all_paths:
            exes.add(os.path.basename(p))

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


def _get_running_processes_tasklist(known_exes_lower: set[str], force_refresh: bool = False) -> list[dict]:
    """Native Windows fallback using tasklist command with snapshot caching."""
    global _PROCESS_CACHE
    now = time.time()

    if force_refresh or (now - _PROCESS_CACHE["timestamp"] >= _PROCESS_CACHE_TTL):
        creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000) if sys.platform == "win32" else 0
        parsed = []
        try:
            proc = subprocess.run(
                ["tasklist", "/FO", "CSV", "/NH"],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                creationflags=creationflags,
                timeout=3,
            )
            if proc.returncode == 0:
                raw_out = proc.stdout
                text_out = None
                for enc in ("gbk", "utf-8", "cp1252", sys.getfilesystemencoding()):
                    try:
                        text_out = raw_out.decode(enc)
                        break
                    except Exception:
                        continue
                if text_out is None:
                    text_out = raw_out.decode("latin-1", errors="ignore")
                reader = csv.reader(io.StringIO(text_out))
                for row in reader:
                    if len(row) >= 2:
                        name = row[0].strip()
                        try:
                            pid = int(row[1].strip())
                            parsed.append((name, pid))
                        except ValueError:
                            continue
        except Exception:
            pass
        _PROCESS_CACHE = {"timestamp": now, "processes": parsed}

    hits = []
    for name, pid in _PROCESS_CACHE["processes"]:
        n_low = name.lower()
        n_stem = n_low[:-4] if n_low.endswith(".exe") else n_low
        if n_low in known_exes_lower or n_stem in known_exes_lower:
            hits.append({
                "pid": pid,
                "name": name,
                "exe": "",
            })
    return hits


def _get_running_processes_ps(known_exes_lower: set[str], force_refresh: bool = False) -> list[dict]:
    """Native POSIX fallback using ps command with snapshot caching."""
    global _PROCESS_CACHE
    now = time.time()

    if force_refresh or (now - _PROCESS_CACHE["timestamp"] >= _PROCESS_CACHE_TTL):
        parsed = []
        try:
            proc = subprocess.run(
                ["ps", "-eo", "pid,comm"],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                timeout=3,
            )
            if proc.returncode == 0:
                for line in proc.stdout.splitlines():
                    parts = line.strip().split(None, 1)
                    if len(parts) == 2:
                        try:
                            pid = int(parts[0])
                            comm = parts[1].strip()
                            parsed.append((comm, pid))
                        except ValueError:
                            continue
        except Exception:
            pass
        _PROCESS_CACHE = {"timestamp": now, "processes": parsed}

    hits = []
    for comm, pid in _PROCESS_CACHE["processes"]:
        comm_base = os.path.basename(comm).lower()
        comm_stem = comm_base[:-4] if comm_base.endswith(".exe") else comm_base
        if comm_base in known_exes_lower or comm_stem in known_exes_lower or comm.lower() in known_exes_lower:
            hits.append({
                "pid": pid,
                "name": comm,
                "exe": "",
            })
    return hits


def get_running_game_processes(game_dir: str, force_refresh: bool = False) -> list[dict]:
    """Return active processes whose executable path or name matches game_dir."""
    if not game_dir or not os.path.isdir(game_dir):
        return []

    if force_refresh:
        global _PROCESS_CACHE
        _PROCESS_CACHE["timestamp"] = 0.0

    game_dir_abs = os.path.realpath(game_dir)
    found_exes = find_game_executables(game_dir)
    known_exes_lower = {e.lower() for e in found_exes}

    # Also include the folder name itself as possible binary name (e.g. Raft -> raft.exe)
    base_name = os.path.basename(os.path.normpath(game_dir)).lower()
    if base_name:
        known_exes_lower.add(base_name)
        known_exes_lower.add(f"{base_name}.exe")
        known_exes_lower.add(base_name.replace(" ", "") + ".exe")
        known_exes_lower.add(base_name.replace(" ", "_") + ".exe")
        known_exes_lower.add(base_name.replace(" ", "-") + ".exe")

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
                    p_name_stem = p_name_low[:-4] if p_name_low.endswith(".exe") else p_name_low
                    p_exe = info.get("exe") or ""
                    cwd = info.get("cwd") or ""

                    matched = False

                    # Check 1: Executable path is inside game directory
                    if p_exe and _is_subpath(game_dir_abs, p_exe):
                        matched = True
                    # Check 2: Working directory is inside game directory
                    elif cwd and _is_subpath(game_dir_abs, cwd):
                        matched = True
                    # Check 3: Process name matches known game executable
                    elif p_name_low and (p_name_low in known_exes_lower or p_name_stem in known_exes_lower):
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
                        p_name_low = p_name.lower() if p_name else ""
                        p_name_stem = p_name_low[:-4] if p_name_low.endswith(".exe") else p_name_low
                        if p_name_low and (p_name_low in known_exes_lower or p_name_stem in known_exes_lower):
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

    # Step 2: Fallback to native tasklist (Windows) or ps (POSIX) when psutil is unavailable or returned no hits
    if not hits:
        if sys.platform == "win32":
            hits = _get_running_processes_tasklist(known_exes_lower, force_refresh=force_refresh)
        else:
            hits = _get_running_processes_ps(known_exes_lower, force_refresh=force_refresh)

    return hits


def is_game_running(game_dir: str, force_refresh: bool = False) -> tuple[bool, list[dict]]:
    """Check if any game process from `game_dir` is currently active."""
    procs = get_running_game_processes(game_dir, force_refresh=force_refresh)
    return len(procs) > 0, procs


def check_game_status(game_dir: str, force_refresh: bool = False) -> dict:
    """Check game executable status: detected binaries, whether any game process is running, and lock risk."""
    game_dir_abs = os.path.abspath(game_dir) if game_dir else ""
    exes = find_game_executables(game_dir_abs) if game_dir_abs else []
    running, running_procs = is_game_running(game_dir_abs, force_refresh=force_refresh) if game_dir_abs else (False, [])
    return {
        "game_dir": game_dir_abs,
        "executables": exes,
        "is_running": running,
        "running_processes": running_procs,
        "processes": running_procs,
        "lock_warning": "Game is currently running! File operations (install/update/uninstall) may fail due to file locks." if running else None,
    }
