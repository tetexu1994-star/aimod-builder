"""Thin, shell-free wrapper around the `rea` CLI (morluto/rea)."""
from __future__ import annotations

import json
import re
import shutil
import subprocess
from collections.abc import Sequence

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


def _run(args: Sequence[str], token_limit: int = _TOKEN_LIMIT) -> str:
    rea = _find_rea()
    if not rea:
        raise RuntimeError("rea not found. Install it: npm install -g rea-agents")
    cmd = [rea, *args, "--format", "json", "--token-limit", str(token_limit)]
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=600, check=False)
    except FileNotFoundError:
        raise RuntimeError("rea not found. Install it: npm install -g rea-agents") from None
    if r.returncode != 0:
        detail = (r.stderr or r.stdout or "").strip()
        raise RuntimeError(f"rea command failed ({r.returncode}): {detail[:1000]}")
    return (r.stdout or "").strip()


def run(args: Sequence[str], token_limit: int = _TOKEN_LIMIT) -> str:
    """Run a REA command without a shell and return its JSON output."""
    return _run(args, token_limit)


def managed_members(path: str, type_name: str | None = None) -> str:
    args = ["inspect-managed-members", path]
    if type_name:
        args += ["--type", type_name]
    return _run(args)


def managed_artifact(path: str) -> str:
    return _run(["inspect-managed-artifact", path])


def pe_resources(path: str) -> str:
    return _run(["inspect-pe-resources", path])


def javascript_application(path: str) -> str:
    return _run(["analyze-javascript-application", path])


def disassemble(target: str, symbol_or_addr: str) -> str:
    return _run(["function", target, symbol_or_addr])


def call_graph(target: str, symbol: str) -> str:
    return _run(["xrefs", target, symbol])


def decompile(target: str, symbol_or_addr: str) -> str:
    return _run(["decompile", target, symbol_or_addr])


def search(target: str, query: str) -> str:
    return _run(["search", target, query])


def trace(target: str, query: str) -> str:
    return _run(["trace", target, query])


def sqlite_database(path: str) -> str:
    return _run(["inspect-sqlite-database", path])


def fast_search_members(path: str, query: str, limit: int = 50) -> list[str]:
    raw = managed_members(path)
    pattern = re.compile(re.escape(query), re.IGNORECASE)
    results: list[str] = []
    for line in _text_values(raw):
        if pattern.search(line):
            results.append(line.strip())
            if len(results) >= limit:
                break
    return results


def _text_values(raw: str):
    try:
        value = json.loads(raw)
    except (TypeError, ValueError):
        yield from raw.splitlines()
        return

    def walk(item):
        if isinstance(item, str):
            yield item
        elif isinstance(item, dict):
            for key, child in item.items():
                yield from walk(key)
                yield from walk(child)
        elif isinstance(item, list):
            for child in item:
                yield from walk(child)

    yield from walk(value)
