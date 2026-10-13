"""Thin wrapper around the `rea` CLI (morluto/rea) for static and binary analysis.

rea bridges coding agents to software reverse engineering tools (Ghidra, Hopper,
IDA, ASAR, .NET members) with structured evidence.

It needs `npm install -g rea-agents` (or the `rea` command on PATH). Without it,
the wrapper raises a clear error instead of failing silently.
"""
from __future__ import annotations

import re
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


def run(command: str, target: str, extra_args: str = "", token_limit: int = _TOKEN_LIMIT) -> str:
    rea = _find_rea()
    if not rea:
        raise RuntimeError("rea not found. Install it: npm install -g rea-agents")
    cmd = f'"{rea}" {command} "{target}" {extra_args} --token-limit {token_limit}'.strip()
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


def disassemble(target: str, symbol_or_addr: str) -> str:
    """Disassemble / inspect a native function via REA."""
    return run("inspect-function", target, extra_args=f'--symbol "{symbol_or_addr}"')


def call_graph(target: str, symbol: str) -> str:
    """Inspect the call graph and references of a function via REA."""
    return run("inspect-call-graph", target, extra_args=f'--symbol "{symbol}"')


def fast_search_members(path: str, query: str, limit: int = 50) -> list[str]:
    """Lightweight search inside .NET members without full project decompilation."""
    raw = managed_members(path)
    pattern = re.compile(re.escape(query), re.IGNORECASE)
    results: list[str] = []
    for line in raw.splitlines():
        if pattern.search(line):
            results.append(line.strip())
            if len(results) >= limit:
                break
    return results
