"""Savegame snapshot and safe restore manager.

Before injecting mods or modifying process memory, creating a fast snapshot of
the game's save data protects players from save corruption.
"""
from __future__ import annotations

import glob
import hashlib
import json
import os
import shutil
import time
import zipfile

from .config import CACHE_ROOT
from .paths import UnsafePathError, safe_component, safe_extract_zip, safe_join, slugify

_COMMON_SAVE_PATTERNS = [
    "saves",
    "SaveData",
    "saved",
    "Saved",
    os.path.join("*", "Saved", "SaveGames"),
    os.path.join("*_Data", "SaveData"),
    os.path.join("*_Data", "saves"),
]


def detect_save_dirs(game_dir: str) -> list[str]:
    """Find local save directories within or adjacent to the game directory."""
    hits: list[str] = []
    if not os.path.isdir(game_dir):
        return hits

    for pattern in _COMMON_SAVE_PATTERNS:
        full_pattern = os.path.join(game_dir, pattern)
        for match in glob.glob(full_pattern):
            if os.path.isdir(match):
                hits.append(os.path.abspath(match))

    return hits


def _get_backup_dir(game_dir: str, cache_root: str = "") -> str:
    root = cache_root or CACHE_ROOT
    norm = os.path.abspath(game_dir)
    digest = hashlib.sha256(os.path.realpath(norm).encode("utf-8")).hexdigest()[:12]
    game_id = f"{slugify(os.path.basename(norm) or 'game')}-{digest}"
    bdir = os.path.join(root, "backups", game_id)
    os.makedirs(bdir, exist_ok=True)
    return bdir


def create_save_backup(game_dir: str, tag: str = "pre-mod", custom_save_dir: str = "", cache_root: str = "") -> dict:
    """Create a timestamped zip snapshot of the game's save directories."""
    tag = safe_component(tag or "backup", "tag")
    save_dirs = [os.path.abspath(custom_save_dir)] if custom_save_dir else list(dict.fromkeys(detect_save_dirs(game_dir)))

    if not save_dirs:
        return {
            "success": False,
            "error": "No save directories detected automatically. Provide custom_save_dir if saves are elsewhere.",
        }

    bdir = _get_backup_dir(game_dir, cache_root)
    timestamp = time.strftime("%Y%m%d_%H%M%S")
    backup_id = f"save_{timestamp}_{time.time_ns()}_{tag}"
    archive_path = os.path.join(bdir, f"{backup_id}.zip")

    files_count = 0
    skipped_links = 0
    source_entries = []
    with zipfile.ZipFile(archive_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for index, sdir in enumerate(save_dirs):
            if not os.path.isdir(sdir):
                continue
            base_name = os.path.basename(sdir) or "save"
            archive_root = f"{index:02d}-{slugify(base_name, fallback='save')}"
            source_entries.append({
                "archive_root": archive_root,
                "source_dir": os.path.abspath(sdir),
                "basename": base_name,
            })
            for root, dirs, files in os.walk(sdir, followlinks=False):
                dirs[:] = [d for d in dirs if not os.path.islink(os.path.join(root, d))]
                for file in files:
                    full_p = os.path.join(root, file)
                    if os.path.islink(full_p):
                        skipped_links += 1
                        continue
                    rel_p = os.path.relpath(full_p, sdir)
                    arc_name = os.path.join(archive_root, rel_p).replace("\\", "/")
                    zf.write(full_p, arc_name)
                    files_count += 1

    size_bytes = os.path.getsize(archive_path) if os.path.isfile(archive_path) else 0
    meta = {
        "backup_id": backup_id,
        "timestamp": timestamp,
        "tag": tag,
        "archive_path": archive_path,
        "source_dirs": save_dirs,
        "sources": source_entries,
        "files_count": files_count,
        "skipped_symlinks": skipped_links,
        "size_bytes": size_bytes,
    }
    with open(os.path.join(bdir, f"{backup_id}.json"), "w", encoding="utf-8") as f:
        json.dump(meta, f, indent=2, ensure_ascii=False)

    return {"success": True, **meta}


def list_save_backups(game_dir: str, cache_root: str = "") -> list[dict]:
    """List all available savegame snapshots for this game."""
    bdir = _get_backup_dir(game_dir, cache_root)
    results: list[dict] = []
    for meta_file in sorted(glob.glob(os.path.join(bdir, "save_*.json")), reverse=True):
        try:
            with open(meta_file, "r", encoding="utf-8") as f:
                results.append(json.load(f))
        except (OSError, ValueError):
            continue
    return results


def restore_save_backup(game_dir: str, backup_id: str, destination: str = "", cache_root: str = "") -> dict:
    """Safely restore a save snapshot back to its destination using safe zip extraction."""
    backup_id = safe_component(backup_id, "backup_id")
    bdir = _get_backup_dir(game_dir, cache_root)
    meta_path = os.path.join(bdir, f"{backup_id}.json")
    zip_path = os.path.join(bdir, f"{backup_id}.zip")

    if not os.path.isfile(zip_path):
        return {"success": False, "error": f"Backup archive not found: {backup_id}"}

    meta = {}
    if os.path.isfile(meta_path):
        try:
            with open(meta_path, "r", encoding="utf-8") as f:
                meta = json.load(f)
        except (OSError, ValueError):
            pass

    source_entries = meta.get("sources", [])
    if source_entries:
        restored_files = 0
        with zipfile.ZipFile(zip_path) as zf:
            for entry in source_entries:
                root = entry.get("archive_root", "")
                source_dir = entry.get("source_dir", "")
                basename = entry.get("basename") or os.path.basename(source_dir)
                target_dir = os.path.abspath(destination and os.path.join(destination, basename) or source_dir)
                os.makedirs(target_dir, exist_ok=True)
                prefix = root.rstrip("/") + "/"
                for info in zf.infolist():
                    name = info.filename.replace("\\", "/")
                    if not name.startswith(prefix):
                        continue
                    rel = name[len(prefix):]
                    if not rel:
                        continue
                    target = safe_join(target_dir, rel)
                    os.makedirs(os.path.dirname(target), exist_ok=True)
                    with zf.open(info) as src, open(target, "wb") as dst:
                        shutil.copyfileobj(src, dst)
                    restored_files += 1
        restored_to = os.path.abspath(destination) if destination else os.path.abspath(source_entries[0].get("source_dir", game_dir))
    else:
        target_dir = destination or game_dir
        os.makedirs(target_dir, exist_ok=True)
        safe_extract_zip(zip_path, target_dir)
        restored_files = 0
        restored_to = os.path.abspath(target_dir)

    return {
        "success": True,
        "backup_id": backup_id,
        "restored_to": restored_to,
        "restored_files": restored_files,
    }
