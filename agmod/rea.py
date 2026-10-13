"""Thin wrapper around the `rea` CLI (morluto/rea) for its static-analysis tools.

rea fills the gaps this project doesn't implement natively yet:
  - inspect-managed-members : .NET type/field/method inventory (no decompiler)
  - inspect-managed-artifact : confirm a PE is managed vs native
  - inspect-pe-resources    : PE icons/version/manifest
  - analyze-javascript-application : Electron/JS app module graph

It needs `npm install -g rea-agents` (or the `rea` command on PATH). Without it,
the wrapper raises a clear error instead of failing silently.
"""
from __future__ import annotations

import shutil
import subprocess

from .config import REA_PATH

_TOKEN_LIMIT = 3000


def _find_rea() -> str | None:
    if REA_PATH:
        return REA_PATH
    for name in ("rea", "rea.cmd", "rea.exe"):
        p = shutil.which(name)
        if p:
            return p
    return None


def run(command: str, target: str, token_limit: int = _TOKEN_LIMIT) -> str:
    rea = _find_rea()
    if not rea:
        raise RuntimeError("rea not found. Install it: npm install -g rea-agents")
    cmd = f'"{rea}" {command} "{target}" --token-limit {token_limit}'
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=600, shell=True)
    except FileNotFoundError:
        raise RuntimeError("rea not found. Install it: npm install -g rea-agents") from None
    out = (r.stdout or "").strip()
    if not out:
        out = (r.stderr or "").strip()
    return out


def managed_members(path: str) -> str:
    """List .NET types/fields/methods of a managed PE (no decompiler needed)."""
    return run("inspect-managed-members", path)


def managed_artifact(path: str) -> str:
    """Confirm whether a PE is managed (.NET) or native."""
    return run("inspect-managed-artifact", path)


def pe_resources(path: str) -> str:
    """Inspect a PE's icons/version/manifest resources."""
    return run("inspect-pe-resources", path)


def javascript_application(path: str) -> str:
    """Reconstruct an Electron/JS app's module graph."""
    return run("analyze-javascript-application", path)
