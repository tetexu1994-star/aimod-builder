"""Unreal Engine (UE4 / UE5) adapter.

Two distinct modding paths:
  - UE4SS (Lua scripting): reliable for UE4, experimental on UE5 — NOT the default.
  - loose `.pak` override mods (repak / UnrealPak -> Content/Paks/~mods/): a
    compiler-free route where the game still loads loose paks. IoStore
    `.utoc/.ucas` containers must be extracted with FModel/CUE4Parse; repak does
    not read or write those containers.
"""
from __future__ import annotations

import glob
import os

from .. import rollback
from ..manifest import ModManifest
from ..paths import safe_component
from ..structures import StructureTable, fingerprint_files
from .base import BaseAdapter


class UnrealAdapter(BaseAdapter):
    id = "unreal"
    runtime = "unreal"
    name = "Unreal Engine (UE4 / UE5)"
    mod_framework = "pak 覆盖 (repak / UnrealPak) + UE4SS Lua (仅 UE4 稳定)"
    structure = "FModel / repak 解包资源；UE4SS dumper 仅 UE4 反射"
    capabilities = ("detect", "fingerprint", "prepare", "launch")

    def _variant(self, game_dir: str) -> str | None:
        """Return 'ue5' (IoStore) or 'ue4' (legacy pak) for an Unreal game."""
        ue5_patterns = [
            "Content/Paks/*.utoc", "Content/Paks/*.ucas",
            "*/*/Content/Paks/*.utoc", "*/*/Content/Paks/*.ucas",
            "*/Content/Paks/*.utoc", "*/Content/Paks/*.ucas",
        ]
        for pat in ue5_patterns:
            if glob.glob(os.path.join(game_dir, pat)):
                return "ue5"
        ue4_patterns = [
            "Content/Paks/*.pak", "*/*/Content/Paks/*.pak", "*/Content/Paks/*.pak",
        ]
        for pat in ue4_patterns:
            if glob.glob(os.path.join(game_dir, pat)):
                return "ue4"
        return None

    def _matched_files(self, game_dir: str) -> list[str]:
        hits = []
        patterns = [
            "*.uproject",
            "Content/Paks/*.pak",
            "Content/Paks/*.utoc",
            "Content/Paks/*.ucas",
            "Engine/Binaries/Win64/*.dll",
            "*/*-Shipping.exe",
            "*/*/Binaries/Win64/*-Shipping.exe",
        ]
        for pat in patterns:
            for p in glob.glob(os.path.join(game_dir, pat)):
                if os.path.isfile(p):
                    hits.append(p)
        return hits

    def detect(self, game_dir: str) -> bool:
        if not os.path.isdir(game_dir):
            return False
        if glob.glob(os.path.join(game_dir, "*.uproject")):
            return True
        if os.path.isdir(os.path.join(game_dir, "Engine", "Binaries")) or os.path.isdir(os.path.join(game_dir, "Engine")):
            return True
        if glob.glob(os.path.join(game_dir, "*", "Content", "Paks")):
            return True
        if glob.glob(os.path.join(game_dir, "Content", "Paks", "*.pak")) or glob.glob(os.path.join(game_dir, "Content", "Paks", "*.ucas")):
            return True
        if glob.glob(os.path.join(game_dir, "*", "Content", "Paks", "*.pak")) or glob.glob(os.path.join(game_dir, "*", "Content", "Paks", "*.ucas")):
            return True
        if glob.glob(os.path.join(game_dir, "*", "Binaries", "Win64", "*-Shipping.exe")):
            return True
        return False

    def fingerprint(self, game_dir: str) -> str:
        return fingerprint_files(self._matched_files(game_dir))

    def prepare(self, game_dir: str, cache_root: str) -> StructureTable:
        files = self._matched_files(game_dir)
        variant = self._variant(game_dir)
        if variant == "ue5":
            guidance = (
                "UE5 (IoStore)：资源定位需 FModel/CUE4Parse 解包 .utoc/.ucas；repak 只处理 .pak。"
                "若游戏确认支持 loose pak，可把覆盖包放入 Content/Paks/~mods/。UE4SS Lua 不作为默认。"
            )
        else:
            guidance = (
                "UE4：可用 UE4SS Lua（放入 Binaries/Win64/）或 pak 覆盖（UnrealPak 打包到 ~mods/）。"
            )
        return StructureTable(
            game_id=os.path.basename(os.path.normpath(game_dir)),
            engine=self.id,
            variant=variant or self.runtime,
            fingerprint=self.fingerprint(game_dir),
            files=[os.path.relpath(p, game_dir) for p in files[:20]],
            guidance=guidance,
        )

    def launch(self, game_dir: str) -> dict | None:
        shippings = glob.glob(os.path.join(game_dir, "*", "Binaries", "Win64", "*-Shipping.exe"))
        if not shippings:
            shippings = glob.glob(os.path.join(game_dir, "*.exe"))
        if shippings:
            return {"exe": shippings[0], "variant": self._variant(game_dir) or "unknown"}
        return None

    # --- UE4SS Lua path (UE4 only) ---

    def scaffold_mod(
        self,
        project_dir: str,
        mod_id: str,
        mod_name: str,
        mod_version: str = "1.0.0",
        author: str = "AI Mod Agent",
    ) -> str:
        """Generate a UE4SS Lua mod skeleton (reliable for UE4 only)."""
        mod_id = safe_component(mod_id, "mod_id")
        lua_name = str(mod_name).replace("\\", "\\\\").replace('"', '\\"').replace("\n", " ")
        scripts_dir = os.path.join(project_dir, "scripts")
        os.makedirs(scripts_dir, exist_ok=True)

        with open(os.path.join(project_dir, "enabled.txt"), "w", encoding="utf-8") as f:
            f.write("1\n")

        ModManifest(
            id=mod_id,
            name=mod_name,
            version=mod_version,
            engine="unreal",
            author=author,
            entry="scripts/main.lua",
            description="UE4SS Lua mod (UE4)",
        ).save(os.path.join(project_dir, "mod.json"))

        lua_template = f"""-- {lua_name} (ID: {mod_id})
-- Built with game-mod-agent for UE4SS (UE4 Lua API)

local ModRef = "{lua_name}"
print(string.format("[%s] Initialized successfully!", ModRef))

-- RegisterHook("/Script/Engine.PlayerController:ClientRestart", function(self, newPawn)
--     print(string.format("[%s] Player restarted!", ModRef))
-- end)
"""
        with open(os.path.join(scripts_dir, "main.lua"), "w", encoding="utf-8") as f:
            f.write(lua_template)

        return project_dir

    def install_mod(self, project_dir: str, game_dir: str, mod_id: str) -> str:
        """Install a UE4SS Lua mod into Binaries/Win64/ue4ss/Mods/<mod_id>/."""
        mod_id = safe_component(mod_id, "mod_id")
        if self._variant(game_dir) == "ue5":
            raise RuntimeError("UE4SS install is not supported for the detected UE5 IoStore layout; use a verified loose .pak override instead")
        target_candidates = glob.glob(os.path.join(game_dir, "*", "Binaries", "Win64"))
        if not target_candidates:
            target_candidates = [os.path.join(game_dir, "Binaries", "Win64")]

        win64_dir = target_candidates[0]
        mods_dir = os.path.join(win64_dir, "ue4ss", "Mods", mod_id)
        if not os.path.exists(os.path.join(win64_dir, "ue4ss")):
            mods_dir = os.path.join(win64_dir, "Mods", mod_id)
        os.makedirs(mods_dir, exist_ok=True)

        pairs = []
        for item in os.listdir(project_dir):
            s = os.path.join(project_dir, item)
            d = os.path.join(mods_dir, item)
            if os.path.isdir(s):
                for root, _, files in os.walk(s):
                    for fn in files:
                        src = os.path.join(root, fn)
                        pairs.append((src, os.path.join(d, os.path.relpath(src, s))))
            else:
                pairs.append((s, d))

        rollback.install_files(game_dir, mod_id, pairs)
        return mods_dir

    # --- pak override path (UE4 + UE5, the reliable default) ---

    def scaffold_pak_mod(
        self,
        project_dir: str,
        mod_id: str,
        mod_name: str,
        mod_version: str = "1.0.0",
        author: str = "AI Mod Agent",
    ) -> str:
        """Generate a loose `.pak` override skeleton; game support must be verified."""
        mod_id = safe_component(mod_id, "mod_id")
        os.makedirs(project_dir, exist_ok=True)

        override_dir = os.path.join(project_dir, "override")
        os.makedirs(override_dir, exist_ok=True)

        ModManifest(
            id=mod_id,
            name=mod_name,
            version=mod_version,
            engine="unreal",
            author=author,
            entry="",
            description="Unreal pak 文件覆盖 mod",
        ).save(os.path.join(project_dir, "mod.json"))

        with open(os.path.join(project_dir, "README.md"), "w", encoding="utf-8") as f:
            f.write(f"""# {mod_name} (pak 覆盖 mod)

## 流程

1. 解包游戏资源定位要改的文件（`.pak` 用 repak；UE5 IoStore `.utoc/.ucas` 用 FModel / CUE4Parse）。
2. 把修改后的文件按游戏内相对路径放进 `override/`。
3. 打包成 `.pak`：
   - `.pak`：`repak pack override {mod_id}.pak`
   - 也可使用游戏/引擎自带的 `UnrealPak.exe`。
4. 把生成的 `.pak` 放到 `dist/`，然后点「安装」自动装入 `Content/Paks/~mods/`。

> IoStore-only 游戏不一定加载 loose `.pak`。安装前必须在目标游戏版本上确认 `~mods` 覆盖有效。
""")

        return project_dir

    def install_pak_mod(self, project_dir: str, game_dir: str, mod_id: str) -> str:
        """Install a built .pak override mod into Content/Paks/~mods/."""
        mod_id = safe_component(mod_id, "mod_id")
        expected = os.path.join(project_dir, "dist", f"{mod_id}.pak")
        if os.path.isfile(expected):
            pak_files = [expected]
        else:
            pak_files = glob.glob(os.path.join(project_dir, "dist", "*.pak"))
            if not pak_files:
                pak_files = glob.glob(os.path.join(project_dir, "*.pak"))
        if not pak_files:
            raise ValueError("no built .pak found in dist/; run repak/UnrealPak to pack first")
        if len(pak_files) > 1:
            raise ValueError("multiple .pak files found; keep only the built mod package in dist/")

        paks_dirs = self._content_paks_dirs(game_dir)
        if not paks_dirs:
            paks_dirs = [os.path.join(game_dir, "Content", "Paks")]
        mods_dir = os.path.join(paks_dirs[0], "~mods")
        os.makedirs(mods_dir, exist_ok=True)

        pairs = [(p, os.path.join(mods_dir, os.path.basename(p))) for p in pak_files]
        rollback.install_files(game_dir, mod_id, pairs)
        return mods_dir

    def pack_pak_mod(self, project_dir: str, game_dir: str, mod_id: str) -> str:
        """Pack override/ into a loose dist/<mod_id>.pak archive with repak."""
        mod_id = safe_component(mod_id, "mod_id")
        variant = self._variant(game_dir)
        override_dir = os.path.join(project_dir, "override")
        if not os.path.isdir(override_dir) or not os.listdir(override_dir):
            raise ValueError("override/ is empty; add overridden files first")

        if variant not in {"ue4", "ue5"}:
            raise RuntimeError("Unreal container type could not be verified; add a game .pak or .utoc marker first")

        from .. import repak
        out_pak = os.path.join(project_dir, "dist", f"{mod_id}.pak")
        os.makedirs(os.path.dirname(out_pak), exist_ok=True)
        return repak.pack_override(override_dir, out_pak)

    def unpack_pak(self, game_dir: str, pak_path: str, out_dir: str) -> str:
        """Unpack a loose `.pak` archive for inspection with repak.

        If `pak_path` is empty, use the largest `.pak`. IoStore `.utoc/.ucas`
        containers are rejected because repak cannot parse them.
        """
        from .. import repak
        if pak_path:
            game_root = os.path.realpath(game_dir)
            candidate = os.path.abspath(os.path.join(game_root, pak_path))
            if os.path.commonpath([game_root, os.path.realpath(candidate)]) != game_root:
                raise ValueError("pak_path escapes game_dir")
            pak_path = candidate
        else:
            paks = [os.path.join(game_dir, p) for p in self.list_paks(game_dir) if p.lower().endswith(".pak")]
            if not paks:
                raise ValueError("no loose .pak archive found; IoStore .utoc/.ucas requires FModel/CUE4Parse")
            pak_path = max(paks, key=os.path.getsize)
        if not os.path.isfile(pak_path):
            raise ValueError(f"pak archive not found: {pak_path}")
        if pak_path.lower().endswith((".utoc", ".ucas")):
            raise ValueError("IoStore .utoc/.ucas is not supported by repak; use FModel/CUE4Parse")
        if not pak_path.lower().endswith(".pak"):
            raise ValueError("repak can only unpack .pak archives")
        return repak.unpack(pak_path, out_dir)

    def _content_paks_dirs(self, game_dir: str) -> list[str]:
        roots = glob.glob(os.path.join(game_dir, "*", "Content", "Paks")) + [
            os.path.join(game_dir, "Content", "Paks"),
            os.path.join(game_dir, "*", "*", "Content", "Paks"),
        ]
        found = []
        for pattern in roots:
            for path in glob.glob(pattern) if "*" in pattern else [pattern]:
                if os.path.isdir(path):
                    found.append(path)
        return sorted(set(found), key=lambda p: (os.path.dirname(p).lower().endswith("engine"), p.lower()))

    def list_paks(self, game_dir: str) -> list[str]:
        """Return relative paths of all pak/IoStore archives in the game directory."""
        seen = set()
        result = []
        patterns = [
            os.path.join("*", "Content", "Paks", pat)
            for pat in ("*.pak", "*.utoc", "*.ucas")
        ] + [
            os.path.join("*", "*", "Content", "Paks", pat)
            for pat in ("*.pak", "*.utoc", "*.ucas")
        ] + [
            os.path.join("Content", "Paks", pat)
            for pat in ("*.pak", "*.utoc", "*.ucas")
        ]
        for pattern in patterns:
            for p in glob.glob(os.path.join(game_dir, pattern)):
                if not os.path.isfile(p):
                    continue
                rel = os.path.relpath(p, game_dir).replace("\\", "/")
                key = rel.lower()
                if key not in seen:
                    seen.add(key)
                    result.append(rel)
        return sorted(result)

    def list_configs(self, game_dir: str) -> list[str]:
        """Return relative paths of all .ini config files (the common 'tweak values' entry)."""
        seen = set()
        result = []
        roots = [
            os.path.join(game_dir, "Saved", "Config"),
            os.path.join(game_dir, "Config"),
        ]
        for sub in glob.glob(os.path.join(game_dir, "*", "Saved", "Config")):
            roots.append(sub)
        for sub in glob.glob(os.path.join(game_dir, "*", "Config")):
            roots.append(sub)
        for root in roots:
            for p in glob.glob(os.path.join(root, "**", "*.ini"), recursive=True):
                if not os.path.isfile(p):
                    continue
                rel = os.path.relpath(p, game_dir).replace("\\", "/")
                key = rel.lower()
                if key not in seen:
                    seen.add(key)
                    result.append(rel)
        return sorted(result)
