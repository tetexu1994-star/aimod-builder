"""C# and compiler error diagnostics with automated self-healing heuristics.

Parses MSBuild/dotnet compile outputs, extracts specific CSxxxx error codes with
file and line locations, and provides targeted auto-repair heuristics (e.g. injecting
missing `using UnityEngine;` or `using HarmonyLib;`).
"""
from __future__ import annotations

import os
import re
from dataclasses import asdict, dataclass

_DOTNET_ERROR_RE = re.compile(
    r"^(?P<file>[^\r\n\(]+)\((?P<line>\d+),(?P<col>\d+)\):\s+(?P<severity>error|warning)\s+(?P<code>CS\d+):\s+(?P<msg>[^\r\n]+)",
    re.MULTILINE,
)

# Common namespace suggestions for CS0246 (type or namespace not found)
_TYPE_TO_USING = {
    "GameObject": "using UnityEngine;",
    "Transform": "using UnityEngine;",
    "Vector3": "using UnityEngine;",
    "Vector2": "using UnityEngine;",
    "Mathf": "using UnityEngine;",
    "Component": "using UnityEngine;",
    "MonoBehaviour": "using UnityEngine;",
    "HarmonyPatch": "using HarmonyLib;",
    "HarmonyPrefix": "using HarmonyLib;",
    "HarmonyPostfix": "using HarmonyLib;",
    "HarmonyTranspiler": "using HarmonyLib;",
    "HarmonyMethod": "using HarmonyLib;",
    "List": "using System.Collections.Generic;",
    "Dictionary": "using System.Collections.Generic;",
    "HashSet": "using System.Collections.Generic;",
    "Action": "using System;",
    "Func": "using System;",
    "Exception": "using System;",
    "BindingFlags": "using System.Reflection;",
    "MethodInfo": "using System.Reflection;",
    "FieldInfo": "using System.Reflection;",
}


@dataclass
class CompileError:
    file: str
    code: str
    message: str
    severity: str
    line: int = 0
    column: int = 0

    def to_dict(self) -> dict:
        return asdict(self)


def parse_dotnet_errors(compiler_output: str) -> list[CompileError]:
    """Parse compiler stdout/stderr into structured CompileError objects."""
    results: list[CompileError] = []
    for match in _DOTNET_ERROR_RE.finditer(compiler_output):
        results.append(
            CompileError(
                file=os.path.basename(match.group("file").strip()),
                line=int(match.group("line")),
                column=int(match.group("col")),
                code=match.group("code"),
                message=match.group("msg").strip(),
                severity=match.group("severity"),
            )
        )
    generic = re.compile(
        r"^(?P<prefix>.*?)(?:\s:\s|\s+)(?P<severity>error|warning)\s+(?P<code>[A-Z]{2,10}\d{2,6}):\s*(?P<msg>[^\r\n]+)",
        re.MULTILINE,
    )
    known = {(e.file, e.code, e.line, e.column) for e in results}
    for match in generic.finditer(compiler_output):
        if match.group("code").startswith("CS"):
            continue
        prefix = match.group("prefix").strip()
        file_name = os.path.basename(prefix) if prefix else "build"
        item = CompileError(
            file=file_name,
            code=match.group("code"),
            message=match.group("msg").strip(),
            severity=match.group("severity"),
        )
        key = (item.file, item.code, item.line, item.column)
        if key not in known:
            results.append(item)
            known.add(key)
    bare = re.compile(r"^(?P<code>[A-Z]{2,10}\d{2,6}):\s*(?P<msg>[^\r\n]+)", re.MULTILINE)
    for match in bare.finditer(compiler_output):
        if match.group("code").startswith("CS"):
            continue
        item = CompileError(
            file="build",
            code=match.group("code"),
            message=match.group("msg").strip(),
            severity="error",
        )
        key = (item.file, item.code, item.line, item.column)
        if key not in known:
            results.append(item)
            known.add(key)
    return results


