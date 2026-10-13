"""Fast, machine-independent smoke check for imports and MCP tool wiring."""
from __future__ import annotations

import os
import shutil
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import server
from agmod.pe import is_managed_assembly
from agmod.registry import adapters, detect_engine

print("adapters:", [a.id for a in adapters()])
with tempfile.TemporaryDirectory() as d:
    print("detect(empty):", detect_engine(d))
print("is_managed(Python source):", is_managed_assembly(__file__))
print("dotnet available:", shutil.which("dotnet") or "NOT FOUND")

tools = [
    "check_environment", "detect_engine", "inspect_feature", "plan_mod", "validate_mod_project",
    "dump_structures", "find_field", "get_source", "find_process",
    "scan_value", "scan_start", "scan_next", "scan_reset", "pattern_scan",
    "read_memory", "write_memory",
    "install_bepinex", "scaffold_mod", "build_mod", "diagnose_build_error",
    "scaffold_ue4ss_mod", "install_ue4ss_mod",
    "scaffold_tmod_mod", "build_tmod_mod", "install_tmod_mod",
    "scaffold_reframework_mod", "install_reframework_mod",
    "scaffold_godot_mod", "install_godot_mod",
    "read_mod_logs", "create_save_backup", "list_save_backups", "restore_save_backup",
    "check_game_status", "uninstall_mod", "rollback_game", "list_installs", "check_install_conflicts",
    "check_update", "update_mod", "package_mod", "validate_package",
    "rea_managed_members", "rea_analyze_js", "rea_inspect_pe",
    "rea_disassemble", "rea_call_graph", "rea_fast_search",
]
status = {t: hasattr(server, t) for t in tools}
print("tools wired:", status)
missing = [t for t, ok in status.items() if not ok]
if missing:
    print(f"ERROR: missing tools: {missing}")
    sys.exit(1)

