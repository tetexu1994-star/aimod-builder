"""Game-specific field notes / techniques (the "knowledge base").

Persistent per-game findings — field names, offsets, techniques — so a later
session doesn't re-derive them. Stored as markdown under
knowledge/<game>/<topic>.md. This is the "field notes" idea the market leaders
use to avoid repeated mistakes.
"""
from __future__ import annotations

import os

from .config import PROJECT_ROOT

KNOWLEDGE_ROOT = os.environ.get("AGMOD_KNOWLEDGE_ROOT", os.path.join(PROJECT_ROOT, "knowledge"))


def _safe(name: str) -> str:
    out = "".join(c for c in name if c.isalnum() or c in "-_. ")
    return out.strip().replace(" ", "-") or "unknown"


def record(game: str, topic: str, content: str) -> str:
    d = os.path.join(KNOWLEDGE_ROOT, _safe(game))
    os.makedirs(d, exist_ok=True)
    path = os.path.join(d, _safe(topic) + ".md")
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)
    return path


def lookup(game: str, query: str = "") -> str:
    d = os.path.join(KNOWLEDGE_ROOT, _safe(game))
    if not os.path.isdir(d):
        return ""
    results = []
    for root, _dirs, files in os.walk(d):
        for fn in sorted(files):
            if not fn.endswith(".md"):
                continue
            p = os.path.join(root, fn)
            try:
                with open(p, "r", encoding="utf-8") as f:
                    text = f.read()
            except OSError:
                continue
            if query and query.lower() not in text.lower() and query.lower() not in fn.lower():
                continue
            results.append(f"## {fn}\n{text}")
    return "\n\n".join(results)
