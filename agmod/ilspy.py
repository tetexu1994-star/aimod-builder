"""ilspycmd: programmatic .NET decompilation via ILSpy (MIT).

Used to recover Unity Mono source/structures (e.g. Assembly-CSharp.dll) so an
agent can read game logic without a GUI decompiler. Auto-installs the `ilspycmd`
dotnet global tool when dotnet is available.
"""
from __future__ import annotations

import os
import shutil
import subprocess

from . import sdk


def _ilspy_dir() -> str:
    d = os.path.join(os.path.expanduser("~"), ".agmod", "tools", "ilspy")
    os.makedirs(d, exist_ok=True)
    return d


def find_ilspycmd() -> str | None:
    p = shutil.which("ilspycmd")
    if p:
        return p
    local = os.path.join(_ilspy_dir(), "ilspycmd.exe")
    return local if os.path.isfile(local) else None


def ensure_ilspycmd() -> str:
    existing = find_ilspycmd()
    if existing:
        return existing
    dotnet = sdk.ensure_dotnet()
    tool_dir = _ilspy_dir()
    subprocess.run(
        [dotnet, "tool", "install", "--tool-path", tool_dir, "ilspycmd"],
        check=True, capture_output=True, text=True, encoding="utf-8", errors="replace",
    )
    local = os.path.join(tool_dir, "ilspycmd.exe")
    if not os.path.isfile(local):
        raise RuntimeError("ilspycmd install failed")
    return local


def decompile_project(assembly: str, out_dir: str) -> str:
    """Decompile a whole assembly into a rebuildable C# project."""
    ilspy = ensure_ilspycmd()
    os.makedirs(out_dir, exist_ok=True)
    subprocess.run(
        [ilspy, "-p", "-o", out_dir, assembly],
        check=True, capture_output=True, text=True, encoding="utf-8", errors="replace",
    )
    return out_dir


def decompile_type(assembly: str, type_name: str) -> str:
    """Decompile a single type to C# text."""
    ilspy = ensure_ilspycmd()
    r = subprocess.run(
        [ilspy, "-t", type_name, assembly],
        capture_output=True, text=True, encoding="utf-8", errors="replace", check=False,
    )
    if r.returncode != 0:
        raise RuntimeError((r.stderr or r.stdout or "").strip()[:1000])
    return (r.stdout or "").strip()
