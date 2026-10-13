"""game-mod-agent MCP server.

Register in Claude Code's `.mcp.json` (or any MCP client):

    { "mcpServers": { "game-mod-agent": {
        "command": "python",
        "args": ["<absolute-path>/server.py"]
    } } }

Exposes a stable tool set the agent drives in order:
    detect_engine -> dump_structures / inspect_feature -> find_field
    -> scan_start -> scan_next -> write_memory -> read_memory (verify)
    or scaffold_mod / scaffold_ue4ss_mod -> build / install
"""
from __future__ import annotations

import json
import os
import subprocess

try:
    from mcp.server.fastmcp import FastMCP
except ImportError:  # pragma: no cover
    class FastMCP:  # type: ignore
        def __init__(self, name: str):
            self.name = name

        def tool(self):
            def decorator(f):
                return f
            return decorator

        def run(self):
            print(f"FastMCP '{self.name}' stub: mcp not installed. Install with `pip install mcp`")

from agmod import bepinex, config, inspector, knowledge, memory, pack, pattern, rea, safety, tmodloader, updater
from agmod.adapters.unreal import UnrealAdapter
from agmod.registry import adapters, detect_engine as _detect_engine, get_adapter
from agmod.structures import load_table

CACHE_ROOT = config.CACHE_ROOT

try:
    import psutil
except ImportError:  # pragma: no cover
    psutil = None

mcp = FastMCP("game-mod-agent")


def _int_kinds():
    return {"int8", "uint8", "int16", "uint16", "int32", "uint32", "int64", "uint64"}


@mcp.tool()
def detect_engine(game_dir: str) -> str:
    """Detect the game engine for a directory. Returns {id, runtime, name}."""
    r = _detect_engine(game_dir)
    if r is None:
        return json.dumps({"detected": False, "hint": "not a supported engine"})
    return json.dumps(r, ensure_ascii=False)


@mcp.tool()
def inspect_feature(game_dir: str, keyword: str) -> str:
    """Inspect game structures for a desired feature (e.g. 'gold', 'health') and get recommended mod route in 1 call."""
    return json.dumps(inspector.inspect_feature(game_dir, keyword), ensure_ascii=False, indent=2)


@mcp.tool()
def dump_structures(game_dir: str) -> str:
    """Recover a game's structures (types/fields) and cache them by build fingerprint.

    Mono Unity: decompiles Assembly-CSharp.dll with ilspycmd.
    IL2CPP Unity: dumps global-metadata.dat with Cpp2IL.
    Unreal: produces UE4SS dumper / reflection guidance.
    """
    r = _detect_engine(game_dir)
    if r is None:
        return json.dumps({"error": "unsupported or unrecognized game directory"})
    adapter = get_adapter(r["id"])
    table = adapter.prepare(game_dir, CACHE_ROOT)
    return json.dumps(table.to_dict(), ensure_ascii=False, indent=2)


@mcp.tool()
def find_field(game_dir: str, query: str) -> str:
    """Grep the dumped structures for a field/type name (e.g. 'gold', 'money', 'health')."""
    r = _detect_engine(game_dir)
    if r is None:
        return json.dumps({"error": "run detect_engine first"})
    adapter = get_adapter(r["id"])
    game_id = os.path.basename(os.path.normpath(game_dir))
    fp = adapter.fingerprint(game_dir)
    table = load_table(CACHE_ROOT, game_id, fp)
    if table is None or not table.decomp_dir:
        return json.dumps({"error": "no structure dump yet; run dump_structures first"})

    matches = adapter.query(table, query)
    return json.dumps({"query": query, "matches": matches}, ensure_ascii=False, indent=2)


@mcp.tool()
def get_source(game_dir: str, name: str) -> str:
    """Return the decompiled source for a type/name (e.g. 'Player')."""
    r = _detect_engine(game_dir)
    if r is None:
        return json.dumps({"error": "run detect_engine first"})
    adapter = get_adapter(r["id"])
    game_id = os.path.basename(os.path.normpath(game_dir))
    table = load_table(CACHE_ROOT, game_id, adapter.fingerprint(game_dir))
    if table is None:
        return json.dumps({"error": "no structure dump yet; run dump_structures first"})
    src = adapter.source(table, name)
    if not src:
        return json.dumps({"error": f"no source found for '{name}'"})
    return src[:8000]


@mcp.tool()
def launch_game(game_dir: str) -> str:
    """Locate the game executable (full auto-launch/testing is future work)."""
    r = _detect_engine(game_dir)
    if r is None:
        return json.dumps({"error": "run detect_engine first"})
    info = get_adapter(r["id"]).launch(game_dir)
    return json.dumps(info or {"error": "launch not supported for this engine"}, ensure_ascii=False)


@mcp.tool()
def find_process(name: str) -> str:
    """List running processes whose name contains `name`. Returns pid + name."""
    if psutil is None:
        return json.dumps({"error": "psutil not installed"})
    hits = [{"pid": p.info["pid"], "name": p.info["name"]}
            for p in psutil.process_iter(["pid", "name"])
            if name.lower() in (p.info["name"] or "").lower()]
    return json.dumps(hits, ensure_ascii=False)


