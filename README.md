# game-mod-agent

一个让 AI agent（Claude Code 等）能"看懂并修改"单机 PC 游戏的 MCP 工具服务器。

**核心设计**：一套稳定的统一接口（`prepare` 看懂 / `query` 查询 / 内存读写 / 连续值扫描 / AOB 特征码），
每个游戏引擎只做一个适配器插件。加新引擎不改核心，只加一个文件。

```
game-mod-agent/
├── server.py              # MCP 服务（工具入口）
├── agmod/
│   ├── memory.py          # 进程内存读写 + Cheat Engine 式连续会话扫描（纯 ctypes，无依赖）
│   ├── pattern.py         # AOB 字节特征码与通配符签名扫描（防游戏更新偏移失效）
│   ├── inspector.py       # 智能特征与意图分析器（一键侦测引擎+符号+方案）
│   ├── rea.py             # morluto/rea 逆向桥接（原生反编译、调用图、成员快搜）
│   ├── structures.py      # 结构表 + 版本指纹 + 磁盘缓存
│   ├── registry.py        # 适配器注册 + 引擎识别
│   └── adapters/
│       ├── base.py        # BaseAdapter 统一接口
│       ├── unity.py       # Unity（Mono / IL2CPP）
│       └── unreal.py      # Unreal Engine（UE4 / UE5 免编译 Lua Mod）
├── AGENT_PROMPT.md        # 给 agent 的系统提示词（工作流 + 红线）
├── mcp_config.json        # Claude Code 注册示例
└── mods/                  # 结构缓存（自动生成）
```

## 已实现的工具

| 工具 | 作用 | 依赖 |
|---|---|---|
| `check_environment` | **环境健康自检 (Doctor)**：检查 Python、.NET SDK、反编译工具与 REA 就绪状态 | 无 |
| `inspect_feature` | **一键意图侦测**：自动识别引擎、秒级检索字段并推荐最佳方案 | 无 |
| `plan_mod` | **自然语言生成 Mod 项目计划**：输出 ModSpec、MODDING_PLAN 和引擎骨架 | 无 |
| `validate_mod_project` | 校验 ModSpec、入口文件和引擎必需文件 | 无 |
| `detect_engine` | 识别游戏引擎（Unity / Unreal / .NET-XNA 等） | 无 |
| `dump_structures` | 恢复结构（反编译/dump） | Mono: ilspycmd；IL2CPP: Cpp2IL |
| `find_field` | 在结构里搜字段名 | dump 之后 |
| `find_process` | 按名字找进程 pid | psutil |
| `scan_start` | **连续扫描初扫**：记录所有候选地址建立 ScanSession | 无 |
| `scan_next` | **连续扫描过滤**：游戏数值改变后再次筛选，收敛到唯一地址 | 无 |
| `scan_reset` | 清除扫描会话 | 无 |
| `pattern_scan` | **AOB 特征码扫描**：用带通配符的机器码签名查找函数（防更新） | 无 |
| `read_memory` / `write_memory` | 读写目标进程内存（临时改值） | 无 |
| `install_bepinex` | 安装 BepInEx 前置 mod loader (Unity) | 网络 |
| `scaffold_mod` | 生成 BepInEx 插件工程 (Unity) | 无 |
| `build_mod` | 编译插件并装入 BepInEx/plugins（**支持自动解析报错并自愈重试**） | .NET SDK |
| `diagnose_build_error` | **编译报错诊断器**：解析 CSxxxx 错误并生成针对性修复代码建议 | 无 |
| `scaffold_ue4ss_mod` | **生成 UE4SS 免编译 Lua Mod 工程 (Unreal Engine 4/5)** | 无 |
| `install_ue4ss_mod` | 安装 UE4SS Lua Mod 至游戏目录 | 无 |
| `scaffold_tmod_mod` | 生成 tModLoader mod 骨架（Terraria） | 无 |
| `build_tmod_mod` | 编译 tModLoader mod | .NET 6 SDK |
| `rea_fast_search` | 秒级搜索 .NET 成员（免全量反编译） | morluto/rea |
| `rea_disassemble` | 反汇编/反编译指定 Native 函数 | morluto/rea |
| `read_mod_logs` | **运行时日志诊断**：查看 BepInEx/UE4SS/tModLoader 日志并自动检测异常 | 无 |
| `create_save_backup` | **存档快照备份**：修改内存或安装 Mod 前一键安全备份游戏存档 | 无 |
| `list_save_backups` | 列出该游戏的所有存档快照历史 | 无 |
| `restore_save_backup` | **安全还原存档**：遭遇坏档时一键安全还原历史快照 | 无 |
| `check_update` / `update_mod` | 检查并拉取 GitHub 最新版本 Mod DLL | 网络 |
| `package_mod` | 打包 Mod 为 Thunderstore/Nexus 风格 ZIP；编译型 Mod 必须先 build，UE4SS Lua Mod 可直接打包源文件 | 无 |

