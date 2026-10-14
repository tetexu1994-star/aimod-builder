# AI Mod Builder 支持矩阵 (Engine Support Matrix)

本文档定义 `game-mod-agent` 对各类单机游戏引擎的官方支持层级、前置 Mod Loader、Hook 机制、逆向工具链与验证游戏。

---

## 核心引擎矩阵总览

| 引擎分类 | 架构与运行时 | 前置 Mod 框架 | 脚本/开发语言 | Hook 与修改机制 | 典型验证游戏 | 支持层级 |
|---|---|---|---|---|---|---|
| **Unity (Mono)** | .NET Framework 4.x / .NET Standard | BepInEx 5.x | C# (Harmony) | Harmony Prefix/Postfix/Transpiler 方法切面 | 戴森球计划, 雾锁王国, 极乐迪斯科 | **Scaffolded / Runtime-pending** |
| **Unity (IL2CPP)** | Native C++ + AOT 编译 | BepInEx 6.x (Bleeding Edge) | C# (Harmony) | Cpp2IL 还原符号 + Harmony IL2CPP 注入 | 鹅鸭杀(离线), 碳酸危机 | **Experimental** |
| **Unreal Engine 4** | UE4 Native (x64) | UE4SS / RE-UE4SS | Lua (免编译) | UFunction Hook (`RegisterHook`), StaticFindObject | 霍格沃茨之遗, 铁拳8, 幻兽帕鲁 | **Scaffolded / Runtime-pending** |
| **Unreal Engine 5** | UE5 Native (x64) | UE4SS (v3.0+) + repak | Lua / PAK 资源覆写 | UFunction Hook + PAK Chunk 资源替换 | 黑色神话(离线测试), 铁拳8 | **Experimental** |
| **Capcom RE Engine** | RE Engine Native (x64) | REFramework (`dinput8.dll`) | Lua / C++ DLL | `sdk.hook` 函数拦截, `re.on_draw_ui` ImGui, 内存修改 | 怪物猎人崛起/荒野, 生化危机2/3/4重制, 鬼泣5, 龙之信条2 | **Scaffolded / Runtime-pending** |
| **Godot (3.x / 4.x)** | Godot Native + GDScript | GodotModLoader | GDScript (免编译) | `mods-unpacked/`, `_init` / `_ready` 节点注入, 资源覆盖 | 土豆兄弟 (Brotato), 磁带怪兽, 穹顶守护者, 恶魔轮盘赌 | **Scaffolded / Runtime-pending** |
| **Terraria** | .NET 6 / 8 (x64) | tModLoader | C# (.NET SDK) | Subclass `Mod`, `ModPlayer`, `GlobalItem` | 泰拉瑞亚 (Terraria) | **Tier-2** |
| **.NET / XNA** | MonoGame / XNA | MonoMod / BepInEx | C# | IL Hook / MonoMod 切面 | 星露谷物语 (SMAPI), 蔚蓝 (Celeste) | **Tier-2** |
| **Bethesda CE** | Creation Engine (x64) | SKSE64 / F4SE / SFSE | Papyrus / C++ DLL | 脚本拓展插件 + ESP/ESM 插件 | 上古卷轴5天际, 辐射4, 星空 | **Tier-2** |
| **Source / Source 2** | Source Engine | SourceMod / VScript | SourcePawn / Lua | VPK 打包 + VScript 挂载 | 半条命: Alyx, CS2(离线) | **Tier-2** |

---

## 支持层级定义

- **Scaffolded**：能识别并生成工程骨架。
- **Build-verified**：生成物已经通过真实编译器构建。
- **Runtime-verified**：已经在指定游戏版本运行并验证行为。
- **Tier-1**：至少两个游戏版本完成编译、安装、运行和无损回滚验证。

当前表格中的 Runtime-pending 不能解读为 Tier-1；真实 Windows 游戏验收完成后再升级。

## 核心引擎规范详解

### 1. Unity 引擎（Unity Mono / IL2CPP）

