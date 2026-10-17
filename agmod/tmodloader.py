"""tModLoader: scaffold and build real loadable Terraria mods.

tModLoader mods are built through ``tMLMod.targets`` and the tModLoader
server build task, which emits the ``.tmod`` archive loaded from
``ModLoader/Mods``.  A plain class-library DLL is not a complete mod package.
"""
from __future__ import annotations

import glob
import os
import re
import shutil
import subprocess
import time


from . import rollback
from .manifest import ModManifest
from .paths import safe_component, safe_join

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
    <AssemblyName>{mod_id}</AssemblyName>
    <RootNamespace>{namespace}</RootNamespace>
    <LangVersion>latest</LangVersion>
  </PropertyGroup>
  <Import Project="$(tMLSteamPath)/tMLMod.targets" />
</Project>
'''

_LIB_README = '''tModLoader builds through the official tMLMod.targets build task.

Set `tMLSteamPath` to the tModLoader install directory (the directory containing
tModLoader.dll and tMLMod.targets), or use `build_tmod_mod(project_dir, game_dir)`.
The build task emits the loadable `.tmod` archive into ModLoader/Mods.
'''


def _one_line(value: str) -> str:
    return re.sub(r"[\r\n]+", " ", str(value)).strip()


def generate_tmod_mod_source(mod_id: str, mod_name: str, params: dict | None = None) -> str:
    """Generate a real tModLoader Mod/ModPlayer implementation for common player tweaks."""
    mod_id = safe_component(mod_id, "mod_id")
    params = params or {}
    namespace = mod_id.replace("-", "_").replace(".", "_")
    class_name = "".join(p.capitalize() for p in re.split(r"[^A-Za-z0-9]+", mod_id) if p) or "MyMod"
    normalized = {re.sub(r"[^a-z0-9]", "", str(k).lower()): v for k, v in params.items()}

    def enabled(*names: str) -> bool:
        return any(bool(normalized.get(name, False)) for name in names)

    def number(*names: str, default: float = 1.0) -> float:
        for name in names:
            if name in normalized:
                try:
                    return float(normalized[name])
                except (TypeError, ValueError):
                    pass
        return default

    god_mode = enabled("godmode", "invincibleactive", "infinitehealth")
    speed_multiplier = number("speedmultiplier", "multiplier", default=1.0)
    damage_multiplier = number("damagemultiplier", "attackmultiplier", default=1.0)
    damage_reduction = number("damagereduction", default=0.0)
    fields_code = "\n".join([
        f"        private const bool GodModeEnabled = {str(god_mode).lower()};",
        f"        private const float SpeedMultiplier = {speed_multiplier!r}f;",
        f"        private const float DamageMultiplier = {damage_multiplier!r}f;",
        f"        private const float DamageReduction = {damage_reduction!r}f;",
    ])

    post_update = ""
    if god_mode or damage_reduction > 0:
        god_code = """
            if (Player.statLife < Player.statLifeMax)
            {
                Player.statLife = Player.statLifeMax;
            }
            Player.immune = true;""" if god_mode else ""
        reduction_code = """
            Player.endurance = Math.Min(1f, Player.endurance + DamageReduction / 100f);""" if damage_reduction > 0 else ""
        post_update = '''
        public override void PostUpdate()
        {
''' + god_code + reduction_code + '''
        }
'''
    run_speed = ""
    if speed_multiplier != 1.0:
        run_speed = '''
        public override void PostUpdateRunSpeeds()
        {
            Player.maxRunSpeed *= SpeedMultiplier;
            Player.accRunSpeed *= SpeedMultiplier;
            Player.moveSpeed *= SpeedMultiplier;
        }
'''
    hit_npc = ""
    if damage_multiplier != 1.0:
        hit_npc = '''
        public override void ModifyHitNPC(Item item, NPC target, ref int damage, ref float knockback, ref bool crit, ref int hitDirection)
        {
            damage = (int)Math.Round(damage * DamageMultiplier);
        }