**内存读写和连续值扫描今天就能用**（纯 ctypes）。终端执行 `python -m agmod.doctor` 可一键查看本机开发环境就绪度。

## 安装

1. Python 3.10+，装依赖：

```bash
pip install -r requirements.txt
```

2. 装 Unity 反编译工具（可选，按需安装）：

```bash
# Mono 游戏（有 *_Data/Managed/Assembly-CSharp.dll）
dotnet tool install -g ilspycmd

# IL2CPP 游戏（有 GameAssembly.dll + global-metadata.dat）
# 下载 Cpp2IL 或 Il2CppDumper，放到 PATH
```

3. 装 REA（可选，强化 Native / JS 逆向能力）：

```bash
npm install -g rea-agents
```

REA 桥接使用当前 `rea-agents` 命令契约：Managed 成员、JS/Electron、PE 资源、`function` 和 `xrefs`。工具会使用 JSON 输出并在命令失败时返回明确错误。

## 注册到 Claude Code

把 `mcp_config.json` 的内容合并进项目的 `.mcp.json`（或用户级配置），
然后重启 Claude Code。或者直接：
```bash
claude mcp add game-mod-agent -- python <绝对路径>/server.py
```

## 核心工作流

### 0. 从一句话开始：先生成可审查的 Mod 项目

```
用户："给主角加 99999 金币，并允许通过配置修改数值"
1. plan_mod(game_dir, request, project_dir, customizations={"amount": 99999})
2. 查看 mod-spec.json / MODDING_PLAN.md，确认范围和自定义项
3. 让 agent 按 plan 实现具体 Harmony / UE4SS / tModLoader 代码
4. validate_mod_project(project_dir) -> build -> install preview -> game test
```

`plan_mod` 负责把用户需求变成稳定契约和引擎骨架，具体功能实现由上层 Agent 基于 `request.md` 和 `mod-spec.json` 完成。

### 1. 内存修改：Cheat Engine 式连续扫描

```
用户："把金币改成 99999"
1. find_process("Game.exe") -> pid: 1234
2. scan_start(pid, 100) -> 发现 1500 个候选地址
3. 提示用户："请在游戏里花掉或赚取一点金币，把新数值告诉我"
4. 用户："现在是 80"
5. scan_next(pid, 80) -> 收敛到 1 个地址 0x1407A890
6. write_memory(pid, 0x1407A890, 99999) -> 成功生效！
```

### 2. 持久化 Mod：Unity (BepInEx) vs Unreal (UE4SS)

- **Unity 游戏**：`scaffold_mod` 生成 C# Harmony 切面工程，`build_mod` 编译装入。
- **虚幻引擎 4/5**：`scaffold_ue4ss_mod` 生成免编译的 Lua 脚本（`scripts/main.lua`），使用 UE4SS 动态 Hook UFunction 与 UObject，`install_ue4ss_mod` 直接部署生效！

## 安全红线

单机、离线、用户自有游戏。禁止对反作弊在线游戏 attach/扫描/注入。
本项目是教学与自用工具，不附带任何游戏文件、不提供绕过 DRM 或联机作弊能力。
