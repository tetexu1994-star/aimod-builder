"""tModLoader: scaffold/build mods for Terraria.

tModLoader is Terraria's mod framework (not BepInEx). A mod is a C# class
library that references tModLoader.dll + Terraria.dll and subclasses
`Terraria.ModLoader.Mod`. The reference DLLs are shipped with tModLoader and
go in the project's `lib/` folder (see the lib/README the scaffold writes).

For the full official template, `dotnet new install tModLoader.Templates`
followed by `dotnet new tmodloader` is the recommended path; this scaffold
produces the same minimal shape by hand.
"""
from __future__ import annotations

import os
import subprocess

from .manifest import ModManifest

_MOD_CS = '''using Terraria.ModLoader;

namespace {namespace};

public class {class_name} : Mod
{{
    public override void Load()
    {{
        // Add content, hooks, etc. here.
    }}
}}
'''

_BUILD_TXT = '''displayName = {mod_name}
author = {author}
version = {mod_version}
'''

_CSPROJ = '''<Project Sdk="Microsoft.NET.Sdk">
  <PropertyGroup>
    <TargetFramework>net6.0</TargetFramework>
    <Nullable>enable</Nullable>
    <AssemblyName>{mod_id}</AssemblyName>
    <RootNamespace>{namespace}</RootNamespace>
  </PropertyGroup>
  <ItemGroup>
    <Reference Include="tModLoader">
      <HintPath>lib/tModLoader.dll</HintPath>
      <Private>false</Private>
    </Reference>
    <Reference Include="Terraria">
      <HintPath>lib/Terraria.dll</HintPath>
      <Private>false</Private>
    </Reference>
  </ItemGroup>
</Project>
'''

_LIB_README = '''Put the tModLoader reference assemblies here (from your tModLoader install):

  lib/tModLoader.dll
  lib/Terraria.dll

tModLoader is a free Steam tool (search "tModLoader"); its install dir contains
both DLLs. For a fully wired template use:
  dotnet new install tModLoader.Templates
  dotnet new tmodloader
'''


def scaffold_tmod_mod(project_dir: str, mod_id: str, mod_name: str, mod_version: str = "0.1.0", author: str = "") -> str:
    """Write a minimal tModLoader mod skeleton into `project_dir`."""
    os.makedirs(os.path.join(project_dir, "lib"), exist_ok=True)
    namespace = mod_id.replace("-", "_").replace(".", "_")
    class_name = "".join(p.capitalize() for p in mod_id.replace("-", " ").replace(".", " ").split()) or "MyMod"

    with open(os.path.join(project_dir, f"{class_name}.cs"), "w", encoding="utf-8") as f:
        f.write(_MOD_CS.format(namespace=namespace, class_name=class_name))
    with open(os.path.join(project_dir, "build.txt"), "w", encoding="utf-8") as f:
        f.write(_BUILD_TXT.format(mod_name=mod_name, author=author or "unknown", mod_version=mod_version))
    with open(os.path.join(project_dir, f"{mod_id}.csproj"), "w", encoding="utf-8") as f:
        f.write(_CSPROJ.format(mod_id=mod_id, namespace=namespace))
    with open(os.path.join(project_dir, "lib", "README.md"), "w", encoding="utf-8") as f:
        f.write(_LIB_README)
    ModManifest(id=mod_id, name=mod_name, version=mod_version, engine="tmodloader",
                entry=f"{mod_id}.dll").save(os.path.join(project_dir, "mod.json"))
    return project_dir


def build_tmod_mod(project_dir: str) -> str:
    """Build the tModLoader mod with `dotnet build`. Returns the output dir."""
    try:
        subprocess.run(
            ["dotnet", "build", "-c", "Release", "-o", os.path.join(project_dir, "out")],
            check=True, capture_output=True, text=True, cwd=project_dir,
        )
    except FileNotFoundError:
        raise RuntimeError("dotnet not found. Install the .NET 6 SDK.") from None
    return os.path.join(project_dir, "out")
