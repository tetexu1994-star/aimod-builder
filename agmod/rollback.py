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
from .process import is_game_running

_PROTECTED_REL_DIRS = {
    "",
    "bepinex",
    "bepinex/plugins",
    "bepinex/config",
    "bepinex/core",
    "bepinex/patchers",
    "mods",
    "reframework",
    "reframework/autorun",
    "reframework/data",
    "reframework/plugins",
    "modloader",
    "modloader/mods",
}


def _game_id(game_dir: str) -> str:
    norm = os.path.abspath(game_dir)
    return slugify(os.path.basename(norm) or "game")


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


def _cleanup_empty_dirs(game_dir: str, directory: str) -> None:
    """Prune empty directories up from `directory` toward `game_dir`."""
    game_dir = os.path.abspath(game_dir)
    cur = os.path.abspath(directory)
    while cur and cur != game_dir and cur.startswith(game_dir + os.sep):
        rel = os.path.relpath(cur, game_dir).replace("\\", "/").lower()
        if rel in _PROTECTED_REL_DIRS:
            break
        try:
            if not os.listdir(cur):
                os.rmdir(cur)
                cur = os.path.dirname(cur)
            else:
                break
        except OSError:
            break


def backup_files(game_dir: str, paths: list[str]) -> dict[str, str]:
    """Copy existing files aside so an overwrite can be undone.

    Returns `{absolute_path: backup_absolute_path}` for the files that already existed.
    Call this *before* overwriting.
    """
    game_dir = os.path.abspath(game_dir)
    backups: dict[str, str] = {}
    base_store = os.path.abspath(_base(game_dir))
    for p in paths:
        p_abs = os.path.abspath(p)
        if not os.path.isfile(p_abs):
            continue
        try:
            rel = os.path.relpath(p_abs, game_dir)
        except ValueError:
            continue
        if rel.startswith("..") or os.path.isabs(rel):
            continue
        dest = safe_join(base_store, "overwritten", rel)
        os.makedirs(os.path.dirname(dest), exist_ok=True)
        shutil.copy2(p_abs, dest)
        backups[p_abs] = dest
    return backups


def record_install(game_dir: str, mod_id: str, added_files: list[str], overwritten_backups: dict[str, str]) -> None:
    """Append one install entry to the journal."""
    game_dir = os.path.abspath(game_dir)
    journal = _load(game_dir)
    valid_added = []
    for f in added_files:
        f_abs = os.path.abspath(f)
        if not os.path.isfile(f_abs):
            continue
        try:
            rel = os.path.relpath(f_abs, game_dir)
            if not rel.startswith(".."):
                valid_added.append(rel.replace("\\", "/"))
        except ValueError:
            pass

    valid_overwritten = {}
    for f, b in overwritten_backups.items():
        try:
            rel = os.path.relpath(os.path.abspath(f), game_dir)
            if not rel.startswith(".."):
                valid_overwritten[rel.replace("\\", "/")] = b
        except ValueError:
            pass

    journal["entries"].append({
        "mod_id": mod_id,
        "added": valid_added,
        "overwritten": valid_overwritten,
    })
    _save(game_dir, journal)


def check_conflicts(game_dir: str, target_files: list[str]) -> dict:
    """Check if proposed target_files conflict with existing files or active mod installations."""
    game_dir = os.path.abspath(game_dir)
    journal = _load(game_dir)
    owner_map: dict[str, str] = {}
    for entry in journal.get("entries", []):
        mid = entry.get("mod_id", "unknown")
        for rel in entry.get("added", []):
            norm = rel.replace("\\", "/")
            owner_map[norm] = mid
            owner_map[norm.lower()] = mid
        for rel in entry.get("overwritten", {}):
            norm = rel.replace("\\", "/")
            owner_map[norm] = mid
            owner_map[norm.lower()] = mid

    conflicts = []
    for tf in target_files:
        tf_abs = os.path.abspath(tf if os.path.isabs(tf) else os.path.join(game_dir, tf))
        try:
            rel = os.path.relpath(tf_abs, game_dir).replace("\\", "/")
        except ValueError:
            continue
        if rel.startswith(".."):
            continue
        if os.path.exists(tf_abs):
            conflicts.append({
                "path": rel,
                "exists": True,
                "installed_by": owner_map.get(rel) or owner_map.get(rel.lower()),
            })

    running, running_procs = is_game_running(game_dir)
    return {
        "has_conflicts": len(conflicts) > 0,
        "conflict_count": len(conflicts),
        "conflicts": conflicts,
        "game_running": {
            "is_running": running,
            "processes": running_procs,
        },
    }


