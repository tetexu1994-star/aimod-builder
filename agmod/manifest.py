"""Mod manifest (mod.json): the single source of truth for a mod's identity and update info.

The field set follows the Thunderstore `manifest.json` convention (name,
version_number, description, dependencies, website_url) plus fields this
project needs (engine, repo, entry). Backward-compatible: omitted keys use
their defaults.
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field


@dataclass
class ModManifest:
    id: str
    name: str
    version: str
    engine: str          # "unity" | "dotnet-xna" | "tmodloader" | catalog id
    repo: str = ""       # "owner/repo" — update source
    entry: str = ""      # entry DLL / package filename
    description: str = ""
    author: str = ""
    website_url: str = ""
    category: str = ""
    license: str = "MIT"
    game: str = ""
    dependencies: list = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "ModManifest":
        kwargs = {k: d[k] for k in cls.__dataclass_fields__ if k in d}
        return cls(**kwargs)

    def save(self, path: str) -> str:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(self.to_dict(), f, ensure_ascii=False, indent=2)
        return path

    @classmethod
    def load(cls, path: str) -> "ModManifest":
        with open(path, "r", encoding="utf-8") as f:
            return cls.from_dict(json.load(f))