'''
    return f'''using System;
using Terraria;
using Terraria.ModLoader;

namespace AIMod_{namespace}
{{
    public class {class_name}Mod : Mod
    {{
    }}

    public class {class_name}Player : ModPlayer
    {{
{fields_code}
{post_update}{run_speed}{hit_npc}    }}
}}
'''


def scaffold_tmod_mod(project_dir: str, mod_id: str, mod_name: str, mod_version: str = "0.1.0", author: str = "") -> str:
    """Write a minimal tModLoader mod skeleton into `project_dir`."""
    mod_id = safe_component(mod_id, "mod_id")
    mod_name = _one_line(mod_name)
    author = _one_line(author or "unknown")
    mod_version = _one_line(mod_version)
    os.makedirs(project_dir, exist_ok=True)
    namespace = mod_id.replace("-", "_").replace(".", "_")
    class_name = "".join(p.capitalize() for p in re.split(r"[^A-Za-z0-9]+", mod_id) if p) or "MyMod"

    with open(os.path.join(project_dir, f"{class_name}.cs"), "w", encoding="utf-8") as f:
        f.write(_MOD_CS.format(namespace=namespace, class_name=class_name))
    with open(os.path.join(project_dir, "build.txt"), "w", encoding="utf-8") as f:
        f.write(_BUILD_TXT.format(mod_name=mod_name, author=author or "unknown", mod_version=mod_version))
    with open(os.path.join(project_dir, f"{mod_id}.csproj"), "w", encoding="utf-8") as f:
        f.write(_CSPROJ.format(mod_id=mod_id, namespace=namespace))
    os.makedirs(os.path.join(project_dir, "docs"), exist_ok=True)
    with open(os.path.join(project_dir, "docs", "BUILD.md"), "w", encoding="utf-8") as f:
        f.write(_LIB_README)
    ModManifest(id=mod_id, name=mod_name, version=mod_version, engine="tmodloader",
                entry=f"{mod_id}.tmod").save(os.path.join(project_dir, "mod.json"))
    return project_dir


def find_tml_root(game_dir: str = "") -> str:
    """Find an installed tModLoader root containing tModLoader.dll and tMLMod.targets."""
    candidates = []
    if game_dir:
        candidates.extend([game_dir, os.path.dirname(os.path.abspath(game_dir))])
    env_root = os.environ.get("TML_PATH") or os.environ.get("TMLSteamPath")
    if env_root:
        candidates.append(env_root)
    home = os.path.expanduser("~")
    candidates.extend([
        os.path.join(home, ".local", "share", "Steam", "steamapps", "common", "tModLoader"),
        os.path.join(home, "Library", "Application Support", "Steam", "steamapps", "common", "tModLoader"),
        r"C:\Program Files (x86)\Steam\steamapps\common\tModLoader",
        r"C:\Program Files\Steam\steamapps\common\tModLoader",
    ])
    for candidate in candidates:
        if os.path.isfile(os.path.join(candidate, "tModLoader.dll")) and os.path.isfile(os.path.join(candidate, "tMLMod.targets")):
            return os.path.abspath(candidate)
    raise RuntimeError("tModLoader install not found; set TML_PATH or pass a tModLoader game directory")


def build_tmod_mod(project_dir: str, game_dir: str = "") -> str:
    """Build with the official tMLMod.targets task and return a directory containing a `.tmod`."""
    tml_root = find_tml_root(game_dir)
    out_dir = os.path.join(project_dir, "out")
    os.makedirs(out_dir, exist_ok=True)
    started = time.time() - 2
    try:
        subprocess.run(
            [
                "dotnet", "build", "-c", "Release", "-o", out_dir,
                f"-p:tMLSteamPath={tml_root}",
            ],
            check=True, capture_output=True, text=True, cwd=project_dir,
        )
    except FileNotFoundError:
        raise RuntimeError("dotnet not found. Install the current .NET SDK used by tModLoader.") from None
    except subprocess.CalledProcessError as exc:
        detail = ((exc.stderr or "") + "\n" + (exc.stdout or "")).strip()[-2000:]
        raise RuntimeError(f"tModLoader build failed: {detail}") from exc

    candidates = glob.glob(os.path.join(out_dir, "*.tmod"))
    candidates += glob.glob(os.path.join(project_dir, "*.tmod"))
    candidates += glob.glob(os.path.join(tml_root, "ModLoader", "Mods", "*.tmod"))
    candidates = [p for p in candidates if os.path.isfile(p) and os.path.getmtime(p) >= started]
    if not candidates:
        raise RuntimeError("tModLoader build completed without producing a loadable .tmod archive")
    built = max(candidates, key=os.path.getmtime)
    target = os.path.join(out_dir, os.path.basename(built))
    if os.path.abspath(built) != os.path.abspath(target):
        shutil.copy2(built, target)
    return out_dir


def install_tmod_mod(project_dir: str, game_dir: str) -> dict:
    """Install built tModLoader mod files into game directory with rollback journal tracking."""
    manifest_path = os.path.join(project_dir, "mod.json")
    if not os.path.isfile(manifest_path):
        raise ValueError(f"no mod.json found in {project_dir}")
    manifest = ModManifest.load(manifest_path)
    out_dir = os.path.join(project_dir, "out")
    if not os.path.isdir(out_dir):
        raise ValueError("no out/ directory found; run build_tmod_mod first")

    # tModLoader mods typically live in ModLoader/Mods or Mods
    mods_dir = os.path.join(game_dir, "ModLoader", "Mods")
    os.makedirs(mods_dir, exist_ok=True)

    targets = [safe_join(mods_dir, fn) for fn in sorted(os.listdir(out_dir)) if fn.endswith(".tmod")]

    if not targets:
        raise ValueError("no loadable .tmod found in out/ directory")

    pairs = [(os.path.join(out_dir, os.path.basename(t)), t) for t in targets]
    result = rollback.install_files(game_dir, manifest.id, pairs)
    return {
        "success": True,
        "mod_id": manifest.id,
        "installed": [os.path.basename(t) for t in result["installed"]],
        "destination": mods_dir,
    }


def verify_tmod_mod(game_dir: str, mod_id: str) -> dict:
    """Verify that a loadable `.tmod` exists and tModLoader logged it as loaded."""
    mods_dir = os.path.join(game_dir, "ModLoader", "Mods")
    candidates = glob.glob(os.path.join(mods_dir, "*.tmod"))
    matches = [p for p in candidates if os.path.splitext(os.path.basename(p))[0].lower() == mod_id.lower()]
    path = matches[0] if matches else ""
    installed = bool(path and os.path.isfile(path) and os.path.getsize(path) > 0)
    log_loaded = False
    log_errors = []
    for log_path in (
        os.path.join(game_dir, "ModLoader", "Logs", "tModLoader.log"),
        os.path.join(game_dir, "Logs", "tModLoader.log"),
        os.path.join(game_dir, "tModLoader.log"),
    ):
        if not os.path.isfile(log_path):
            continue
        try:
            with open(log_path, "r", encoding="utf-8", errors="ignore") as f:
                lines = f.readlines()[-300:]
        except OSError:
            continue
        for line in lines:
            low = line.lower()
            if mod_id.lower() in low and any(token in low for token in ("loaded", "enabled", "adding mod", "loading mod")):
                log_loaded = True
            if mod_id.lower() in low and any(token in low for token in ("error", "exception", "failed")):
                log_errors.append(line.strip()[:200])
    return {
        "mod_id": mod_id,
        "installed": installed,
        "path": path,
        "log_loaded": log_loaded,
        "log_errors": log_errors,
        "effective": installed and log_loaded,
    }

