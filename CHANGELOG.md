# Changelog

## 2026-10-13

### Added

- Added `check_environment` tool and CLI `agmod doctor` (`python -m agmod.doctor`) for checking Python, .NET SDK, decompilers (ilspycmd/Cpp2IL), and REA readiness with actionable setup commands.
- Added C# compiler error parsing and auto-healing loop (`agmod/repair.py`, `diagnose_build_error`):
  - Parses MSBuild/dotnet `CSxxxx` error codes, line numbers, and error descriptions.
  - Generates targeted fix suggestions (missing using directives, missing semicolons, unmatched braces).
  - Automatically heals common C# errors (e.g. injecting missing `using UnityEngine;` / `using HarmonyLib;`) and retries `dotnet build` up to 2 attempts.
- Added end-to-end integration test suite (`tests/test_e2e_pipeline.py`) validating the complete lifecycle from doctor check, save backup, feature inspection, planning, validation, error healing, to log diagnostics and restore.
- Added `read_mod_logs` for tailing mod framework logs (BepInEx `LogOutput.log`, UE4SS `UE4SS.log`, tModLoader `Launch.log`) with automated diagnostics for `NullReferenceException`, failed patches, missing methods, and Lua syntax errors.
- Added savegame snapshot and recovery manager (`create_save_backup`, `list_save_backups`, `restore_save_backup`) with traversal-safe zip extraction to protect players from save corruption before mod injection.
- Added `plan_mod` for turning a natural-language mod request into:
  - `mod-spec.json` (now populated with candidate symbols from automated inspection)
  - `request.md`
  - `MODDING_PLAN.md`
  - a Unity/BepInEx, Unreal/UE4SS, or tModLoader starter project
- Added `validate_mod_project` for checking the manifest, entry file, engine-specific required files, semantic `Plugin.cs` validity, and path safety before build/install/package.
- Added shared path/archive safety helpers and regression coverage for traversal, ZIP extraction, update downloads, packaging, REA invocation, and scan sessions.

### Changed

- `build_mod` now uses `build_plugin_with_diagnostics`, returning structured CS error codes, file lines, and actionable fix suggestions on failure instead of raw unparsed stack traces.
- `plan_mod` now automatically calls `inspect_feature` on request keywords, injecting detected symbol candidates and route recommendations into `mod-spec.json`.
- REA integration now targets the current `rea-agents` command contract (`function`, `xrefs`) and invokes the CLI without `shell=True`.
- Process-memory tools now fail closed when the target cannot be inspected or an anti-cheat service is active.
- Scan sessions preserve non-`int32` kinds and track previous values per address for relative scans.
- Structure fingerprints hash complete file contents, and decompiler output directories are fingerprint-scoped to avoid stale dumps after game updates.
- Update downloads require the exact declared DLL asset, reject path traversal, download atomically, and verify SHA-256 digests when GitHub provides them.
- Packaging rejects empty packages, validates semantic versions and manifest entries, supports UE4SS Lua source packages, and writes a usable README.
- Generated C#, Lua, and tModLoader metadata escape or normalize user-provided names and versions.
- `verify.py` is now a machine-independent smoke check instead of relying on developer-specific absolute paths.
- The wheel now includes `server.py`, so the `game-mod-agent` console entry point works after installation.

### Fixed

- `create_save_backup` / `list_save_backups` / `restore_save_backup` crashed with `UnsafePathError` for game directories containing spaces or non-ASCII characters (e.g. "Monster Hunter World"). The backup key is now slugified via `paths.slugify`.
- Structure fingerprints hashed complete file contents, forcing multi-GB Unreal `.pak` archives to be fully read on every fingerprint computation. Fingerprints now use file size plus bounded head/tail sampling.
- `scaffold_ue4ss_mod` wrote `mod.json` as an ad-hoc dict; it now uses `ModManifest` so every engine scaffold emits a consistent manifest schema.

### Verification

- `pytest`: 35 unit and E2E integration tests passed in 0.09s.
- `python -m compileall -q server.py agmod tests`: passed.
- `python verify.py`: passed (all 33 tools wired and verified).
- `python -m agmod.doctor`: passed with structured report output.
- `python -m pip wheel . --no-deps`: wheel built with full modules included.
