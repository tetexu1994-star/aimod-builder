"""Path and archive safety helpers shared by install/package/update paths."""
from __future__ import annotations

import os
import re
import unicodedata
import zipfile


class UnsafePathError(ValueError):
    """Raised when an untrusted name escapes its allowed directory."""


_COMPONENT_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")


def safe_component(value: str, field: str = "name") -> str:
    value = (value or "").strip()
    if not value or value in {".", ".."} or "/" in value or "\\" in value or "\x00" in value:
        raise UnsafePathError(f"unsafe {field}: {value!r}")
    if not _COMPONENT_RE.fullmatch(value):
        raise UnsafePathError(f"unsafe {field}: {value!r}")
    return value


def slugify(value: str, fallback: str = "item") -> str:
    """Turn an arbitrary name into a safe filesystem identifier (ASCII, no spaces).

    Used for derived identifiers like a game-directory basename, where we want
    a usable key rather than rejecting names with spaces or non-ASCII chars.
    """
    value = unicodedata.normalize("NFKD", str(value or "")).encode("ascii", "ignore").decode()
    value = re.sub(r"[^A-Za-z0-9]+", "-", value).strip("-").lower()
    return value or fallback


def safe_basename(value: str, field: str = "file") -> str:
    value = (value or "").strip()
    if not value or "/" in value or "\\" in value or "\x00" in value:
        raise UnsafePathError(f"unsafe {field}: {value!r}")
    if value in {".", ".."} or os.path.basename(value) != value:
        raise UnsafePathError(f"unsafe {field}: {value!r}")
    return value


def safe_join(base_dir: str, *parts: str) -> str:
    for part in parts:
        normalized = str(part).replace("\\", "/")
        if not normalized or normalized.startswith("/") or ".." in normalized.split("/") or "\x00" in str(part):
            raise UnsafePathError(f"path escapes {base_dir}: {os.path.join(*parts)!r}")
    base = os.path.abspath(base_dir)
    candidate = os.path.abspath(os.path.join(base, *parts))
    try:
        contained = os.path.commonpath([base, candidate]) == base
    except ValueError:
        contained = False
    if not contained:
        raise UnsafePathError(f"path escapes {base_dir}: {os.path.join(*parts)!r}")
    return candidate


def safe_extract_zip(archive: str | zipfile.ZipFile, destination: str) -> None:
    zf = archive if isinstance(archive, zipfile.ZipFile) else zipfile.ZipFile(archive)
    close = not isinstance(archive, zipfile.ZipFile)
    try:
        for info in zf.infolist():
            name = info.filename
            if not name or name.startswith(("/", "\\")) or "\x00" in name:
                raise UnsafePathError(f"unsafe zip member: {name!r}")
            if os.path.isabs(name) or ".." in name.replace("\\", "/").split("/"):
                raise UnsafePathError(f"unsafe zip member: {name!r}")
            safe_join(destination, name)
        zf.extractall(destination)
    finally:
        if close:
            zf.close()
