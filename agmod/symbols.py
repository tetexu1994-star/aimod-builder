"""Collect real symbol evidence from REA and local loader/dump artifacts."""
from __future__ import annotations

import os
import re
from dataclasses import asdict, dataclass

from . import rea

_TEXT_SUFFIXES = {".txt", ".json", ".lua", ".cs", ".h", ".hpp", ".cpp", ".log", ".md"}
_SKIP_DIRS = {"content", "paks", "movies", "video", "sound", "audio", "textures", "__pycache__", ".git"}
_MAX_FILES = 1200
_MAX_FILE_BYTES = 2 * 1024 * 1024


@dataclass
class SymbolCandidate:
    symbol: str
    source: str
    status: str
    confidence: float
    path: str = ""
    line: int = 0
    signature: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


def _walk_text_files(root: str, limit: int = _MAX_FILES):
    count = 0
    for base, dirs, files in os.walk(root, followlinks=False):
        dirs[:] = [d for d in dirs if d.lower() not in _SKIP_DIRS]
        for name in files:
            path = os.path.join(base, name)
            if os.path.splitext(name)[1].lower() not in _TEXT_SUFFIXES:
                continue
            try:
                if os.path.getsize(path) > _MAX_FILE_BYTES:
                    continue
            except OSError:
                continue
            yield path
            count += 1
            if count >= limit:
                return


def _symbol_from_line(line: str, query: str) -> str:
    stripped = line.strip()
    for token in re.findall(r"[A-Za-z_][A-Za-z0-9_:.<>\[\]-]*", stripped):
        if query.lower() in token.lower():
            return token
    return stripped[:180]


def collect_symbol_evidence(game_dir: str, engine_id: str, query: str, limit: int = 20) -> dict:
    """Return observed symbols from REA or local dumps, never presenting guesses as facts."""
    query = (query or "").strip()
    candidates: list[SymbolCandidate] = []
    errors: list[str] = []
    if not query:
        return {"query": query, "status": "unknown", "candidates": [], "errors": ["query is empty"]}

    if engine_id == "unity":
        import glob
        managed = glob.glob(os.path.join(game_dir, "*_Data", "Managed", "Assembly-CSharp.dll"))
        if managed:
            try:
                for raw in rea.fast_search_members(managed[0], query, limit=limit):
                    candidates.append(SymbolCandidate(raw[:240], "rea_fast_search", "observed", 0.82, managed[0]))
            except Exception as exc:
                errors.append(f"REA managed search failed: {exc}")

    artifact_roots = [game_dir]
    if engine_id == "unreal":
        artifact_roots += [os.path.join(game_dir, "ue4ss"), os.path.join(game_dir, "UE4SS")]
    elif engine_id == "re-engine":
        artifact_roots += [os.path.join(game_dir, "reframework")]
    elif engine_id == "godot":
        artifact_roots += [os.path.join(game_dir, "mods-unpacked")]

    seen = {c.symbol for c in candidates}
    for root in artifact_roots:
        if not os.path.isdir(root):
            continue
        for path in _walk_text_files(root):
            try:
                with open(path, "r", encoding="utf-8", errors="ignore") as f:
                    for line_no, line in enumerate(f, 1):
                        if query.lower() not in line.lower():
                            continue
                        symbol = _symbol_from_line(line, query)
                        if symbol in seen:
                            continue
                        seen.add(symbol)
                        source = "ue4ss_dump" if engine_id == "unreal" else "reframework_dump" if engine_id == "re-engine" else "local_dump"
                        candidates.append(SymbolCandidate(symbol, source, "observed", 0.68, path, line_no, line.strip()[:300]))
                        if len(candidates) >= limit:
                            break
            except OSError as exc:
                errors.append(f"{path}: {exc}")
            if len(candidates) >= limit:
                break
        if len(candidates) >= limit:
            break

    return {
        "query": query,
        "engine_id": engine_id,
        "status": "observed" if candidates else "unknown",
        "candidates": [c.to_dict() for c in candidates[:limit]],
        "errors": errors,
    }
