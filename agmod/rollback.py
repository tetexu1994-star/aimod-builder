"""Installation journal: record every file a mod adds/overwrites so it can be undone.

The journal lives in `CACHE_ROOT/backups/<game>/install-journal.json` and records,
per install operation, which files were added (created) and which were overwritten
(with a backup copy of the original). `uninstall` reverses one mod; `rollback_all`
reverses all installs newest-first to restore the game to its pre-mod state.

This is what makes modding safe: if a mod breaks the game, you can always get back.
"""
from __future__ import annotations

import json
import os
import shutil

from .config import CACHE_ROOT
from .paths import slugify, safe_join


def _game_id(game_dir: str) -> str:
    return slugify(os.path.basename(os.path.normpath(game_dir)) or "game")


def _base(game_dir: str) -> str:
    return os.path.join(CACHE_ROOT, "backups", _game_id(game_dir))


def _journal_path(game_dir: str) -> str:
    return os.path.join(_base(game_dir), "install-journal.json")


def _load(game_dir: str) -> dict:
    path = _journal_path(game_dir)
    if os.path.isfile(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except (OSError, ValueError):
            pass
    return {"game_dir": os.path.abspath(game_dir), "entries": []}


def _save(game_dir: str, journal: dict) -> None:
    path = _journal_path(game_dir)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(journal, f, indent=2, ensure_ascii=False)


def backup_files(game_dir: str, paths: list[str]) -> dict[str, str]:
    """Copy existing files aside so an overwrite can be undone.

    Returns `{absolute_path: backup_absolute_path}` for the files that already existed.
    Call this *before* overwriting.
    """
    backups: dict[str, str] = {}
    for p in paths:
        if not os.path.isfile(p):
            continue
        rel = os.path.relpath(p, game_dir)
        dest = os.path.join(_base(game_dir), "overwritten", rel)
        os.makedirs(os.path.dirname(dest), exist_ok=True)
        shutil.copy2(p, dest)
        backups[p] = dest
    return backups


def record_install(game_dir: str, mod_id: str, added_files: list[str], overwritten_backups: dict[str, str]) -> None:
    """Append one install entry to the journal."""
    journal = _load(game_dir)
    journal["entries"].append({
        "mod_id": mod_id,
        "added": [os.path.relpath(f, game_dir) for f in added_files if os.path.isfile(f)],
        "overwritten": {os.path.relpath(f, game_dir): b for f, b in overwritten_backups.items()},
    })
    _save(game_dir, journal)


def _reverse_entry(game_dir: str, entry: dict) -> tuple[list[str], list[str]]:
    removed: list[str] = []
    restored: list[str] = []
    for rel in entry.get("added", []):
        try:
            p = safe_join(game_dir, rel)
        except Exception:
            continue
        if os.path.isfile(p):
            os.remove(p)
            removed.append(rel)
    for rel, backup in entry.get("overwritten", {}).items():
        try:
            p = safe_join(game_dir, rel)
        except Exception:
            continue
        if os.path.isfile(backup):
            os.makedirs(os.path.dirname(p), exist_ok=True)
            shutil.copy2(backup, p)
            restored.append(rel)
    return removed, restored


def uninstall(game_dir: str, mod_id: str) -> dict:
    """Reverse one mod's recorded install (delete added, restore overwritten)."""
    journal = _load(game_dir)
    removed: list[str] = []
    restored: list[str] = []
    kept: list[dict] = []
    for entry in journal["entries"]:
        if entry.get("mod_id") == mod_id:
            r, s = _reverse_entry(game_dir, entry)
            removed += r
            restored += s
        else:
            kept.append(entry)
    journal["entries"] = kept
    _save(game_dir, journal)
    return {"mod_id": mod_id, "removed": removed, "restored": restored}


def rollback_all(game_dir: str) -> dict:
    """Reverse every recorded install, newest first, restoring the pre-mod state."""
    journal = _load(game_dir)
    removed: list[str] = []
    restored: list[str] = []
    for entry in reversed(journal["entries"]):
        r, s = _reverse_entry(game_dir, entry)
        removed += r
        restored += s
    journal["entries"] = []
    _save(game_dir, journal)
    return {"removed": removed, "restored": restored}


def list_installs(game_dir: str) -> list[dict]:
    """Return the recorded install entries (newest last)."""
    return list(_load(game_dir).get("entries", []))
