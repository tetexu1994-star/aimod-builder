# game-mod-agent

一个让 AI agent（Claude Code 等）能"看懂并修改"单机 PC 游戏的 MCP 工具服务器。

**核心设计**：一套稳定的统一接口（`prepare` 看懂 / `query` 查询 / 内存读写 / 值扫描），
每个游戏引擎只做一个适配器插件。加新引擎不改核心，只加一个文件。

```
game-mod-agent/
├── server.py              # MCP 服务（工具入口）
├── agmod/
│   ├── memory.py          # 进程内存读写 + 值扫描（纯 ctypes，无依赖）
│   ├── structures.py      # 结构表 + 版本指纹 + 磁盘缓存
│   ├── registry.py        # 适配器注册 + 引擎识别
│   └── adapters/
│       ├── base.py        # BaseAdapter 统一接口
│       └── unity.py       # Unity（Mono / IL2CPP）
├── AGENT_PROMPT.md        # 给 agent 的系统提示词（工作流 + 红线）
├── mcp_config.json        # Claude Code 注册示例
└── mods/                  # 结构缓存（自动生成）
```

## 已实现的工具

| 工具 | 作用 | 依赖 |
|---|---|---|
| `detect_engine` | 识别游戏引擎（Unity / .NET-XNA） | 无 |
| `dump_structures` | 恢复结构（反编译/dump） | Mono: ilspycmd；IL2CPP: Cpp2IL |
| `find_field` | 在结构里搜字段名 | dump 之后 |
| `find_process` | 按名字找进程 pid | psutil |
| `scan_value` | Cheat-Engine 式值扫描 | 无 |
| `read_memory` / `write_memory` | 读写目标进程内存（临时改值） | 无 |
| `install_bepinex` | 安装 BepInEx 前置 mod loader | 网络 |
| `scaffold_mod` | 生成 BepInEx 插件工程 | 无 |
| `build_mod` | 编译插件并装入 BepInEx/plugins | .NET SDK |
| `check_update` | 查 GitHub 是否有新版本 | 网络 |
| `update_mod` | 拉取新版插件 DLL 并替换 | 网络 |
| `catalog` | 列出支持的引擎/适配器 | 无 |
| `scaffold_tmod_mod` | 生成 tModLoader mod 骨架（Terraria） | 无 |
| `build_tmod_mod` | 编译 tModLoader mod | .NET 6 SDK |

**内存读写和值扫描今天就能用**（纯 ctypes）。结构 dump 需要装一个反编译工具。

## 安装

1. Python 3.10+，装依赖：

```bash
pip install -r requirements.txt
```

2. 装 Unity 反编译工具（二选一，按你的游戏）：

```bash
# Mono 游戏（有 *_Data/Managed/Assembly-CSharp.dll）
dotnet tool install -g ilspycmd

# IL2CPP 游戏（有 GameAssembly.dll + global-metadata.dat）
# 下载 Cpp2IL 或 Il2CppDumper，放到 PATH
```

## 注册到 Claude Code

把 `mcp_config.json` 的内容合并进项目的 `.mcp.json`（或用户级配置），
然后重启 Claude Code。或者直接 `claude mcp add game-mod-agent -- python <绝对路径>/server.py`。

## 使用示例（对 Claude Code 说）

```
我有个 Unity 单机游戏在 D:\Games\MyGame，给主角加 99999 金币。
```

Agent 会自动：`detect_engine` → `dump_structures` → `find_field("gold")` →
`find_process` 拿 pid → `scan_value` 或直接读 → `write_memory` → `read_memory` 验证。

## 持久化 Mod 生命周期（BepInEx + 自动更新）

改内存是临时的（重启就没了）。要做成真正的 Mod，走 BepInEx 插件：

