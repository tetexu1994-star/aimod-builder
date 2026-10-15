"""Dry-run installation checks for file-tree diffs, dependency compatibility and conflicts."""
from __future__ import annotations

import hashlib
import json
import os
from typing import Any

from . import packages, rollback, safety


def _sha256(path: str) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _pairs(files: Any) -> list[tuple[str, str]]:
    if not isinstance(files, list):
        raise ValueError("files must be a list")
    out: list[tuple[str, str]] = []
    for index, item in enumerate(files):
        if isinstance(item, dict):
            source, target = item.get("source"), item.get("target")
        elif isinstance(item, (list, tuple)) and len(item) == 2:
            source, target = item
        else:
            raise ValueError(f"files[{index}] must be a source/target pair")
        if not str(source or "").strip() or not str(target or "").strip():
            raise ValueError(f"files[{index}] has an empty source or target")
        out.append((str(source), str(target)))
    return out


def _load_package_spec(package_spec: dict | None, project_dir: str) -> dict | None:
    if isinstance(package_spec, dict):
        return package_spec
    path = os.path.join(project_dir, "package-spec.json") if project_dir else ""
    if path and os.path.isfile(path):
        with open(path, "r", encoding="utf-8") as f:
            value = json.load(f)
        if not isinstance(value, dict):
            raise ValueError("package-spec.json must contain an object")
        return value
    return None


def preview_install(
    game_dir: str,
    mod_id: str,
    files: Any,
    package_spec: dict | None = None,
    project_dir: str = "",
    engine_id: str = "",
) -> dict:
    """Return a non-mutating install diff and blockers for the proposed file set."""
    game_dir = os.path.abspath(game_dir)
    mod_id = str(mod_id or "").strip()
    errors: list[str] = []
    warnings: list[str] = []
    if not mod_id:
        errors.append("mod_id is required")
    allowed, reason = safety.check_game_target(game_dir)
    if not allowed:
        errors.append(reason)

    try:
        proposed = _pairs(files)
    except ValueError as exc:
        proposed = []
        errors.append(str(exc))

    package = _load_package_spec(package_spec, project_dir)
    dependency_check = {"ready": True, "errors": [], "warnings": ["no package dependency spec supplied"]}
    if package is not None:
        dependency_check = packages.check_dependency_compatibility(game_dir, package)
    elif engine_id:
        dependency_check = packages.check_dependency_compatibility(
            game_dir,
            packages.build_package_spec(game_dir, engine_id, mod_id or "preview-mod", mod_id or "Preview Mod", "1.0.0"),
        )
    errors.extend(dependency_check.get("errors", []))
    warnings.extend(dependency_check.get("warnings", []))
    running_state = rollback.check_conflicts(game_dir, []).get("game_running", {})
    if running_state.get("is_running"):
        errors.append(f"game is running; close it before installing: {running_state.get('processes', [])}")

    changes: list[dict] = []
    seen: set[str] = set()
    for source, target in proposed:
        source_abs = os.path.abspath(os.path.expanduser(source))
        target_abs = os.path.abspath(os.path.expanduser(target if os.path.isabs(target) else os.path.join(game_dir, target)))
        try:
            rel = os.path.relpath(target_abs, game_dir).replace("\\", "/")
        except ValueError:
            rel = "../invalid"
        if rel == ".." or rel.startswith("../") or os.path.isabs(rel):
            errors.append(f"install target escapes game directory: {target}")
            continue
        if rel.lower() in seen:
            errors.append(f"duplicate install target: {rel}")
            continue
        seen.add(rel.lower())
        if not os.path.isfile(source_abs) or os.path.islink(source_abs):
            errors.append(f"install source is not a regular file: {source}")
            continue
        if os.path.isdir(target_abs):
            errors.append(f"install target is a directory: {rel}")
            continue
        target_exists = os.path.isfile(target_abs)
        identical = target_exists and _sha256(source_abs) == _sha256(target_abs)
        action = "unchanged" if identical else "overwrite" if target_exists else "add"
        conflicts = rollback.check_conflicts(game_dir, [rel]).get("conflicts", [])
        conflict = conflicts[0] if conflicts else {}
        owner = conflict.get("installed_by")
        blocking_owner = bool(owner and owner != mod_id)
        if blocking_owner:
            errors.append(f"target is owned by another mod: {rel} ({owner})")
        elif target_exists and not identical:
            warnings.append(f"existing file will be backed up and overwritten: {rel}")
        changes.append({
            "source": source_abs,
            "target": rel,
            "action": action,
            "exists": target_exists,
            "identical": identical,
            "installed_by": owner,
            "blocking_owner": blocking_owner,
        })

    summary = {"add": 0, "overwrite": 0, "unchanged": 0}
    for change in changes:
        summary[change["action"]] += 1
    return {
        "ready": not errors,
        "mod_id": mod_id,
        "game_dir": game_dir,
        "changes": changes,
        "summary": summary,
        "dependencies": dependency_check,
        "game_running": running_state,
        "errors": errors,
        "warnings": warnings,
    }
