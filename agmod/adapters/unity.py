"""Unity adapter: Mono and IL2CPP structure recovery.

Mono:   decompile Assembly-CSharp.dll with `ilspycmd` into a greppable C# tree.
IL2CPP: dump global-metadata.dat with Cpp2IL (or Il2CppDumper) into dump.cs.

The decompiled output is the "structure table" the agent greps to find fields
like `gold` / `money`, then resolves the live address at runtime with a value
scan or the engine's runtime dump.
"""
from __future__ import annotations

import glob
import hashlib
import os
import subprocess

from ..structures import StructureTable, fingerprint_files, load_table, save_table
from .base import BaseAdapter


def _sha1(path: str) -> str:
    h = hashlib.sha1()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


class UnityAdapter(BaseAdapter):
    id = "unity"
    runtime = "unity"
    name = "Unity (Mono / IL2CPP)"
    mod_framework = "BepInEx (Mono/IL2CPP) / MelonLoader"
    structure = "ilspycmd (Mono) / Cpp2IL 或 Il2CppDumper (IL2CPP)"
    capabilities = ("detect", "fingerprint", "prepare", "query", "source", "launch")

    def detect(self, game_dir: str) -> bool:
        return self._variant(game_dir) is not None

    def _variant(self, game_dir: str) -> str | None:
        if os.path.exists(os.path.join(game_dir, "GameAssembly.dll")):
            metas = glob.glob(os.path.join(game_dir, "*_Data", "il2cpp_data", "Metadata", "global-metadata.dat"))
            if metas:
                return "il2cpp"
        if glob.glob(os.path.join(game_dir, "*_Data", "Managed", "Assembly-CSharp.dll")):
            return "mono"
        if os.path.exists(os.path.join(game_dir, "UnityPlayer.dll")):
            return "unity-unknown"
        return None

    def fingerprint(self, game_dir: str) -> str:
        paths = glob.glob(os.path.join(game_dir, "GameAssembly.dll"))
        paths += glob.glob(os.path.join(game_dir, "UnityPlayer.dll"))
        paths += glob.glob(os.path.join(game_dir, "*_Data", "Managed", "Assembly-CSharp.dll"))
        paths += glob.glob(os.path.join(game_dir, "*_Data", "il2cpp_data", "Metadata", "global-metadata.dat"))
        return fingerprint_files(paths)

    def prepare(self, game_dir: str, cache_root: str) -> StructureTable:
        variant = self._variant(game_dir)
        if variant is None:
            raise ValueError(f"{game_dir} is not a Unity game")

        game_id = os.path.basename(os.path.normpath(game_dir))
        fp = self.fingerprint(game_dir)
        cached = load_table(cache_root, game_id, fp)
        if cached is not None:
            return cached

        table = StructureTable(game_id=game_id, engine=self.id, variant=variant, fingerprint=fp)
        if variant == "mono":
            self._prepare_mono(game_dir, table)
        elif variant == "il2cpp":
            self._prepare_il2cpp(game_dir, table)
        else:
            raise ValueError("Unity variant could not be determined; no managed data found")

        save_table(cache_root, table)
        return table

    def _prepare_mono(self, game_dir: str, table: StructureTable) -> None:
        asm = glob.glob(os.path.join(game_dir, "*_Data", "Managed", "Assembly-CSharp.dll"))
        if not asm:
            raise ValueError("Assembly-CSharp.dll not found")
        table.files = [os.path.relpath(a, game_dir) for a in asm]
        table.decomp_dir = self._decompile_mono(asm[0], table.fingerprint)

    def _decompile_mono(self, assembly: str, fingerprint: str) -> str:
        out = assembly + ".decomp-" + fingerprint[:12]
        if os.path.isdir(out) and os.listdir(out):
            return out
        try:
            subprocess.run(
                ["ilspycmd", "-p", "-o", out, assembly],
                check=True,
                capture_output=True,
                text=True,
            )
        except FileNotFoundError:
            raise RuntimeError(
                "ilspycmd not found. Install it with: dotnet tool install -g ilspycmd"
            ) from None
        return out

    def _prepare_il2cpp(self, game_dir: str, table: StructureTable) -> None:
        meta = glob.glob(os.path.join(game_dir, "*_Data", "il2cpp_data", "Metadata", "global-metadata.dat"))
        game_asm = os.path.join(game_dir, "GameAssembly.dll")
        if not meta or not os.path.exists(game_asm):
            raise ValueError("IL2CPP metadata/assembly missing")
        table.files = [
            os.path.relpath(meta[0], game_dir),
            "GameAssembly.dll",
        ]
        table.decomp_dir = self._dump_il2cpp(game_asm, meta[0], table.fingerprint)

    def _dump_il2cpp(self, game_asm: str, metadata: str, fingerprint: str) -> str:
        out = os.path.dirname(game_asm) + ".il2cpp-dump-" + fingerprint[:12]
        if os.path.isdir(out) and os.listdir(out):
            return out
        try:
            subprocess.run(
                ["Cpp2IL", "--game-path", os.path.dirname(game_asm), "--output", out],
                check=True,
                capture_output=True,
                text=True,
            )
        except FileNotFoundError:
            raise RuntimeError(
                "Cpp2IL not found. Install Cpp2IL (or Il2CppDumper) to dump IL2CPP structures."
            ) from None
        return out

    def launch(self, game_dir: str) -> dict:
        skip = {"unitycrashhandler64.exe", "unitycrashhandler32.exe"}
        for f in sorted(os.listdir(game_dir)):
            if f.lower().endswith(".exe") and f.lower() not in skip:
                return {"exe": os.path.join(game_dir, f)}
        return {}

    def script(self, game_dir: str, goal: str) -> str:
        return f"Use scaffold_mod to create a BepInEx plugin, then write a Harmony patch in Plugin.cs to: {goal}"
