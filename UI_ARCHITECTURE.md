# AI Mod Builder UI 架构设计说明书 (UI Architecture Specification)

> **版本**: 1.0.0  
> **面向对象**: 人类开发者、Codex / Claude 审查员、终端 Mod 创作者  
> **核心定位**: 为 `game-mod-agent` 提供免编译、零重量级依赖、跨平台的现代 Web 交互工作台，实现 AI Agent 与终端用户的协同操作。

## 0. 视觉系统 (2026-10-14 Refresh)

视觉方向定位为 **本地 Mod 维修台 / Field Console**，不是通用 SaaS 仪表盘，也不是霓虹赛博 HUD。界面从 Mod 管理器、代码编辑器和内部运维工具中提取真实工作习惯：先锁定目标，再读证据，生成、验证，最后保留无损恢复路径。

- **色彩**：暖石墨背景、纸张白正文、氧化铜主动作、薄荷绿安全状态、旧金黄待确认状态。避免蓝紫渐变和单一霓虹色。
- **字体**：Space Grotesk 用于工作区标题，Inter 用于正文，IBM Plex Mono 用于路径、签名、日志和状态。Monospace 只承载代码与测量数据。
- **布局**：固定工作区侧栏 + 目标目录命令条 + 非对称操作面板。主要任务保持宽阔输出区，安全与工具链状态放在侧栏，不把所有内容平均切成同尺寸卡片。
- **交互**：Tab 使用原生 button、`role=tab`、`aria-selected` 和 URL hash；异步按钮有 busy 状态；结果状态使用 `role=status`；破坏性恢复使用 `<dialog>` 二次确认。
- **视觉签名**：氧化铜色工作台标记、目标目录命令条、状态线和结构化证据输出共同构成“维修台”识别感。
- **动效**：只保留状态切换和 Toast 的短反馈，遵守 `prefers-reduced-motion`，不使用装饰性视差或故障特效。

### GitHub 参考

