"""UAssetGUI: low-level Unreal .uasset/.umap edit via a UAssetAPI JSON round-trip.

Downloads the single-file UAssetGUI.exe (MIT) and wraps its headless CLI::

    UAssetGUI tojson   <asset> <json> <engine_version> [mappings]
    UAssetGUI fromjson <json>  <asset> [mappings]

This is the "write/modify" half of the Unreal asset pipeline: repak/retoc handle
the .pak/.utoc containers, and UAssetGUI edits the .uasset contents.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
import urllib.request

UASSETGUI_VERSION = os.environ.get("AGMOD_UASSETGUI_VERSION", "v1.1.0")
_UASSETGUI_URL = (
    f"https://github.com/atenfyr/UAssetGUI/releases/download/{UASSETGUI_VERSION}/UAssetGUI.exe"
)
_HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}


def _tools_dir() -> str:
    d = os.path.join(os.path.expanduser("~"), ".agmod", "tools", "uassetgui")
    os.makedirs(d, exist_ok=True)
    return d


def find_uassetgui() -> str | None:
    p = shutil.which("UAssetGUI")
    if p:
        return p
    local = os.path.join(_tools_dir(), "UAssetGUI.exe")
    return local if os.path.isfile(local) else None


def _download(dest: str) -> None:
    req = urllib.request.Request(_UASSETGUI_URL, headers=_HEADERS)
    with urllib.request.urlopen(req, timeout=300) as resp, open(dest, "wb") as f:
        shutil.copyfileobj(resp, f)


def ensure_uassetgui() -> str:
    """Return the UAssetGUI.exe path, auto-downloading it if necessary."""
    existing = find_uassetgui()
    if existing:
        return existing
    if sys.platform != "win32":
        raise RuntimeError("UAssetGUI auto-download currently supports Windows only")
    dest = os.path.join(_tools_dir(), "UAssetGUI.exe")
    _download(dest)
    if not os.path.isfile(dest):
        raise RuntimeError("UAssetGUI download failed")
    return dest


def _run(args: list[str]) -> None:
    exe = ensure_uassetgui()
    subprocess.run([exe, *args], check=True, capture_output=True, text=True)


def to_json(source: str, dest: str, engine_version: str, mappings: str = "") -> str:
    """Export a .uasset/.umap to UAssetAPI JSON. Returns the JSON path."""
    args = ["tojson", source, dest, engine_version]
    if mappings:
        args.append(mappings)
    _run(args)
    return dest


def from_json(source: str, dest: str, mappings: str = "") -> str:
    """Import UAssetAPI JSON back into a .uasset/.umap. Returns the asset path."""
    args = ["fromjson", source, dest]
    if mappings:
        args.append(mappings)
    _run(args)
    return dest
