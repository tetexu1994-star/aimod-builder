# game-mod-agent 架构

## 一句话

一个 MCP 工具服务器，让 AI agent（Claude Code 等）能"看懂并修改"单机 PC 游戏。
核心是一套**稳定的能力接口** + **每引擎一个适配器**；加引擎不改核心。

## 分层

```
[1] 交互层          Claude Code / Codex / Cursor (MCP stdio) 
                    + 本地可视化工作台 (agmod.ui Web SPA @ 127.0.0.1:8765)
        │
[2] 工具/API层      server.py (FastMCP 45+ tools) + agmod/ui/server.py (REST API)
        │
[3] 适配器层        agmod/adapters/ —— 统一接口，每引擎一个（17 个）
        │
[4] 能力模块        planning / bepinex / tmodloader / memory / updater / rea / pack /
                    knowledge / codegen / log_repair / process / rollback / saves
        │
[5] 目标游戏进程 / 文件
```

详细 UI 交互工作台架构、REST API 契约与六大工作区设计请查阅根目录 [UI_ARCHITECTURE.md](../UI_ARCHITECTURE.md)。


## 能力接口（BaseAdapter）

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

## 数据流（"给主角加金币"）

```
detect_engine → dump_structures(prepare) → find_field(query)
  → find_process → scan_value / write_memory → read_memory 验证
```

## 关键设计（为什么"稳"）

- **数据驱动的引擎目录**（`engines.py`）：17 个引擎，每个带识别标记 + 前置 mod 框架 + 看懂方式。加引擎 = 加一条数据，或写一个深度适配器，核心零改动。
- **版本指纹缓存**（`structures.py`）：结构 dump 按游戏构建指纹缓存，版本变了不会用旧偏移改崩游戏。
- **安全护栏**（`safety.py`）：代码级拒绝反作弊进程 + `write_memory` 的 dry_run 预览。
- **知识库**（`knowledge.py`）：游戏字段笔记持久化，避免重复逆向。
- **mod 生命周期**：scaffold → build → package → check/update（GitHub 轮询自动更新）。
- **需求工作流**：`plan_mod` 将自然语言请求固化为 `mod-spec.json`、`request.md`、`MODDING_PLAN.md`，再由 adapter 生成引擎骨架；`validate_mod_project` 在 build/install/package 前校验入口和必需文件。

## 扩展点

- 加引擎：`engines.py` 加一条（目录级），或写深度适配器（能 prepare/query/source）。
- 加能力：`BaseAdapter` 加方法 + 适配器在 `capabilities` 里声明。
- 加发布平台：`pack.py` 加打包格式（当前 Thunderstore 风格 zip）。

## 平台

核心跨平台；**内存读写是 Windows-only**（`memory.py` 有 `IS_WINDOWS` 护栏，在 Mac 上正常 import、调用时返回清晰报错）。
