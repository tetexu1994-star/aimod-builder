"""Turn a natural-language request into a stable ModSpec, scaffold, and inspection plan."""
from __future__ import annotations

import json
import hashlib
import os
import re
import unicodedata

from . import bepinex, inspector, packages, tmodloader
from .adapters.godot import GodotAdapter
from .adapters.reengine import ReEngineAdapter
from .adapters.unreal import UnrealAdapter
from .manifest import ModManifest
from .paths import UnsafePathError, safe_component, safe_join
from .registry import detect_engine, get_adapter


def _slug(value: str) -> str:
    source = str(value)
    normalized = unicodedata.normalize("NFKD", source).encode("ascii", "ignore").decode()
    normalized = re.sub(r"[^A-Za-z0-9]+", "-", normalized).strip("-").lower()
    if normalized and not normalized.isdigit() and len(normalized) >= 3:
        return normalized
    digest = hashlib.sha256(source.encode("utf-8")).hexdigest()[:6]
    return f"ai-mod-{digest}"


_STOPWORDS = {
    "add", "set", "make", "give", "create", "enable", "disable", "increase", "decrease",
    "the", "and", "with", "for", "from", "into", "game", "mod", "please",
}
_FEATURE_TERMS = {
    "金币": "gold", "金钱": "money", "血量": "health", "生命": "health",
    "经验": "experience", "速度": "speed", "伤害": "damage", "物品": "item",
    "背包": "inventory", "弹药": "ammo", "任务": "quest",
}


def _route(engine_id: str, adapter) -> tuple[str, list[str]]:
    if engine_id == "unity":
        return "BepInEx plugin + Harmony patch", ["BepInEx", ".NET SDK", "ilspycmd/Cpp2IL as needed"]
    if engine_id == "unreal":
        return "UE4SS Lua mod", ["UE4SS", "game-specific UProperty/UFunction evidence"]
    if engine_id == "re-engine":
        return "REFramework Lua mod", ["REFramework (dinput8.dll)", "REFramework ImGui / Lua API"]
    if engine_id == "godot":
        return "GodotModLoader GDScript mod", ["GodotModLoader", "res://mods-unpacked"]
    if engine_id == "dotnet-xna":
        return "game-specific managed loader (tModLoader/SMAPI)", ["loader reference assemblies", ".NET SDK"]
    return getattr(adapter, "mod_framework", "engine-specific mod framework"), []


