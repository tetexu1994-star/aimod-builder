"""Portable .NET SDK bootstrap via the official dotnet-install script.

Downloads and runs the official ``dotnet-install.ps1`` to install a .NET SDK
into a user-writable directory (no admin, no system-wide change). This unlocks
MelonLoader IL2CPP builds, CUE4Parse, tModLoader and ilspycmd without requiring
a pre-installed SDK.

The install is cached under ``~/.agmod/tools/dotnet``; repeated calls return
the cached path instantly.
"""
from __future__ import annotations

import logging
import os
import shutil
import subprocess
import sys
import urllib.request

DOTNET_CHANNEL = os.environ.get("AGMOD_DOTNET_CHANNEL", "8.0")
_INSTALL_SCRIPT_URL = "https://dot.net/v1/dotnet-install.ps1"
_HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}

logger = logging.getLogger(__name__)


def _dotnet_dir() -> str:
    d = os.path.join(os.path.expanduser("~"), ".agmod", "tools", "dotnet")
    os.makedirs(d, exist_ok=True)
    return d


def find_dotnet() -> str | None:
    """Return a usable dotnet.exe: PATH first, then the cached local install."""
    p = shutil.which("dotnet")
    if p:
        return p
    local = os.path.join(_dotnet_dir(), "dotnet.exe")
    return local if os.path.isfile(local) else None


def ensure_dotnet() -> str:
    """Return a dotnet.exe path, auto-installing a portable SDK if necessary."""
    existing = find_dotnet()
    if existing:
        return existing
    if sys.platform != "win32":
        raise RuntimeError("dotnet auto-install currently supports Windows only")

    install_dir = _dotnet_dir()
    script = os.path.join(install_dir, "dotnet-install.ps1")
    logger.info("Downloading .NET SDK installer (first time; the SDK is large)...")
    req = urllib.request.Request(_INSTALL_SCRIPT_URL, headers=_HEADERS)
    with urllib.request.urlopen(req, timeout=120) as resp, open(script, "wb") as f:
        shutil.copyfileobj(resp, f)

    logger.info("Installing .NET SDK channel %s into %s ...", DOTNET_CHANNEL, install_dir)
    r = subprocess.run(
        ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", script,
         "-Channel", DOTNET_CHANNEL, "-InstallDir", install_dir, "-NoPath"],
        capture_output=True, text=True, encoding="utf-8", errors="replace", check=False, timeout=1800,
    )
    if r.returncode != 0:
        detail = (r.stderr or r.stdout or "").strip()[-1500:]
        raise RuntimeError(f"dotnet install failed: {detail}")

    local = os.path.join(install_dir, "dotnet.exe")
    if not os.path.isfile(local):
        raise RuntimeError("dotnet install finished but dotnet.exe was not found")
    logger.info(".NET SDK installed at %s", install_dir)
    return local


def dotnet_version(dotnet: str | None = None) -> str:
    """Report the dotnet SDK version string (empty on failure)."""
    exe = dotnet or find_dotnet()
    if not exe:
        return ""
    try:
        r = subprocess.run([exe, "--version"], capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=30, check=False)
        return (r.stdout or "").strip() if r.returncode == 0 else ""
    except Exception:
        return ""
