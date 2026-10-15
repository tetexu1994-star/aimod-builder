"""BepInEx: install the Unity mod-loader prerequisite and scaffold/build plugin mods.

BepInEx is the "前置" (prerequisite) mod loader for Unity games. A mod is a
BepInEx plugin DLL dropped into `BepInEx/plugins/` that patches the game with
Harmony. This module:
  1. installs BepInEx into a game directory,
  2. scaffolds a plugin C# project,
  3. builds it with `dotnet build` and installs the DLL.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
import urllib.request
import zipfile

from . import rollback
from .manifest import ModManifest
from .paths import safe_component, safe_extract_zip

BEPINEX_VERSION = "5.4.23.5"
_BASE_URL = "https://github.com/BepInEx/BepInEx/releases/download"


def _find_bundled_zip() -> str | None:
    pkg_dir = os.path.dirname(os.path.abspath(__file__))
    res_dir = os.path.join(pkg_dir, "resources", "bepinex")
    if os.path.isdir(res_dir):
        for f in sorted(os.listdir(res_dir), reverse=True):
            if f.startswith("BepInEx") and f.endswith(".zip"):
                candidate = os.path.join(res_dir, f)
                if os.path.isfile(candidate):
                    return candidate
    return None


def install_bepinex(game_dir: str, version: str = BEPINEX_VERSION, allow_running: bool = False) -> str:
    """Extract bundled BepInEx or download into `game_dir`. Returns the BepInEx dir path."""
    running, processes = rollback.is_game_running(game_dir)
    if running and not allow_running:
        raise RuntimeError(f"game is running; close it before installing BepInEx: {processes}")
    bepin = os.path.join(game_dir, "BepInEx")
    if os.path.isdir(os.path.join(bepin, "core")) and os.path.isdir(os.path.join(bepin, "plugins")):
        return "already-installed:" + bepin

    bundled_zip = _find_bundled_zip()
    should_remove_zip = False
    if bundled_zip:
        zip_path = bundled_zip
    else:
        url = f"{_BASE_URL}/v{version}/BepInEx_win_x64_{version}.zip"
        zip_path = os.path.join(game_dir, "_bepinex_tmp.zip")
        urllib.request.urlretrieve(url, zip_path)
        should_remove_zip = True

    try:
        staging = tempfile.mkdtemp(prefix=".bepinex-stage-", dir=game_dir)
        try:
            safe_extract_zip(zip_path, staging)
            pairs = []
            for root, _, files in os.walk(staging):
                for fn in files:
                    src = os.path.join(root, fn)
                    rel = os.path.relpath(src, staging)
                    pairs.append((src, os.path.join(game_dir, rel)))
            rollback.install_files(game_dir, "bepinex", pairs, check_running=False)
        finally:
            shutil.rmtree(staging, ignore_errors=True)
    finally:
        if should_remove_zip and os.path.exists(zip_path):
            os.remove(zip_path)
    return bepin


_PLUGIN_CS = '''using BepInEx;
using HarmonyLib;

namespace {namespace}
{{
    [BepInPlugin(MyPluginInfo.PLUGIN_GUID, MyPluginInfo.PLUGIN_NAME, MyPluginInfo.PLUGIN_VERSION)]
    public class {class_name} : BaseUnityPlugin
    {{
        private void Awake()
        {{
            Harmony.CreateAndPatchAll(typeof({class_name}));
            Logger.LogInfo($"Plugin {{MyPluginInfo.PLUGIN_NAME}} loaded.");
        }}
    }}

    internal static class MyPluginInfo
    {{
        public const string PLUGIN_GUID = "{mod_id}";
        public const string PLUGIN_NAME = "{mod_name}";
        public const string PLUGIN_VERSION = "{mod_version}";
    }}
}}
'''


def _cs_string(value: str) -> str:
    return str(value).replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")

_CSPROJ = '''<Project Sdk="Microsoft.NET.Sdk">
  <PropertyGroup>
    <TargetFramework>net472</TargetFramework>
    <LangVersion>latest</LangVersion>
    <AssemblyName>{mod_id}</AssemblyName>
    <RootNamespace>{namespace}</RootNamespace>
    <EnableDynamicLoading>true</EnableDynamicLoading>
  </PropertyGroup>
  <ItemGroup>
    <PackageReference Include="Microsoft.NETFramework.ReferenceAssemblies" Version="1.0.3" PrivateAssets="all" />
  </ItemGroup>
  <ItemGroup>
    <Reference Include="BepInEx">
      <HintPath>{bepin_core}/BepInEx.dll</HintPath>
      <Private>false</Private>
    </Reference>
    <Reference Include="0Harmony">
      <HintPath>{bepin_core}/0Harmony.dll</HintPath>
      <Private>false</Private>
    </Reference>
  </ItemGroup>
</Project>
'''


def scaffold_plugin(project_dir: str, game_dir: str, mod_id: str, mod_name: str, mod_version: str = "1.0.0", repo: str = "") -> str:
    """Write a BepInEx plugin project (Plugin.cs + .csproj + mod.json) into `project_dir`."""
    mod_id = safe_component(mod_id, "mod_id")
    manifest_name = mod_name
    manifest_version = mod_version
    os.makedirs(project_dir, exist_ok=True)
    namespace = mod_id.replace("-", "_").replace(".", "_")
    class_name = "".join(part.capitalize() for part in mod_id.replace("-", " ").replace(".", " ").split()) or "Plugin"
    bepin_core = os.path.join(game_dir, "BepInEx", "core").replace("\\", "/")

    with open(os.path.join(project_dir, "Plugin.cs"), "w", encoding="utf-8") as f:
        f.write(_PLUGIN_CS.format(
            namespace=namespace, class_name=class_name,
            mod_id=mod_id, mod_name=_cs_string(mod_name), mod_version=_cs_string(mod_version),
        ))
    with open(os.path.join(project_dir, f"{mod_id}.csproj"), "w", encoding="utf-8") as f:
        f.write(_CSPROJ.format(mod_id=mod_id, namespace=namespace, bepin_core=bepin_core))
    ModManifest(id=mod_id, name=manifest_name, version=manifest_version, engine="unity",
                repo=repo, entry=f"{mod_id}.dll").save(os.path.join(project_dir, "mod.json"))
    return project_dir


def build_plugin_with_diagnostics(project_dir: str, game_dir: str, auto_repair: bool = True) -> dict:
    """Build the plugin with automated error parsing and self-healing repair loop."""
    from . import repair

    out_dir = os.path.join(project_dir, "out")
    cmd = ["dotnet", "build", "-c", "Release", "-o", out_dir]
    repairs_applied = []
    plugin_path = os.path.join(project_dir, "Plugin.cs")
    original_source = ""
    repair_backup = ""

    for attempt in range(2 if auto_repair else 1):
        try:
            res = subprocess.run(cmd, capture_output=True, text=True, cwd=project_dir, check=False)
        except FileNotFoundError:
            raise RuntimeError("dotnet not found. Install the .NET SDK (dotnet).") from None

        if res.returncode == 0:
            manifest = ModManifest.load(os.path.join(project_dir, "mod.json"))
            plugins = os.path.join(game_dir, "BepInEx", "plugins")
            os.makedirs(plugins, exist_ok=True)
            targets = []
            if os.path.isdir(out_dir):
                for name in os.listdir(out_dir):
                    if name.endswith(".dll") and (not manifest.entry or name == manifest.entry):
                        targets.append(os.path.join(plugins, name))
            installed = []
            pairs = []
            for t in targets:
                pairs.append((os.path.join(out_dir, os.path.basename(t)), t))
                installed.append(os.path.basename(t))
            if not installed:
                return {
                    "success": False,
                    "error": f"manifest entry not found in build output: {manifest.entry or '*.dll'}",
                    "raw_output": res.stdout,
                }
            rollback.install_files(game_dir, manifest.id, pairs)
            return {
                "success": True,
                "installed": ", ".join(installed),
                "auto_repaired": bool(repairs_applied),
                "repairs": repairs_applied,
            }

        # Build failed: run diagnostics
        combined_output = (res.stdout or "") + "\n" + (res.stderr or "")
        diag = repair.diagnose_build_output(combined_output, return_code=res.returncode)

        if auto_repair and attempt == 0 and diag["errors"]:
            # Try auto-healing Plugin.cs
            if os.path.isfile(plugin_path):
                with open(plugin_path, "r", encoding="utf-8") as f:
                    src = f.read()
                err_objs = [e for e in repair.parse_dotnet_errors(combined_output) if e.file.lower() == "plugin.cs"]
                new_src, applied = repair.auto_heal_csharp_source(src, err_objs)
                if applied:
                    original_source = src
                    repair_backup = plugin_path + ".pre-repair"
                    with open(repair_backup, "w", encoding="utf-8") as f:
                        f.write(src)
                    with open(plugin_path, "w", encoding="utf-8") as f:
                        f.write(new_src)
                    repairs_applied.extend(applied)
                    continue  # Retry build on next attempt

        result = {
            "success": False,
            "error_code": res.returncode,
            "summary": diag["summary"],
            "errors": diag["errors"],
            "suggested_fixes": diag["suggested_fixes"],
            "raw_output": combined_output[:2000],
        }
        if repairs_applied and original_source:
            with open(plugin_path, "w", encoding="utf-8") as f:
                f.write(original_source)
            result["repair_rolled_back"] = True
            result["repair_backup"] = repair_backup
        return result

    return {"success": False, "error": "Build failed after repair attempts"}


def build_plugin(project_dir: str, game_dir: str) -> str:
    """Build the plugin and install the DLL into `game_dir/BepInEx/plugins/`."""
    res = build_plugin_with_diagnostics(project_dir, game_dir)
    if not res.get("success"):
        summary = res.get("summary", res.get("error", "Build failed"))
        fixes = res.get("suggested_fixes", [])
        msg = f"Build failed: {summary}"
        if fixes:
            msg += "\nSuggested fixes:\n" + "\n".join(f"  - {f}" for f in fixes)
        raise RuntimeError(msg)
    return res["installed"]
