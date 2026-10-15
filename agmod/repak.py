"""repak (.pak archive tool) discovery, checksum-verified download, and CLI wrapper.

repak reads and writes Unreal Engine `.pak` archives. It does **not** parse
IoStore `.utoc/.ucas` containers; those still require FModel/CUE4Parse or a
game-specific extractor. The Windows release is downloaded with its published
SHA-256 before it is cached.
"""
from __future__ import annotations

import hashlib
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
REPAK_SHA256_URL = REPAK_ZIP_URL + ".sha256"


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
    sha_path = os.path.join(_tools_dir(), "repak.zip.sha256")
    try:
        urllib.request.urlretrieve(REPAK_ZIP_URL, zip_path)
        urllib.request.urlretrieve(REPAK_SHA256_URL, sha_path)
        with open(sha_path, "r", encoding="utf-8") as f:
            parts = f.read(256).split()
        if not parts or len(parts[0]) != 64:
            raise RuntimeError("repak checksum file is malformed")
        expected = parts[0].lower()
        actual = hashlib.sha256()
        with open(zip_path, "rb") as f:
            for chunk in iter(lambda: f.read(1 << 20), b""):
                actual.update(chunk)
        if actual.hexdigest().lower() != expected:
            raise RuntimeError("repak download checksum mismatch")
        with zipfile.ZipFile(zip_path) as z:
            candidate = next(
                (
                    n for n in z.namelist()
                    if os.path.basename(n).lower() in {"repak.exe", "repak_cli.exe"}
                ),
                None,
            )
            if not candidate:
                raise RuntimeError("no .exe found in repak archive")
            with z.open(candidate) as src, open(dest_exe, "wb") as out:
                shutil.copyfileobj(src, out)
    finally:
        for temp_path in (zip_path, sha_path):
            if os.path.exists(temp_path):
                os.remove(temp_path)

    if not os.path.isfile(dest_exe):
        raise RuntimeError("repak download failed; install repak manually and put it on PATH")
    return dest_exe


def pack_override(override_dir: str, out_pak: str, compression: str = "") -> str:
    """Pack a directory of overridden files into a loose Unreal Engine .pak.

    `compression` is one of gzip/zlib/zstd/none; empty means repak's default.
    If a game fails to load the pak, retry with compression="none".
    """
    repak = ensure_repak()
    os.makedirs(os.path.dirname(out_pak) or ".", exist_ok=True)
    cmd = [repak, "pack"]
    if compression and compression.lower() != "none":
        cmd += ["--compression", compression.lower()]
    cmd += [override_dir, out_pak]
    subprocess.run(cmd, check=True, capture_output=True, text=True)
    return out_pak


def unpack(pak_path: str, out_dir: str) -> str:
    """Unpack a .pak archive into a directory for inspection."""
    repak = ensure_repak()
    os.makedirs(out_dir, exist_ok=True)
    subprocess.run(
        [repak, "unpack", pak_path, "--output", out_dir],
        check=True, capture_output=True, text=True,
    )
    return out_dir


def info(pak_path: str) -> str:
    """Print .pak metadata (mount point, entries, version) via `repak info`."""
    repak = ensure_repak()
    r = subprocess.run([repak, "info", pak_path], capture_output=True, text=True)
    return (r.stdout or r.stderr or "").strip()
