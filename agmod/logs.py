"""Mod runtime log inspector and failure diagnostics.

Locates and parses logs produced by BepInEx, UE4SS, tModLoader, or native engines,
extracting exceptions, failed patches, and syntax errors to enable agent self-healing.
"""
from __future__ import annotations

import glob
import os
import re


# Known log patterns across mod frameworks
_LOG_CANDIDATES = [
    # Unity / BepInEx
    os.path.join("BepInEx", "LogOutput.log"),
    os.path.join("BepInEx", "log.txt"),
    "output_log.txt",
    os.path.join("*_Data", "output_log.txt"),
    # Unreal / UE4SS
    os.path.join("*", "Binaries", "Win64", "ue4ss", "UE4SS.log"),
    os.path.join("*", "Binaries", "Win64", "Mods", "UE4SS.log"),
    os.path.join("Binaries", "Win64", "ue4ss", "UE4SS.log"),
    os.path.join("ue4ss", "UE4SS.log"),
    # tModLoader / Terraria
    os.path.join("tModLoader-Logs", "Launch.log"),
    os.path.join("tModLoader-Logs", "client.log"),
]

# Error patterns to detect in logs
_ERROR_PATTERNS = [
    (re.compile(r"NullReferenceException", re.I), "NullReferenceException: Object reference not set to an instance of an object"),
    (re.compile(r"Patch\s+failed|Failed\s+to\s+patch", re.I), "Harmony patch failed: Target method or signature not found"),
    (re.compile(r"MethodNotFoundException|MissingMethodException", re.I), "MethodNotFoundException: Incompatible game version or method renamed"),
    (re.compile(r"Lua\s+error|syntax\s+error", re.I), "Lua runtime or syntax error in UE4SS script"),
    (re.compile(r"System\.IO\.FileNotFoundException", re.I), "FileNotFoundException: Missing dependency or assembly reference"),
]


def find_mod_logs(game_dir: str) -> list[str]:
    """Find all potential mod framework log files in the game directory."""
    hits: list[str] = []
    if not os.path.isdir(game_dir):
        return hits

    root = os.path.realpath(game_dir)
    for pattern in _LOG_CANDIDATES:
        full_pattern = os.path.join(game_dir, pattern)
        for match in glob.glob(full_pattern):
            real = os.path.realpath(match)
            try:
                contained = os.path.commonpath([root, real]) == root
            except ValueError:
                contained = False
            if os.path.isfile(match) and not os.path.islink(match) and contained:
                hits.append(os.path.abspath(match))
    return hits


def read_mod_logs(game_dir: str, tail_lines: int = 120) -> dict:
    """Read recent lines of the mod log and perform automated diagnostics."""
    if not isinstance(tail_lines, int) or not 1 <= tail_lines <= 10000:
        raise ValueError("tail_lines must be between 1 and 10000")
    logs = find_mod_logs(game_dir)
    if not logs:
        return {
            "found": False,
            "message": "No mod framework log files found yet. Launch the game once with the mod loader installed.",
            "candidates_checked": _LOG_CANDIDATES,
        }

    # Pick the most recently modified log
    logs.sort(key=lambda p: os.path.getmtime(p), reverse=True)
    active_log = logs[0]

    try:
        with open(active_log, "r", encoding="utf-8", errors="replace") as f:
            lines = f.readlines()
    except OSError as exc:
        return {
            "found": True,
            "log_path": active_log,
            "error": f"Failed to read log file: {exc}",
        }

    tail = lines[-tail_lines:] if len(lines) > tail_lines else lines
    content = "".join(tail)

    # Run diagnostics
    diagnostics: list[str] = []
    for pat, desc in _ERROR_PATTERNS:
        if pat.search(content):
            diagnostics.append(desc)

    return {
        "found": True,
        "log_path": active_log,
        "total_lines": len(lines),
        "tail_lines": len(tail),
        "content": content,
        "diagnostics": diagnostics,
        "has_errors": bool(diagnostics),
    }
