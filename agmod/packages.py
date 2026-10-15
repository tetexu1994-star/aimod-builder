"""Dependency profiles and package layouts for real mod distributions.

Public mod ecosystems are layered: a loader, an API/library, code, config,
assets, localization and compatibility metadata.  This module keeps those
layers explicit so a generated project is closer to a package that can be
installed and maintained than to a single hook file.
"""
from __future__ import annotations

import json
import os
import re
from typing import Any

_SEMVER = re.compile(r"^\d+\.\d+\.\d+(?:[-+][0-9A-Za-z.-]+)?$")
_GROUPS = ("code", "config", "assets", "localization", "manifest", "documentation")


_PROFILES = {
    "unity": {
        "loader": ("BepInEx/BepInExPack", "BepInEx", "5.4.23.0", "5.4.2100"),
        "apis": (("HarmonyLib/0Harmony", "Harmony", "2.10.1"),),
    },
    "unreal": {
        "loader": ("UE4SS/UE4SS", "UE4SS", "3.0.1", "3.0.1"),
        "apis": (),
    },
    "re-engine": {
        "loader": ("REFramework/REFramework", "REFramework", "1.5.7", "1.5.7"),
        "apis": (),
    },
    "godot": {
        "loader": ("GodotModLoader/GodotModLoader", "GodotModLoader", "0.9.0", "0.9.0"),
        "apis": (),
    },
    "dotnet-xna": {
        "loader": ("tModLoader/tModLoader", "tModLoader", "1.4.4.9", "1.4.4.9"),
        "apis": (),
    },
}


def _version(value: Any, fallback: str) -> str:
    value = str(value or "").strip()
    return value if _SEMVER.fullmatch(value) else fallback


def _dependency(
    identifier: str,
    name: str,
    version: str,
    kind: str,
    *,
    required: bool = True,
    distribution: bool = True,
    provided_by: str = "",
    distribution_version: str = "",
) -> dict:
    return {
        "id": identifier,
        "name": name,
        "kind": kind,
        "version": version,
        "distribution_version": distribution_version or version,
        "version_policy": "profile-pinned",
        "required": required,
        "distribution": distribution,
        "provided_by": provided_by,
        "status": "unresolved",
        "resolved_version": "",
        "evidence": "",
    }


def _installed_loader(game_dir: str, engine_id: str) -> tuple[str, str]:
    """Return a conservative (status, evidence) pair for the local loader."""
    checks = {
        "unity": (os.path.join(game_dir, "BepInEx", "core"), "BepInEx/core"),
        "unreal": (os.path.join(game_dir, "ue4ss"), "ue4ss/"),
        "re-engine": (os.path.join(game_dir, "reframework"), "reframework/"),
        "godot": (os.path.join(game_dir, "mods-unpacked"), "mods-unpacked/"),
        "dotnet-xna": (os.path.join(game_dir, "ModLoader"), "ModLoader/"),
    }
    path, label = checks.get(engine_id, ("", ""))
    return ("installed", f"local loader directory: {label}") if path and os.path.isdir(path) else ("missing", "")


def resolve_package_dependencies(game_dir: str, package_spec: dict) -> dict:
    """Resolve dependency state against the target game and return a plan.

    Profile versions are pinned in the spec, while the presence of a local
    loader is evidence of an installed prerequisite.  The result never claims
    a dependency is verified merely because a guessed symbol or loader name
    exists.
    """
    engine_id = str(package_spec.get("engine", {}).get("id", package_spec.get("engine_id", "generic")))
    overrides = package_spec.get("dependency_versions", {}) or {}
    dependencies = [dict(item) for item in package_spec.get("dependencies", [])]
    loader_status, loader_evidence = _installed_loader(game_dir, engine_id)
    for item in dependencies:
        override = overrides.get(item["id"])
        if override:
            item["version"] = _version(override, item["version"])
            item["distribution_version"] = item["version"]
        item["resolved_version"] = item["version"]
        if item["kind"] == "loader":
            item["status"] = loader_status
            item["evidence"] = loader_evidence
        elif item.get("provided_by"):
            item["status"] = "provided-by-loader" if loader_status == "installed" else "unresolved"
            item["evidence"] = f"provided by {item['provided_by']}"
        else:
            item["status"] = "required"
    manifest_dependencies = [
        f"{item['id'].replace('/', '-')}-{item.get('distribution_version') or item['resolved_version']}"
        for item in dependencies
        if item.get("distribution") and item.get("required") and item.get("resolved_version")
    ]
    return {
        "dependencies": dependencies,
        "manifest_dependencies": manifest_dependencies,
        "unresolved": [item["id"] for item in dependencies if item["status"] in {"missing", "unresolved"}],
    }


def _artifact_groups() -> dict:
    return {
        "code": {"required": True, "paths": ["*.csproj", "*.cs", "*.lua", "*.gd", "build.txt", "scripts", "autorun"], "package": True},
        "config": {"required": True, "paths": ["config"], "package": True},
        "assets": {"required": False, "paths": ["assets"], "package": True},
        "localization": {"required": False, "paths": ["localization"], "package": True},
        "manifest": {"required": True, "paths": ["mod.json", "package-spec.json", "compatibility.json"], "package": True},
        "documentation": {"required": False, "paths": ["README.md", "CHANGELOG.md", "LICENSE", "docs"], "package": True},
    }


