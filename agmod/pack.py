"""Package a built mod for distribution (Thunderstore / Nexus style).

Produces `Author-ModName-Version.zip` containing:
  - manifest.json (Thunderstore schema: name, version_number, description,
    website_url, dependencies)
  - built DLL(s), scripts, or a loose `.pak` from the project's output dirs

Uploading to Nexus Mods / Thunderstore / mod.io is a separate step (Nexus needs
an API key, Thunderstore uploads via the app or API); this just produces a
ready-to-upload package.
"""
from __future__ import annotations

import json
import os
import re
import stat
import zipfile

from .manifest import ModManifest
from .paths import safe_join

_BUILD_DIRS = [
    "out",
    "dist",
    os.path.join("bin", "Release", "net472"),
    os.path.join("bin", "Release", "net6.0"),
]


def _safe(name: str) -> str:
    out = "".join(c for c in name if c.isalnum() or c in ".-_")
    return out or "mod"


def package_mod(project_dir: str, output_dir: str = "") -> str:
    m = ModManifest.load(os.path.join(project_dir, "mod.json"))
    if not m.id or not m.name or not m.version:
        raise ValueError("mod.json must define id, name, and version")
    if not re.fullmatch(r"\d+\.\d+\.\d+(?:[-+][0-9A-Za-z.-]+)?", m.version):
        raise ValueError(f"invalid semantic version: {m.version!r}")

    out = output_dir or os.path.join(project_dir, "dist")
    os.makedirs(out, exist_ok=True)

    pkg_name = _safe(f"{m.author or 'Unknown'}-{m.name}-{m.version}") + ".zip"
    path = os.path.join(out, pkg_name)

    manifest = {
        "name": m.name,
        "version_number": m.version,
        "website_url": m.website_url,
        "description": m.description,
        "dependencies": m.dependencies or [],
    }

    dlls: dict[str, str] = {}
    paks: dict[str, str] = {}
    for d in _BUILD_DIRS:
        d = os.path.join(project_dir, d)
        if not os.path.isdir(d):
            continue
        for fn in sorted(os.listdir(d)):
            if fn.endswith(".dll"):
                dlls.setdefault(fn, os.path.join(d, fn))
            elif fn.lower().endswith(".pak"):
                paks.setdefault(fn, os.path.join(d, fn))
    entry_file = None
    if m.entry:
        entry_path = safe_join(project_dir, m.entry)
        if os.path.isfile(entry_path):
            entry_file = entry_path
        elif os.path.basename(m.entry) not in dlls:
            raise ValueError(f"manifest entry not found: {m.entry}")
    if not dlls and not paks and not (m.engine in {"unreal", "re-engine", "godot"} and entry_file):
        raise ValueError("no built DLL, .pak, or entry script found; build the mod before packaging")

    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("manifest.json", json.dumps(manifest, ensure_ascii=False, indent=2))
        for metadata in ("mod.json", "package-spec.json", "compatibility.json"):
            metadata_path = os.path.join(project_dir, metadata)
            if os.path.isfile(metadata_path):
                z.write(metadata_path, metadata)
        for fn in sorted(dlls):
            z.write(dlls[fn], fn)
        for fn in sorted(paks):
            z.write(paks[fn], f"dist/{fn}")
        for group in ("config", "assets", "localization", "docs"):
            group_dir = os.path.join(project_dir, group)
            if not os.path.isdir(group_dir):
                continue
            for root, dirs, files in os.walk(group_dir):
                dirs[:] = [d for d in dirs if d not in {"__pycache__", ".git"}]
                for fn in files:
                    source = os.path.join(root, fn)
                    rel = os.path.relpath(source, project_dir).replace("\\", "/")
                    z.write(source, rel)
        if entry_file and not entry_file.lower().endswith(".dll"):
            z.write(entry_file, m.entry.replace("\\", "/"))
            if m.engine in {"unreal", "re-engine", "godot"}:
                for root, dirs, files in os.walk(project_dir):
                    dirs[:] = [d for d in dirs if d not in {"dist", "__pycache__"}]
                    for fn in files:
                        source = os.path.join(root, fn)
                        rel = os.path.relpath(source, project_dir).replace("\\", "/")
                        if rel == m.entry.replace("\\", "/"):
                            continue
                        if rel in {"mod.json", "mod-spec.json", "request.md", "MODDING_PLAN.md", "README.md", "icon.png", "package-spec.json", "compatibility.json"} or rel.startswith(("config/", "assets/", "localization/", "docs/")):
                            continue
                        z.write(source, rel)
        readme = os.path.join(project_dir, "README.md")
        if os.path.isfile(readme):
            z.write(readme, "README.md")
        else:
            z.writestr("README.md", f"{m.name} v{m.version} by {m.author or 'unknown'}\n\n{m.description}\n")
        icon = os.path.join(project_dir, "icon.png")
        if os.path.isfile(icon):
            z.write(icon, "icon.png")

    return path


def validate_package(package_path: str) -> dict:
    """Validate a generated Thunderstore/Nexus mod ZIP archive."""
    if not os.path.isfile(package_path):
        return {"valid": False, "error": f"file not found: {package_path}"}

    errors: list[str] = []
    warnings: list[str] = []
    manifest_data = {}

    try:
        with zipfile.ZipFile(package_path, "r") as z:
            names = z.namelist()
            seen = set()
            for info in z.infolist():
                name = info.filename.replace("\\", "/")
                normalized = name.rstrip("/")
                if (
                    not name
                    or name.startswith("/")
                    or re.match(r"^[A-Za-z]:", name)
                    or ".." in normalized.split("/")
                    or "\x00" in name
                ):
                    errors.append(f"unsafe archive path: {info.filename}")
                if name in seen:
                    errors.append(f"duplicate archive path: {name}")
                seen.add(name)
                mode = info.external_attr >> 16
                if stat.S_ISLNK(mode):
                    errors.append(f"symbolic links are not allowed: {name}")
            if "manifest.json" not in names:
                errors.append("missing manifest.json")
            else:
                try:
                    manifest_data = json.loads(z.read("manifest.json").decode("utf-8"))
                    for req in ("name", "version_number", "description", "dependencies"):
                        if req not in manifest_data:
                            errors.append(f"manifest.json missing required key: {req}")
                    if "version_number" in manifest_data and not re.fullmatch(r"\d+\.\d+\.\d+(?:[-+][0-9A-Za-z.-]+)?", str(manifest_data["version_number"])):
                        warnings.append(f"version_number '{manifest_data['version_number']}' is not standard semver")
                except json.JSONDecodeError:
                    errors.append("manifest.json is not valid JSON")

            if "README.md" not in names:
                warnings.append("missing README.md (recommended for distribution)")

            payloads = [n for n in names if n not in {"manifest.json", "README.md", "icon.png"}]
            if not payloads:
                errors.append("archive contains no mod payload files (dll, scripts, assets)")

            has_code = any(n.lower().endswith((".dll", ".lua", ".cs", ".tmod", ".gd", ".pak")) for n in payloads)
            if not has_code:
                warnings.append("archive has no executable DLL or script files")

            return {
                "valid": len(errors) == 0,
                "errors": errors,
                "warnings": warnings,
                "file_count": len(names),
                "payload_files": payloads,
                "manifest": manifest_data,
            }
    except zipfile.BadZipFile:
        return {"valid": False, "error": "file is not a valid zip archive"}

