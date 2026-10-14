"""Reverse-engineering symbol to mod hook code generator.

Transforms recovered class/method/parameter symbols into syntactically correct,
engine-tailored hook templates for Unity (Harmony), Unreal (UE4SS Lua),
Capcom RE Engine (REFramework Lua), and Godot (GDScript).
"""
from __future__ import annotations

import re


def _sanitize_ident(ident: str) -> str:
    s = re.sub(r"[^A-Za-z0-9_]+", "_", ident.strip()).strip("_")
    return s or "Target"


def generate_hook_template(
    engine: str,
    class_name: str,
    method_name: str,
    hook_type: str = "prefix",
    return_type: str = "void",
    parameters: list[dict] | None = None,
) -> dict:
    """Generate engine-specific hook snippet from reverse engineered symbol info.

    Args:
        engine: "unity", "unreal", "re-engine", or "godot"
        class_name: Target class / type name (e.g. "PlayerController")
        method_name: Target method / function name (e.g. "AddMoney")
        hook_type: "prefix", "postfix", or "both"
        return_type: Return type string (e.g. "void", "bool", "int32")
        parameters: List of {"type": "int", "name": "amount"} dicts

    Returns:
        dict with {"engine": str, "language": str, "code": str, "instructions": str}
    """
    engine_norm = (engine or "").lower().strip()
    cls_clean = _sanitize_ident(class_name or "TargetClass")
    mth_clean = _sanitize_ident(method_name or "TargetMethod")
    params = parameters or []

    if engine_norm == "unity":
        # Generate C# Harmony Patch
        param_sigs = [f"ref {p.get('type', 'object')} {p.get('name', 'arg' + str(i))}" for i, p in enumerate(params)]
        prefix_params = [f"{cls_clean} __instance"] + param_sigs
        postfix_params = [f"{cls_clean} __instance"] + [f"{p.get('type', 'object')} {p.get('name', 'arg' + str(i))}" for i, p in enumerate(params)]
        if return_type.lower() not in ("void", ""):
            postfix_params.append(f"ref {return_type} __result")

        code = f'''using HarmonyLib;

[HarmonyPatch(typeof({cls_clean}), "{mth_clean}")]
public static class {cls_clean}_{mth_clean}_Patch
{{
'''
        if hook_type in ("prefix", "both"):
            code += f'''    [HarmonyPrefix]
    public static bool Prefix({", ".join(prefix_params)})
    {{
        // Pre-hook logic: inspect or modify parameters.
        // Return true to continue original method, false to skip it.
        return true;
    }}
'''
        if hook_type in ("postfix", "both"):
            code += f'''    [HarmonyPostfix]
    public static void Postfix({", ".join(postfix_params)})
    {{
        // Post-hook logic: inspect or override return value (__result).
    }}
'''
        code += "}\n"
        return {
            "engine": "unity",
            "language": "csharp",
            "framework": "Harmony",
            "code": code,
            "instructions": f"Add this class into your BepInEx Plugin.cs or patches directory; Harmony will automatically discover it on Harmony.PatchAll().",
        }

    elif engine_norm in ("unreal", "ue4", "ue5"):
        # Generate UE4SS Lua RegisterHook
        lua_params = ["self"] + [p.get("name", f"param{i+1}") for i, p in enumerate(params)]
        hook_path = f"/Script/{cls_clean}:{mth_clean}"
        code = f'''-- UE4SS Hook for {cls_clean}:{mth_clean}
RegisterHook("{hook_path}", function({", ".join(lua_params)})
    local obj = self:get()
    -- Pre-hook callback: parameters are accessible as UE4SS RemoteUnrealParam objects
'''
        for p in params:
            pn = p.get("name", "param")
            code += f'    -- local val_{pn} = {pn}:get()\n'
        code += f'''    print("[UE4SS] Executed hook for {cls_clean}:{mth_clean}")
end)
'''
        return {
            "engine": "unreal",
            "language": "lua",
            "framework": "UE4SS",
            "code": code,
            "instructions": f"Place this hook inside your scripts/main.lua within the UE4SS mod directory.",
        }

    elif engine_norm in ("re-engine", "reengine", "capcom"):
        # Generate REFramework sdk.hook Lua code
        code = f'''-- REFramework Hook for {cls_clean}.{mth_clean}
local typedef = sdk.find_type_definition("{cls_clean}")
if typedef then
    local method = typedef:get_method("{mth_clean}")
    if method then
        sdk.hook(method, function(args)
            -- Pre-hook: args[1] is this pointer (native object)
            -- args[2] is the first parameter, etc.
'''
        for i, p in enumerate(params):
            pn = p.get("name", f"param{i+1}")
            code += f'            -- local arg_{pn} = args[{i+2}]\n'
        code += f'''        end, function(retval)
            -- Post-hook: inspect or override return value
            return retval
        end)
    else
        print("[REFramework] Method '{mth_clean}' not found on type '{cls_clean}'")
    end
else
    print("[REFramework] Type '{cls_clean}' not found")
end
'''
        return {
            "engine": "re-engine",
            "language": "lua",
            "framework": "REFramework",
            "code": code,
            "instructions": f"Paste into autorun/<mod_id>.lua. REFramework executes this script automatically at game startup.",
        }

    elif engine_norm == "godot":
        # Generate GodotModLoader GDScript hook
        code = f'''# Godot Hook / Wrapper for {cls_clean}.{mth_clean}
func hook_{cls_clean.lower()}_{mth_clean.lower()}(target_node: Node) -> void:
    if target_node and target_node.has_method("{mth_clean}"):
        print("[GodotMod] Hooking {cls_clean}.{mth_clean} on: ", target_node.name)
        # Register signal, scene hook, or call overrides here
'''
        return {
            "engine": "godot",
            "language": "gdscript",
            "framework": "GodotModLoader",
            "code": code,
            "instructions": f"Call this helper from mod_main.gd _ready() or when target scenes enter the SceneTree.",
        }

    else:
        raise ValueError(f"unsupported engine '{engine}'; supported: unity, unreal, re-engine, godot")
