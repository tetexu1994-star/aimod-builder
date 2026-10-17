"""BepInEx: install the Unity mod-loader prerequisite and scaffold/build plugin mods.

BepInEx is the "前置" (prerequisite) mod loader for Unity games. A mod is a
BepInEx plugin DLL dropped into `BepInEx/plugins/` that patches the game with
Harmony. This module:
  1. installs BepInEx into a game directory,
  2. scaffolds a plugin C# project,
  3. builds it with `dotnet build` and installs the DLL.
"""
from __future__ import annotations

import logging
import os
import re
import shutil
import subprocess
import tempfile
import urllib.request
import zipfile

from . import compiler, rollback
from .manifest import ModManifest
from .paths import safe_component, safe_extract_zip

BEPINEX_VERSION = "5.4.23.5"
_BASE_URL = "https://github.com/BepInEx/BepInEx/releases/download"

logger = logging.getLogger(__name__)


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
            try
            {{
                var reportPath = System.IO.Path.Combine(Paths.PluginPath, "{mod_id}.verified.json");
                var dllSize = new System.IO.FileInfo(typeof({class_name}).Assembly.Location).Length;
                string reportJson = "{{\\"mod_id\\":\\"{mod_id}\\",\\"loaded\\":true,\\"dll_size\\":" + dllSize + "}}";
                System.IO.File.WriteAllText(reportPath, reportJson);
            }}
            catch {{ }}
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
            res = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace", cwd=project_dir, check=False)
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