- **自动侦测标志**：
  - Mono: `*_Data/Managed/Assembly-CSharp.dll`
  - IL2CPP: `GameAssembly.dll` + `*_Data/il2cpp_data/Metadata/global-metadata.dat`
- **Mod 部署位置**：
  `<game_dir>/BepInEx/plugins/<ModId>.dll`
- **开发与逆向流程**：
  1. 使用 `dump_structures(game_dir)` 调用 `ilspycmd` (Mono) 或 `Cpp2IL` (IL2CPP) 恢复结构签名；
  2. 使用 `scaffold_mod` 生成带 `Plugin.cs` 与 Harmony Patch 模板的工程；
  3. 使用 `build_mod` 编译，自动触发 CSxxxx 编译报错自愈诊断；
  4. 自动写入 `install-journal.json`，支持一键 `uninstall_mod` 与 `rollback_game`。

---

### 2. 虚幻引擎（Unreal Engine 4 / 5）

- **自动侦测标志**：
  `*.uproject`, `Content/Paks/*.pak`, `Content/Paks/*.ucas`, `Content/Paks/*.utoc`
- **Mod 部署位置**：
  `<game_dir>/.../Binaries/Win64/ue4ss/Mods/<ModId>/scripts/main.lua`
- **开发与逆向流程**：
  1. 使用 UE4SS Dumper-7 导出完整的 UClass / UProperty / UFunction 符号；
  2. 使用 `scaffold_ue4ss_mod` 零编译生成 Lua Mod，内含 `scripts/main.lua` 与 `enabled.txt`；
  3. 在 Lua 中通过 `RegisterHook("/Script/Engine.Actor:K2_DestroyActor", ...)` 挂钩；
  4. 通过 `install_ue4ss_mod` 原子安装，全量纳入事务回滚系统。

---

### 3. 卡普空 RE 引擎（Capcom RE Engine）

- **自动侦测标志**：
  `re_chunk_000.pak`, `*.pak.patch_000`, `MonsterHunterRise.exe`, `re4.exe`, `re8.exe`
- **Mod 部署位置**：
  `<game_dir>/reframework/autorun/<ModId>.lua`
- **开发与逆向流程**：
  1. 前置依赖 `dinput8.dll` (REFramework)；
  2. 使用 `scaffold_reframework_mod` 生成 Lua 模板，内置 ImGui 绘制菜单与按帧逻辑；
  3. 通过 `sdk.hook(sdk.find_type_definition("..."):get_method("..."), ...)` 拦截游戏 Native 函数；
  4. 通过 `install_reframework_mod` 安装，支持冲突检测与无损卸载。

---

### 4. Godot 引擎（Godot 3.x / 4.x）

- **自动侦测标志**：
  `*.pck`, `*.godot`
- **Mod 部署位置**：
  `<game_dir>/mods-unpacked/<Author>-<ModId>/mod_main.gd`
- **开发与逆向流程**：
  1. 前置依赖 GodotModLoader；
  2. 使用 `scaffold_godot_mod` 创建 GDScript Mod 骨架；
  3. 在 `mod_main.gd` 的 `_init()` 与 `_ready()` 中实现场景挂载或使用 `gdunpack` 替换解包后的资源；
  4. 通过 `install_godot_mod` 部署，并受安装事务锁与 Hash 防误删机制保护。

---

## 安全与质量底线 (Hard Safety Invariants)

1. **绝对禁止联机作弊与 DRM 破解**：严格限单机、离线、本地自有游戏；目标进程含 EAC、BE、Vanguard 等反作弊服务时直接 Fail Closed。
2. **写盘前进程锁感知**：执行任何安装/卸载/更新前，通过 `check_game_status` 预检目标可执行文件与 PID，若游戏运行中强提醒或阻止写盘，避免 Windows Error 13 文件锁崩溃。
3. **安装日志强隔离与事务性**：所有安装操作必须通过 `install_files` 统一事务执行，Hash 校验失败自动滚回，支持绝对路径隔离，杜绝同名游戏相互污染。
4. **存档安全防御**：每次内存侵入式写入或重大 Mod 安装前，强制引导或调用 `create_save_backup` 生成带防路径穿越的安全快照。
