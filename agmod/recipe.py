"""Mod Recipe export and import engine inspired by ComfyUI workflow serialization.

Allows sharing and reproducible deployment of game mods via lightweight, portable
recipe JSON specs without compiling or distributing bulky binary packages.
"""
from __future__ import annotations

import json
import logging
import os
import time
from typing import Any, Dict, Optional

logger = logging.getLogger("agmod.recipe")

RECIPE_FORMAT_VERSION = "aimod-recipe-v1"


def export_recipe(
    mod_id: str,
    mod_name: str,
    game_dir: str,
    engine_id: str,
    summary: str,
    hook_target: str,
    params: Dict[str, Any],
    rea_insight: Optional[Dict[str, Any]] = None,
    healed_by: str = "",
) -> Dict[str, Any]:
    """Serialize current mod configuration, symbols, and parameters into a portable recipe."""
    rea = rea_insight or {}
    boundary = rea.get("boundary_scope", {})
    game_name = os.path.basename(game_dir) if game_dir else "GenericGame"

    recipe = {
        "format": RECIPE_FORMAT_VERSION,
        "recipe_id": mod_id,
        "recipe_name": mod_name,
        "summary": summary,
        "target_game": {
            "name": game_name,
            "engine_id": engine_id,
        },
        "hook_target": hook_target,
        "params": dict(params),
        "boundary_guard": {
            "safe_min": boundary.get("safe_min", 1.0),
            "safe_max": boundary.get("safe_max", 5.0),
            "step": boundary.get("step", 0.1),
            "warning": boundary.get("boundary_warning", "已开启物理与数值边界防护"),
        },
        "self_healing": {
            "healed_by": healed_by,
            "isolated_unity_dependency": engine_id in ("dotnet-xna", "dotnet", "tmodloader", "smapi"),
        },
        "pipeline_metadata": {
            "exported_at": time.strftime("%Y-%m-%d %H:%M:%S"),
            "generator": "AIModBuilder/1.0",
        },
    }
    return recipe


def validate_recipe(data: Any) -> tuple[bool, str, Dict[str, Any]]:
    """Validate incoming recipe structure and version compatibility."""
    if not isinstance(data, dict):
        return False, "Recipe data must be a valid JSON object", {}

    fmt = data.get("format")
    if fmt != RECIPE_FORMAT_VERSION:
        return False, f"Unsupported recipe format: {fmt} (expected {RECIPE_FORMAT_VERSION})", {}

    recipe_name = data.get("recipe_name")
    if not recipe_name or not isinstance(recipe_name, str):
        return False, "Recipe must contain a valid 'recipe_name'", {}

    recipe_id = data.get("recipe_id")
    if recipe_id is not None and str(recipe_id).strip() != "":
        try:
            from .paths import safe_component
            safe_component(str(recipe_id), "recipe_id")
        except Exception:
            return False, "'recipe_id' must be a safe identifier (letters, digits, . _ -)", {}

    hook_target = data.get("hook_target", "")
    if hook_target and not isinstance(hook_target, str):
        return False, "'hook_target' must be a string", {}

    params = data.get("params", {})
    if not isinstance(params, dict):
        return False, "'params' must be a JSON dictionary", {}
    for key, value in params.items():
        if not isinstance(key, str):
            return False, "'params' keys must be strings", {}
        if not isinstance(value, (bool, int, float, str)):
            return False, f"'params' value for '{key}' must be bool/int/float/str", {}

    return True, "", data
