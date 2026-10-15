# Changelog

## 2026-10-15

### Evidence Normalization and Install Dry-Run

- Normalized UE4SS, REFramework, REA and Cpp2IL symbol shapes into typed `HookTarget` records with source/status/confidence and parameter signatures; generated hooks preserve this provenance.
- `inspect_feature` and mod planning now carry `normalized_targets` alongside raw observed symbols.
- Added `agmod/install_preview.py` for non-mutating install previews: add/overwrite/unchanged file-tree diff, required dependency compatibility, loader version evidence, duplicate paths, unsafe targets and ownership conflicts.
- Pinning from the UI and the MCP tool surface now run the preview before `rollback.install_files`; high-risk ownership conflicts and missing/incompatible dependencies block installation.
- UE4SS dependency detection now recognizes nested `Binaries/Win64/ue4ss` installs; compatibility records warn when game version or loader version cannot be read.

### Real Evidence and Package Structure

- Added `agmod/symbols.py` to collect observed symbol evidence from REA managed-member search and local UE4SS, REFramework, Godot and text dump artifacts. Heuristic symbols remain explicitly `suggested`, never `verified`.
- Feature plans now prefer observed symbols and expose source, confidence, file/line, signature and collection errors through `symbol_evidence`.
- Added `agmod/packages.py` with per-engine loader/API dependency profiles, local loader resolution, exact distribution dependency coordinates and explicit code/config/assets/localization/manifest/documentation artifact groups.
- `plan_mod` now writes `package-spec.json`, materializes config/default, localization and install documentation layers, records `dependency_plan`, and updates `mod.json` dependencies.
- Distribution ZIPs now include package metadata and declared artifact layers without duplicate paths; project and package validation reject incomplete package structures.
- Added regression tests for UE4SS/REFramework/REA evidence sources, dependency resolution, package layout validation and packaged artifact contents.

## 2026-10-14

### Architecture Review Follow-up

- Added `MOD_ECOSYSTEM_PLAYBOOK.md` based on Nexus Mods and Thunderstore loader/API/content packages, covering dependency graphs, loader profiles, package shape, config, assets, localization, compatibility and reversible installation.
- `plan_mod` now records a per-engine ecosystem pattern and expected implementation shape.
- Added a hard anti-cheat target gate before launch and transactional install.
- Pinned Mod generation now stages files and uses `rollback.install_files`; supported engines generate code from `generate_hook_from_evidence` instead of writing placeholder scripts.
- Primary executable selection now prefers the actual nested Shipping binary over an unrelated root launcher, and runtime matching no longer trusts executable names alone.

### Added

