"""Feature inspector and modding strategy advisor.

Aggregates engine detection, structure scanning, and modding route recommendations
into a single call, drastically reducing agent roundtrips.
"""
from __future__ import annotations

import glob
import os

from . import rea
from .registry import detect_engine, get_adapter


def inspect_feature(game_dir: str, keyword: str) -> dict:
    """Inspect game structures for a desired feature and suggest the best modding path."""
    engine_info = detect_engine(game_dir)
    if engine_info is None:
        return {
            "success": False,
            "error": "Engine could not be detected. Check that game_dir is valid.",
            "game_dir": game_dir,
        }

    engine_id = engine_info["id"]
    keyword_lower = keyword.lower()
    matches: list[str] = []
    recommended_route = {}

    if engine_id == "unity":
        # Check for Assembly-CSharp.dll
        csharp_dlls = glob.glob(os.path.join(game_dir, "*_Data", "Managed", "Assembly-CSharp.dll"))
        if csharp_dlls:
            dll_path = csharp_dlls[0]
            try:
                # Fast member search with REA without full decompile
                matches = rea.fast_search_members(dll_path, keyword_lower, limit=20)
            except Exception:
                pass

        recommended_route = {
            "type": "unity_bepinex_or_memory",
            "runtime_hack": f"Use scan_start(pid, current_{keyword_lower}_val) -> change in game -> scan_next(pid, new_val) -> write_memory",
            "persistent_mod": "Use install_bepinex(game_dir) -> scaffold_mod(...) with a Harmony Patch on the matching method/getter.",
        }

    elif engine_id == "unreal":
        recommended_route = {
            "type": "unreal_ue4ss_lua",
            "runtime_hack": "Use scan_start on process memory for raw scalar values.",
            "persistent_mod": (
                f"Use scaffold_ue4ss_mod(...) to create a Lua hook in scripts/main.lua. "
                f"Look for UProperty or UFunction related to '{keyword}' (e.g. Set{keyword.capitalize()} or Get{keyword.capitalize()})."
            ),
        }

    elif engine_id == "dotnet-xna":
        recommended_route = {
            "type": "tmodloader",
            "persistent_mod": "Use scaffold_tmod_mod(...) and override ModPlayer / GlobalItem hooks in C#.",
        }

    else:
        adapter = get_adapter(engine_id)
        recommended_route = {
            "type": "generic_catalog",
            "guidance": getattr(adapter, "mod_framework", "Check engine documentation"),
        }

    return {
        "success": True,
        "engine": engine_info,
        "keyword": keyword,
        "symbol_matches": matches[:15],
        "recommended_strategy": recommended_route,
    }
