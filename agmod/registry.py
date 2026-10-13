"""Adapter registry and engine detection."""
from __future__ import annotations

import os

from .adapters.base import BaseAdapter
from .adapters.catalog import CatalogAdapter
from .adapters.dotnet import XnaAdapter
from .adapters.unity import UnityAdapter
from .engines import ENGINE_CATALOG

# Register adapters here. Specialized adapters (Unity, .NET-XNA) first for their
# deep detection + structure dump; the rest come from the engine catalog.
_ADAPTERS: list[BaseAdapter] = [
    UnityAdapter(),
    XnaAdapter(),
] + [CatalogAdapter(e) for e in ENGINE_CATALOG]


def adapters() -> list[BaseAdapter]:
    return _ADAPTERS


def detect_engine(game_dir: str) -> dict | None:
    """Return {id, runtime, name} of the first adapter that claims `game_dir`."""
    if not os.path.isdir(game_dir):
        raise ValueError(f"not a directory: {game_dir}")
    for a in _ADAPTERS:
        if a.detect(game_dir):
            return {"id": a.id, "runtime": a.runtime, "name": a.name}
    return None


def get_adapter(engine_id: str) -> BaseAdapter:
    for a in _ADAPTERS:
        if a.id == engine_id:
            return a
    raise ValueError(f"unknown engine: {engine_id}")