def _ecosystem_pattern(engine_id: str) -> dict:
    patterns = {
        "unity": {
            "loader": "BepInEx",
            "loader_profile": "Mono plugin / IL2CPP interop profile",
            "package_shape": ["loader", "plugin DLL", "config", "assets", "localization"],
            "implementation": ["Harmony patch", "plugin lifecycle", "config binding", "dependency manifest"],
        },
        "unreal": {
            "loader": "UE4SS",
            "loader_profile": "UE4/UE5 Lua and reflection profile",
            "package_shape": ["loader", "enabled.txt", "scripts/main.lua", "assets", "mod.json"],
            "implementation": ["UFunction hook", "UObject lookup", "config binding", "asset override"],
        },
        "re-engine": {
            "loader": "REFramework",
            "loader_profile": "RE Engine Lua and SDK profile",
            "package_shape": ["REFramework", "autorun/*.lua", "config", "assets", "localization"],
            "implementation": ["sdk.hook", "runtime type lookup", "ImGui controls", "version guard"],
        },
        "godot": {
            "loader": "GodotModLoader",
            "loader_profile": "Godot 3/4 GDScript profile",
            "package_shape": ["mod folder", "mod_main.gd", "mod.json", "assets", "localization"],
            "implementation": ["scene hook", "resource override", "config binding", "runtime compatibility"],
        },
        "dotnet-xna": {
            "loader": "tModLoader or SMAPI",
            "loader_profile": "game-specific managed loader profile",
            "package_shape": ["loader", "managed plugin", "config", "assets", "localization"],
            "implementation": ["loader API", "content registration", "config binding", "dependency manifest"],
        },
    }
    return patterns.get(engine_id, {
        "loader": "engine-specific loader",
        "loader_profile": "unverified profile",
        "package_shape": ["loader", "source", "manifest", "assets"],
        "implementation": ["inspect community package shape", "record evidence", "verify before install"],
    })


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
    keywords: list[str] = []
    for zh, en in _FEATURE_TERMS.items():
        if zh in request:
            keywords.append(en)
    keywords.extend(
        token for token in re.findall(r"[A-Za-z0-9_]{3,}", request)
        if token.lower() not in _STOPWORDS
    )
    if isinstance(customizations, dict):
        keywords.extend(str(key) for key in customizations.keys())
    keywords = list(dict.fromkeys(keywords))[:6]
    if not keywords:
        keywords = [request.strip()]
    candidate_symbols: list[str] = []
    normalized_targets: list[dict] = []
    recommended_strategy: dict = {}
    inspection_warnings: list[str] = []
    for keyword in keywords:
        try:
            ins = inspector.inspect_feature(game_dir, keyword)
            if ins.get("success"):
                candidate_symbols.extend(ins.get("symbol_matches", []))
                normalized_targets.extend(ins.get("symbol_evidence", {}).get("normalized_targets", []))
                recommended_strategy = recommended_strategy or ins.get("recommended_strategy", {})
        except Exception:
            inspection_warnings.append(f"inspection failed for keyword: {keyword}")
    candidate_symbols = list(dict.fromkeys(candidate_symbols))
    unique_targets = {}
    for target in normalized_targets:
        if isinstance(target, dict):
            unique_targets[(target.get("engine"), target.get("full_class_name"), target.get("method_name"), target.get("signature"))] = target
    normalized_targets = list(unique_targets.values())

    package_spec = packages.build_package_spec(
        game_dir=game_dir,
        engine_id=engine["id"],
        mod_id=mod_id,
        mod_name=name,
        version=mod_version,
        customizations=customizations,
    )
    spec = {
        "schema_version": 1,
        "id": mod_id,
        "name": name,
        "version": mod_version,
        "request": request.strip(),
        "customizations": customizations or {},
        "engine": engine,
        "route": route,
        "ecosystem_pattern": _ecosystem_pattern(engine["id"]),
        "dependency_plan": package_spec["dependency_plan"],
        "artifact_groups": package_spec["artifact_groups"],
        "package_spec": package_spec,
        "prerequisites": prerequisites,
        "candidate_symbols": candidate_symbols,
        "normalized_targets": normalized_targets,
        "inspection_keywords": keywords,
        "inspection_warnings": inspection_warnings,
        "recommended_strategy": recommended_strategy,
        "expected_artifacts": ["source", "manifest", "build output", "install preview", "verification report"],
        "validation": ["compile", "install preview", "runtime read-back or game log", "package contents"],
        "status": "planned",
    }
    if engine["id"] == "unity":
        bepinex.scaffold_plugin(project_dir, game_dir, mod_id, name, mod_version)
    elif engine["id"] == "unreal":
        UnrealAdapter().scaffold_mod(project_dir, mod_id, name, mod_version)
    elif engine["id"] == "re-engine":
        ReEngineAdapter().scaffold_mod(project_dir, mod_id, name, mod_version)
    elif engine["id"] == "godot":
        GodotAdapter().scaffold_mod(project_dir, mod_id, name, mod_version)
    elif engine["id"] == "dotnet-xna":
        tmodloader.scaffold_tmod_mod(project_dir, mod_id, name, mod_version)
    package_materialization = packages.materialize_package_layout(project_dir, package_spec)
    manifest_path = os.path.join(project_dir, "mod.json")
    if os.path.isfile(manifest_path):
        manifest = ModManifest.load(manifest_path)
        manifest.dependencies = package_spec["dependency_plan"]["manifest_dependencies"]
        manifest.save(manifest_path)
    spec["package_materialization"] = package_materialization
    os.makedirs(project_dir, exist_ok=True)
    with open(os.path.join(project_dir, "mod-spec.json"), "w", encoding="utf-8") as f:
        json.dump(spec, f, ensure_ascii=False, indent=2)
    with open(os.path.join(project_dir, "package-spec.json"), "w", encoding="utf-8") as f:
        json.dump(package_spec, f, ensure_ascii=False, indent=2)
    with open(os.path.join(project_dir, "request.md"), "w", encoding="utf-8") as f:
        f.write(request.strip() + "\n")
    with open(os.path.join(project_dir, "MODDING_PLAN.md"), "w", encoding="utf-8") as f:
        f.write(_plan_markdown(spec))
    return spec


plan_mod = create_mod_plan



def _plan_markdown(spec: dict) -> str:
    custom = json.dumps(spec["customizations"], ensure_ascii=False, indent=2)
    symbols = "\n".join(f"- `{s}`" for s in spec.get("candidate_symbols", [])) or "None detected automatically"
    dependencies = "\n".join(
        f"- `{item['id']}` `{item.get('resolved_version') or item.get('version')}` — {item.get('kind')} ({item.get('status')})"
        for item in spec.get("dependency_plan", {}).get("dependencies", [])
    ) or "No external dependencies declared"
    groups = "\n".join(f"- `{name}`" for name in spec.get("artifact_groups", {}))
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

## Dependency Plan

{dependencies}

## Package Artifact Groups

{groups}

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


def validate_project(project_dir: str, stage: str = "pre_build") -> dict:
    """Validate the stable project shape before build/install/package."""
    if stage not in {"pre_build", "post_build"}:
        raise ValueError("stage must be pre_build or post_build")
    errors: list[str] = []
    warnings: list[str] = []
    try:
        manifest = ModManifest.load(os.path.join(project_dir, "mod.json"))
    except (OSError, ValueError, TypeError) as exc:
        return {"ok": False, "errors": [f"invalid mod.json: {exc}"], "warnings": []}
    if manifest.entry:
        try:
            entry_path = safe_join(project_dir, manifest.entry)
            if stage == "post_build" and not os.path.isfile(entry_path):
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
    package_spec_path = os.path.join(project_dir, "package-spec.json")
    if os.path.isfile(package_spec_path):
        try:
            with open(package_spec_path, "r", encoding="utf-8") as f:
                package_spec = json.load(f)
            package_check = packages.validate_package_spec(project_dir, package_spec)
            errors.extend(package_check.get("errors", []))
            warnings.extend(package_check.get("warnings", []))
        except (OSError, ValueError, TypeError) as exc:
            errors.append(f"invalid package-spec.json: {exc}")
    else:
        warnings.append("missing package-spec.json; generated by plan_mod")

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
