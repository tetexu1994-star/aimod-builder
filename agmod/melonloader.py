"""MelonLoader: Unity IL2CPP (and Mono) mod loader.

BepInEx 5 only loads Mono Unity games. MelonLoader loads IL2CPP Unity titles
(and Mono), so it unlocks the IL2CPP segment BepInEx can't reach. This module
installs MelonLoader into a game directory, scaffolds a MelonMod C# project,
and builds/installs the mod DLL.

MelonLoader IL2CPP mods target .NET 6, so building them requires the .NET SDK
(dotnet); install + scaffold work without it.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
import urllib.request
import zipfile

from . import rollback, sdk
from .manifest import ModManifest
from .paths import safe_component, safe_extract_zip

MELONLOADER_VERSION = os.environ.get("AGMOD_MELONLOADER_VERSION", "v0.7.3")
_MELONLOADER_URL = (
    f"https://github.com/LavaGang/MelonLoader/releases/download/{MELONLOADER_VERSION}/MelonLoader.x64.zip"
)
_HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}

_IL2CPP_MARKERS = ("GameAssembly.dll", "global-metadata.dat")


def is_il2cpp_unity(game_dir: str) -> bool:
    """True if the game directory looks like an IL2CPP Unity build (not Mono)."""
    return any(os.path.isfile(os.path.join(game_dir, marker)) for marker in _IL2CPP_MARKERS)


def _cs_string(value: str) -> str:
    return str(value).replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")


_MOD_CS = '''using MelonLoader;

[assembly: MelonInfo(typeof({namespace}.{class_name}), "{mod_name}", "{mod_version}", "AI Mod Builder")]
[assembly: MelonGame(null, null)]

namespace {namespace}
{{
    public class {class_name} : MelonMod
    {{
        public override void OnInitializeMelon()
        {{
            LoggerInstance.Msg($"Mod {{MyModInfo.NAME}} loaded.");
        }}
    }}

    internal static class MyModInfo
    {{
        public const string NAME = "{mod_name}";
        public const string VERSION = "{mod_version}";
        public const string ID = "{mod_id}";
    }}
}}
'''

_CSPROJ = '''<Project Sdk="Microsoft.NET.Sdk">
  <PropertyGroup>
    <TargetFramework>net6.0</TargetFramework>
    <LangVersion>latest</LangVersion>
    <AssemblyName>{mod_id}</AssemblyName>
    <RootNamespace>{namespace}</RootNamespace>
  </PropertyGroup>
  <ItemGroup>
    <Reference Include="MelonLoader"><HintPath>{net6}/MelonLoader.dll</HintPath><Private>false</Private></Reference>
    <Reference Include="Il2CppInterop.Runtime"><HintPath>{net6}/Il2CppInterop.Runtime.dll</HintPath><Private>false</Private></Reference>
    <Reference Include="Il2CppInterop.Common"><HintPath>{net6}/Il2CppInterop.Common.dll</HintPath><Private>false</Private></Reference>
  </ItemGroup>
</Project>
'''


def install_melonloader(game_dir: str, allow_running: bool = False) -> str:
    """Download and extract MelonLoader into `game_dir`. Returns the MelonLoader dir."""
    running, processes = rollback.is_game_running(game_dir)
    if running and not allow_running:
        raise RuntimeError(f"game is running; close it before installing MelonLoader: {processes}")
    ml_dir = os.path.join(game_dir, "MelonLoader")
    if os.path.isdir(ml_dir) and os.path.isfile(os.path.join(ml_dir, "MelonLoader.dll")):
        return "already-installed:" + ml_dir

    zip_path = os.path.join(game_dir, "_melonloader_tmp.zip")
    req = urllib.request.Request(_MELONLOADER_URL, headers=_HEADERS)
    with urllib.request.urlopen(req, timeout=300) as resp, open(zip_path, "wb") as f:
        shutil.copyfileobj(resp, f)
    try:
        staging = tempfile.mkdtemp(prefix=".melonloader-stage-", dir=game_dir)
        try:
            safe_extract_zip(zip_path, staging)
            pairs = []
            for root, _, files in os.walk(staging):
                for fn in files:
                    src = os.path.join(root, fn)
                    rel = os.path.relpath(src, staging)
                    pairs.append((src, os.path.join(game_dir, rel)))
            rollback.install_files(game_dir, "melonloader", pairs, check_running=False)
        finally:
            shutil.rmtree(staging, ignore_errors=True)
    finally:
        if os.path.exists(zip_path):
            os.remove(zip_path)
    return ml_dir


def _net6_dir(game_dir: str) -> str:
    return os.path.join(game_dir, "MelonLoader", "net6").replace("\\", "/")


def scaffold_melon_mod(project_dir: str, game_dir: str, mod_id: str, mod_name: str,
                       mod_version: str = "1.0.0", repo: str = "") -> str:
    """Write a MelonMod C# project (Mod.cs + .csproj + mod.json) into `project_dir`."""
    mod_id = safe_component(mod_id, "mod_id")
    os.makedirs(project_dir, exist_ok=True)
    namespace = mod_id.replace("-", "_").replace(".", "_")
    class_name = "".join(part.capitalize() for part in mod_id.replace("-", " ").replace(".", " ").split()) or "Mod"
    net6 = _net6_dir(game_dir)

    with open(os.path.join(project_dir, "Mod.cs"), "w", encoding="utf-8") as f:
        f.write(_MOD_CS.format(
            namespace=namespace, class_name=class_name, mod_id=mod_id,
            mod_name=_cs_string(mod_name), mod_version=_cs_string(mod_version),
        ))
    with open(os.path.join(project_dir, f"{mod_id}.csproj"), "w", encoding="utf-8") as f:
        f.write(_CSPROJ.format(mod_id=mod_id, namespace=namespace, net6=net6))
    ModManifest(id=mod_id, name=mod_name, version=mod_version, engine="unity-il2cpp",
                repo=repo, entry=f"{mod_id}.dll").save(os.path.join(project_dir, "mod.json"))
    return project_dir


def build_melon_mod(project_dir: str, game_dir: str) -> dict:
    """Build the MelonMod with dotnet and install its DLL into `game_dir/Mods/`."""
    dotnet = None
    try:
        dotnet = sdk.ensure_dotnet()
    except Exception as e:
        return {
            "success": False,
            "error": (
                "MelonLoader IL2CPP mods target .NET 6 and require the .NET SDK; "
                f"auto-install failed: {e}"
            ),
        }
    out_dir = os.path.join(project_dir, "out")
    r = subprocess.run(
        [dotnet, "build", "-c", "Release", "-o", out_dir],
        cwd=project_dir, capture_output=True, text=True, encoding="utf-8", errors="replace", check=False,
    )
    if r.returncode != 0:
        return {"success": False, "error": (r.stderr or r.stdout or "").strip()[-1500:]}

    manifest = ModManifest.load(os.path.join(project_dir, "mod.json"))
    built = os.path.join(out_dir, f"{manifest.id}.dll")
    if not os.path.isfile(built):
        return {"success": False, "error": f"built DLL not found: {built}"}
    mods_dir = os.path.join(game_dir, "Mods")
    os.makedirs(mods_dir, exist_ok=True)
    target = os.path.join(mods_dir, os.path.basename(built))
    rollback.install_files(game_dir, manifest.id, [(built, target)])
    return {"success": True, "installed": target}