@mcp.tool()
def scan_start(pid: int, value: float, kind: str = "int32") -> str:
    """Start an iterative Cheat-Engine style scan session for `value` in the target process."""
    ok, reason = safety.check_target(pid)
    if not ok:
        return json.dumps({"ok": False, "error": reason})
    if kind in _int_kinds():
        value = int(value)
    h = memory.open_process(pid)
    try:
        sess = memory.get_scan_session(pid, kind)
        count = sess.start_scan(h, value)
    finally:
        memory.close_process(h)
    return json.dumps({
        "pid": pid,
        "round": sess.round,
        "kind": kind,
        "matched_count": count,
        "addresses_sample": [hex(a) for a in sess.candidates[:30]],
        "hint": "Now change the value inside the game, then call scan_next(pid, new_value) to narrow down.",
    })


@mcp.tool()
def scan_next(pid: int, new_value: float, scan_type: str = "exact") -> str:
    """Filter previous scan results by matching against `new_value`.

    `scan_type` is one of: exact, increased, decreased, changed, unchanged.
    """
    ok, reason = safety.check_target(pid)
    if not ok:
        return json.dumps({"ok": False, "error": reason})
    sess = memory.get_scan_session(pid)
    if not sess.candidates:
        return json.dumps({"error": "No active candidates. Call scan_start first."})
    if sess.kind in _int_kinds():
        new_value = int(new_value)
    h = memory.open_process(pid)
    try:
        count = sess.next_scan(h, new_value, scan_type=scan_type)
    finally:
        memory.close_process(h)
    return json.dumps({
        "pid": pid,
        "round": sess.round,
        "scan_type": scan_type,
        "remaining_count": count,
        "candidates": [hex(a) for a in sess.candidates[:30]],
        "converged": (count <= 3),
        "hint": "If remaining_count <= 3, you can write_memory to modify the value!" if count <= 3 else "Change value again in game and run scan_next.",
    })


@mcp.tool()
def scan_reset(pid: int = 0) -> str:
    """Clear memory scan session for a PID or all sessions."""
    if pid:
        memory.clear_scan_session(pid)
        return json.dumps({"status": f"Session cleared for pid {pid}"})
    memory.clear_all_sessions()
    return json.dumps({"status": "All scan sessions cleared"})


@mcp.tool()
def scan_value(pid: int, value: float, kind: str = "int32") -> str:
    """Cheat-Engine style single scan for `value` in the target process (compat wrapper)."""
    ok, reason = safety.check_target(pid)
    if not ok:
        return json.dumps({"ok": False, "error": reason})
    if kind in _int_kinds():
        value = int(value)
    h = memory.open_process(pid)
    try:
        hits = memory.scan_value(h, value, kind, limit=200)
    finally:
        memory.close_process(h)
    return json.dumps({"count": len(hits), "addresses": [hex(a) for a in hits[:60]]})


@mcp.tool()
def pattern_scan(pid: int, aob_pattern: str, limit: int = 20) -> str:
    """Scan process memory for an AOB byte signature with wildcards (e.g. '48 89 5C 24 ?? 48 89')."""
    ok, reason = safety.check_target(pid)
    if not ok:
        return json.dumps({"ok": False, "error": reason})
    try:
        hits = pattern.scan_process_pattern(pid, aob_pattern, limit=limit)
        return json.dumps({"pattern": aob_pattern, "matches": [hex(a) for a in hits]})
    except Exception as e:
        return json.dumps({"error": str(e)})


@mcp.tool()
def read_memory(pid: int, address: int, kind: str = "int32") -> str:
    """Read one value at `address` from the target process."""
    ok, reason = safety.check_target(pid)
    if not ok:
        return json.dumps({"ok": False, "error": reason})
    h = memory.open_process(pid)
    try:
        v = memory.read_value(h, address, kind)
    finally:
        memory.close_process(h)
    return json.dumps({"address": hex(address), "kind": kind, "value": v})


@mcp.tool()
def write_memory(pid: int, address: int, value: float, kind: str = "int32", dry_run: bool = False) -> str:
    """Write one value at `address`. Pass dry_run=True to preview without writing."""
    ok, reason = safety.check_target(pid)
    if not ok:
        return json.dumps({"ok": False, "error": reason})
    if kind in _int_kinds():
        value = int(value)
    if dry_run:
        return json.dumps({"dry_run": True, "address": hex(address), "kind": kind, "would_write": value})
    h = memory.open_process(pid)
    try:
        memory.write_value(h, address, value, kind)
        v = memory.read_value(h, address, kind)
    finally:
        memory.close_process(h)
    return json.dumps({"address": hex(address), "kind": kind, "written": value, "read_back": v})


@mcp.tool()
def install_bepinex(game_dir: str) -> str:
    """Install the BepInEx mod loader into a Unity game directory."""
    return bepinex.install_bepinex(game_dir)


