"""Unreal Engine (UE4 / UE5) adapter using UE4SS (Lua scripting).

Unreal Engine games have standardized structures (UObject, UClass, UProperty).
The cleanest, compiler-free modding route for UE4/UE5 is UE4SS, which exposes a
powerful Lua API that runs in-process without requiring MSVC/C++ compilation.
"""
from __future__ import annotations

import glob
import json
import os
import shutil

from ..structures import StructureTable, fingerprint_files
from ..paths import safe_component
from .base import BaseAdapter


class UnrealAdapter(BaseAdapter):
    id = "unreal"
    runtime = "unreal"
    name = "Unreal Engine (UE4 / UE5)"
    mod_framework = "UE4SS (Lua API) / pak 覆盖 (repak)"
    structure = "UE4SS dumper / Dumper-7 导出 UClass/UProperty"
    capabilities = ("detect", "fingerprint", "prepare", "launch")

    def _matched_files(self, game_dir: str) -> list[str]:
        hits = []
        patterns = [
            "*.uproject",
            "Content/Paks/*.pak",
            "Content/Paks/*.utoc",
            "Content/Paks/*.ucas",
            "Engine/Binaries/Win64/*.dll",
            "*/*-Shipping.exe",
            "*/*/Binaries/Win64/*-Shipping.exe",
        ]
        for pat in patterns:
            for p in glob.glob(os.path.join(game_dir, pat)):
                if os.path.isfile(p):
                    hits.append(p)
        return hits

    def detect(self, game_dir: str) -> bool:
        if not os.path.isdir(game_dir):
            return False
        # Direct markers
        if glob.glob(os.path.join(game_dir, "*.uproject")):
            return True
        if os.path.isdir(os.path.join(game_dir, "Engine", "Binaries")):
            return True
        if glob.glob(os.path.join(game_dir, "*", "Content", "Paks")):
            return True
        if glob.glob(os.path.join(game_dir, "Content", "Paks", "*.pak")):
            return True
        if glob.glob(os.path.join(game_dir, "*", "Binaries", "Win64", "*-Shipping.exe")):
            return True
        return False

    def fingerprint(self, game_dir: str) -> str:
        return fingerprint_files(self._matched_files(game_dir))

    def prepare(self, game_dir: str, cache_root: str) -> StructureTable:
        files = self._matched_files(game_dir)
        return StructureTable(
            game_id=os.path.basename(os.path.normpath(game_dir)),
            engine=self.id,
            variant=self.runtime,
            fingerprint=self.fingerprint(game_dir),
            files=[os.path.relpath(p, game_dir) for p in files[:20]],
            guidance=(
                "前置: UE4SS (放入 <Game>/Binaries/Win64/)；"
                "Mod 编写: 在 Mods/<ModName>/scripts/main.lua 编写 Lua Hook；"
                "免编译热加载: 支持 RegisterHook, StaticFindObject, NotifyOnNewObject"
            ),
        )

    def launch(self, game_dir: str) -> dict | None:
        shippings = glob.glob(os.path.join(game_dir, "*", "Binaries", "Win64", "*-Shipping.exe"))
        if not shippings:
            shippings = glob.glob(os.path.join(game_dir, "*.exe"))
        if shippings:
            return {"exe": shippings[0], "hint": "Run game with UE4SS injected"}
        return None

    def scaffold_mod(
        self,
        project_dir: str,
        mod_id: str,
        mod_name: str,
        mod_version: str = "1.0.0",
        author: str = "AI Mod Agent",
    ) -> str:
        """Generate a complete UE4SS Lua Mod skeleton."""
        mod_id = safe_component(mod_id, "mod_id")
        lua_name = str(mod_name).replace("\\", "\\\\").replace('"', '\\"').replace("\n", " ")
        scripts_dir = os.path.join(project_dir, "scripts")
        os.makedirs(scripts_dir, exist_ok=True)

        # 1. enabled.txt
        with open(os.path.join(project_dir, "enabled.txt"), "w", encoding="utf-8") as f:
            f.write("1\n")

        # 2. mod.json metadata
        meta = {
            "id": mod_id,
            "name": mod_name,
            "version": mod_version,
            "author": author,
            "engine": "unreal",
            "framework": "UE4SS",
            "entry": "scripts/main.lua",
        }
        with open(os.path.join(project_dir, "mod.json"), "w", encoding="utf-8") as f:
            json.dump(meta, f, indent=2, ensure_ascii=False)

        # 3. scripts/main.lua template
        lua_template = f"""-- {lua_name} (ID: {mod_id})
-- Built with game-mod-agent for UE4SS (Lua API)

local ModRef = "{lua_name}"
print(string.format("[%s] Initialized successfully!", ModRef))

-- Hooking template:
-- RegisterHook("/Script/Engine.PlayerController:ClientRestart", function(self, newPawn)
--     print(string.format("[%s] Player restarted!", ModRef))
-- end)

-- Object inspection template:
-- NotifyOnNewObject("/Script/Engine.Character", function(character)
--     print(string.format("[%s] Found new Character instance: %s", ModRef, character:GetFullName()))
-- end)
"""
        with open(os.path.join(scripts_dir, "main.lua"), "w", encoding="utf-8") as f:
            f.write(lua_template)

        return project_dir

    def install_mod(self, project_dir: str, game_dir: str, mod_id: str) -> str:
        """Install UE4SS mod into <Game>/Binaries/Win64/ue4ss/Mods/<mod_id>/."""
        mod_id = safe_component(mod_id, "mod_id")
        target_candidates = glob.glob(os.path.join(game_dir, "*", "Binaries", "Win64"))
        if not target_candidates:
            target_candidates = [os.path.join(game_dir, "Binaries", "Win64")]

        win64_dir = target_candidates[0]
        # UE4SS can use either ue4ss/Mods/ or Mods/
        mods_dir = os.path.join(win64_dir, "ue4ss", "Mods", mod_id)
        if not os.path.exists(os.path.join(win64_dir, "ue4ss")):
            mods_dir = os.path.join(win64_dir, "Mods", mod_id)

        os.makedirs(mods_dir, exist_ok=True)
        # Copy scripts/ and enabled.txt
        for item in os.listdir(project_dir):
            s = os.path.join(project_dir, item)
            d = os.path.join(mods_dir, item)
            if os.path.isdir(s):
                shutil.copytree(s, d, dirs_exist_ok=True)
            else:
                shutil.copy2(s, d)
        return mods_dir
