"""Package a built mod for distribution (Thunderstore / Nexus style).

Produces `Author-ModName-Version.zip` containing:
  - manifest.json (Thunderstore schema: name, version_number, description,
    website_url, dependencies)
  - the built DLL(s) from the project's output dir

Uploading to Nexus Mods / Thunderstore / mod.io is a separate step (Nexus needs
an API key, Thunderstore uploads via the app or API); this just produces a
ready-to-upload package.
"""
from __future__ import annotations

import json
import os
import re
import zipfile

from .manifest import ModManifest
from .paths import safe_join

_BUILD_DIRS = [
    "out",
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
    for d in _BUILD_DIRS:
        d = os.path.join(project_dir, d)
        if not os.path.isdir(d):
            continue
        for fn in sorted(os.listdir(d)):
            if fn.endswith(".dll"):
                dlls.setdefault(fn, os.path.join(d, fn))
    entry_file = None
    if m.entry:
        entry_path = safe_join(project_dir, m.entry)
        if os.path.isfile(entry_path):
            entry_file = entry_path
        elif os.path.basename(m.entry) not in dlls:
            raise ValueError(f"manifest entry not found: {m.entry}")
    if not dlls and not (m.engine == "unreal" and entry_file):
        raise ValueError("no built DLL found; run build_mod/build_tmod_mod before packaging")

    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("manifest.json", json.dumps(manifest, ensure_ascii=False, indent=2))
        for fn in sorted(dlls):
            z.write(dlls[fn], fn)
        if entry_file and not entry_file.lower().endswith(".dll"):
            z.write(entry_file, m.entry.replace("\\", "/"))
            if m.engine == "unreal":
                for root, dirs, files in os.walk(project_dir):
                    dirs[:] = [d for d in dirs if d not in {"dist", "__pycache__"}]
                    for fn in files:
                        source = os.path.join(root, fn)
                        rel = os.path.relpath(source, project_dir).replace("\\", "/")
                        if rel == m.entry.replace("\\", "/"):
                            continue
                        if rel in {"mod-spec.json", "request.md", "MODDING_PLAN.md"}:
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
