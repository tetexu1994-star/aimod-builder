"""Fast, machine-independent smoke check for imports and MCP tool wiring."""
from __future__ import annotations

import ast
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

def _registered_tools() -> list[str]:
    with open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "server.py"), "r", encoding="utf-8") as f:
        tree = ast.parse(f.read())
    tools = []
    for node in tree.body:
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        for decorator in node.decorator_list:
            if isinstance(decorator, ast.Call) and isinstance(decorator.func, ast.Attribute) and decorator.func.attr == "tool":
                tools.append(node.name)
                break
    return tools


tools = _registered_tools()
status = {t: hasattr(server, t) for t in tools}
print("tools wired:", status)
missing = [t for t, ok in status.items() if not ok]
if missing:
    print(f"ERROR: missing tools: {missing}")
    sys.exit(1)

