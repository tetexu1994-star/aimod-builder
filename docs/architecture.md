# game-mod-agent 架构

## 一句话

一个 MCP 工具服务器，让 AI agent（Claude Code 等）能"看懂并修改"单机 PC 游戏。
核心是一套**稳定的能力接口** + **每引擎一个适配器**；加引擎不改核心。

## 分层

```
[1] 交互层          Claude Code / Codex / Cursor (MCP stdio) 
                    + 本地独立桌面工作台 (AIModBuilder.exe 原生窗口 / Web SPA @ 127.0.0.1:8765)
        │
[2] 工具/API层      server.py (FastMCP 45+ tools) + agmod/ui/server.py (REST API)
        │
[3] 适配器与生态层  agmod/adapters/ —— 统一接口，覆盖 Nexus Mods 核心 21+ 款引擎
                    + agmod/frameworks.py (专有前置加载器自检: tModLoader/SMAPI/SKSE/BG3SE/ModEngine2 等)
        │
[4] 能力模块        planning / bepinex / tmodloader / memory / updater / rea / pack /
                    knowledge / codegen / log_repair / process / rollback / saves / sdk
        │
[5] 目标游戏进程 / 文件
```

详细 UI 交互工作台架构、桌面启动器与 REST API 契约请查阅根目录 [UI_ARCHITECTURE.md](../UI_ARCHITECTURE.md)。
关于 **Nexus Mods (N网) 头部 20+ 款 3A 及热门单机游戏的前置架构与部署矩阵**，请查阅专门文档 [nexus_mods_matrix.md](nexus_mods_matrix.md)。


## 核心能力接口（BaseAdapter）

| 能力 | 必做 | 含义 |
|---|---|---|
| detect | ✅ | 目录是否属于该引擎 |
| fingerprint | ✅ | 构建版本指纹（缓存键） |
| prepare | ✅ | 恢复结构（"看懂"） |
| query | 可选 | 在结构里搜字段/类型 |
| source | 可选 | 取某类型/函数的反编译源码 |
| script | 可选 | 为某个目标生成 mod 脚本/工程 |
| launch | 可选 | 定位游戏可执行文件 |

适配器用 `capabilities` 声明自己真正实现了哪些能力；可选能力默认返回空、不报错，调用方优雅降级。

## 数据流（"给主角加金币 / 制作持久 Mod"）

```
detect_engine + detect_game_framework
  → dump_structures(prepare) → find_field / rea_members(query)
  → generate_hook_from_evidence (C# Harmony / UE4SS Lua / CET Lua / REFramework Lua / Papyrus)
  → auto_deploy_mod (编译 DLL / 写入 Mods 目录 / 部署 manifest.json)
  → 校验构建结果 (拦截大模型幻觉，强一致状态仲裁)
  → 一键拉起或重启游戏进程验证
```

## 关键设计（为什么"稳"）

- **数据驱动的引擎目录与 N网矩阵**（`engines.py` & `nexus_mods_matrix.md`）：全面覆盖 Unreal (UE4/UE5)、Unity (Mono/IL2CPP)、RE Engine (怪猎/生化)、Bethesda (天际/辐射/星空)、FromSoftware (法环/只狼/魂系)、REDengine (2077/巫师3)、Divinity (博德之门3)、TaleWorlds (骑砍2)、.NET-XNA (泰拉瑞亚/星露谷) 等 21 个引擎家族。
- **前置模组生态智能自检**（`frameworks.py`）：自动扫描游戏安装目录及 Steam 库，秒级识别 tModLoader、SMAPI、SKSE64、F4SE、BG3SE (DWrite.dll)、Mod Engine 2、CET、REDmod、REFramework、UE4SS 等專属前置状态；缺失时自动在控制台呈现一键直达安装指引。
- **双轨部署机制（Dual-Pathway Deployment）**：
  - 官方加载器路径：检测到 tModLoader/SMAPI/Mod Engine 2 时自动按照其标准打包并写入相应 `Mods/`、`mod/` 或 `ModLoader/` 目录；
  - 原生底层注入路径：纯净原版客户端支持利用 BepInEx / Doorstop 原生挂载 DLL 插件，开箱即用。
- **构建状态强一致仲裁（防大模型幻觉）**：编译结果作为事实唯一来源。一旦本地编译未通过，底层强制拦截大模型生成的虚假成功话术，下发明确的编译器诊断日志，并强制禁用一键重启催促，根绝前后矛盾。
- **多语言/多框架代码生成**（`codegen.py`）：支持将符号特征一键输出为规范的 C# (Harmony)、Lua (UE4SS / REFramework / CET)、Papyrus、GDScript 代码。
- **版本指纹缓存**（`structures.py`）：结构 dump 按游戏构建指纹缓存，版本变了不会用旧偏移改崩游戏。
- **安全护栏**（`safety.py`）：代码级拒绝反作弊进程 + `write_memory` 的 dry_run 预览。
- **知识库**（`knowledge.py`）：游戏字段笔记持久化，避免重复逆向。
- **便携式运行时与零依赖工具链**（`sdk.py` / `Launcher.cs`）：
  - 免安装便携式 .NET SDK 与独立 Roslyn `csc.exe` 自动化按需下载引导，摆脱系统环境依赖。
  - C# 原生启动器 `AIModBuilder.exe`（单例 Mutex 防多开），拉起独立应用模式窗口，关闭窗口自动杀死后台 Python 进程，不留残留。
  - 内置免配置 Python 3.11 Runtime，整包发布体积极限压缩至 11 MB。
- **3A 游戏逆向生态支持**：
  - MelonLoader IL2CPP 元数据校验（准确识别 `global-metadata.dat`）。
  - CUE4Parse 无头解析虚幻引擎 Pak/IoStore 资源。
  - UAssetGUI 自动化 JSON 资产逆向与写回。
  - ilspycmd 无头程序集反编译集成。
  - UI 校验接口 `/api/mods/verify` 闭环。

## 扩展点

- 加引擎：`engines.py` 加一条（目录级），或写深度适配器（能 prepare/query/source）。
- 加能力：`BaseAdapter` 加方法 + 适配器在 `capabilities` 里声明。
- 加发布平台：`pack.py` 加打包格式（当前 Thunderstore 风格 zip）。

## 平台

核心跨平台；**内存读写是 Windows-only**（`memory.py` 有 `IS_WINDOWS` 护栏，在 Mac 上正常 import、调用时返回清晰报错）。
Windows 发行版提供完整打包的绿色独立客户端包 `AIModBuilder_v1.0_Win64.zip`。
