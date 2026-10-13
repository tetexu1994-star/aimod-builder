# Changelog

## 2026-10-13

### Added

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

### Verification

- `pytest`: 31 tests passed in 0.07s.
- `python -m compileall -q server.py agmod tests`: passed.
- `python verify.py`: passed (all 31 tools wired and verified).
- `python -m pip wheel . --no-deps`: wheel built with full modules included.

### Known follow-ups

- Run real Windows game integration tests for BepInEx, UE4SS, tModLoader, and REFramework.
- Add an automatic compile-error repair loop after the generated implementation is edited.
- Add strict Thunderstore/Nexus publishing validators and release provenance.
- Pin and test the exact REA runtime version against a real binary fixture.
