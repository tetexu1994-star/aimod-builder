"""Thin, shell-free wrapper around the `rea` CLI (morluto/rea v6.7+)."""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
from collections.abc import Sequence

from .config import REA_PATH

_TOKEN_LIMIT = 3000


def _find_rea() -> str | None:
    """Find the best command invocation for REA CLI, supporting Windows, Mac, and npm/npx."""
    if REA_PATH:
        return REA_PATH

    # 1. Specialized Windows Node 24 runtime check to ensure exact file stat precision
    if sys.platform == "win32":
        node_candidates = [
            r"C:\Users\qeeyou\.ai-manager\runtimes\node\24.18.0\node.exe",
            r"D:\node-v22.14.0-win-x64\node.exe",
        ]
        mjs_candidates = [
            r"D:\npm-global\node_modules\rea-agents\scripts\rea.mjs",
            os.path.expandvars(r"%APPDATA%\npm\node_modules\rea-agents\scripts\rea.mjs"),
        ]
        for nc in node_candidates:
            if os.path.isfile(nc):
                for mc in mjs_candidates:
                    if os.path.isfile(mc):
                        return f'"{nc}" "{mc}"'

        for p in (r"D:\npm-global\rea.cmd", os.path.expandvars(r"%APPDATA%\npm\rea.cmd")):
            if os.path.isfile(p):
                return p

    # 2. System PATH lookup
    for name in ("rea", "rea.cmd", "rea.exe"):
        p = shutil.which(name)
        if p:
            return p

    # 3. Unix common npm global locations
    if sys.platform != "win32":
        user_npm = os.path.expanduser("~/.npm-global/bin/rea")
        if os.path.isfile(user_npm):
            return user_npm
        for p in ("/usr/local/bin/rea", "/opt/homebrew/bin/rea"):
            if os.path.isfile(p):
                return p

    # 4. Fallback to npx if node/npx is available
    npx = shutil.which("npx") or shutil.which("npx.cmd")
    if npx:
        return f"{npx} --yes rea-agents"

    return None


def _find_rea_cmd() -> list[str] | None:
    """Return a list of command arguments for invoking REA."""
    rea = _find_rea()
    if not rea:
        return None
    if " " in rea and not os.path.exists(rea):
        import shlex
        return shlex.split(rea)
    return [rea]


def _run(args: Sequence[str], token_limit: int | None = None) -> str:
    cmd_prefix = _find_rea_cmd()
    if not cmd_prefix:
        raise RuntimeError("rea not found. Install it: npm install -g rea-agents")

    # In REA v6+, --format json cannot be combined with --token-limit
    cmd = [*cmd_prefix, *args, "--format", "json"]

    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=600, check=False)
    except FileNotFoundError:
        raise RuntimeError("rea not found. Install it: npm install -g rea-agents") from None
    if r.returncode != 0:
        detail = (r.stderr or r.stdout or "").strip()
        raise RuntimeError(f"rea command failed ({r.returncode}): {detail[:1000]}")
    return (r.stdout or "").strip()


def run(args: Sequence[str], token_limit: int | None = None) -> str:
    """Run a REA command without a shell and return its JSON output."""
    return _run(args, token_limit)


def inspect_managed_artifact(path: str) -> dict:
    """Identify managed PE/CLI identity, runtime family (unity-mono, dotnet), and metadata."""
    raw = _run(["inspect-managed-artifact", path])
    try:
        return json.loads(raw)
    except Exception:
        return {"raw": raw}


def inspect_managed_members(path: str, type_names: Sequence[str] | str | None = None) -> dict:
    """Deeply inspect member signatures, CIL anchors, and fields within managed assembly."""
    args = ["inspect-managed-members", path]
    if type_names:
        if isinstance(type_names, str):
            type_names = [type_names]
        for t in type_names:
            if t:
                args.extend(["--type", t])
    raw = _run(args)
    try:
        return json.loads(raw)
    except Exception:
        return {"raw": raw}


def managed_members(path: str, type_name: str | None = None) -> str:
    args = ["inspect-managed-members", path]
    if type_name:
        args.extend(["--type", type_name])
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


def fast_search_members(
    path: str,
    query: str,
    candidate_types: Sequence[str] | None = None,
    limit: int = 50,
) -> list[str]:
    """Smart targeted search of game classes and methods using REA v6.7 managed analysis.

    Uses candidate types to prevent the 64MB metadata representation budget limit,
    returning structured Type:Method or Type.Field entries.
    """
    if not path or not os.path.isfile(path):
        return []

    q_low = query.lower().strip()
    matched: list[str] = []
    seen = set()

    # Determine candidate types for deep inspection
    types_to_try: list[str] = list(candidate_types) if candidate_types else []
    if not types_to_try:
        # Inferred domain types based on query keyword
        inferred = [
            "Player", "PlayerStats", "PlayerController", "Character", "CharacterMotor",
            "PlayerMovement", "Movement", "Health", "PlayerHealth", "Stats", "Combat",
            "GameManager", "Inventory", "PlayerInventory", "Farmer", "HeroController"
        ]
        if q_low:
            title_q = q_low.capitalize()
            types_to_try.extend([title_q, f"Player{title_q}", f"{title_q}Controller", f"{title_q}Manager", f"{title_q}Stats"])
        for inf in inferred:
            if inf not in types_to_try:
                types_to_try.append(inf)

    # 1. Try REA targeted type inspection
    try:
        for t in types_to_try[:6]:
            try:
                res = inspect_managed_members(path, type_names=t)
                norm = res.get("normalized_result") or {}
                # Methods
                for m in norm.get("methods", []):
                    name = m.get("name")
                    if name and (not q_low or q_low in name.lower() or q_low in t.lower()):
                        item = f"{t}:{name}"
                        if item not in seen:
                            seen.add(item)
                            matched.append(item)
                            if len(matched) >= limit:
                                return matched
                # Fields
                for f in norm.get("fields", []):
                    name = f.get("name")
                    if name and (not q_low or q_low in name.lower() or q_low in t.lower()):
                        item = f"{t}.{name}"
                        if item not in seen:
                            seen.add(item)
                            matched.append(item)
                            if len(matched) >= limit:
                                return matched
            except Exception:
                continue
    except Exception:
        pass

    if matched:
        return matched

    # 2. Fallback: inspect without --type or string stream
    try:
        raw = managed_members(path)
        pattern = re.compile(re.escape(query), re.IGNORECASE)
        for line in _text_values(raw):
            if pattern.search(line):
                clean = line.strip()
                if clean not in seen:
                    seen.add(clean)
                    matched.append(clean)
                    if len(matched) >= limit:
                        break
    except Exception:
        pass

    return matched


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

