"""Structure table + version fingerprint + on-disk cache.

A "structure table" is the map the agent needs to turn a natural-language
request ("increase gold") into a concrete action ("write int32 at <addr>").
It is keyed by a fingerprint of the game build so a stale dump is never
silently reused against an updated game.
"""
from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass, field

def fingerprint_files(paths) -> str:
    """Hash (basename + size + first 256 KiB) of the given files, order-independent."""
    h = hashlib.sha256()
    entries = []
    for path in paths:
        try:
            size = os.path.getsize(path)
            with open(path, "rb") as f:
                head = f.read(256 * 1024)
        except OSError:
            continue
        entries.append((os.path.basename(path), size, hashlib.sha256(head).hexdigest()))
    entries.sort()
    for name, size, digest in entries:
        h.update(f"{name}|{size}|{digest}".encode())
        h.update(b"\x00")
    return h.hexdigest()


@dataclass
class StructureTable:
    game_id: str
    engine: str
    variant: str
    fingerprint: str
    decomp_dir: str = ""
    files: list = field(default_factory=list)
    types: list = field(default_factory=list)
    guidance: str = ""

    def to_dict(self) -> dict:
        return {
            "game_id": self.game_id,
            "engine": self.engine,
            "variant": self.variant,
            "fingerprint": self.fingerprint,
            "decomp_dir": self.decomp_dir,
            "files": self.files,
            "types": self.types,
            "guidance": self.guidance,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "StructureTable":
        return cls(**d)


def cache_path(cache_root: str, game_id: str, fingerprint: str) -> str:
    return os.path.join(cache_root, game_id, "structures", fingerprint + ".json")


def save_table(cache_root: str, table: StructureTable) -> str:
    path = cache_path(cache_root, table.game_id, table.fingerprint)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(table.to_dict(), f, ensure_ascii=False, indent=2)
    return path


def load_table(cache_root: str, game_id: str, fingerprint: str) -> StructureTable | None:
    path = cache_path(cache_root, game_id, fingerprint)
    if not os.path.exists(path):
        return None
    with open(path, "r", encoding="utf-8") as f:
        return StructureTable.from_dict(json.load(f))