def suggest_fixes(errors: list[CompileError]) -> list[str]:
    """Generate high-probability fix suggestions based on error codes."""
    suggestions: list[str] = []
    for err in errors:
        if err.severity != "error":
            continue

        if err.code == "CS0246":  # Type or namespace not found
            for type_name, using_stmt in _TYPE_TO_USING.items():
                if re.search(rf"(?<![A-Za-z0-9_]){re.escape(type_name)}(?![A-Za-z0-9_])", err.message):
                    suggestion = f"{err.file}:{err.line} Missing namespace: add `{using_stmt}` at top of file"
                    if suggestion not in suggestions:
                        suggestions.append(suggestion)

        elif err.code == "CS1002":  # ; expected
            suggestions.append(f"{err.file}:{err.line} Semicolon missing: add `;` at end of statement")

        elif err.code == "CS1513":  # } expected
            suggestions.append(f"{err.file}:{err.line} Closing brace missing: check matching `}}` for class/method")

        elif err.code == "CS0103":  # Name does not exist in current context
            suggestions.append(f"{err.file}:{err.line} Identifier {err.message}: check variable name, scope, or class member")

        elif err.code == "CS0117":  # Does not contain a definition
            suggestions.append(f"{err.file}:{err.line} Member not found: check API spelling or game version differences")
        elif err.code.startswith("NETSDK"):
            suggestions.append(f"{err.file}: Restore/build prerequisites first ({err.code}: {err.message})")
        elif err.code.startswith("MSB"):
            suggestions.append(f"{err.file}: Check project path/tooling ({err.code}: {err.message})")
        elif err.code.startswith("NU"):
            suggestions.append(f"{err.file}: Restore NuGet dependencies ({err.code}: {err.message})")

    return suggestions


def diagnose_build_output(output: str, return_code: int | None = None) -> dict:
    """Analyze compiler output and return a structured diagnostic report."""
    all_hits = parse_dotnet_errors(output)
    errors = [e for e in all_hits if e.severity == "error"]
    warnings = [e for e in all_hits if e.severity == "warning"]
    fixes = suggest_fixes(errors)

    if return_code not in (None, 0) and not errors:
        detail = next((line.strip() for line in output.splitlines() if line.strip()), "unknown build failure")
        errors = [CompileError(file="build", code="BUILD_FAILED", message=detail, severity="error")]
        fixes = suggest_fixes(errors)
    summary = "Build succeeded with no errors"
    if errors or return_code not in (None, 0):
        if not errors:
            errors = [CompileError(file="build", code="BUILD_FAILED", message="Build failed without a recognized compiler diagnostic", severity="error")]
            fixes = suggest_fixes(errors)
        summary = f"Build failed with {len(errors)} error(s): " + ", ".join(
            f"{e.code} in {e.file}:{e.line}" for e in errors[:3]
        )

    return {
        "has_errors": bool(errors),
        "error_count": len(errors),
        "warning_count": len(warnings),
        "errors": [e.to_dict() for e in errors],
        "warnings": [w.to_dict() for w in warnings[:5]],
        "suggested_fixes": fixes,
        "summary": summary,
    }


def auto_heal_csharp_source(source_code: str, errors: list[CompileError]) -> tuple[str, list[str]]:
    """Apply safe automated fixes (like missing using statements) to C# source code."""
    applied: list[str] = []
    lines = source_code.splitlines()

    # Collect missing using statements
    missing_usings: set[str] = set()
    for err in errors:
        if err.code == "CS0246":
            for type_name, using_stmt in _TYPE_TO_USING.items():
                if re.search(rf"(?<![A-Za-z0-9_]){re.escape(type_name)}(?![A-Za-z0-9_])", err.message) and using_stmt not in source_code:
                    missing_usings.add(using_stmt)

    if missing_usings:
        # Find where usings are declared or insert at beginning
        insert_idx = 0
        for i, line in enumerate(lines):
            if line.strip().startswith("using "):
                insert_idx = i + 1

        for u in sorted(missing_usings):
            lines.insert(insert_idx, u)
            applied.append(f"Injected `{u}`")
            insert_idx += 1

    result = "\n".join(lines)
    if source_code.endswith(("\n", "\r\n")):
        result += "\n"
    return result, applied
