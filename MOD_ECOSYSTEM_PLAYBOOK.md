# Mod Ecosystem Playbook

This note captures implementation patterns observed in public mod ecosystems. It is used to make AI Mod Builder plans closer to real loader/package expectations.

## Sources reviewed

- Nexus Mods: [Skyrim Script Extender (SKSE64)](https://www.nexusmods.com/skyrimspecialedition/mods/30379)
- Nexus Mods: [SMAPI - Stardew Modding API](https://www.nexusmods.com/stardewvalley/mods/2400)
- Thunderstore: [BepInExPack](https://thunderstore.io/package/BepInEx/BepInExPack/)
- Thunderstore: [BepInExPack_Valheim](https://thunderstore.io/package/denikson/BepInExPack_Valheim/)
- Thunderstore: [Jotunn](https://thunderstore.io/package/ValheimModding/Jotunn/)
- Thunderstore: [R2API.Core](https://thunderstore.io/package/RiskofThunder/R2API_Core/)
- Thunderstore: [LC_API](https://thunderstore.io/package/2018/LC_API/)

## What the packages actually contain

### Loader layer

BepInEx packs are not just a DLL. A usable loader package contains:

- `doorstop_config.ini` and the platform doorstop library
- `BepInEx/core` runtime assemblies
- a game-specific `BepInEx.cfg`
- a log channel and startup path
- loader/version metadata
- installation and update notes

Valheim's pack is explicitly game-tuned: entry point, Linux/server scripts, loader flags and compatibility patches. AI Mod Builder should model this as a loader profile, not a generic `install BepInEx` action.

### Library/API layer

Jotunn, R2API.Core and LC_API expose stable abstractions:

- item, creature, prefab, recipe and localization managers
- command/input/UI managers
- network compatibility and config synchronization
- event hooks for gameplay systems
- versioned dependencies on the loader and other API modules

These are the best source of real hook names and implementation patterns. They should be treated as first-class evidence providers for plan and code generation.

### Content/mod layer

Real content mods commonly combine:

- code/plugin entry point
- loader/API dependency
- configuration
- assets such as textures, models, sounds and prefabs
- localization
- compatibility/version metadata
- install and uninstall instructions
- changelog and license

This means a generated mod should declare its dependency graph and artifact set before code generation. A single `main.lua` or `Plugin.cs` is only the code slice of a larger package.

## Observed rules for AI Mod Builder

1. Resolve loader and API prerequisites first. Never generate a plugin for a loader that is absent or incompatible.
2. Store exact dependency versions in `ModSpec` and `mod.json`.
3. Separate code, config, assets and localization into explicit artifact groups.
4. Prefer official library managers and public API methods over guessed class names.
5. Preserve game-specific entry points and loader profiles. Valheim BepInEx is not identical to generic BepInEx.
6. Validate package shape before install: manifest, README/license, entry point, dependency versions and payload paths.
7. Record observed evidence separately from heuristic suggestions. A community symbol is not proof that it exists in the target game build.
8. Keep a compatibility record for game version, loader version, API version and target platform.
9. Make every install reversible and verify the final file tree before and after.
10. Refuse anti-cheat-protected or online-only targets. This repository only supports single-player/offline games the user owns.

## Target architecture

```text
game discovery
→ engine + build profile
→ loader/API capability profile
→ package shape and dependency plan
→ REA / dump / loader API evidence
→ normalized HookTarget
→ code + config + assets + localization
→ package validation
→ dry-run diff
→ transactional install
→ runtime log/behavior verification
→ uninstall or rollback
```

The implementation should never jump directly from a user prompt to a guessed hook. The package shape and evidence chain are part of the product.
