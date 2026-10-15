"""Safety guardrails enforced in code, not just in the agent prompt.

Refuses to attach/scan/write to known anti-cheat processes, and can list active
anti-cheat services so the agent can warn the user before doing anything.
"""
from __future__ import annotations

try:
    import psutil
except ImportError:  # pragma: no cover
    psutil = None

# Known anti-cheat service executables. Keep the list conservative: these are
# the processes whose very presence means the game is protected.
BLOCKED = {
    "easyanticheat.exe",
    "easyanticheat_eos.exe",
    "beservice.exe",
    "beservice_x64.exe",
    "battleye.exe",
    "vgc.exe",                 # Riot Vanguard
    "vgtray.exe",
    "faceitservice.exe",
    "faceitclient.exe",
    "mrac.exe",
    "equ8.exe",
    "fisecurityservice.exe",
    "nprotect game monitor.exe",
}


def is_blocked_name(name: str) -> bool:
    return name.strip().lower() in BLOCKED


def process_name(pid: int) -> str:
    if psutil is None:
        return ""
    try:
        return psutil.Process(pid).name() or ""
    except Exception:
        return ""


def check_target(pid: int) -> tuple[bool, str]:
    """Return (allowed, reason), failing closed for unknown/protected targets."""
    if not isinstance(pid, int) or pid <= 0:
        return False, "pid must be a positive integer"
    if psutil is None:
        return False, "psutil is required before process memory access"
    name = process_name(pid)
    if not name:
        return False, f"process {pid} is not running or cannot be inspected"
    if is_blocked_name(name):
        return False, f"target process '{name}' is anti-cheat; refusing to touch it"
    active = active_anticheat()
    if active:
        return False, "anti-cheat service is active: " + ", ".join(active)
    return True, ""


def check_game_target(game_dir: str) -> tuple[bool, str]:
    """Refuse work on game directories while a known anti-cheat is active."""
    active = active_anticheat()
    if active:
        return False, "anti-cheat service is active: " + ", ".join(active)
    return True, ""


def active_anticheat() -> list[str]:
    """Names of any currently-running known anti-cheat services."""
    if psutil is None:
        return []
    out = set()
    for p in psutil.process_iter(["name"]):
        try:
            n = (p.info.get("name") or "").lower()
        except Exception:
            continue
        if n in BLOCKED:
            out.add(p.info["name"])
    return sorted(out)
