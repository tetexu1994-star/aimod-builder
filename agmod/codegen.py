"""Reverse-engineering symbol to mod hook code generator."""
from __future__ import annotations

import re

from .evidence import HookTarget


def _sanitize_ident(ident: str) -> str:
    s = re.sub(r"[^A-Za-z0-9_]+", "_", ident.strip()).strip("_")
    return s or "Target"


def _lua_string(value: str) -> str:
    return str(value).replace("\\", "\\\\").replace('"', '\\"').replace("\n", " ")


def _validation(code: str, target: HookTarget, language: str) -> dict:
    checks = {
        "contains_target_class": target.class_name in code,
        "contains_target_method": target.method_name in code,
        "balanced_delimiters": code.count("{") == code.count("}") if language == "csharp" else True,
    }
    if language == "lua":
        checks["balanced_function_end"] = len(re.findall(r"\bfunction\b", code)) <= len(re.findall(r"\bend\b", code))
    return {"valid": all(checks.values()), "checks": checks, "language": language}


def _result(target: HookTarget, language: str, framework: str, code: str, instructions: str) -> dict:
    return {
        "engine": target.engine,
        "language": language,
        "framework": framework,
        "code": code,
        "instructions": instructions,
        "target": target.to_dict(),
        "evidence": {
            "source": target.evidence_source,
            "status": target.evidence_status,
            "verified": target.verified,
            "confidence": target.confidence,
            "signature": target.signature,
            "overload_key": target.overload_key,
        },
        "validation": _validation(code, target, language),
    }