1. `install_bepinex(game_dir)` —— 装前置 mod loader。
2. `scaffold_mod(project_dir, game_dir, mod_id, mod_name)` —— 生成 Plugin.cs + .csproj 模板。
3. 编辑 Plugin.cs 加入 Harmony patch（真正改游戏逻辑的部分）。
4. `build_mod(project_dir, game_dir)` —— `dotnet build` 并把 DLL 装进 `BepInEx/plugins/`。

自动更新：Mod 源码放 GitHub，用 GitHub Actions 在 push 时编译并发布 release（附 DLL 资产）。客户端侧：

- `check_update(owner, repo, current_version)` —— 对比 GitHub 最新 release/commit；
- `update_mod(game_dir, owner, repo, entry_dll)` —— 下载新版 DLL 替换旧的。

> 真正的"实时"是 webhook 推送给客户端；对桌面 Mod 而言，轮询 GitHub API（每次会话或启动时查一次）是最省事、最稳的做法。

配套：每个 mod 项目带一个 `mod.json`（id/name/version/engine/repo/entry），是更新和打包的单一事实来源；[templates/build-release.yml](templates/build-release.yml) 是一份 GitHub Actions 模板，push 到 tag `v*` 时自动编译并把 DLL 发成 release，`update_mod` 就能拉到。写内存前可用 `write_memory(..., dry_run=True)` 先预览再真写。

## 支持的引擎（按前置 mod 框架分类）

每个引擎一个适配器，识别 + 告诉你该用哪个前置框架、怎么"看懂"。引擎清单参考了 Universal Modder 的引擎分类。

| 引擎 | 前置 mod 框架 | 看懂方式 |
|---|---|---|
| Unity (Mono/IL2CPP) | BepInEx / MelonLoader | ilspycmd (Mono) / Il2CppDumper·Cpp2IL (IL2CPP) |
| .NET / XNA / FNA (Terraria 等) | tModLoader / SMAPI | ilspycmd / dnSpy |
| Unreal Engine (UE4/5) | UE4SS + pak 覆盖 | 反射 dump（UE4SS / Dumper-7） |
| Capcom RE Engine（怪猎崛起/荒野、生化、鬼泣5等） | REFramework + Fluffy Mod Manager | REFramework / FirstNatives 解 PAK |
| Capcom MT Framework（怪物猎人世界） | Stracker's Loader + nativePC | nativePC 覆盖 / REFramework Lua |
| Godot (3/4) | GDExtension / .pck 解包 | gdunpack / godotpcktool |
| Source / Source 2 | SourceMod / VScript | VPK 工具 |
| Bethesda（老滚/辐射/星空） | SKSE / F4SE / SFSE + Papyrus | xEdit / zEdit |
| FromSoftware（法环/只狼/黑魂） | ModEngine2 | WitchyBND / Smithbox |
| Rockstar RAGE（GTA/RDR2） | Script Hook V / RPH | OpenIV |
| CDPR REDengine（巫师3/2077） | RED4ext + Redscript / WitcherScript | WolvenKit |
| Minecraft (Java) | Fabric / Forge / NeoForge + Mixin | Vineflower / CFR |
| GameMaker | UndertaleModTool | UTMT |
| RPG Maker (MV/MZ/VX) | 插件 .js / Ruby | data/*.json |
| id Tech（DOOM/Quake） | GZDoom source port | WAD 工具 |
| Electron / Web | 改 app.asar JS | asar 解包 / rea |
| Ren'Py 视觉小说 | unrpa + .rpy | unrpa / rpatool |
| 原生 / 自定义引擎 | 注入 + Cheat Engine / Frida | Ghidra / IDA + 值扫描 |

**rea 集成**：`rea_managed_members` / `rea_inspect_pe` / `rea_analyze_js` 三个工具直接调用 morluto/rea 的静态分析能力（.NET 成员清单、PE 资源、JS 模块图），补上不装反编译器也能看结构的路子。

## 安全红线

单机、离线、用户自有游戏。禁止对反作弊在线游戏 attach/扫描/注入。
本项目是教学与自用工具，不附带任何游戏文件、不提供绕过 DRM 或联机作弊能力。