- Added UI Architecture Specification (`UI_ARCHITECTURE.md`) documenting the design principles, six functional workspaces, REST API contracts, security guardrails, and data flows.
- Added lightweight, zero-heavy-runtime-dependency local Web UI server and SPA dashboard (`agmod/ui/server.py`, `agmod/ui/index.html`, `agmod/ui/__main__.py`) serving:
  1. **Game & Runtime Inspector**: Engine detection, process lock detection, Doctor environment report.
  2. **AI Mod Studio**: Natural language prompts to structured `mod-spec.json` and plan preview.
  3. **Symbol & Hook Code Lab**: Multi-engine code synthesis (Harmony C#, UE4SS Lua, REFramework, Godot) with live syntax verification.
  4. **Mod Manager & Safe Rollback**: Active mod cards, conflict radar, and one-click nuclear rollback.
  5. **Live Logs & Runtime Diagnostics**: Multi-framework log reading, crash line extraction, and actionable fix suggestions.
  6. **Savegame Time Machine**: Save directory detection, pre-mod snapshots, and one-click restore.
- Added `launch_ui` tool in `server.py` and CLI runner (`python -m agmod.ui`) for instant local browser dashboard launch.
- Added UI unit test suite (`tests/test_ui.py`) covering HTTP server lifecycle, REST API endpoints, SPA static delivery, and error handling.
- Added official support matrix documentation (`SUPPORT_MATRIX.md`) defining support tiers, loader mechanisms, hook styles, tools, and candidate verification games.
- Added reverse engineering symbol-to-hook code generator (`agmod/codegen.py`, `generate_hook_template`) for synthesizing ready-to-use Harmony patches, UE4SS Lua `RegisterHook`, REFramework `sdk.hook`, and GodotModLoader GDScript wrappers from recovered symbols.
- Added runtime crash log diagnostics (`agmod/log_repair.py`, `diagnose_runtime_error`) parsing stack traces, pinpointing file and line numbers, and suggesting actionable fixes for UE4SS, REFramework, BepInEx, and GodotModLoader. Automatic source rewriting and re-verification remain future work.

### UI Refresh & Modernization

- Upgraded the UI design system to a modern obsidian & deep slate gaming palette (`#090d16` / `#141c2e`), eliminating archaic CRT terminal tints and cheap AI glowing aesthetics.
- Added interactive Preset Quick-Fill bar in AI Mod Studio (`💰 99999 金币`, `⚡ 2倍移速`, `🛡️ 锁血无敌`, `♾️ 无限耐力`, `🗡️ 攻击加成`) for instant prompt and parameter generation without raw JSON friction.
- Polished desktop layout with Vortex / Thunderstore style Mod Manager list, individual uninstall actions, conflict tracking, and modal double confirmations.
- Enhanced Log console with level filtering (`All`, `Errors`, `Warnings`), instant copy feedback, and dedicated crash diagnostic preview cards.
- Restyled Savegame Time Machine with visual snapshot cards, relative timestamps, and one-click restore.
- Verified responsive layouts on 1440px desktop and 390px mobile viewports with zero horizontal overflow.
- Tightened interaction states: hover styles no longer override disabled controls, focus rings are visible, workflow steppers and the brand are real buttons, game cards support keyboard activation, and password fields no longer trigger browser form warnings.

### Hardened

- Install journal keys now include a hash of the absolute game path, preventing same-named game directories from sharing rollback state.
- Added `rollback.install_files`, a transactional installer used by BepInEx, UE4SS, REFramework, Godot, tModLoader, and DLL updates. It blocks installs while the game is running, records pending state before copying, verifies installed hashes, and reverses partial copies on failure.
- Uninstall and rollback now preserve user-modified files, retain incomplete journal entries after errors, use atomic journal writes, and validate backup paths with real containment checks.
- Save backup keys also include the absolute game-path hash.
- Package validation now rejects ZIP traversal paths, duplicate members, and symbolic links.
- RE Engine detection no longer treats `dinput8.dll` alone as sufficient; Godot detection requires `.pck` or `.godot` evidence.
- Game-process detection no longer matches unrelated executables by filename alone and uses path containment for executable/cwd evidence.
- LLM config endpoints now mask API keys, preserve stored keys when the browser field is blank, and stop echoing secrets in save responses.
- Chat endpoints no longer accept arbitrary client-side provider config or system-role history; message roles, limits, URLs, temperature, and token counts are validated.
- Dynamic UI lists use escaped values and data attributes for uninstall/restore actions, removing the chat action-button quote escape path.
- Windows launchers now verify the portable Python archive SHA-256 before extraction and pass launcher paths through environment variables instead of interpolating them into PowerShell source.

### Verification

- `python -m unittest discover -s tests`: 85 tests passed.
- `verify.py`: 45 tools wired and verified.

## 2026-10-13

### Added

- Added Godot Engine adapter (`agmod/adapters/godot.py`) with `scaffold_godot_mod` and `install_godot_mod` supporting Godot 3.x/4.x games (Brotato, Cassette Beasts, Dome Keeper, Buckshot Roulette) with GodotModLoader GDScript modding and install journal tracking.
- Added game process discovery and runtime lock detection (`agmod/process.py`, `check_game_status`):
  - Automatically identifies primary game executables while filtering crash reporters and uninstallers.
  - Detects active game processes and warns the agent before file operations to prevent Windows file-lock errors (`ERROR_ACCESS_DENIED` / Errno 13).
  - Wired into `check_install_conflicts` to provide unified pre-install health status.
- Added Capcom RE Engine (REFramework) adapter (`agmod/adapters/reengine.py`) with `scaffold_reframework_mod` and `install_reframework_mod` supporting Monster Hunter Rise/Wilds, Resident Evil series, DMC5, and Dragon's Dogma 2 via Lua scripting and automatic install journal tracking.
- Added pre-installation mod conflict detector (`check_install_conflicts` / `agmod/rollback.py:check_conflicts`) to check whether incoming mod files overwrite existing files or collide with active mods before copying.
- Hardened installation journal (`agmod/rollback.py`):
  - Added recursive pruning of empty mod directories after uninstallation (`_cleanup_empty_dirs`), keeping framework root directories protected (`BepInEx`, `Mods`, `reframework`, `ModLoader`).
  - Added safe error capture on file locks or permission errors during file removal and restoration.
  - Added safe path bounds preventing directory traversal outside the target game folder and backup storage.
  - Added automatic pruning of restored backup copies from the backup store to save disk space.
- Added tModLoader installation support (`install_tmod_mod`) with full installation journal recording and reversible uninstallation.
- Added mod distribution package validator (`validate_package` / `agmod/pack.py`) to verify Thunderstore/Nexus ZIP structure, manifest schema, README, and payload code files before release.
- Added an installation journal (`agmod/rollback.py`) with `uninstall_mod`, `rollback_game`, and `list_installs` tools. Every install path (BepInEx, UE4SS mod install, plugin build, mod update) now records the files it added or overwrote — backing up overwritten originals — so a broken mod can always be removed and the game restored to its pre-mod state.
- Added `check_environment` tool and CLI `agmod doctor` (`python -m agmod.doctor`) for checking Python, .NET SDK, decompilers (ilspycmd/Cpp2IL), and REA readiness with actionable setup commands.
- Added C# compiler error parsing and auto-healing loop (`agmod/repair.py`, `diagnose_build_error`):
  - Parses MSBuild/dotnet `CSxxxx` error codes, line numbers, and error descriptions.
  - Generates targeted fix suggestions (missing using directives, missing semicolons, unmatched braces).
  - Automatically heals common C# errors (e.g. injecting missing `using UnityEngine;` / `using HarmonyLib;`) and retries `dotnet build` up to 2 attempts.
- Added integration workflow tests (`tests/test_e2e_pipeline.py`) validating the simulated lifecycle from doctor check, save backup, feature inspection, planning, validation, error healing, to log diagnostics and restore. Real Windows/game-process E2E coverage remains a follow-up.
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

- `build_mod` now uses `build_plugin_with_diagnostics`, returning structured compiler diagnostics and actionable fix suggestions on failure; non-CS MSBuild/NETSDK failures are reported too.
- `plan_mod` now automatically calls `inspect_feature` on request keywords, injecting detected symbol candidates and route recommendations into `mod-spec.json`.
- REA integration now targets the current `rea-agents` command contract (`function`, `xrefs`) and invokes the CLI without `shell=True`.
- Process-memory tools now fail closed when the target cannot be inspected or an anti-cheat service is active.
- Scan sessions preserve non-`int32` kinds and track previous values per address for relative scans.
- Structure fingerprints use bounded head/middle/tail samples, and decompiler output directories are fingerprint-scoped to avoid stale dumps after game updates.
- Update downloads require the exact declared DLL asset, reject path traversal, download atomically, and verify SHA-256 digests when GitHub provides them.
- Packaging rejects empty packages, validates semantic versions and manifest entries, supports UE4SS Lua source packages, and writes a usable README.
- Generated C#, Lua, and tModLoader metadata escape or normalize user-provided names and versions.
- `verify.py` is now a machine-independent smoke check instead of relying on developer-specific absolute paths.
- The wheel now includes `server.py`, so the `game-mod-agent` console entry point works after installation.

### Fixed

- `create_save_backup` / `list_save_backups` / `restore_save_backup` crashed with `UnsafePathError` for game directories containing spaces or non-ASCII characters (e.g. "Monster Hunter World"). The backup key is now slugified via `paths.slugify`.
- Structure fingerprints hashed complete file contents, forcing multi-GB Unreal `.pak` archives to be fully read on every fingerprint computation. Fingerprints now use file size plus bounded head/middle/tail sampling.
- `scaffold_ue4ss_mod` wrote `mod.json` as an ad-hoc dict; it now uses `ModManifest` so every engine scaffold emits a consistent manifest schema.
- `validate_mod_project` now supports `pre_build`/`post_build`, so compiled Unity/tModLoader projects can be validated before their DLL exists.
- Build diagnostics now recognize MSBuild/NETSDK/NUGet failures instead of reporting non-CS failures as successful builds.
- Planning now extracts Chinese feature terms, filters command verbs, checks multiple keywords, and records inspection warnings.
- Save backups now use collision-resistant IDs, skip symlinks, and preserve distinct source directories during restore.
- Log discovery now rejects symlinks escaping the game directory and bounds `tail_lines`.
- C# auto-repair now matches type names precisely and rolls back its source edit when the retry build still fails.
- IL2CPP doctor checks now match the adapter's actual `Cpp2IL` requirement instead of treating Il2CppDumper as equivalent.

### Verification

- `python -m unittest discover -s tests`: 44 unit and integration workflow tests passed.
- `python -m compileall -q server.py agmod tests`: passed.
- `python verify.py`: passed (all 33 tools wired and verified).
- `python -m agmod.doctor`: passed with structured report output.
- `python -m pip wheel . --no-deps`: wheel built with full modules included.
