"""Runtime mod log parser and error self-healing diagnostic analyzer.

Parses runtime crashes and execution errors from BepInEx, UE4SS, REFramework,
and GodotModLoader logs, pinpointing file paths, line numbers, and suggesting
direct code fixes.
"""
from __future__ import annotations

import re


def diagnose_runtime_error(log_text: str) -> dict:
    """Analyze runtime crash/error log snippet and suggest actionable fixes."""
    if not log_text or not log_text.strip():
        return {
            "has_error": False,
            "issues": [],
            "summary": "log snippet is empty",
        }

    issues = []

    # 1. UE4SS Lua Errors
    # e.g.: [LuaError] .../scripts/main.lua:42: attempt to index a nil value
    for match in re.finditer(r"\[LuaError\]\s*(.*?):(\d+):\s*(.*)", log_text):
        file_path, line_no, msg = match.groups()
        suggestion = "Check that the target UObject is valid using `if obj and obj:IsValid() then ... end`."
        if "syntax error" in msg.lower():
            suggestion = "Fix Lua syntax error (check unmatched parentheses, brackets, or 'then/end' keywords)."
        elif "attempt to call" in msg.lower():
            suggestion = "Verify that the function name exists on the target UObject before calling it."

        issues.append({
            "framework": "UE4SS",
            "file": file_path.strip(),
            "line": int(line_no),
            "raw_message": msg.strip(),
            "category": "LuaRuntimeError",
            "suggestion": suggestion,
        })

    # 2. REFramework Errors
    # e.g.: [REFramework] Sol: runtime error: [string "autorun/my_mod.lua"]:25: ...
    for match in re.finditer(r"\[REFramework\].*?\[string\s*\"(.*?)\"\]:(\d+):\s*(.*)", log_text):
        file_path, line_no, msg = match.groups()
        suggestion = "Check sdk.to_managed_object() return value and ensure args are not nil."
        if "attempt to index" in msg.lower():
            suggestion = "Add nil checks before accessing fields: `if obj ~= nil then ... end`."

        issues.append({
            "framework": "REFramework",
            "file": file_path.strip(),
            "line": int(line_no),
            "raw_message": msg.strip(),
            "category": "REFrameworkLuaError",
            "suggestion": suggestion,
        })

    # 2b. REFramework Type/Method Not Found
    for match in re.finditer(r"\[REFramework\]\s*(Type|Method)\s*['\"](.*?)['\"]\s*not found", log_text):
        kind, name = match.groups()
        issues.append({
            "framework": "REFramework",
            "file": "",
            "line": 0,
            "raw_message": f"{kind} '{name}' not found",
            "category": "SymbolNotFound",
            "suggestion": f"Check spelling of {kind.lower()} '{name}' using inspect_feature or REFramework Object Explorer.",
        })

    # 3. BepInEx / Harmony C# Errors
    # e.g.: System.NullReferenceException: Object reference not set to an instance of an object
    #       at MyNamespace.MyPlugin.Prefix (...) in ...\Plugin.cs:line 45
    for match in re.finditer(r"(System\.\w+Exception):\s*(.*?)\n\s*at\s+([^\r\n]+)", log_text):
        exc_type, exc_msg, callsite_full = match.groups()
        file_path = ""
        line_no = 0
        in_match = re.search(r"\s+in\s+(.*?):line\s+(\d+)", callsite_full)
        if in_match:
            file_path = in_match.group(1).strip()
            line_no = int(in_match.group(2))
            callsite = callsite_full[:in_match.start()].strip()
        else:
            callsite = callsite_full.strip()

        suggestion = "Inspect call site variables for null instances or invalid casts."
        if "NullReferenceException" in exc_type:
            suggestion = "Verify that __instance or target component is not null before accessing its members."
        elif "MissingMethodException" in exc_type:
            suggestion = "The target game method signature has changed in this game version. Re-run dump_structures."

        issues.append({
            "framework": "BepInEx",
            "file": file_path,
            "line": line_no,
            "raw_message": f"{exc_type}: {exc_msg.strip()} at {callsite}",
            "category": exc_type,
            "suggestion": suggestion,
        })

    # 4. Godot SCRIPT ERROR
    # e.g.: SCRIPT ERROR: Invalid get index 'val' (on base: 'Nil').
    #          at: _ready (res://mods-unpacked/Author-Mod/mod_main.gd:15)
    for match in re.finditer(r"SCRIPT ERROR:\s*(.*?)\n\s*at:\s*.*?\((.*?):(\d+)\)", log_text):
        msg, file_path, line_no = match.groups()
        suggestion = "Use get_node_or_null() and check `if node != null:` before calling methods or accessing properties."
        issues.append({
            "framework": "GodotModLoader",
            "file": file_path.strip(),
            "line": int(line_no),
            "raw_message": msg.strip(),
            "category": "GDScriptError",
            "suggestion": suggestion,
        })

    return {
        "has_error": len(issues) > 0,
        "issue_count": len(issues),
        "issues": issues,
        "summary": f"detected {len(issues)} runtime issue(s)" if issues else "no known runtime crashes or syntax errors detected",
    }