def generate_hook_from_evidence(evidence: dict) -> dict:
    """Generate engine code from a normalized REA/dump symbol evidence object."""
    target = HookTarget.from_dict(evidence)
    cls_clean = _sanitize_ident(target.class_name)
    mth_clean = _sanitize_ident(target.method_name)
    params = target.parameters

    if target.engine == "unity":
        param_sigs = [f"{p.get('type', 'object')} {p.get('name', f'arg{i + 1}')}" for i, p in enumerate(params)]
        instance_param = [] if target.is_static else [f"{cls_clean} __instance"]
        prefix_params = instance_param + param_sigs
        postfix_params = instance_param + param_sigs
        if target.return_type.lower() not in ("void", ""):
            postfix_params.append(f"ref {target.return_type} __result")
        code = f'''using HarmonyLib;

[HarmonyPatch(typeof({target.full_class_name}), "{mth_clean}")]
public static class {cls_clean}_{mth_clean}_Patch
{{
'''
        if target.hook_type in ("prefix", "both"):
            code += f'''    [HarmonyPrefix]
    public static bool Prefix({", ".join(prefix_params)})
    {{
        // Inspect or modify parameters before the original method.
        return true;
    }}
'''
        if target.hook_type in ("postfix", "both"):
            code += f'''    [HarmonyPostfix]
    public static void Postfix({", ".join(postfix_params)})
    {{
        // Inspect or override __result after the original method.
    }}
'''
        code += "}\n"
        return _result(target, "csharp", "Harmony", code, "Add this patch to a BepInEx plugin and call Harmony.PatchAll().")

    if target.engine == "unreal":
        lua_params = ["self"] + [p.get("name", f"param{i + 1}") for i, p in enumerate(params)]
        hook_path = f"{target.full_class_name}:{mth_clean}"
        code = f'''-- UE4SS Hook for {hook_path}
RegisterHook("{_lua_string(hook_path)}", function({", ".join(lua_params)})
    local obj = self:get()
    -- Access parameters through UE4SS RemoteUnrealParam objects.
'''
        for i, p in enumerate(params, 1):
            p_name = p.get("name", f"param{i}")
            safe_name = _sanitize_ident(p_name)
            code += f'    -- local value_{safe_name} = {p_name}:get()\n'
        code += 'end)\n'
        return _result(target, "lua", "UE4SS", code, "Place this hook in the UE4SS mod scripts/main.lua file.")

    if target.engine == "re-engine":
        code = f'''-- REFramework Hook for {target.full_class_name}.{mth_clean}
local typedef = sdk.find_type_definition("{_lua_string(target.full_class_name)}")
if typedef then
    local method = typedef:get_method("{_lua_string(mth_clean)}")
    if method then
        sdk.hook(method, function(args)
            -- args[1] is the target instance; later indexes are method arguments.
        end, function(retval)
            return retval
        end)
    end
end
'''
        return _result(target, "lua", "REFramework", code, "Place this hook in an REFramework autorun Lua file.")

    if target.engine == "godot":
        code = f'''# Godot hook helper for {target.full_class_name}.{mth_clean}
func hook_{cls_clean.lower()}_{mth_clean.lower()}(target_node: Node) -> void:
    if target_node != null and target_node.has_method("{_lua_string(mth_clean)}"):
        print("[GodotMod] Hooking {target.full_class_name}.{mth_clean}")
'''
        return _result(target, "gdscript", "GodotModLoader", code, "Call this helper from the GodotModLoader mod_main.gd lifecycle.")

    if target.engine in {"dotnet-xna", "dotnet", "tmodloader", "smapi"}:
        code = f'''using System;

namespace AIModPlugin
{{
    // Hook target: {target.full_class_name}.{mth_clean}
    public static class Patch_{cls_clean}_{mth_clean}
    {{
        public static void Postfix()
        {{
            // Execute custom game logic hook
        }}
    }}
}}
'''
        return _result(target, "csharp", "tModLoader/SMAPI", code, "Compile this C# hook class into your plugin assembly.")

    if target.engine in {"redengine", "cyberpunk"}:
        code = f'''-- Cyber Engine Tweaks (CET) Hook for {target.full_class_name}.{mth_clean}
Override("{_lua_string(target.full_class_name)}", "{_lua_string(mth_clean)}", function(this, wrappedMethod)
    -- Pre-hook execution
    wrappedMethod()
    -- Post-hook execution
end)
'''
        return _result(target, "lua", "CET", code, "Place this Lua hook in your CET init.lua mod script.")

    if target.engine == "taleworlds":
        code = f'''using HarmonyLib;
using TaleWorlds.Core;

namespace BannerlordMod
{{
    [HarmonyPatch(typeof({target.full_class_name}), "{mth_clean}")]
    public static class Patch_{cls_clean}_{mth_clean}
    {{
        public static void Postfix()
        {{
            // Mod behavior logic
        }}
    }}
}}
'''
        return _result(target, "csharp", "Bannerlord Harmony", code, "Include this Harmony patch in your Bannerlord SubModule.")

    if target.engine == "bethesda":
        code = f'''; Papyrus Script Hook for {target.full_class_name}.{mth_clean}
ScriptName {cls_clean}_{mth_clean}_Hook Extends Quest

Event OnInit()
    ; Register for custom game events or hook functions
EndEvent
'''
        return _result(target, "papyrus", "Papyrus/SKSE", code, "Attach this Papyrus script to an ESP quest or compile with Creation Kit.")

    raise ValueError(f"unsupported engine '{target.engine}'")


def generate_hook_template(
    engine: str,
    class_name: str,
    method_name: str,
    hook_type: str = "prefix",
    return_type: str = "void",
    parameters: list[dict] | None = None,
    namespace: str = "",
    signature: str = "",
    overload_key: str = "",
    is_static: bool = False,
    evidence_source: str = "",
    confidence: float = 1.0,
) -> dict:
    """Backward-compatible wrapper around evidence-based generation."""
    return generate_hook_from_evidence({
        "engine": engine,
        "target": {
            "class_name": class_name,
            "method_name": method_name,
            "hook_type": hook_type,
            "return_type": return_type,
            "parameters": parameters or [],
            "namespace": namespace,
            "signature": signature,
            "overload_key": overload_key,
            "is_static": is_static,
        },
        "evidence": {"source": evidence_source, "confidence": confidence},
    })
