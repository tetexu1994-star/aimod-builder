"""repak (UE5 IoStore pak tool) discovery, auto-download, and pack/unpack wrapper.

repak is the community-standard tool for packing/unpacking UE5's IoStore
(.utoc/.ucas) archives. This module auto-downloads the Windows binary on first
use, so a user never has to install anything manually to build a pak override.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
import urllib.request
import zipfile

REPAK_VERSION = os.environ.get("AGMOD_REPAK_VERSION", "v0.2.3")
REPAK_ZIP_URL = (
    f"https://github.com/trumank/repak/releases/download/{REPAK_VERSION}/"
    "repak_cli-x86_64-pc-windows-msvc.zip"
)


def _tools_dir() -> str:
    d = os.path.join(os.path.expanduser("~"), ".agmod", "tools")
    os.makedirs(d, exist_ok=True)
    return d


def find_repak() -> str | None:
    """Locate repak on PATH or in the local tool cache."""
    for name in ("repak", "repak.exe", "repak_cli.exe"):
        p = shutil.which(name)
        if p:
            return p
    local = os.path.join(_tools_dir(), "repak.exe")
    return local if os.path.isfile(local) else None


def ensure_repak() -> str:
    """Return the repak executable path, auto-downloading it if necessary."""
    existing = find_repak()
    if existing:
        return existing
    if sys.platform != "win32":
        raise RuntimeError("repak auto-download currently supports Windows only")

    dest_exe = os.path.join(_tools_dir(), "repak.exe")
    zip_path = os.path.join(_tools_dir(), "repak.zip")
    try:
        urllib.request.urlretrieve(REPAK_ZIP_URL, zip_path)
        with zipfile.ZipFile(zip_path) as z:
            candidate = next((n for n in z.namelist() if n.lower().endswith(".exe")), None)
            if not candidate:
                raise RuntimeError("no .exe found in repak archive")
            with z.open(candidate) as src, open(dest_exe, "wb") as out:
                shutil.copyfileobj(src, out)
    finally:
        if os.path.exists(zip_path):
            os.remove(zip_path)

    if not os.path.isfile(dest_exe):
        raise RuntimeError("repak download failed; install repak manually and put it on PATH")
    return dest_exe


def pack_override(override_dir: str, out_pak: str) -> str:
    """Pack a directory of overridden files into a .pak (UE5 IoStore)."""
    repak = ensure_repak()
    os.makedirs(os.path.dirname(out_pak) or ".", exist_ok=True)
    subprocess.run(
        [repak, "pack", override_dir, out_pak],
        check=True, capture_output=True, text=True,
    )
    return out_pak


def unpack(pak_path: str, out_dir: str) -> str:
    """Unpack a .pak/.utoc archive into a directory for inspection."""
    repak = ensure_repak()
    os.makedirs(out_dir, exist_ok=True)
    subprocess.run(
        [repak, "unpack", pak_path, out_dir],
        check=True, capture_output=True, text=True,
    )
    return out_dir
