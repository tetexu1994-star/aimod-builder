"""Environment diagnostics and readiness inspector (agmod doctor).

Evaluates the workstation's modding readiness:
- Python environment and memory manipulation support
- .NET SDK (for building BepInEx / tModLoader mods)
- Decompilation tools (ilspycmd, Cpp2IL)
- Reverse-engineering bridge (morluto/rea CLI)
- Cache directories and disk permissions
"""
from __future__ import annotations

import os
import platform
import shutil
import subprocess
import sys
from dataclasses import asdict, dataclass

from .config import CACHE_ROOT
from .rea import _find_rea


@dataclass
class ToolCheck:
    name: str
    category: str
    status: str  # "ok", "missing", "optional_missing"
    version: str
    path: str
    remedy: str

    def to_dict(self) -> dict:
        return asdict(self)


def check_environment() -> dict:
    """Run full environment diagnostics and return structured status report."""
    checks: list[ToolCheck] = []
    actions_needed: list[str] = []

    # 1. Python & OS
    is_win = sys.platform == "win32"
    mem_support = "Full (ctypes Windows API)" if is_win else "Partial (Linux/macOS development mode; live memory is Windows-only)"
    checks.append(
        ToolCheck(
            name="Python",
            category="runtime",
            status="ok",
            version=platform.python_version(),
            path=sys.executable,
            remedy="",
        )
    )
    checks.append(
        ToolCheck(
            name="Memory Engine",
            category="runtime",
            status="ok" if is_win else "warn",
            version=platform.system(),
            path=mem_support,
            remedy="Run game-mod-agent on Windows to perform live memory scanning/injection" if not is_win else "",
        )
    )

    # 2. .NET SDK
    dotnet = shutil.which("dotnet")
    dotnet_ver = ""
    if dotnet:
        try:
            r = subprocess.run([dotnet, "--version"], capture_output=True, text=True, timeout=5, check=False)
            dotnet_ver = (r.stdout or "").strip()
        except Exception:
            pass
    if dotnet and dotnet_ver:
        checks.append(
            ToolCheck(
                name=".NET SDK (dotnet)",
                category="compiler",
                status="ok",
                version=dotnet_ver,
                path=dotnet,
                remedy="",
            )
        )
    else:
        checks.append(
            ToolCheck(
                name=".NET SDK (dotnet)",
                category="compiler",
                status="missing",
                version="",
                path="NOT FOUND",
                remedy="Install .NET SDK (https://dotnet.microsoft.com/download) to build Unity C# and tModLoader mods",
            )
        )
        actions_needed.append("Install .NET 6/8 SDK: https://dotnet.microsoft.com/download")

    # 3. REA CLI (morluto/rea)
    rea_bin = _find_rea()
    if rea_bin:
        rea_version = "installed"
        rea_status = "ok"
        rea_remedy = ""
        try:
            rea_check = subprocess.run([rea_bin, "--version"], capture_output=True, text=True, timeout=5, check=False)
            if rea_check.returncode != 0:
                rea_status = "warn"
                rea_remedy = "REA binary exists but failed its version check"
            else:
                rea_version = (rea_check.stdout or rea_check.stderr or "installed").strip()[:120]
        except Exception as exc:
            rea_status = "warn"
            rea_remedy = f"REA binary exists but could not be executed: {exc}"
        checks.append(
            ToolCheck(
                name="REA (morluto/rea)",
                category="reverse_engineering",
                status=rea_status,
                version=rea_version,
                path=rea_bin,
                remedy=rea_remedy,
            )
        )
    else:
        checks.append(
            ToolCheck(
                name="REA (morluto/rea)",
                category="reverse_engineering",
                status="optional_missing",
                version="",
                path="NOT FOUND",
                remedy="npm install -g rea-agents (enables native disassembly and call graph analysis)",
            )
        )
        actions_needed.append("npm install -g rea-agents")

    # 4. ilspycmd
    ilspy = shutil.which("ilspycmd")
    if ilspy:
        checks.append(
            ToolCheck(
                name="ilspycmd",
                category="decompiler",
                status="ok",
                version="installed",
                path=ilspy,
                remedy="",
            )
        )
    else:
        checks.append(
            ToolCheck(
                name="ilspycmd",
                category="decompiler",
                status="optional_missing",
                version="",
                path="NOT FOUND",
                remedy="dotnet tool install -g ilspycmd (enables Unity Mono structure recovery)",
            )
        )
        actions_needed.append("dotnet tool install -g ilspycmd")

    # 5. Cpp2IL / Il2CppDumper
    cpp2il = shutil.which("Cpp2IL")
    if cpp2il:
        checks.append(
            ToolCheck(
                name="IL2CPP Dumper",
                category="decompiler",
                status="ok",
                version="installed",
                path=cpp2il,
                remedy="",
            )
        )
    else:
        checks.append(
            ToolCheck(
                name="IL2CPP Dumper",
                category="decompiler",
                status="optional_missing",
                version="",
                path="NOT FOUND",
                remedy="Install Cpp2IL on PATH; the current Unity adapter invokes Cpp2IL directly",
            )
        )

    # 6. Cache Directory
    cache_error = ""
    try:
        os.makedirs(CACHE_ROOT, exist_ok=True)
        cache_writable = os.access(CACHE_ROOT, os.W_OK)
    except OSError as exc:
        cache_writable = False
        cache_error = str(exc)
    checks.append(
        ToolCheck(
            name="Cache & Backups Root",
            category="storage",
            status="ok" if cache_writable else "error",
            version="",
            path=os.path.abspath(CACHE_ROOT),
            remedy=(cache_error or "Ensure write permissions on CACHE_ROOT") if not cache_writable else "",
        )
    )

    all_ok = all(c.status in ("ok", "optional_missing", "warn") for c in checks)
    return {
        "ready": all_ok,
        "platform": platform.platform(),
        "checks": [c.to_dict() for c in checks],
        "actions_recommended": actions_needed,
    }


def format_doctor_report(report: dict) -> str:
    """Format the report into clean terminal/markdown output."""
    lines = ["# 🩺 game-mod-agent Environment Doctor Report\n"]
    lines.append(f"**Platform**: {report['platform']}")
    lines.append(f"**Overall Readiness**: {'✅ Ready for Mod Development' if report['ready'] else '⚠️ Configuration Needed'}\n")
    lines.append("| Component | Category | Status | Path / Detail | Action |")
    lines.append("|:---|:---|:---|:---|:---|")

    symbols = {"ok": "✅ OK", "warn": "⚠️ WARN", "missing": "❌ MISSING", "optional_missing": "ℹ️ OPTIONAL", "error": "❌ ERROR"}
    for c in report["checks"]:
        stat = symbols.get(c["status"], c["status"])
        rem = c["remedy"] or "—"
        lines.append(f"| **{c['name']}** | {c['category']} | {stat} | `{c['path']}` | {rem} |")

    if report["actions_recommended"]:
        lines.append("\n### 🚀 Recommended Setup Commands:")
        for act in report["actions_recommended"]:
            lines.append(f"```bash\n{act}\n```")

    return "\n".join(lines)


if __name__ == "__main__":
    report = check_environment()
    print(format_doctor_report(report))
