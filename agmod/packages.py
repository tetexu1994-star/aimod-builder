"""Dependency profiles and package layouts for real mod distributions.

Public mod ecosystems are layered: a loader, an API/library, code, config,
assets, localization and compatibility metadata.  This module keeps those
layers explicit so a generated project is closer to a package that can be
installed and maintained than to a single hook file.
"""
from __future__ import annotations

import json
import glob
import os
import re
from typing import Any

_SEMVER = re.compile(r"^\d+\.\d+\.\d+(?:\.\d+)?(?:[-+][0-9A-Za-z.-]+)?$")
_GROUPS = ("code", "config", "assets", "localization", "manifest", "documentation")


_PROFILES = {
    "unity": {
        "loader": ("BepInEx/BepInExPack", "BepInEx", "5.4.23.5", "5.4.2100"),
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
    "bethesda": {
        "loader": ("SKSE/SKSE64", "SKSE64", "2.2.6", "2.2.6"),
        "apis": (),
    },
    "divinity": {
        "loader": ("Norbyte/bg3se", "BG3 Script Extender", "1.0.0", "1.0.0"),
        "apis": (),
    },
    "fromsoftware": {
        "loader": ("soulsmods/ModEngine2", "Mod Engine 2", "2.1.0", "2.1.0"),
        "apis": (),
    },
    "redengine": {
        "loader": ("yamashi/CyberEngineTweaks", "Cyber Engine Tweaks", "1.32.0", "1.32.0"),
        "apis": (),
    },
    "taleworlds": {
        "loader": ("BUTR/Bannerlord.Harmony", "Bannerlord Harmony", "2.2.2", "2.2.2"),
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
    if not game_dir:
        return "missing", ""
    def has_marker(path: str, names: tuple[str, ...]) -> bool:
        return os.path.isdir(path) and any(os.path.isfile(os.path.join(path, name)) for name in names)

    checks = {
        "unity": ([os.path.join(game_dir, "BepInEx", "core")], "BepInEx/core", ("BepInEx.dll", "BepInEx.Core.dll", "0Harmony.dll")),
        "unreal": (
            glob.glob(os.path.join(game_dir, "*", "Binaries", "Win64", "ue4ss"))
            + [os.path.join(game_dir, "Binaries", "Win64", "ue4ss"), os.path.join(game_dir, "ue4ss")],
            "Binaries/Win64/ue4ss",
            ("UE4SS.dll", "ue4ss.dll", "dwmapi.dll"),
        ),
        "re-engine": ([os.path.join(game_dir, "reframework")], "reframework/", (os.path.join(os.pardir, "dinput8.dll"), "reframework.dll")),
        "godot": ([os.path.join(game_dir, "mods-unpacked")], "mods-unpacked/", ()),
        "dotnet-xna": ([os.path.join(game_dir, "ModLoader"), os.path.join(game_dir, "Mods"), os.path.join(game_dir, "BepInEx", "plugins")], "ModLoader/Mods", ()),
        "bethesda": ([os.path.join(game_dir, "Data", "SKSE"), os.path.join(game_dir, "Data", "F4SE"), os.path.join(game_dir, "Data")], "Data/SKSE", ()),
        "divinity": ([os.path.join(game_dir, "bin")], "bin/DWrite.dll", ("DWrite.dll", "dwrite.dll")),
        "fromsoftware": ([os.path.join(game_dir, "modengine2"), os.path.join(game_dir, "mod")], "modengine2/", ()),
        "redengine": ([os.path.join(game_dir, "bin", "x64", "plugins"), os.path.join(game_dir, "Mods")], "bin/x64/plugins", ()),
        "taleworlds": ([os.path.join(game_dir, "Modules", "Bannerlord.Harmony")], "Modules/Bannerlord.Harmony", ()),
    }
    paths, label, markers = checks.get(engine_id, ([], "", ()))
    for path in paths:
        if path and (not markers or has_marker(path, markers)):
            return "installed", f"local loader directory: {label}"
    return "missing", ""


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


def _version_markers(engine_id: str, game_dir: str) -> list[str]:
    roots = {
        "unity": [os.path.join(game_dir, "BepInEx")],
        "unreal": glob.glob(os.path.join(game_dir, "*", "Binaries", "Win64", "ue4ss")) + [
            os.path.join(game_dir, "Binaries", "Win64", "ue4ss"),
            os.path.join(game_dir, "ue4ss"),
            os.path.join(game_dir, "UE4SS"),
        ],
        "re-engine": [os.path.join(game_dir, "reframework")],
        "godot": [os.path.join(game_dir, "mods-unpacked")],
        "dotnet-xna": [os.path.join(game_dir, "ModLoader")],
    }.get(engine_id, [])
    names = ("version.txt", "Version", "VERSION", "version.json", "changelog.txt", "CHANGELOG.md")
    values: list[str] = []
    for root in roots:
        for name in names:
            path = os.path.join(root, name)
            if not os.path.isfile(path):
                continue
            try:
                with open(path, "r", encoding="utf-8", errors="ignore") as f:
                    values.append(f.read(16384))
            except OSError:
                continue
    return values


def check_dependency_compatibility(game_dir: str, package_spec: dict) -> dict:
    """Check required loader/API prerequisites without claiming unreadable versions are verified."""
    resolved = resolve_package_dependencies(game_dir, package_spec)
    engine_id = str(package_spec.get("engine", {}).get("id", package_spec.get("engine_id", "generic")))
    marker_text = "\n".join(_version_markers(engine_id, game_dir))
    errors: list[str] = []
    warnings: list[str] = []
    compatibility_record = package_spec.get("compatibility", {}) if isinstance(package_spec.get("compatibility"), dict) else {}
    if str(compatibility_record.get("game_version", "")).strip().lower() in {"", "record before release"}:
        warnings.append("game version has not been recorded in compatibility.json")
    if package_spec.get("dependency_profile_status") == "game-specific-loose-pak":
        warnings.append("IoStore game support for loose .pak overrides must be verified on the target game version")
    checks: list[dict] = []
    for dep in resolved["dependencies"]:
        required = bool(dep.get("required"))
        status = dep.get("status")
        expected = str(dep.get("resolved_version") or dep.get("version") or "")
        detected = ""
        if marker_text:
            match = re.search(r"\b\d+\.\d+\.\d+(?:\.\d+)?\b", marker_text)
            detected = match.group(0) if match else ""
        compatibility = "unknown"
        if status == "missing":
            compatibility = "missing"
            if required:
                errors.append(f"required dependency is missing: {dep.get('id')}@{expected}")
        elif status == "installed":
            if not detected:
                warnings.append(f"installed dependency version is not readable: {dep.get('id')}")
            elif detected == expected or detected.startswith(expected + ".") or expected.startswith(detected + "."):
                compatibility = "compatible"
            else:
                compatibility = "incompatible"
                errors.append(f"dependency version mismatch: {dep.get('id')} expected {expected}, found {detected}")
        checks.append({
            "id": dep.get("id"),
            "kind": dep.get("kind"),
            "required": required,
            "status": status,
            "expected_version": expected,
            "detected_version": detected,
            "compatibility": compatibility,
            "evidence": dep.get("evidence", ""),
        })
    return {
        "ready": not errors,
        "errors": errors,
        "warnings": warnings,
        "checks": checks,
        "manifest_dependencies": resolved["manifest_dependencies"],
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
    unreal_patterns = ("Content/Paks/*.utoc", "Content/Paks/*.ucas", "*/Content/Paks/*.utoc", "*/Content/Paks/*.ucas", "*/*/Content/Paks/*.utoc", "*/*/Content/Paks/*.ucas")
    unreal_iostore = engine_id == "unreal" and bool(game_dir) and any(glob.glob(os.path.join(game_dir, pattern)) for pattern in unreal_patterns)
    if loader and not unreal_iostore:
        dependencies.append(_dependency(loader[0], loader[1], loader[2], "loader", distribution_version=loader[3]))
        dependencies.extend(_dependency(*api, kind="runtime-api", required=False, distribution=False, provided_by=loader[1]) for api in profile.get("apis", ()))
    overrides = customizations.get("dependency_versions", {}) if isinstance(customizations, dict) else {}
    spec = {
        "schema_version": 1,
        "id": mod_id,
        "name": mod_name,
        "version": version,
        "engine": {"id": engine_id, "variant": "ue5-iostore" if unreal_iostore else ""},
        "customizations": customizations or {},
        "dependency_versions": overrides,
        "dependencies": dependencies,
        "artifact_groups": _artifact_groups(),
        "compatibility": {
            "game_version": "record before release",
            "loader_version": loader[2] if loader and not unreal_iostore else "",
            "api_version": "",
            "platform": "win64",
            "anti_cheat": "unsupported",
            "verification": "profile-pinned; verify against the installed game and loader before release",
        },
        "dependency_profile_status": "game-specific-loose-pak" if unreal_iostore else "known" if loader else "unverified",
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
