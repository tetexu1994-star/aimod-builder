"""The one stable interface every engine adapter implements.

Capability surface (mirrors AiMod's adapter extensions + Universal Modder's
skills), declared per adapter via `capabilities`:

  detect     — does this directory belong to this engine?      (required)
  fingerprint— build-version fingerprint for cache keying      (required)
  prepare    — recover structures ("read" the game)            (required)
  query      — search recovered structures for a field/type name
  source     — return decompiled source for a type/name
  script     — generate a mod script/project for a goal
  launch     — locate/launch the game for testing

Optional methods return empty results rather than raising, so callers degrade
gracefully. This is the contract that lets the core drive any engine without
knowing engine specifics.
"""
from __future__ import annotations

import os
from abc import ABC, abstractmethod

from ..structures import StructureTable


class BaseAdapter(ABC):
    id: str = ""
    runtime: str = ""
    name: str = ""
    capabilities: tuple[str, ...] = ("detect", "fingerprint", "prepare")

    # ---- required ----

    @abstractmethod
    def detect(self, game_dir: str) -> bool:
        """Return True if `game_dir` is this engine."""

    @abstractmethod
    def fingerprint(self, game_dir: str) -> str:
        """Return a build fingerprint over the files this engine cares about."""

    @abstractmethod
    def prepare(self, game_dir: str, cache_root: str) -> StructureTable:
        """'Read' the game: recover structures and return a (cached) table."""

    # ---- optional ----

    def query(self, table: StructureTable, needle: str) -> list[dict]:
        """Search recovered structures for a field/type name."""
        return self._grep_decomp(table.decomp_dir, needle)

    def source(self, table: StructureTable, name: str) -> str:
        """Return decompiled source for a type/name (empty if unavailable)."""
        path = self._find_cs_file(table.decomp_dir, name)
        if not path:
            return ""
        with open(path, "r", encoding="utf-8", errors="ignore") as f:
            return f.read()

    def script(self, game_dir: str, goal: str) -> str:
        """Guidance for turning `goal` into a mod. Empty = not supported."""
        return ""

    def launch(self, game_dir: str) -> dict:
        """Locate the game executable ({} if not supported)."""
        return {}

    # ---- helpers shared by adapters that decompile to a source tree ----

    def _grep_decomp(self, decomp_dir: str, needle: str, limit: int = 50) -> list[dict]:
        if not decomp_dir:
            return []
        matches = []
        n = needle.lower()
        for root, _dirs, files in os.walk(decomp_dir):
            for fn in files:
                if not fn.endswith((".cs", ".h", ".txt")):
                    continue
                path = os.path.join(root, fn)
                try:
                    with open(path, "r", encoding="utf-8", errors="ignore") as f:
                        for lineno, line in enumerate(f, 1):
                            if n in line.lower():
                                matches.append({
                                    "file": os.path.relpath(path, decomp_dir),
                                    "line": lineno,
                                    "text": line.strip()[:160],
                                })
                                if len(matches) >= limit:
                                    return matches
                except OSError:
                    continue
        return matches

    def _find_cs_file(self, decomp_dir: str, name: str) -> str:
        if not decomp_dir:
            return ""
        n = name.lower()
        for root, _dirs, files in os.walk(decomp_dir):
            for fn in files:
                if fn.endswith(".cs") and n in fn.lower():
                    return os.path.join(root, fn)
        return ""

    def describe(self) -> dict:
        """Adapter identity + capabilities + framework guidance."""
        return {
            "id": self.id,
            "runtime": self.runtime,
            "name": self.name,
            "capabilities": list(self.capabilities),
            "mod_framework": getattr(self, "mod_framework", ""),
            "structure": getattr(self, "structure", ""),
            "examples": getattr(self, "examples", ""),
        }
