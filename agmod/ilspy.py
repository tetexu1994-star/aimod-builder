"""ilspycmd: programmatic .NET decompilation via ILSpy (MIT).

Used to recover Unity Mono source/structures (e.g. Assembly-CSharp.dll) so an
agent can read game logic without a GUI decompiler. Auto-installs the `ilspycmd`
dotnet global tool when dotnet is available.
"""
from __future__ import annotations

import os
import shutil
import subprocess


def find_ilspycmd() -> str | None:
    p = shutil.which("ilspycmd")
    return p if p else None


def ensure_ilspycmd() -> str:
    existing = find_ilspycmd()
    if existing:
        return existing
    dotnet = shutil.which("dotnet")
    if not dotnet:
        raise RuntimeError(
            "ilspycmd requires the .NET SDK. Install it: https://dotnet.microsoft.com/download"
        )
    subprocess.run(
        [dotnet, "tool", "install", "--global", "ilspycmd"],
        check=True, capture_output=True, text=True,
    )
    installed = find_ilspycmd()
    if not installed:
        raise RuntimeError(
            "ilspycmd install succeeded but was not found on PATH; "
            "add the dotnet tools bin directory to PATH"
        )
    return installed


def decompile_project(assembly: str, out_dir: str) -> str:
    """Decompile a whole assembly into a rebuildable C# project."""
    ilspy = ensure_ilspycmd()
    os.makedirs(out_dir, exist_ok=True)
    subprocess.run(
        [ilspy, "-p", "-o", out_dir, assembly],
        check=True, capture_output=True, text=True,
    )
    return out_dir


def decompile_type(assembly: str, type_name: str) -> str:
    """Decompile a single type to C# text."""
    ilspy = ensure_ilspycmd()
    r = subprocess.run(
        [ilspy, "-t", type_name, assembly],
        capture_output=True, text=True, check=False,
    )
    if r.returncode != 0:
        raise RuntimeError((r.stderr or r.stdout or "").strip()[:1000])
    return (r.stdout or "").strip()
