"""CUE4Parse host: programmatic Unreal .pak / .utoc/.ucas reading.

CUE4Parse is a .NET *library* (no CLI), so this module scaffolds a tiny C# console
host, builds it with the portable .NET SDK, and wraps its `list` command. This
replaces the manual FModel step for locating assets inside Unreal packages.

The host is built once and cached under ``~/.agmod/tools/cue4parse``.
"""
from __future__ import annotations

import os
import shutil
import subprocess

CUE4PARSE_VERSION = os.environ.get("AGMOD_CUE4PARSE_VERSION", "1.2.0")

_PROGRAM_CS = r'''using CUE4Parse.Encryption.Aes;
using CUE4Parse.FileProvider;
using CUE4Parse.UE4.Objects.Core.Misc;
using CUE4Parse.UE4.Versions;

if (args.Length < 1)
{
    Console.Error.WriteLine("usage: agmod_cue4parse <gameDir> [aesKey]");
    return 1;
}
var gameDir = args[0];
string? aesKey = args.Length > 1 && args[1].Length > 0 ? args[1] : null;

var provider = new DefaultFileProvider(
    gameDir, SearchOption.AllDirectories, true, new VersionContainer(EGame.GAME_UE5_4));
provider.Initialize();
if (aesKey is not null)
{
    provider.SubmitKey(new FGuid(), new FAesKey(aesKey));
}

foreach (var (path, _) in provider.Files)
{
    Console.WriteLine(path);
}
return 0;
'''

_CSPROJ = r'''<Project Sdk="Microsoft.NET.Sdk">
  <PropertyGroup>
    <OutputType>Exe</OutputType>
    <TargetFramework>net8.0</TargetFramework>
    <AssemblyName>agmod_cue4parse</AssemblyName>
    <Nullable>enable</Nullable>
    <ImplicitUsings>enable</ImplicitUsings>
  </PropertyGroup>
  <ItemGroup>
    <PackageReference Include="CUE4Parse" Version="{version}" />
  </ItemGroup>
</Project>
'''


def _host_dir() -> str:
    d = os.path.join(os.path.expanduser("~"), ".agmod", "tools", "cue4parse")
    os.makedirs(d, exist_ok=True)
    return d


def find_host() -> str | None:
    exe = os.path.join(_host_dir(), "bin", "Release", "net8.0", "agmod_cue4parse.exe")
    return exe if os.path.isfile(exe) else None


def _host_dll() -> str:
    return os.path.join(_host_dir(), "bin", "Release", "net8.0", "agmod_cue4parse.dll")


def scaffold_host(host_dir: str) -> str:
    os.makedirs(host_dir, exist_ok=True)
    with open(os.path.join(host_dir, "Program.cs"), "w", encoding="utf-8") as f:
        f.write(_PROGRAM_CS)
    with open(os.path.join(host_dir, "agmod_cue4parse.csproj"), "w", encoding="utf-8") as f:
        f.write(_CSPROJ.format(version=CUE4PARSE_VERSION))
    return host_dir


def build_host(host_dir: str) -> str:
    from . import sdk

    dotnet = sdk.ensure_dotnet()
    r = subprocess.run(
        [dotnet, "build", "-c", "Release", "-o", os.path.join(host_dir, "bin", "Release", "net8.0")],
        cwd=host_dir, capture_output=True, text=True, encoding="utf-8", errors="replace", check=False,
    )
    if r.returncode != 0:
        detail = (r.stderr or r.stdout or "").strip()[-2500:]
        raise RuntimeError(f"CUE4Parse host build failed: {detail}")
    exe = find_host()
    if not exe:
        raise RuntimeError("CUE4Parse host build finished but the exe was not found")
    return exe


def ensure_host() -> str:
    existing = find_host()
    if existing:
        return existing
    host_dir = _host_dir()
    scaffold_host(host_dir)
    return build_host(host_dir)


def list_assets(game_dir: str, aes_key: str = "") -> list[str]:
    """List all asset paths inside a game directory's .pak/.utoc/.ucas archives."""
    from . import sdk

    if not os.path.isfile(_host_dll()):
        ensure_host()
    dotnet = sdk.ensure_dotnet()
    cmd = [dotnet, _host_dll(), game_dir] + ([aes_key] if aes_key else [])
    r = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace", check=False)
    if r.returncode != 0:
        raise RuntimeError((r.stderr or r.stdout or "").strip()[-2000:])
    return [line for line in (r.stdout or "").splitlines() if line.strip()]
