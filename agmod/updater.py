"""GitHub release/commit polling + mod auto-update.

When the mod's GitHub repo updates, the client can detect it (check) and pull
the new plugin DLL (update). Uses only stdlib (urllib), no third-party deps.
"""
from __future__ import annotations

import json
import hashlib
import os
import re
import tempfile
import urllib.error
import urllib.request

from . import rollback
from .paths import UnsafePathError, safe_basename, safe_join

API = "https://api.github.com/repos"
_HEADERS = {"User-Agent": "game-mod-agent", "Accept": "application/vnd.github+json"}


def _get_json(url: str) -> dict:
    req = urllib.request.Request(url, headers=_HEADERS)
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read().decode())


def latest_release(owner: str, repo: str) -> dict:
    """Latest GitHub release: {tag_name, name, assets:[{name, browser_download_url}], ...}."""
    try:
        return _get_json(f"{API}/{owner}/{repo}/releases/latest")
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return {}
        raise


def latest_commit(owner: str, repo: str, branch: str = "main") -> dict:
    """Latest commit: {sha, commit:{message}, ...}. For repos without releases."""
    return _get_json(f"{API}/{owner}/{repo}/commits/{branch}")


def check_update(owner: str, repo: str, current_version: str) -> dict:
    """Compare the installed version against the latest release tag.

    Returns {update_available, latest, current}.
    Falls back to latest commit sha for repos that don't cut releases.
    """
    rel = latest_release(owner, repo)
    if rel.get("tag_name"):
        latest = rel["tag_name"].lstrip("v")
        return {
            "update_available": _version_gt(latest, current_version),
            "latest": latest,
            "current": current_version,
            "source": "release",
        }
    commit = latest_commit(owner, repo)
    latest = (commit.get("sha") or "")[:8]
    return {
        "update_available": bool(latest) and latest != current_version,
        "latest": latest,
        "current": current_version,
        "source": "commit",
    }


def _version_gt(candidate: str, current: str) -> bool:
    def parts(value: str) -> tuple[int, ...]:
        value = value.lstrip("vV")
        core = re.split(r"[-+]", value, 1)[0]
        return tuple(int(p) for p in re.findall(r"\d+", core))

    if not candidate or not current:
        return bool(candidate) and candidate != current
    try:
        return parts(candidate) > parts(current)
    except ValueError:
        return candidate != current


def _verify_digest(path: str, expected: str | None) -> None:
    if not expected or not expected.startswith("sha256:"):
        return
    digest = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            digest.update(chunk)
    if digest.hexdigest() != expected.split(":", 1)[1]:
        raise RuntimeError("downloaded asset failed SHA-256 verification")


def update_mod(game_dir: str, owner: str, repo: str, entry_dll: str) -> str:
    """Download exactly the named release DLL into BepInEx/plugins/."""
    try:
        entry_dll = safe_basename(entry_dll, "entry_dll")
    except UnsafePathError as exc:
        raise ValueError(str(exc)) from exc
    if not entry_dll.lower().endswith(".dll"):
        raise ValueError("entry_dll must be a .dll filename")
    rel = latest_release(owner, repo)
    if not rel.get("assets"):
        raise RuntimeError(f"repo {owner}/{repo} has no release assets to download")
    match = None
    for a in rel["assets"]:
        if a.get("name", "").lower() == entry_dll.lower():
            match = a
            break
    if match is None:
        raise RuntimeError(f"asset {entry_dll!r} not found in latest release of {owner}/{repo}")

    plugins = os.path.join(game_dir, "BepInEx", "plugins")
    os.makedirs(plugins, exist_ok=True)
    dest = safe_join(plugins, entry_dll)
    backups = rollback.backup_files(game_dir, [dest])
    fd, temp_path = tempfile.mkstemp(prefix=entry_dll + ".", suffix=".part", dir=plugins)
    os.close(fd)
    try:
        urllib.request.urlretrieve(match["browser_download_url"], temp_path)
        _verify_digest(temp_path, match.get("digest"))
        os.replace(temp_path, dest)
    finally:
        if os.path.exists(temp_path):
            os.unlink(temp_path)
    added = [dest] if dest not in backups else []
    rollback.record_install(game_dir, entry_dll, added, backups)
    return dest