- [Nexus-Mods/Vortex](https://github.com/Nexus-Mods/Vortex) 与 [ModOrganizer2/modorganizer](https://github.com/modorganizer2/modorganizer)：借鉴 Mod 管理器的文件清单、部署状态和恢复心智模型，不照搬桌面框架。
- [shadcn-ui/ui](https://github.com/shadcn-ui/ui)：借鉴可访问组件语义、状态和可定制默认值，不直接使用其视觉皮肤。
- [zed-industries/zed](https://github.com/zed-industries/zed) 与 [tldraw/tldraw](https://github.com/tldraw/tldraw)：借鉴开发工具中克制、连贯、像人手工打磨的交互细节。
- [refinedev/refine](https://github.com/refinedev/refine)：借鉴内部工具的信息密度和任务导向布局，避免营销页式仪表盘。

---

## 1. 架构目标与设计哲学

`game-mod-agent` 原生基于 MCP (Model Context Protocol) 运作，供 Claude Code、Codex 等 AI 驱动。然而在实际使用中，用户与 AI 的交互存在以下关键痛点：
1. **黑盒焦虑**: 用户无法直观看到游戏引擎识别结果、文件锁占用、已安装文件清单。
2. **逆向代码验证**: 生成的 Hook 代码 (C#/Lua/GDScript) 需要人工即时审查与参数微调。
3. **安全回滚与存档救砖**: 一键快照、原子级卸载与坏档恢复需要具备直观的视觉反馈与时间线。

为此，UI 架构确立了以下核心设计准则：
- **零重量级依赖 (Zero Heavy Runtime Bloat)**: 不引入 Node.js/Electron/Qt/wxWidgets。由 Python 标准库 (`http.server` + `threading`) 驱动轻量 Web 服务，前端采用响应式现代 HTML5 + Tailwind CSS + 原生响应式状态模型，秒级冷启动 (<100ms)。
- **双模并行 (Dual Mode)**: MCP 命令行无头模式与本地 Web GUI 无缝共存，UI 通过调用底层 Python API 直接复用所有核心模块。
- **本地优先与沙箱安全 (Local-First & Safety Sandboxed)**: 默认绑定 `127.0.0.1`，内置严格路径防穿越校验与只读/写入权限边界保护。

---

## 2. 整体系统架构图

```
+-----------------------------------------------------------------------+
|                           Client Interface                            |
|  +--------------------+  +--------------------+  +-----------------+  |
|  | Modern Web Browser |  | Claude Code/Codex  |  | CLI / Terminal  |  |
|  | (Chrome/Edge/Safari)|  | (MCP stdio client) |  | (python -m ...) |  |
|  +---------+----------+  +---------+----------+  +--------+--------+  |
+------------|-----------------------|----------------------|-----------+
             | HTTP / REST (8765)    | JSON-RPC (stdio)     | CLI Args
             v                       v                      v
+------------------------------------+----------------------------------+
|                    game-mod-agent Core Platform                       |
|                                                                       |
|  +-----------------------------------------------------------------+  |
|  |                        agmod.ui.server                          |  |
|  | - ThreadingHTTPServer (127.0.0.1:8765)                          |  |
|  | - Embedded SPA Dashboard (index.html)                           |  |
|  | - RESTful JSON API Router & Path Traversal Guards              |  |
|  +--------------------------------+--------------------------------+  |
|                                   | In-process python calls           |
|                                   v                                   |
|  +-----------------------------------------------------------------+  |
|  |                        Core Service Layer                       |  |
|  |  +-------------------+ +-------------------+ +----------------+ |  |
|  |  | registry/engines  | | doctor (Health)   | | planning/spec  | |  |
|  |  +-------------------+ +-------------------+ +----------------+ |  |
|  |  +-------------------+ +-------------------+ +----------------+ |  |
|  |  | codegen (Hooks)   | | rollback (Atomic) | | saves (Backup) | |  |
|  |  +-------------------+ +-------------------+ +----------------+ |  |
|  |  +-------------------+ +-------------------+ +----------------+ |  |
|  |  | log_repair (Fix)  | | process (Locks)   | | memory/rea     | |  |
|  |  +-------------------+ +-------------------+ +----------------+ |  |
|  +--------------------------------+--------------------------------+  |
+-----------------------------------|-----------------------------------+
                                    v
                     Target Game Directory & Processes
```

---

## 3. 六大核心工作台模块 (Functional Workspaces)

### 3.1 游戏与运行环境巡检台 (Game & Runtime Inspector)
- **游戏目录选择器**: 支持输入/选择目标游戏根目录。
- **引擎指纹雷达**: 实时调用 `registry.detect_engine`，高亮显示引擎 ID、Runtime (Mono/IL2CPP/UE4/UE5/RE/Godot) 与已识别特征文件。
- **进程状态与文件锁卫士**: 联动 `process.check_game_status`，实时检测游戏是否运行、占用哪些 DLL/PAK 文件，预防覆盖写入引发崩溃。
- **Doctor 诊断仪表盘**: 检查 `.NET SDK`、`REA` 逆向套件、反编译器及缓存健康度评分。

### 3.2 AI Mod 需求与蓝图工作室 (AI Mod Studio)
- **自然语言需求输入框**: 支持中英文需求描述（例如："让主角移动速度提高2倍，耐力不减"）。
- **参数可视化调节板**: 提供数值倍率、按键绑定、功能开关的可视化滑块与切换器。
- **蓝图实时预览**: 动态生成并展示 `mod-spec.json` 与 `MODDING_PLAN.md`。
- **脚手架触发器**: 一键生成对应引擎专属的项目脚手架与目录布局。

### 3.3 符号逆向与 Hook 代码实验室 (Symbol & Hook Code Lab)
- **多引擎语法生成器**:
  - **Unity (C# Harmony)**: 前置/后置补丁，自动处理静态方法 `__instance` 剔除与 `ref` 参数。
  - **Unreal Engine (UE4SS Lua)**: UFunction 挂钩，自动生成 `ExecuteInEngineThread` 与参数解引用。
  - **RE-Engine (REFramework Lua)**: `sdk.hook` 原生绑定与托管参数读取。
  - **Godot (GDScript)**: `script_extension` 继承与信号拦截。
- **语法静态校验器**: 实时验证花括号/圆括号配对、Lua `end` 闭合及参数命名规范。
- **代码编辑器与导出**: 具备语法高亮展示、代码一键复制、直接保存到项目工程目录。

### 3.4 Mod 资产管理与原子回滚中心 (Mod Manager & Safe Rollback)
- **已安装 Mod 目录卡片**: 列表化显示当前游戏目录中已安装的 Mod，标识其引擎类型、版本、安装时间戳。
- **冲突雷达 (Conflict Radar)**: 安装新 Mod 前，调用 `check_install_conflicts` 对比哈希，提前告警同名文件覆盖风险。
- **原子卸载 (Pruning Uninstall)**: 精准删除属于该 Mod 的已安装文件，并自动清理多余的空目录。
- **一键核武级回滚 (Rollback Game)**: 出现坏档或游戏无法启动时，一键撤销所有 Mod 变更，将游戏还原至最原始纯净状态。

### 3.5 运行日志流与诊断器 (Live Logs & Runtime Diagnostics)
- **实时日志捕捉**: 针对不同引擎自动定位日志源（BepInEx `LogOutput.log`、UE4SS `ue4ss.log`、REFramework 运行日志）。
- **崩溃定位与堆栈解析**: 借助 `log_repair.diagnose_runtime_error` 提取崩溃行号、报错模块及缺失依赖。
- **修复建议**: 根据崩溃位置给出明确的补丁方向；自动改写源码和重新验证仍需后续人工确认。

### 3.6 存档时光机 (Savegame Time Machine)
- **多路径存档探测**: 自动扫描 Windows AppData (Local/Roaming/LocalLow)、Saved Games、Steam userdata 及游戏内存档目录。
- **Mod 前自动快照**: 在安装 Mod 前自动弹出创建快照提示（例如：`pre-mod-v1.0.0-speedhack`）。
- **存档时间线与差异对比**: 展示存档历史列表、备份时间、文件大小及备份标签。
- **一键回溯恢复**: 提供无损还原能力，彻底免除玩家坏档后顾之忧。

---

## 4. RESTful API 契约设计 (API Specification)

本地 UI 服务默认监听 `http://127.0.0.1:8765`。所有请求与响应均采用 JSON 格式，统一响应体标准：
- 成功: `{"success": true, "data": ...}`
- 失败: `{"success": false, "error": "错误描述"}`

| 端点 (Endpoint) | 方法 | 描述 | 请求体示例 / 参数 |
|---|---|---|---|
| `/api/health` | GET | 服务健康检查 | 无 |
| `/api/doctor` | GET | 环境诊断报告 | 无 |
| `/api/detect` | POST | 游戏引擎识别 | `{"game_dir": "/path/to/game"}` |
| `/api/process` | POST | 检查游戏运行与进程文件锁 | `{"game_dir": "/path/to/game"}` |
| `/api/plan` | POST | 生成 Mod 规划与 Spec | `{"game_dir": "...", "request": "...", "project_dir": "..."}` |
| `/api/codegen/template` | POST | 生成 Hook 模板代码 | `{"engine": "unity", "class_name": "Player", "method_name": "Move", ...}` |
| `/api/codegen/evidence` | POST | 基于逆向证据生成 Hook | `{"evidence": {"engine": "unreal", "target_symbol": "...", ...}}` |
| `/api/mods/list` | POST | 列出已安装 Mod 清单 | `{"game_dir": "/path/to/game"}` |
| `/api/mods/conflicts` | POST | 冲突检查 | `{"game_dir": "...", "incoming_files": ["..."]}` |
| `/api/mods/uninstall` | POST | 卸载特定 Mod | `{"game_dir": "...", "mod_id": "speed_mod"}` |
| `/api/mods/rollback` | POST | 全量回滚恢复原始状态 | `{"game_dir": "..."}` |
| `/api/saves/list` | POST | 列出存档快照时间线 | `{"game_dir": "..."}` |
| `/api/saves/create` | POST | 创建新存档快照 | `{"game_dir": "...", "label": "pre-mod"}` |
| `/api/saves/restore` | POST | 恢复指定快照 | `{"game_dir": "...", "backup_id": "20261014_100000"}` |
| `/api/logs/read` | POST | 读取日志文件最后 N 行 | `{"game_dir": "...", "lines": 100}` |
| `/api/logs/diagnose` | POST | 智能诊断报错日志并给出修复建议 | `{"log_text": "NullReferenceException..."}` |

---

## 5. 前端视觉与交互系统设计

### 5.1 视觉风格
- **主题基调**: 赛博朋克深色模式（Cyberpunk Dark Mode），采用深灰色底底色（`#0f172a`）、高对比度内容卡片（`#1e293b`）与科技蓝/荧光绿强调色（`#38bdf8` / `#22c55e` / `#a855f7`）。
- **引擎标签色彩系统**:
  - Unity: 绿色胶囊标签 (`badge-unity`, `#22c55e`)
  - Unreal Engine: 科技紫胶囊标签 (`badge-unreal`, `#a855f7`)
  - RE-Engine: 炽热橙胶囊标签 (`badge-reengine`, `#f97316`)
  - Godot: 天空蓝胶囊标签 (`badge-godot`, `#0284c7`)
  - tModLoader / XNA: 琥珀金胶囊标签 (`badge-tmod`, `#eab308`)

### 5.2 状态管理与响应机制
- 原生轻量化响应式状态容器（Vanilla Reactive Store），无打包编译环节，页面在浏览器直接渲染。
- 状态字段包括：当前选定游戏目录、检测结果、进程运行状态、活跃工作台 Tab、日志刷新计时器。
- 支持快捷键：`Ctrl/Cmd + Enter` 立即触发分析或生成；`Esc` 关闭弹窗。

---

## 6. 安全防线与沙箱约束 (Security Guardrails)

1. **Localhost 严格绑定**: 服务默认仅侦听 `127.0.0.1`，拒绝外网 IP 访问。
2. **CORS 与 Origin 白名单机制 (CSRF 防御)**: 坚决废除 `Access-Control-Allow-Origin: *` 全开放策略。只允许 `127.0.0.1` 与 `localhost` 本地同源/安全来源，外站跨域探测（如恶意网页通过 JS 扫描本地 `127.0.0.1:8765`）一律返回 `403 Forbidden` 并剥离 CORS 响应头，彻底杜绝本地敏感信息泄漏与跨站命令伪造。
3. **路径穿越防御 (`safe_path`)**: 对所有前端传入的 `game_dir`、`project_dir`、`backup_id` 做 `os.path.abspath` 和 `os.path.commonpath` 归一化校验，防止 `../` 越界读取主机系统敏感目录。
4. **破坏性操作二次确认**: 涉及 `rollback_game`（清空已安装 mod）与 `restore_save_backup`（覆盖当前游戏存档）操作，前端强制弹出确认模态框，后端记录操作审计日志。
5. **反作弊防护联动**: 内存扫描与进程挂钩时复用 `agmod.safety`，检测到 EasyAntiCheat / BattlEye / VAC 游戏时强制进入只读/阻止状态。

---

## 7. 部署与启动方式

### 命令行独立启动
```bash
# 启动 UI 服务并自动在默认浏览器中打开
python -m agmod.ui

# 指定端口启动且不自动弹窗
python -m agmod.ui --port 9000 --no-browser
```

### Agent MCP 工具调用
在 Claude Code / Codex 中，用户可以直接输入：
> "帮我打开 Mod 工作台可视化界面"

Agent 会直接调用 MCP 工具：
```json
{
  "name": "launch_ui",
  "arguments": { "port": 8765, "open_browser": true }
}
```
返回 UI 访问地址 `http://127.0.0.1:8765` 并向用户呈现。
