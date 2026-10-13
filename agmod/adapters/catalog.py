"""A data-driven adapter that wraps one engine-catalog entry.

Covers engines we haven't built a deep `prepare` for: detection + the correct
pre-requisite mod framework + the structure-recovery guidance. Deep structure
dumps for these engines are a per-engine TODO; the framework guidance tells the
agent which tool to install and what to do next.
"""
from __future__ import annotations

import glob
import os

from ..structures import StructureTable, fingerprint_files
from .base import BaseAdapter


class CatalogAdapter(BaseAdapter):
    def __init__(self, entry: dict):
        self._entry = entry
        self.id = entry["id"]
        self.runtime = entry["family"]
        self.name = entry["name"]
        self.mod_framework = entry.get("mod_framework", "")
        self.structure = entry.get("structure", "")
        self.examples = entry.get("examples", "")
        # Catalog adapters only detect + give framework guidance; no deep
        # structure recovery yet, so no query/source/launch.
        self.capabilities = ("detect", "fingerprint", "prepare")

    def _matched_files(self, game_dir: str) -> list[str]:
        out = []
        for m in self._entry.get("markers", []):
            for p in glob.glob(os.path.join(game_dir, m)):
                if os.path.isfile(p):
                    out.append(p)
        return out

    def detect(self, game_dir: str) -> bool:
        for m in self._entry.get("markers", []):
            if glob.glob(os.path.join(game_dir, m)):
                return True
        return False

    def fingerprint(self, game_dir: str) -> str:
        return fingerprint_files(self._matched_files(game_dir))

    def prepare(self, game_dir: str, cache_root: str) -> StructureTable:
        return StructureTable(
            game_id=os.path.basename(os.path.normpath(game_dir)),
            engine=self.id,
            variant=self.runtime,
            fingerprint=self.fingerprint(game_dir),
            files=[os.path.relpath(p, game_dir) for p in self._matched_files(game_dir)],
            guidance=f"前置: {self.mod_framework}；看懂: {self.structure}",
        )
