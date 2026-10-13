"""Adapter registry and engine detection."""
from __future__ import annotations

import os

from .adapters.base import BaseAdapter
from .adapters.catalog import CatalogAdapter
from .adapters.dotnet import XnaAdapter
from .adapters.reengine import ReEngineAdapter
from .adapters.unity import UnityAdapter
from .adapters.unreal import UnrealAdapter
from .engines import ENGINE_CATALOG

# Register adapters here. Specialized adapters (Unity, Unreal, RE-Engine, .NET-XNA) first for their
# deep detection + structure dump / scaffolding; the rest come from the engine catalog.
_ADAPTERS: list[BaseAdapter] = [
    UnityAdapter(),
    UnrealAdapter(),
    ReEngineAdapter(),
    XnaAdapter(),
] + [CatalogAdapter(e) for e in ENGINE_CATALOG if e["id"] not in {"unreal", "re-engine"}]


def adapters() -> list[BaseAdapter]:
    return _ADAPTERS


def detect_engine(game_dir: str) -> dict | None:
    """Return {id, runtime, name} of the first adapter that claims `game_dir`."""
    if not os.path.isdir(game_dir):
        return None
    for a in _ADAPTERS:
        if a.detect(game_dir):
            return {"id": a.id, "runtime": a.runtime, "name": a.name}
    return None


def get_adapter(engine_id: str) -> BaseAdapter:
    for a in _ADAPTERS:
        if a.id == engine_id:
            return a
    raise ValueError(f"unknown engine: {engine_id}")
