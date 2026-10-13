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
import zipfile

from .manifest import ModManifest

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

    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("manifest.json", json.dumps(manifest, ensure_ascii=False, indent=2))
        added = 0
        for d in _BUILD_DIRS:
            d = os.path.join(project_dir, d)
            if not os.path.isdir(d):
                continue
            for fn in sorted(os.listdir(d)):
                if fn.endswith(".dll"):
                    z.write(os.path.join(d, fn), fn)
                    added += 1
        z.writestr("README.txt", f"{m.name} v{m.version} by {m.author or 'unknown'}\n{m.description}\n")

    return path
