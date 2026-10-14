"""RE Engine (Capcom) adapter for REFramework-based Lua modding.

Supports Monster Hunter Rise / Wilds, Resident Evil series (RE2/3/4 Remake, RE7, Village),
Devil May Cry 5, Dragon's Dogma 2, and Street Fighter 6.

Mods are Lua scripts installed into `<game_dir>/reframework/autorun/` and executed
in-process by REFramework.
"""
from __future__ import annotations

import glob
import os

from .. import rollback
from ..manifest import ModManifest
from ..paths import safe_component, safe_join
from ..structures import StructureTable, fingerprint_files
from .base import BaseAdapter

_LUA_TEMPLATE = '''-- REFramework Lua Mod: {mod_name}
-- Author: {author}
-- Version: {mod_version}

local mod_name = "{mod_name}"
local enabled = true

re.on_draw_ui(function()
    if imgui.tree_node(mod_name) then
        local changed, new_val = imgui.checkbox("Enabled", enabled)
        if changed then
            enabled = new_val
        end
        imgui.tree_pop()
    end
end)

re.on_frame(function()
    if not enabled then return end
    -- Game logic executed every frame
end)
'''

_README_TEMPLATE = '''# {mod_name}

A REFramework Lua mod for Capcom RE Engine games.

## Installation
1. Install REFramework (place `dinput8.dll` in your game directory).
2. Copy `autorun/{mod_id}.lua` into `<game_dir>/reframework/autorun/`.
'''


class ReEngineAdapter(BaseAdapter):
    def __init__(self):
        self.id = "re-engine"
        self.runtime = "reframework-lua"
        self.name = "Capcom RE Engine (REFramework)"
        self.capabilities = ("detect", "fingerprint", "prepare", "scaffold", "install")

    def _matched_files(self, game_dir: str) -> list[str]:
        patterns = [
            "re_chunk_000.pak",
            "*.pak.patch_000",
            "re8.exe",
            "MonsterHunterRise.exe",
            "MonsterHunterWilds.exe",
            "re4.exe",
            "dinput8.dll",
        ]
        out = []
        for pat in patterns:
            for p in glob.glob(os.path.join(game_dir, pat)):
                if os.path.isfile(p):
                    out.append(p)
        return out

    def detect(self, game_dir: str) -> bool:
        strong = [
            p for p in self._matched_files(game_dir)
            if os.path.basename(p).lower() != "dinput8.dll"
        ]
        return bool(strong)

    def fingerprint(self, game_dir: str) -> str:
        return fingerprint_files(self._matched_files(game_dir))

    def prepare(self, game_dir: str, cache_root: str) -> StructureTable:
        return StructureTable(
            game_id=os.path.basename(os.path.normpath(game_dir)),
            engine=self.id,
            variant=self.runtime,
            fingerprint=self.fingerprint(game_dir),
            files=[os.path.relpath(p, game_dir) for p in self._matched_files(game_dir)],
            guidance="前置: REFramework (dinput8.dll)；脚本放入 reframework/autorun；PAK 资源用 Fluffy Mod Manager",
        )

    def scaffold_mod(self, project_dir: str, mod_id: str, mod_name: str, mod_version: str = "0.1.0", author: str = "") -> str:
        """Create a complete REFramework Lua mod project skeleton."""
        mod_id = safe_component(mod_id, "mod_id")
        mod_name_lua = str(mod_name).replace("\\", "\\\\").replace('"', '\\"').replace("\n", " ")
        autorun_dir = os.path.join(project_dir, "autorun")
        os.makedirs(autorun_dir, exist_ok=True)

        entry_rel = f"autorun/{mod_id}.lua"
        lua_path = os.path.join(project_dir, entry_rel)
        with open(lua_path, "w", encoding="utf-8") as f:
            f.write(_LUA_TEMPLATE.format(
                mod_name=mod_name_lua,
                author=author or "unknown",
                mod_version=mod_version,
            ))

        with open(os.path.join(project_dir, "README.md"), "w", encoding="utf-8") as f:
            f.write(_README_TEMPLATE.format(
                mod_name=mod_name,
                mod_id=mod_id,
            ))

        manifest = ModManifest(
            id=mod_id,
            name=mod_name,
            version=mod_version,
            author=author,
            engine=self.id,
            entry=entry_rel,
            description=f"REFramework Lua mod: {mod_name}",
        )
        manifest.save(os.path.join(project_dir, "mod.json"))
        return project_dir

    def install_mod(self, project_dir: str, game_dir: str) -> str:
        """Install REFramework Lua mod into `<game_dir>/reframework/autorun` with rollback journal tracking."""
        manifest_path = os.path.join(project_dir, "mod.json")
        if not os.path.isfile(manifest_path):
            raise ValueError(f"no mod.json found in {project_dir}")
        manifest = ModManifest.load(manifest_path)

        dest_autorun = os.path.join(game_dir, "reframework", "autorun")
        os.makedirs(dest_autorun, exist_ok=True)

        # Collect files to install from autorun/ or root
        autorun_src = os.path.join(project_dir, "autorun")
        pairs = []
        if os.path.isdir(autorun_src):
            for root, dirs, files in os.walk(autorun_src, followlinks=False):
                dirs[:] = [d for d in dirs if not os.path.islink(os.path.join(root, d))]
                for fn in files:
                    s = os.path.join(root, fn)
                    if os.path.islink(s):
                        continue
                    rel = os.path.relpath(s, autorun_src)
                    pairs.append((s, os.path.join(dest_autorun, rel)))
        elif manifest.entry and os.path.isfile(os.path.join(project_dir, manifest.entry)):
            s = os.path.join(project_dir, manifest.entry)
            d = os.path.join(dest_autorun, os.path.basename(s))
            pairs.append((s, d))

        if not pairs:
            raise ValueError("no autorun scripts found in project to install")

        rollback.install_files(game_dir, manifest.id, pairs)
        return dest_autorun