def _reverse_entry(game_dir: str, entry: dict) -> tuple[list[str], list[str], list[str]]:
    game_dir = os.path.abspath(game_dir)
    removed: list[str] = []
    restored: list[str] = []
    errors: list[str] = []
    base_store = os.path.abspath(_base(game_dir))

    for rel in entry.get("added", []):
        try:
            p = safe_join(game_dir, rel)
        except Exception as e:
            errors.append(f"invalid added path {rel}: {e}")
            continue
        if os.path.isfile(p):
            try:
                os.remove(p)
                removed.append(rel)
                _cleanup_empty_dirs(game_dir, os.path.dirname(p))
            except OSError as e:
                errors.append(f"failed to remove {rel}: {e}")

    for rel, backup in entry.get("overwritten", {}).items():
        try:
            p = safe_join(game_dir, rel)
        except Exception as e:
            errors.append(f"invalid overwritten path {rel}: {e}")
            continue
        backup_abs = os.path.abspath(backup)
        if not backup_abs.startswith(base_store):
            errors.append(f"unauthorized backup path {backup}")
            continue
        if os.path.isfile(backup_abs):
            try:
                os.makedirs(os.path.dirname(p), exist_ok=True)
                shutil.copy2(backup_abs, p)
                restored.append(rel)
                try:
                    os.remove(backup_abs)
                    _cleanup_empty_dirs(base_store, os.path.dirname(backup_abs))
                except OSError:
                    pass
            except OSError as e:
                errors.append(f"failed to restore {rel}: {e}")

    return removed, restored, errors


def uninstall(game_dir: str, mod_id: str) -> dict:
    """Reverse one mod's recorded install (delete added, restore overwritten)."""
    game_dir = os.path.abspath(game_dir)
    journal = _load(game_dir)
    removed: list[str] = []
    restored: list[str] = []
    errors: list[str] = []
    matching_indices = [i for i, e in enumerate(journal["entries"]) if e.get("mod_id") == mod_id]

    if not matching_indices:
        return {
            "success": False,
            "mod_id": mod_id,
            "error": f"no install record found for mod '{mod_id}'",
            "removed": [],
            "restored": [],
            "errors": [],
        }

    # Reverse matching entries in reverse chronological order
    for idx in reversed(matching_indices):
        entry = journal["entries"][idx]
        r, s, errs = _reverse_entry(game_dir, entry)
        removed += r
        restored += s
        errors += errs

    journal["entries"] = [e for i, e in enumerate(journal["entries"]) if i not in matching_indices]
    _save(game_dir, journal)
    return {
        "success": len(errors) == 0,
        "mod_id": mod_id,
        "removed": removed,
        "restored": restored,
        "errors": errors,
    }


def rollback_all(game_dir: str) -> dict:
    """Reverse every recorded install, newest first, restoring the pre-mod state."""
    game_dir = os.path.abspath(game_dir)
    journal = _load(game_dir)
    removed: list[str] = []
    restored: list[str] = []
    errors: list[str] = []
    for entry in reversed(journal.get("entries", [])):
        r, s, errs = _reverse_entry(game_dir, entry)
        removed += r
        restored += s
        errors += errs
    journal["entries"] = []
    _save(game_dir, journal)
    return {
        "success": len(errors) == 0,
        "removed": removed,
        "restored": restored,
        "errors": errors,
    }


def list_installs(game_dir: str) -> list[dict]:
    """Return the recorded install entries (newest last)."""
    return list(_load(game_dir).get("entries", []))
