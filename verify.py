"""Verify the full project: imports, adapters, PE check, GitHub updater, tool wiring."""
import os
import shutil
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import server
from agmod import updater
from agmod.pe import is_managed_assembly
from agmod.registry import adapters, detect_engine

print("adapters:", [a.id for a in adapters()])
print("detect(non-game):", detect_engine(r"C:\Users\Administrator\kanbanpachong"))
print("is_managed(aimodv1.exe native):", is_managed_assembly(r"C:\Users\Administrator\Desktop\aimodv1.exe"))
print("dotnet available:", shutil.which("dotnet") or "NOT FOUND")

tools = [
    "detect_engine", "dump_structures", "find_field", "find_process",
    "scan_value", "scan_start", "scan_next", "scan_reset", "pattern_scan",
    "inspect_feature", "read_memory", "write_memory",
    "install_bepinex", "scaffold_mod", "build_mod",
    "scaffold_ue4ss_mod", "install_ue4ss_mod",
    "check_update", "update_mod",
]
print("tools wired:", {t: hasattr(server, t) for t in tools})

print("check_update(morluto/rea vs 0.0.0):", updater.check_update("morluto", "rea", "0.0.0"))