@mcp.tool()
def scaffold_mod(project_dir: str, game_dir: str, mod_id: str, mod_name: str, mod_version: str = "1.0.0") -> str:
    """Write a BepInEx plugin project (Plugin.cs + .csproj) for a Unity game."""
    bepinex.scaffold_plugin(project_dir, game_dir, mod_id, mod_name, mod_version)
    return json.dumps({
        "project_dir": project_dir,
        "mod_id": mod_id,
        "hint": "edit Plugin.cs to add Harmony patches, then call build_mod",
    })


@mcp.tool()
def build_mod(project_dir: str, game_dir: str) -> str:
    """Build the BepInEx plugin and install the DLL into the game's BepInEx/plugins/."""
    installed = bepinex.build_plugin(project_dir, game_dir)
    return json.dumps({"installed": installed})


@mcp.tool()
def scaffold_ue4ss_mod(project_dir: str, mod_id: str, mod_name: str, mod_version: str = "1.0.0", author: str = "AI Mod Agent") -> str:
    """Generate a compiler-free Lua Mod skeleton for Unreal Engine (UE4 / UE5) using UE4SS."""
    adapter = UnrealAdapter()
    adapter.scaffold_mod(project_dir, mod_id, mod_name, mod_version, author)
    return json.dumps({
        "project_dir": project_dir,
        "engine": "unreal",
        "framework": "UE4SS",
        "hint": "Edit scripts/main.lua to register hooks via RegisterHook / StaticFindObject, then install_ue4ss_mod",
    })


@mcp.tool()
def install_ue4ss_mod(project_dir: str, game_dir: str, mod_id: str) -> str:
    """Install a UE4SS Lua Mod into the game's Binaries/Win64/ue4ss/Mods/<mod_id>/ directory."""
    adapter = UnrealAdapter()
    dest = adapter.install_mod(project_dir, game_dir, mod_id)
    return json.dumps({"installed": dest})


@mcp.tool()
def check_update(owner: str, repo: str, current_version: str) -> str:
    """Check a GitHub repo for a newer release/commit than `current_version`."""
    return json.dumps(updater.check_update(owner, repo, current_version))


@mcp.tool()
def update_mod(game_dir: str, owner: str, repo: str, entry_dll: str) -> str:
    """Download the latest release .dll from owner/repo into the game's BepInEx/plugins/."""
    dest = updater.update_mod(game_dir, owner, repo, entry_dll)
    return json.dumps({"installed": dest})


@mcp.tool()
def catalog() -> str:
    """List supported game engines and their adapters."""
    return json.dumps([a.describe() for a in adapters()], ensure_ascii=False)


@mcp.tool()
def scaffold_tmod_mod(project_dir: str, mod_id: str, mod_name: str, mod_version: str = "0.1.0", author: str = "") -> str:
    """Write a tModLoader mod skeleton for Terraria (Mod.cs + build.txt + .csproj)."""
    tmodloader.scaffold_tmod_mod(project_dir, mod_id, mod_name, mod_version, author)
    return json.dumps({
        "project_dir": project_dir,
        "engine": "tmodloader",
        "hint": "edit the Mod class, put tModLoader.dll + Terraria.dll in lib/, then build_tmod_mod",
    })


@mcp.tool()
def build_tmod_mod(project_dir: str) -> str:
    """Build a tModLoader mod with dotnet. Returns the output directory."""
    out = tmodloader.build_tmod_mod(project_dir)
    return json.dumps({"output": out})


@mcp.tool()
def rea_managed_members(path: str) -> str:
    """List .NET types/fields/methods of a managed assembly via rea (no decompiler needed)."""
    return rea.managed_members(path)


@mcp.tool()
def rea_analyze_js(path: str) -> str:
    """Reconstruct an Electron/JS app's module graph via rea."""
    return rea.javascript_application(path)


@mcp.tool()
def rea_inspect_pe(path: str) -> str:
    """Inspect a PE's icons/version/manifest via rea."""
    return rea.pe_resources(path)


@mcp.tool()
def rea_disassemble(target: str, symbol_or_addr: str) -> str:
    """Disassemble or inspect a native function in binary via REA."""
    return rea.disassemble(target, symbol_or_addr)


@mcp.tool()
def rea_call_graph(target: str, symbol: str) -> str:
    """Inspect function call graph and cross-references via REA."""
    return rea.call_graph(target, symbol)


@mcp.tool()
def rea_fast_search(path: str, query: str) -> str:
    """Fast-search .NET types and fields without running full decompiler."""
    matches = rea.fast_search_members(path, query)
    return json.dumps({"query": query, "matches": matches}, ensure_ascii=False)


@mcp.tool()
def record_knowledge(game: str, topic: str, content: str) -> str:
    """Save a per-game finding (field names, offsets, techniques) to the knowledge base."""
    path = knowledge.record(game, topic, content)
    return json.dumps({"saved": path})


@mcp.tool()
def lookup_knowledge(game: str, query: str = "") -> str:
    """Look up previously recorded findings for a game."""
    return knowledge.lookup(game, query) or json.dumps({"found": False})


@mcp.tool()
def package_mod(project_dir: str, output_dir: str = "") -> str:
    """Package a built mod into a Thunderstore/Nexus-style zip (manifest.json + dlls)."""
    path = pack.package_mod(project_dir, output_dir or "")
    return json.dumps({"package": path})


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
