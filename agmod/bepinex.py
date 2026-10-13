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
import urllib.request
import zipfile

from .manifest import ModManifest

BEPINEX_VERSION = "5.4.23.0"
_BASE_URL = "https://github.com/BepInEx/BepInEx/releases/download"


def install_bepinex(game_dir: str, version: str = BEPINEX_VERSION) -> str:
    """Download + extract BepInEx into `game_dir`. Returns the BepInEx dir path."""
    bepin = os.path.join(game_dir, "BepInEx")
    if os.path.isdir(os.path.join(bepin, "core")) and os.path.isdir(os.path.join(bepin, "plugins")):
        return "already-installed:" + bepin
    url = f"{_BASE_URL}/v{version}/BepInEx_win_x64_{version}.zip"
    zip_path = os.path.join(game_dir, "_bepinex_tmp.zip")
    urllib.request.urlretrieve(url, zip_path)
    try:
        with zipfile.ZipFile(zip_path) as z:
            z.extractall(game_dir)
    finally:
        if os.path.exists(zip_path):
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
    os.makedirs(project_dir, exist_ok=True)
    namespace = mod_id.replace("-", "_").replace(".", "_")
    class_name = "".join(part.capitalize() for part in mod_id.replace("-", " ").replace(".", " ").split()) or "Plugin"
    bepin_core = os.path.join(game_dir, "BepInEx", "core").replace("\\", "/")

    with open(os.path.join(project_dir, "Plugin.cs"), "w", encoding="utf-8") as f:
        f.write(_PLUGIN_CS.format(
            namespace=namespace, class_name=class_name,
            mod_id=mod_id, mod_name=mod_name, mod_version=mod_version,
        ))
    with open(os.path.join(project_dir, f"{mod_id}.csproj"), "w", encoding="utf-8") as f:
        f.write(_CSPROJ.format(mod_id=mod_id, namespace=namespace, bepin_core=bepin_core))
    ModManifest(id=mod_id, name=mod_name, version=mod_version, engine="unity",
                repo=repo, entry=f"{mod_id}.dll").save(os.path.join(project_dir, "mod.json"))
    return project_dir


def build_plugin(project_dir: str, game_dir: str) -> str:
    """Build the plugin and install the DLL into `game_dir/BepInEx/plugins/`."""
    try:
        subprocess.run(
            ["dotnet", "build", "-c", "Release", "-o", os.path.join(project_dir, "out")],
            check=True, capture_output=True, text=True, cwd=project_dir,
        )
    except FileNotFoundError:
        raise RuntimeError("dotnet not found. Install the .NET SDK (dotnet).") from None

    plugins = os.path.join(game_dir, "BepInEx", "plugins")
    os.makedirs(plugins, exist_ok=True)
    installed = []
    for name in os.listdir(os.path.join(project_dir, "out")):
        if name.endswith(".dll"):
            shutil.copy2(os.path.join(project_dir, "out", name), os.path.join(plugins, name))
            installed.append(name)
    return ", ".join(installed)