def build_package_spec(
    game_dir: str,
    engine_id: str,
    mod_id: str,
    mod_name: str,
    version: str,
    customizations: dict | list | None = None,
) -> dict:
    """Build a package specification with dependency graph and artifact groups."""
    if not _SEMVER.fullmatch(str(version)):
        raise ValueError(f"invalid semantic version: {version!r}")
    engine_id = str(engine_id)
    profile = _PROFILES.get(engine_id, {})
    loader = profile.get("loader")
    dependencies = []
    if loader:
        dependencies.append(_dependency(loader[0], loader[1], loader[2], "loader", distribution_version=loader[3]))
        dependencies.extend(_dependency(*api, kind="runtime-api", required=False, distribution=False, provided_by=loader[1]) for api in profile.get("apis", ()))
    overrides = customizations.get("dependency_versions", {}) if isinstance(customizations, dict) else {}
    spec = {
        "schema_version": 1,
        "id": mod_id,
        "name": mod_name,
        "version": version,
        "engine": {"id": engine_id},
        "customizations": customizations or {},
        "dependency_versions": overrides,
        "dependencies": dependencies,
        "artifact_groups": _artifact_groups(),
        "compatibility": {
            "game_version": "record before release",
            "loader_version": loader[2] if loader else "",
            "api_version": "",
            "platform": "win64",
            "anti_cheat": "unsupported",
            "verification": "profile-pinned; verify against the installed game and loader before release",
        },
        "dependency_profile_status": "known" if loader else "unverified",
        "validation": ["dependency resolution", "artifact completeness", "package contents", "install preview"],
    }
    spec["dependency_plan"] = resolve_package_dependencies(game_dir, spec)
    spec["dependencies"] = spec["dependency_plan"]["dependencies"]
    return spec


def materialize_package_layout(project_dir: str, package_spec: dict) -> dict:
    """Create config/assets/localization/documentation layers around code."""
    created: list[str] = []
    customizations = package_spec.get("customizations", {}) if isinstance(package_spec.get("customizations"), dict) else {}
    config_dir = os.path.join(project_dir, "config")
    localization_dir = os.path.join(project_dir, "localization")
    assets_dir = os.path.join(project_dir, "assets")
    docs_dir = os.path.join(project_dir, "docs")
    for directory in (config_dir, localization_dir, assets_dir, docs_dir):
        os.makedirs(directory, exist_ok=True)
    config_path = os.path.join(config_dir, "default.json")
    if not os.path.exists(config_path):
        with open(config_path, "w", encoding="utf-8") as f:
            json.dump(customizations, f, ensure_ascii=False, indent=2)
        created.append("config/default.json")
    localization_path = os.path.join(localization_dir, "en-US.json")
    if not os.path.exists(localization_path):
        with open(localization_path, "w", encoding="utf-8") as f:
            description = customizations.get("description", "") if isinstance(customizations, dict) else ""
            json.dump({"name": package_spec.get("name", ""), "description": description}, f, ensure_ascii=False, indent=2)
        created.append("localization/en-US.json")
    assets_readme = os.path.join(assets_dir, "README.md")
    if not os.path.exists(assets_readme):
        with open(assets_readme, "w", encoding="utf-8") as f:
            f.write("Declare only the assets used by this mod. Keep source assets out of the distributable package.\n")
        created.append("assets/README.md")
    install_path = os.path.join(docs_dir, "INSTALL.md")
    if not os.path.exists(install_path):
        with open(install_path, "w", encoding="utf-8") as f:
            f.write("# Installation\n\nInstall the resolved loader dependency first, then install this package through the generated installer or its documented copy step.\n")
        created.append("docs/INSTALL.md")
    compatibility_path = os.path.join(project_dir, "compatibility.json")
    if not os.path.exists(compatibility_path):
        with open(compatibility_path, "w", encoding="utf-8") as f:
            json.dump(package_spec.get("compatibility", {}), f, ensure_ascii=False, indent=2)
        created.append("compatibility.json")
    return {"created": created, "groups": list(_GROUPS)}


def validate_package_spec(project_dir: str, package_spec: dict) -> dict:
    """Validate dependency declarations and the generated artifact layout."""
    errors: list[str] = []
    warnings: list[str] = []
    for key in ("schema_version", "id", "name", "version", "dependencies", "artifact_groups"):
        if key not in package_spec:
            errors.append(f"package spec missing {key}")
    if package_spec.get("version") and not _SEMVER.fullmatch(str(package_spec["version"])):
        errors.append(f"invalid package version: {package_spec.get('version')!r}")
    dependencies = package_spec.get("dependencies", [])
    if not isinstance(dependencies, list):
        errors.append("dependencies must be a list")
        dependencies = []
    for dep in dependencies:
        if not isinstance(dep, dict) or not dep.get("id") or not dep.get("version"):
            errors.append(f"invalid dependency declaration: {dep!r}")
            continue
        dependency_version = dep.get("distribution_version") or dep.get("version")
        if not _SEMVER.fullmatch(str(dependency_version)):
            errors.append(f"dependency version is not standard semver: {dep['id']}@{dependency_version}")
    groups = package_spec.get("artifact_groups", {})
    for name in _GROUPS:
        if name not in groups:
            errors.append(f"artifact group missing: {name}")
    if os.path.isfile(os.path.join(project_dir, "package-spec.json")):
        try:
            with open(os.path.join(project_dir, "package-spec.json"), encoding="utf-8") as f:
                on_disk = json.load(f)
            if on_disk.get("id") != package_spec.get("id"):
                errors.append("package-spec.json id does not match validation input")
        except (OSError, json.JSONDecodeError) as exc:
            errors.append(f"invalid package-spec.json: {exc}")
    else:
        warnings.append("package-spec.json is missing")
    for required in ("mod.json", os.path.join("config", "default.json"), os.path.join("localization", "en-US.json"), os.path.join("docs", "INSTALL.md"), "compatibility.json"):
        if not os.path.exists(os.path.join(project_dir, required)):
            errors.append(f"missing package artifact: {required}")
    return {"ok": not errors, "errors": errors, "warnings": warnings, "dependency_count": len(dependencies)}
