"""Portable C# compiler discovery and checksum-verified download.

Unity BepInEx plugins and tModLoader mods need a modern C# compiler. The .NET
SDK (``dotnet``) is preferred, but many modding machines don't have it — and
Windows' built-in ``csc.exe`` only understands C# 5. This module downloads the
standalone Roslyn ``csc.exe`` (from the ``Microsoft.Net.Compilers`` NuGet
package), which runs on the .NET Framework runtime that Windows already ships
and compiles current C#, so plugin builds work with no SDK install.
"""
from __future__ import annotations

import hashlib
import os
import shutil
import subprocess
import sys
import urllib.request
import zipfile

ROSLYN_VERSION = os.environ.get("AGMOD_ROSLYN_VERSION", "4.2.0")
_PKG_ID = "microsoft.net.compilers"
_FLAT_BASE = "https://api.nuget.org/v3-flatcontainer"
_NUPKG_URL = f"{_FLAT_BASE}/{_PKG_ID}/{ROSLYN_VERSION}/{_PKG_ID}.{ROSLYN_VERSION}.nupkg"
# SHA-256 of the pinned Microsoft.Net.Compilers 4.2.0 nupkg; detects tampered or
# truncated downloads. A custom AGMOD_ROSLYN_VERSION skips this check.
_ROSLYN_SHA256 = "d1a8d866d6806202b2f1f5e21cb77839cef2606de9c0d9e6939a7e1f1baa4244"
_HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}

# Core .NET Framework reference assemblies most plugin code needs. Facade
# assemblies are deliberately omitted to avoid duplicate-reference conflicts.
_FRAMEWORK_DLLS = (
    "mscorlib.dll",
    "System.dll",
    "System.Core.dll",
    "System.Xml.dll",
    "System.Xml.Linq.dll",
    "System.Data.dll",
    "System.Drawing.dll",
    "System.Numerics.dll",
    "System.Net.Http.dll",
    "Microsoft.CSharp.dll",
)


def _tools_dir() -> str:
    d = os.path.join(os.path.expanduser("~"), ".agmod", "tools", "roslyn")
    os.makedirs(d, exist_ok=True)
    return d


def find_roslyn_csc() -> str | None:
    """Return the cached standalone Roslyn csc.exe, if already downloaded."""
    p = os.path.join(_tools_dir(), "csc.exe")
    return p if os.path.isfile(p) else None


def _download(url: str, dest: str) -> None:
    req = urllib.request.Request(url, headers=_HEADERS)
    with urllib.request.urlopen(req, timeout=180) as resp, open(dest, "wb") as f:
        shutil.copyfileobj(resp, f)


def _sha256_hex(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _extract_tools(nupkg_path: str, dest_dir: str) -> None:
    with zipfile.ZipFile(nupkg_path) as z:
        names = [n for n in z.namelist() if n.startswith("tools/") and not n.endswith("/")]
        if not names:
            raise RuntimeError("no tools/ directory found in Microsoft.Net.Compilers package")
        for name in names:
            basename = os.path.basename(name)
            if not basename:
                continue
            target = os.path.join(dest_dir, basename)
            with z.open(name) as src, open(target, "wb") as out:
                shutil.copyfileobj(src, out)


def ensure_roslyn_csc() -> str:
    """Return the standalone Roslyn csc.exe path, auto-downloading it if needed."""
    existing = find_roslyn_csc()
    if existing:
        return existing
    if sys.platform != "win32":
        raise RuntimeError("Roslyn csc auto-download currently supports Windows only")

    tools_dir = _tools_dir()
    nupkg_path = os.path.join(tools_dir, "roslyn.nupkg")
    try:
        _download(_NUPKG_URL, nupkg_path)
        expected = _ROSLYN_SHA256 if ROSLYN_VERSION == "4.2.0" else None
        if expected and _sha256_hex(nupkg_path) != expected:
            raise RuntimeError("Roslyn download checksum mismatch")
        _extract_tools(nupkg_path, tools_dir)
    finally:
        if os.path.exists(nupkg_path):
            os.remove(nupkg_path)

    csc = os.path.join(tools_dir, "csc.exe")
    if not os.path.isfile(csc):
        raise RuntimeError("Roslyn download failed; install the .NET SDK and retry")
    return csc


def framework_reference_dir() -> str:
    """Directory holding .NET Framework 4.x reference assemblies.

    Prefers the reference-assemblies targeting pack (installed with the
    Developer Pack); falls back to the runtime directory, which always exists
    on Windows and is what the built-in csc.exe compiles against.
    """
    base = r"C:\Program Files (x86)\Reference Assemblies\Microsoft\Framework\.NETFramework"
    for v in ("v4.8.1", "v4.8", "v4.7.2", "v4.7.1", "v4.7", "v4.6.2",
              "v4.6.1", "v4.6", "v4.5.2", "v4.5.1", "v4.5", "v4.0"):
        d = os.path.join(base, v)
        if os.path.isdir(d):
            return d
    for d in (
        r"C:\Windows\Microsoft.NET\Framework64\v4.0.30319",
        r"C:\Windows\Microsoft.NET\Framework\v4.0.30319",
    ):
        if os.path.isdir(d):
            return d
    return ""


def framework_references() -> list[str]:
    """Absolute paths of the standard .NET Framework assemblies to reference."""
    d = framework_reference_dir()
    if not d:
        return []
    return [os.path.join(d, name) for name in _FRAMEWORK_DLLS if os.path.isfile(os.path.join(d, name))]


def find_compiler() -> dict:
    """Best available C# compiler, in preference order: dotnet SDK, standalone
    Roslyn csc.exe, then Windows built-in csc.exe (C# 5 only)."""
    dotnet = shutil.which("dotnet")
    if dotnet:
        return {"type": "dotnet", "path": dotnet}
    roslyn = find_roslyn_csc()
    if roslyn:
        return {"type": "roslyn", "path": roslyn}
    for csc in (
        r"C:\Windows\Microsoft.NET\Framework64\v4.0.30319\csc.exe",
        r"C:\Windows\Microsoft.NET\Framework\v4.0.30319\csc.exe",
    ):
        if os.path.isfile(csc):
            return {"type": "csc", "path": csc}
    which_csc = shutil.which("csc")
    if which_csc:
        return {"type": "csc", "path": which_csc}
    return {"type": None, "path": None}


def compile_with_csc(csc: str, out_dll_path: str, refs: list[str], cs_source_path: str, langversion: str = "latest") -> subprocess.CompletedProcess:
    """Run a standalone csc.exe (Roslyn or built-in) against `refs` + framework assemblies."""
    fw_refs = framework_references()
    all_refs = list(dict.fromkeys(refs + fw_refs))  # de-dupe, preserve order
    cmd = [csc, "/noconfig"]
    if all_refs:
        # With an explicit reference set (mscorlib included) there is nothing to
        # inherit, so compile fully deterministically against what we list.
        cmd.append("/nostdlib+")
    cmd += ["/target:library", f"/out:{out_dll_path}", f"/langversion:{langversion}"]
    cmd += [f"/reference:{r}" for r in all_refs]
    cmd += [cs_source_path]
    return subprocess.run(cmd, capture_output=True, text=True, check=False)
