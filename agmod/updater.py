"""GitHub release/commit polling + mod auto-update.

When the mod's GitHub repo updates, the client can detect it (check) and pull
the new plugin DLL (update). Uses only stdlib (urllib), no third-party deps.
"""
from __future__ import annotations

import json
import os
import shutil
import urllib.error
import urllib.request

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
            "update_available": latest != current_version,
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


def update_mod(game_dir: str, owner: str, repo: str, entry_dll: str) -> str:
    """Download the latest release asset matching `entry_dll` into BepInEx/plugins/."""
    rel = latest_release(owner, repo)
    if not rel.get("assets"):
        raise RuntimeError(f"repo {owner}/{repo} has no release assets to download")
    match = None
    for a in rel["assets"]:
        if a["name"].lower() == entry_dll.lower() or a["name"].lower().endswith(".dll"):
            match = a
            break
    if match is None:
        raise RuntimeError(f"no .dll asset found in latest release of {owner}/{repo}")

    plugins = os.path.join(game_dir, "BepInEx", "plugins")
    os.makedirs(plugins, exist_ok=True)
    dest = os.path.join(plugins, entry_dll)
    urllib.request.urlretrieve(match["browser_download_url"], dest)
    return dest
