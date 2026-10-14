"""XNA / FNA / MonoGame adapter (Terraria, Stardew Valley, Celeste, ...).

These are plain managed .NET games: the game logic lives in a .NET assembly
(e.g. Terraria.exe), so "reading" the game = decompiling that assembly.
"""
from __future__ import annotations

import os
import subprocess

from ..pe import is_managed_assembly
from ..structures import StructureTable, fingerprint_files, load_table, save_table
from .base import BaseAdapter

_MARKERS = [
    "FNA.dll",
    "FNA.Core.dll",
    "MonoGame.Framework.dll",
    "Microsoft.Xna.Framework.dll",
    "Microsoft.Xna.Framework.Content.Pipeline.dll",
    "Microsoft.Xna.Framework.Video.dll",
    "ReLogic.Native.dll",
]


class XnaAdapter(BaseAdapter):
    id = "dotnet-xna"
    runtime = "dotnet"
    name = ".NET / XNA / FNA / MonoGame"
    mod_framework = "tModLoader (Terraria) / SMAPI (星露谷)"
    structure = "ilspycmd / dnSpy 反编译 .NET 程序集"
    capabilities = ("detect", "fingerprint", "prepare", "query", "source", "launch")

    def detect(self, game_dir: str) -> bool:
        if not any(os.path.exists(os.path.join(game_dir, m)) for m in _MARKERS):
            return False
        return self._managed_exe(game_dir) is not None

    def _managed_exe(self, game_dir: str) -> str | None:
        exes = sorted(f for f in os.listdir(game_dir) if f.lower().endswith(".exe"))
        for f in exes:
            p = os.path.join(game_dir, f)
            if is_managed_assembly(p):
                return p
        return None

    def fingerprint(self, game_dir: str) -> str:
        paths = [os.path.join(game_dir, m) for m in _MARKERS if os.path.exists(os.path.join(game_dir, m))]
        exe = self._managed_exe(game_dir)
        if exe:
            paths.append(exe)
        return fingerprint_files(paths)

    def prepare(self, game_dir: str, cache_root: str) -> StructureTable:
        exe = self._managed_exe(game_dir)
        if exe is None:
            raise ValueError("no managed .NET game executable found")
        game_id = os.path.basename(os.path.normpath(game_dir))
        fp = self.fingerprint(game_dir)
        cached = load_table(cache_root, game_id, fp)
        if cached is not None:
            return cached

        out = exe + ".decomp-" + fp[:12]
        if not (os.path.isdir(out) and os.listdir(out)):
            try:
                subprocess.run(
                    ["ilspycmd", "-p", "-o", out, exe],
                    check=True, capture_output=True, text=True,
                )
            except FileNotFoundError:
                raise RuntimeError(
                    "ilspycmd not found. Install: dotnet tool install -g ilspycmd"
                ) from None

        table = StructureTable(
            game_id=game_id,
            engine=self.id,
            variant="managed",
            fingerprint=fp,
            decomp_dir=out,
            files=[os.path.relpath(exe, game_dir)],
        )
        save_table(cache_root, table)
        return table

    def launch(self, game_dir: str) -> dict:
        exe = self._managed_exe(game_dir)
        return {"exe": exe} if exe else {}

    def script(self, game_dir: str, goal: str) -> str:
        return f"Use scaffold_tmod_mod (Terraria) or a .NET mod loader to implement: {goal}"
