"""Godot Engine adapter for GodotModLoader and GDScript modding.

Supports Godot 3.x and 4.x games (e.g., Brotato, Cassette Beasts, Dome Keeper, Buckshot Roulette).
Mods are unpacked GDScript trees deployed into `<game_dir>/mods-unpacked/<Author>-<ModId>/`.
"""
from __future__ import annotations

import glob
import os

from .. import rollback
from ..manifest import ModManifest
from ..paths import safe_component, safe_join
from ..structures import StructureTable, fingerprint_files
from .base import BaseAdapter

_GD_TEMPLATE = '''extends Node

const MOD_DIR := "{folder_name}/"
const MOD_NAME := "{mod_name}"

func _init() -> void:
    # Called when GodotModLoader loads the mod
    print(str("[", MOD_NAME, "] Initializing..."))

func _ready() -> void:
    # Called when the node enters the scene tree
    print(str("[", MOD_NAME, "] Ready!"))
    # Scene/resource hooks or patch overrides can be registered here
'''

_README_TEMPLATE = '''# {mod_name}

A GodotModLoader GDScript mod for Godot games.

## Installation
Place the `{folder_name}` folder inside `<game_dir>/mods-unpacked/`.
'''


class GodotAdapter(BaseAdapter):
    def __init__(self):
        self.id = "godot"
        self.runtime = "gdscript"
        self.name = "Godot Engine (GodotModLoader / GDScript)"
        self.capabilities = ("detect", "fingerprint", "prepare", "scaffold", "install")

    def _matched_files(self, game_dir: str) -> list[str]:
        out = []
        for pat in ("*.pck", "*.godot", "mods-unpacked"):
            for p in glob.glob(os.path.join(game_dir, pat)):
                if os.path.exists(p):
                    out.append(p)
        return out

    def detect(self, game_dir: str) -> bool:
        return bool(glob.glob(os.path.join(game_dir, "*.pck")) or glob.glob(os.path.join(game_dir, "*.godot")))

    def fingerprint(self, game_dir: str) -> str:
        return fingerprint_files([p for p in self._matched_files(game_dir) if os.path.isfile(p)])

    def prepare(self, game_dir: str, cache_root: str) -> StructureTable:
        return StructureTable(
            game_id=os.path.basename(os.path.normpath(game_dir)),
            engine=self.id,
            variant=self.runtime,
            fingerprint=self.fingerprint(game_dir),
            files=[os.path.relpath(p, game_dir) for p in self._matched_files(game_dir) if os.path.isfile(p)],
            guidance="前置: GodotModLoader；Mod 放置于 mods-unpacked/<Author>-<ModId>；.pck 资源可用 gdunpack 解包",
        )

    def scaffold_mod(self, project_dir: str, mod_id: str, mod_name: str, mod_version: str = "0.1.0", author: str = "") -> str:
        """Scaffold a GodotModLoader GDScript mod project."""
        mod_id = safe_component(mod_id, "mod_id")
        author_name = safe_component(author or "Unknown", "author")
        folder_name = f"{author_name}-{mod_id}"

        os.makedirs(project_dir, exist_ok=True)
        entry_file = "mod_main.gd"

        with open(os.path.join(project_dir, entry_file), "w", encoding="utf-8") as f:
            f.write(_GD_TEMPLATE.format(
                folder_name=folder_name,
                mod_name=mod_name,
            ))

        with open(os.path.join(project_dir, "README.md"), "w", encoding="utf-8") as f:
            f.write(_README_TEMPLATE.format(
                mod_name=mod_name,
                folder_name=folder_name,
            ))

        manifest = ModManifest(
            id=mod_id,
            name=mod_name,
            version=mod_version,
            author=author or "Unknown",
            engine=self.id,
            entry=entry_file,
            description=f"Godot GDScript mod: {mod_name}",
        )
        manifest.save(os.path.join(project_dir, "mod.json"))
        return project_dir

    def install_mod(self, project_dir: str, game_dir: str) -> str:
        """Install Godot GDScript mod into `<game_dir>/mods-unpacked/<Author>-<ModId>/` with rollback tracking."""
        manifest_path = os.path.join(project_dir, "mod.json")
        if not os.path.isfile(manifest_path):
            raise ValueError(f"no mod.json found in {project_dir}")
        manifest = ModManifest.load(manifest_path)

        author_name = safe_component(manifest.author or "Unknown", "author")
        folder_name = f"{author_name}-{manifest.id}"
        dest_mod_dir = os.path.join(game_dir, "mods-unpacked", folder_name)
        os.makedirs(dest_mod_dir, exist_ok=True)

        pairs = []
        for root, dirs, files in os.walk(project_dir, followlinks=False):
            dirs[:] = [d for d in dirs if d not in {"out", "dist", "lib", "__pycache__", ".git", ".pytest_cache"}]
            for fn in files:
                if fn in {"mod-spec.json", "request.md", "MODDING_PLAN.md"} or fn.endswith(".pre-repair"):
                    continue
                src = os.path.join(root, fn)
                if os.path.islink(src):
                    continue
                rel = os.path.relpath(src, project_dir)
                dest = os.path.join(dest_mod_dir, rel)
                pairs.append((src, dest))

        if not pairs:
            raise ValueError("no files found in project to install")

        rollback.install_files(game_dir, manifest.id, pairs)
        return dest_mod_dir
