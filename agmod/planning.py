"""Turn a natural-language request into a stable ModSpec, scaffold, and inspection plan."""
from __future__ import annotations

import json
import os
import re
import unicodedata

from . import bepinex, inspector, tmodloader
from .adapters.unreal import UnrealAdapter
from .manifest import ModManifest
from .paths import UnsafePathError, safe_component, safe_join
from .registry import detect_engine, get_adapter


def _slug(value: str) -> str:
    value = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode()
    value = re.sub(r"[^A-Za-z0-9]+", "-", value).strip("-").lower()
    return value or "ai-mod"


def _route(engine_id: str, adapter) -> tuple[str, list[str]]:
    if engine_id == "unity":
        return "BepInEx plugin + Harmony patch", ["BepInEx", ".NET SDK", "ilspycmd/Cpp2IL as needed"]
    if engine_id == "unreal":
        return "UE4SS Lua mod", ["UE4SS", "game-specific UProperty/UFunction evidence"]
    if engine_id == "dotnet-xna":
        return "game-specific managed loader (tModLoader/SMAPI)", ["loader reference assemblies", ".NET SDK"]
    return getattr(adapter, "mod_framework", "engine-specific mod framework"), []


def create_mod_plan(
    game_dir: str,
    request: str,
    project_dir: str,
    mod_id: str = "",
    mod_name: str = "",
    mod_version: str = "1.0.0",
    customizations: dict | list | None = None,
) -> dict:
    """Create `mod-spec.json`, `MODDING_PLAN.md`, and a route-specific skeleton."""
    if not request or not request.strip():
        raise ValueError("request must describe the desired mod")
    engine = detect_engine(game_dir)
    if engine is None:
        raise ValueError("game_dir is not a supported or recognized engine")
    adapter = get_adapter(engine["id"])
    if not re.fullmatch(r"\d+\.\d+\.\d+(?:[-+][0-9A-Za-z.-]+)?", mod_version):
        raise ValueError(f"invalid semantic version: {mod_version!r}")
    name = re.sub(r"[\r\n]+", " ", (mod_name or request.strip().splitlines()[0])[:80]).strip()
    mod_id = safe_component(mod_id or _slug(name), "mod_id")
    route, prerequisites = _route(engine["id"], adapter)

    # Automated feature inspection linked with the request
    keywords = re.findall(r"[A-Za-z0-9_]{3,}", request)
    candidate_symbols: list[str] = []
    recommended_strategy: dict = {}
    if keywords:
        try:
            ins = inspector.inspect_feature(game_dir, keywords[0])
            if ins.get("success"):
                candidate_symbols = ins.get("symbol_matches", [])
                recommended_strategy = ins.get("recommended_strategy", {})
        except Exception:
            pass

    spec = {
        "schema_version": 1,
        "id": mod_id,
        "name": name,
        "version": mod_version,
        "request": request.strip(),
        "customizations": customizations or {},
        "engine": engine,
        "route": route,
        "prerequisites": prerequisites,
        "candidate_symbols": candidate_symbols,
        "recommended_strategy": recommended_strategy,
        "expected_artifacts": ["source", "manifest", "build output", "install preview", "verification report"],
        "validation": ["compile", "install preview", "runtime read-back or game log", "package contents"],
        "status": "planned",
    }
    os.makedirs(project_dir, exist_ok=True)
    with open(os.path.join(project_dir, "mod-spec.json"), "w", encoding="utf-8") as f:
        json.dump(spec, f, ensure_ascii=False, indent=2)
    with open(os.path.join(project_dir, "request.md"), "w", encoding="utf-8") as f:
        f.write(request.strip() + "\n")
    with open(os.path.join(project_dir, "MODDING_PLAN.md"), "w", encoding="utf-8") as f:
        f.write(_plan_markdown(spec))

    if engine["id"] == "unity":
        bepinex.scaffold_plugin(project_dir, game_dir, mod_id, name, mod_version)
    elif engine["id"] == "unreal":
        UnrealAdapter().scaffold_mod(project_dir, mod_id, name, mod_version)
    elif engine["id"] == "dotnet-xna":
        tmodloader.scaffold_tmod_mod(project_dir, mod_id, name, mod_version)
    return spec


def _plan_markdown(spec: dict) -> str:
    custom = json.dumps(spec["customizations"], ensure_ascii=False, indent=2)
    symbols = "\n".join(f"- `{s}`" for s in spec.get("candidate_symbols", [])) or "None detected automatically"
    return f"""# Modding Plan

## Request

{spec["request"]}

## Scope

- ID: `{spec["id"]}`
- Engine: `{spec["engine"]["id"]}`
- Route: {spec["route"]}
- Version: `{spec["version"]}`

## Reverse Engineering Candidates

{symbols}

## Customizations

```json
{custom}
```

## Build and verify

1. Implement the smallest working feature in the generated source.
2. Compile it and preserve the complete compiler output.
3. Preview installation before touching the game.
4. Launch the game and verify the requested behavior and log output.
5. Package only generated code, declared assets, and the manifest.

## Safety

Use only a single-player/offline game you own. Back up saves before installation,
confirm before installing loaders, and never bypass anti-cheat, DRM, or ownership checks.
"""


def validate_project(project_dir: str) -> dict:
    """Validate the stable project shape before build/install/package."""
    errors: list[str] = []
    warnings: list[str] = []
    try:
        manifest = ModManifest.load(os.path.join(project_dir, "mod.json"))
    except (OSError, ValueError, TypeError) as exc:
        return {"ok": False, "errors": [f"invalid mod.json: {exc}"], "warnings": []}
    if manifest.entry:
        try:
            entry_path = safe_join(project_dir, manifest.entry)
            if not os.path.isfile(entry_path):
                errors.append(f"manifest entry does not exist: {manifest.entry}")
        except UnsafePathError as exc:
            errors.append(str(exc))
    for required in ("mod-spec.json", "MODDING_PLAN.md", "request.md"):
        if not os.path.isfile(os.path.join(project_dir, required)):
            warnings.append(f"missing {required}; generated by plan_mod")
    if manifest.engine == "unity":
        required = ["Plugin.cs"]
    elif manifest.engine == "unreal":
        required = ["enabled.txt", os.path.join("scripts", "main.lua")]
    elif manifest.engine == "tmodloader":
        required = ["build.txt"]
    else:
        required = []
    for item in required:
        if not os.path.isfile(os.path.join(project_dir, item)):
            errors.append(f"missing required file: {item}")

    # Semantic sanity checks
    if manifest.engine == "unity":
        plugin_cs = os.path.join(project_dir, "Plugin.cs")
        if os.path.isfile(plugin_cs):
            try:
                with open(plugin_cs, "r", encoding="utf-8", errors="ignore") as f:
                    txt = f.read()
                if "BaseUnityPlugin" not in txt and "[BepInPlugin" not in txt:
                    warnings.append("Plugin.cs does not appear to declare a standard BaseUnityPlugin class")
            except OSError:
                pass

    return {"ok": not errors, "errors": errors, "warnings": warnings, "engine": manifest.engine, "entry": manifest.entry}
