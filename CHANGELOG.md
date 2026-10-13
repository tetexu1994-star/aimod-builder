# Changelog

## 2026-10-13

### Added

- Added `plan_mod` for turning a natural-language mod request into:
  - `mod-spec.json`
  - `request.md`
  - `MODDING_PLAN.md`
  - a Unity/BepInEx, Unreal/UE4SS, or tModLoader starter project
- Added `validate_mod_project` for checking the manifest, entry file, engine-specific required files, and path safety before build/install/package.
- Added shared path/archive safety helpers and regression coverage for traversal, ZIP extraction, update downloads, packaging, REA invocation, and scan sessions.

### Changed

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

- `python -m unittest discover -s tests -q`: 28 tests passed.
- `python -m compileall -q server.py agmod tests`: passed.
- `python verify.py`: passed.
- `python -m pip wheel . --no-deps`: wheel built with `server.py`, `agmod/planning.py`, `agmod/paths.py`, and the entry point included.

### Known follow-ups

- Run real Windows game integration tests for BepInEx, UE4SS, tModLoader, and REFramework.
- Add an automatic compile-error repair loop after the generated implementation is edited.
- Add strict Thunderstore/Nexus publishing validators and release provenance.
- Pin and test the exact REA runtime version against a real binary fixture.
