"""retoc (Unreal IoStore tool) discovery, checksum-verified download, and CLI wrapper.

retoc converts UE5 IoStore containers (.utoc/.ucas) to/from legacy cooked
assets (.uasset/.uexp), enabling asset editing with UAssetGUI. It is the missing
link for editing IoStore-only games (e.g. Phantom Blade Zero), where repak only
handles loose `.pak`.
"""
from __future__ import annotations

import hashlib
import os
import shutil
import subprocess
import sys
import urllib.request
import zipfile

RETOC_VERSION = os.environ.get("AGMOD_RETOC_VERSION", "v0.1.5")
RETOC_ZIP_URL = (
    f"https://github.com/trumank/retoc/releases/download/{RETOC_VERSION}/"
    "retoc_cli-x86_64-pc-windows-msvc.zip"
)
RETOC_SHA256_URL = RETOC_ZIP_URL + ".sha256"


def _tools_dir() -> str:
    d = os.path.join(os.path.expanduser("~"), ".agmod", "tools")
    os.makedirs(d, exist_ok=True)
    return d


def find_retoc() -> str | None:
    for name in ("retoc", "retoc.exe", "retoc_cli.exe"):
        p = shutil.which(name)
        if p:
            return p
    local = os.path.join(_tools_dir(), "retoc.exe")
    return local if os.path.isfile(local) else None


def ensure_retoc() -> str:
    """Return the retoc executable path, auto-downloading it (with SHA-256 check)."""
    existing = find_retoc()
    if existing:
        return existing
    if sys.platform != "win32":
        raise RuntimeError("retoc auto-download currently supports Windows only")

    dest_exe = os.path.join(_tools_dir(), "retoc.exe")
    zip_path = os.path.join(_tools_dir(), "retoc.zip")
    sha_path = os.path.join(_tools_dir(), "retoc.zip.sha256")
    try:
        urllib.request.urlretrieve(RETOC_ZIP_URL, zip_path)
        urllib.request.urlretrieve(RETOC_SHA256_URL, sha_path)
        with open(sha_path, "r", encoding="utf-8") as f:
            parts = f.read(256).split()
        if not parts or len(parts[0]) != 64:
            raise RuntimeError("retoc checksum file is malformed")
        expected = parts[0].lower()
        actual = hashlib.sha256()
        with open(zip_path, "rb") as f:
            for chunk in iter(lambda: f.read(1 << 20), b""):
                actual.update(chunk)
        if actual.hexdigest().lower() != expected:
            raise RuntimeError("retoc download checksum mismatch")
        with zipfile.ZipFile(zip_path) as z:
            candidate = next(
                (n for n in z.namelist() if os.path.basename(n).lower() in {"retoc.exe", "retoc_cli.exe"}),
                None,
            )
            if not candidate:
                raise RuntimeError("no .exe found in retoc archive")
            with z.open(candidate) as src, open(dest_exe, "wb") as out:
                shutil.copyfileobj(src, out)
    finally:
        for temp in (zip_path, sha_path):
            if os.path.exists(temp):
                os.remove(temp)

    if not os.path.isfile(dest_exe):
        raise RuntimeError("retoc download failed; install retoc manually and put it on PATH")
    return dest_exe


def to_legacy(paks_dir: str, out_dir: str, asset_filter: str = "", version: str = "") -> str:
    """Extract IoStore assets to legacy .uasset/.uexp for editing (UAssetGUI)."""
    retoc = ensure_retoc()
    os.makedirs(out_dir, exist_ok=True)
    cmd = [retoc, "to-legacy", "--no-shaders", paks_dir]
    if asset_filter:
        cmd += ["--filter", asset_filter]
    if version:
        cmd += ["--version", version]
    cmd += [out_dir]
    subprocess.run(cmd, check=True, capture_output=True, text=True)
    return out_dir


def to_zen(input_dir: str, out_utoc: str, version: str = "") -> str:
    """Repack legacy assets into an IoStore .utoc (plus sibling .ucas/.pak)."""
    retoc = ensure_retoc()
    os.makedirs(os.path.dirname(out_utoc) or ".", exist_ok=True)
    cmd = [retoc, "to-zen", input_dir, out_utoc]
    if version:
        cmd += ["--version", version]
    subprocess.run(cmd, check=True, capture_output=True, text=True)
    return out_utoc