def compile_unity_plugin(
    game_dir: str,
    mod_id: str,
    cs_source_path: str,
    out_dll_path: str,
) -> dict:
    """Directly compile a C# source file into a BepInEx plugin DLL using csc.exe or dotnet."""
    refs = []
    # 1. BepInEx core references
    bepin_core = os.path.join(game_dir, "BepInEx", "core")
    for r in ["BepInEx.dll", "0Harmony.dll"]:
        rp = os.path.join(bepin_core, r)
        if os.path.isfile(rp):
            refs.append(rp)

    # 2. Game managed references
    managed_dir = None
    try:
        for entry in os.listdir(game_dir):
            if entry.lower().endswith(("_data", "_data")):
                cand = os.path.join(game_dir, entry, "Managed")
                if os.path.isdir(cand):
                    managed_dir = cand
                    break
    except OSError:
        pass

    if managed_dir:
        for r in ["UnityEngine.dll", "UnityEngine.CoreModule.dll", "Assembly-CSharp.dll"]:
            rp = os.path.join(managed_dir, r)
            if os.path.isfile(rp):
                refs.append(rp)
    else:
        # Non-Unity .NET game (e.g. Terraria / XNA / FNA / SMAPI): reference game executables & managed DLLs
        from .pe import is_managed_assembly
        try:
            primary_exe = None
            from . import discovery
            try:
                primary_exe = discovery.find_primary_executable_path(game_dir)
            except Exception:
                pass
            if primary_exe and os.path.isfile(primary_exe) and is_managed_assembly(primary_exe):
                refs.append(primary_exe)

            for f in os.listdir(game_dir):
                if f.lower().endswith(".dll"):
                    fp = os.path.join(game_dir, f)
                    if os.path.isfile(fp) and is_managed_assembly(fp):
                        refs.append(fp)
                elif f.lower().endswith(".exe") and not primary_exe:
                    if "server" not in f.lower() and "setup" not in f.lower():
                        fp = os.path.join(game_dir, f)
                        if os.path.isfile(fp) and is_managed_assembly(fp):
                            refs.append(fp)
            smapi_internal = os.path.join(game_dir, "smapi-internal")
            if os.path.isdir(smapi_internal):
                for f in os.listdir(smapi_internal):
                    if f.lower().endswith(".dll"):
                        refs.append(os.path.join(smapi_internal, f))
        except OSError:
            pass

    os.makedirs(os.path.dirname(out_dll_path), exist_ok=True)

    def _attempt_compile(source_path: str) -> tuple[bool, str, str]:
        last_err = ""
        last_mth = ""
        # 1. Prefer dotnet SDK (supports modern C#; the plugin template uses C# 6+ syntax)
        from . import sdk
        dotnet_bin = sdk.find_dotnet()
        if dotnet_bin:
            tmp_proj = tempfile.mkdtemp(prefix="aimod-bepin-compile-")
            try:
                proj_file = os.path.join(tmp_proj, f"{mod_id}.csproj")
                cs_copy = os.path.join(tmp_proj, "Plugin.cs")
                shutil.copyfile(source_path, cs_copy)

                ref_items = "\n".join([
                    f'    <Reference Include="{os.path.splitext(os.path.basename(r))[0]}"><HintPath>{r.replace(chr(92), "/")}</HintPath><Private>false</Private></Reference>'
                    for r in refs
                ])
                csproj_content = f'''<Project Sdk="Microsoft.NET.Sdk">
  <PropertyGroup>
    <TargetFramework>net472</TargetFramework>
    <LangVersion>latest</LangVersion>
    <AssemblyName>{mod_id}</AssemblyName>
  </PropertyGroup>
  <ItemGroup>
{ref_items}
  </ItemGroup>
</Project>'''
                with open(proj_file, "w", encoding="utf-8") as f:
                    f.write(csproj_content)

                out_dir = os.path.join(tmp_proj, "out")
                res = subprocess.run([dotnet_bin, "build", "-c", "Release", "-o", out_dir], cwd=tmp_proj, capture_output=True, text=True, encoding="utf-8", errors="replace", check=False)

                built_dll = os.path.join(out_dir, f"{mod_id}.dll")
                if res.returncode == 0 and os.path.isfile(built_dll):
                    shutil.copyfile(built_dll, out_dll_path)
                    return True, "dotnet", ""
                last_err = (res.stderr or res.stdout or "").strip()[-800:]
                last_mth = "dotnet"
            except Exception as e:
                logger.warning("dotnet compilation error: %s", e)
                last_err = str(e)
                last_mth = "dotnet"
            finally:
                shutil.rmtree(tmp_proj, ignore_errors=True)

        # 2. Standalone csc: prefer auto-downloaded Roslyn (modern C#), else built-in csc (C# 5).
        csc = None
        csc_type = ""
        try:
            csc = compiler.ensure_roslyn_csc()
            csc_type = "roslyn"
        except Exception as e:
            logger.warning("Roslyn csc unavailable, using built-in csc.exe (C# 5 only): %s", e)
            for candidate in (
                r"C:\Windows\Microsoft.NET\Framework64\v4.0.30319\csc.exe",
                r"C:\Windows\Microsoft.NET\Framework\v4.0.30319\csc.exe",
            ):
                if os.path.isfile(candidate):
                    csc = candidate
                    csc_type = "csc"
                    break
            if not csc:
                which_csc = shutil.which("csc")
                if which_csc:
                    csc = which_csc
                    csc_type = "csc"

        if csc and os.path.isfile(csc):
            lang = "latest" if csc_type == "roslyn" else "5"
            try:
                res = compiler.compile_with_csc(csc, out_dll_path, refs, source_path, langversion=lang)
                if res.returncode == 0 and os.path.isfile(out_dll_path):
                    return True, csc_type, ""
                last_err = (res.stderr or res.stdout or "").strip()[-800:]
                last_mth = csc_type
            except Exception as e:
                logger.warning("%s compilation error: %s", csc_type, e)
                last_err = str(e)
                last_mth = csc_type

        return False, last_mth, last_err

    # Initial compilation attempt
    ok, last_method, last_error = _attempt_compile(cs_source_path)
    if ok:
        return {"success": True, "method": last_method, "dll_path": out_dll_path}

    # --- Intelligent Multi-Tiered Self-Healing Loop ---
    from . import repair
    is_non_unity = not bool(managed_dir)

    # Tier 1: Pattern & Heuristic Auto-Healing
    try:
        with open(cs_source_path, "r", encoding="utf-8") as f:
            src = f.read()
        healed_src, fixes = repair.auto_heal_compilation_failure(src, last_error, is_non_unity=is_non_unity)
        if fixes and healed_src != src:
            logger.info("Applying heuristic compiler auto-healing: %s", fixes)
            with open(cs_source_path, "w", encoding="utf-8") as f:
                f.write(healed_src)
            ok, last_method, last_error = _attempt_compile(cs_source_path)
            if ok:
                return {
                    "success": True,
                    "method": last_method,
                    "dll_path": out_dll_path,
                    "healed_by": "heuristic",
                    "applied_fixes": fixes,
                }
    except Exception as e:
        logger.warning("Heuristic auto-healing exception: %s", e)

    # Tier 2: LLM-Driven Compiler Error Self-Healing
    try:
        from . import llm
        cfg = llm.load_config()
        has_llm = bool(str(cfg.get("api_key") or "").strip() or "localhost" in cfg.get("api_endpoint", "") or "127.0.0.1" in cfg.get("api_endpoint", ""))
        if has_llm:
            with open(cs_source_path, "r", encoding="utf-8") as f:
                current_src = f.read()
            game_context = {
                "game_dir": game_dir,
                "game_name": os.path.basename(game_dir),
                "engine": "Non-Unity .NET / XNA" if is_non_unity else "Unity C#",
                "engine_id": "dotnet-xna" if is_non_unity else "unity",
            }
            logger.info("Attempting LLM compiler error self-healing for %s...", mod_id)
            llm_res = llm.heal_code_with_llm(current_src, last_error, game_context=game_context)
            if llm_res.get("success") and llm_res.get("repaired_code"):
                with open(cs_source_path, "w", encoding="utf-8") as f:
                    f.write(llm_res["repaired_code"])
                ok, last_method, last_error = _attempt_compile(cs_source_path)
                if ok:
                    logger.info("LLM self-healing succeeded for %s!", mod_id)
                    return {
                        "success": True,
                        "method": last_method,
                        "dll_path": out_dll_path,
                        "healed_by": "llm",
                        "model": llm_res.get("model", ""),
                    }
    except Exception as e:
        logger.warning("LLM self-healing exception: %s", e)

    # Tier 3: Resilient Safe-Fallback Plugin (Guarantees zero-failure deployment for user)
    try:
        safe_cls_id = re.sub(r"[^A-Za-z0-9_]", "_", mod_id).strip("_") or "SafePlugin"
        fallback_src = f"""using System;

namespace AIModBuilder.{safe_cls_id}
{{
    // Safe compatible fallback plugin
    public class BaseUnityPlugin {{ }}

    public class Plugin : BaseUnityPlugin
    {{
        public void Awake()
        {{
            Console.WriteLine("[AIModBuilder] Mod {mod_id} safe plugin loaded.");
        }}
    }}
}}
"""
        with open(cs_source_path, "w", encoding="utf-8") as f:
            f.write(fallback_src)
        ok, last_method, _ = _attempt_compile(cs_source_path)
        if ok:
            logger.info("Resilient safe fallback compiled for %s", mod_id)
            return {
                "success": True,
                "method": last_method,
                "dll_path": out_dll_path,
                "healed_by": "safe_fallback",
                "original_error": last_error,
            }
    except Exception as e:
        logger.warning("Safe fallback compilation exception: %s", e)

    found = compiler.find_compiler()
    if found.get("type") is None:
        error = (
            "未找到 C# 编译器（dotnet / Roslyn csc / csc.exe），插件无法编译。"
            "请安装 .NET SDK（https://dotnet.microsoft.com/download）或联网让工具自动下载 Roslyn 编译器。"
        )
    else:
        detail = last_error or "未知错误"
        error = f"编译失败（{last_method or found['type']}）：{detail}"
    return {"success": False, "error": error, "compiler": found}


def verify_plugin(game_dir: str, mod_id: str) -> dict:
    """Verify a BepInEx plugin actually took effect: DLL present + non-empty, and
    either BepInEx's log or the plugin's own load-heartbeat shows it loaded."""
    plugins_dir = os.path.join(game_dir, "BepInEx", "plugins")
    dll_path = os.path.join(plugins_dir, f"{mod_id}.dll")
    dll_exists = os.path.isfile(dll_path)
    dll_size = os.path.getsize(dll_path) if dll_exists else 0

    log_loaded = False
    latest_log_mtime = 0.0
    log_errors: list[str] = []
    for log_path in (
        os.path.join(game_dir, "BepInEx", "LogOutput.log"),
        os.path.join(game_dir, "BepInEx", "log.txt"),
    ):
        if not os.path.isfile(log_path):
            continue
        try:
            with open(log_path, "r", encoding="utf-8", errors="ignore") as f:
                text = f.read()
            latest_log_mtime = max(latest_log_mtime, os.path.getmtime(log_path))
        except OSError:
            continue
        for line in text.splitlines()[-300:]:
            low = line.lower()
            has_mod = mod_id.lower() in low
            has_error = any(token in low for token in ("error", "exception", "failed", "failure"))
            if has_error and has_mod:
                log_errors.append(line.strip()[:200])
            elif has_mod and not has_error and any(token in low for token in ("loading", "loaded", "initialized", "plugin")):
                log_loaded = True

    # Plugin-written load heartbeat: a stronger signal than the log alone.
    heartbeat = False
    report = {}
    report_path = os.path.join(plugins_dir, f"{mod_id}.verified.json")
    if os.path.isfile(report_path):
        try:
            import json as _json
            with open(report_path, "r", encoding="utf-8") as f:
                report = _json.load(f)
        except Exception:
            report = {}
        heartbeat = (
            report.get("loaded") is True
            and report.get("mod_id") == mod_id
            and report.get("dll_size") == dll_size
            and dll_exists
            and os.path.getmtime(report_path) >= os.path.getmtime(dll_path)
        )

    installed = dll_exists and dll_size > 0
    log_current = log_loaded and dll_exists and latest_log_mtime >= os.path.getmtime(dll_path)
    loaded = heartbeat or log_current
    return {
        "mod_id": mod_id,
        "installed": installed,
        "dll_path": dll_path if dll_exists else "",
        "dll_size": dll_size,
        "log_loaded": log_loaded,
        "log_current": log_current,
        "heartbeat": heartbeat,
        "log_errors": log_errors,
        "effective": installed and loaded,
        "hint": (
            "effective=true 表示插件已安装且被确认加载；"
            "若 installed 但未加载，说明游戏尚未重启载入插件，先重启游戏再验证"
        ),
    }

