# Nexus Mods 全景主流游戏与架构适配矩阵

本文档梳理了全球最大 PC 模组社区 **Nexus Mods (N网)** 排名前列的 20+ 款核心 3A 及热门单机游戏，定义了 AI Mod Builder 对其引擎家族、前置加载器（Prerequisite Mod Frameworks）、数据反编译方式以及模组部署路径的完整支持矩阵。

---

## 一、 Nexus Mods 头部核心游戏全景矩阵

| 排名 | 游戏名称 | 游戏引擎 | 核心前置加载器 (Prerequisite) | 关键识别特征文件 | 模组目标写入路径 | 逆向与反编译手段 |
| :---: | :--- | :--- | :--- | :--- | :--- | :--- |
| **1** | **上古卷轴5：天际 (SE/VR/LE)** | Bethesda Creation Engine | **SKSE64 (Script Extender)** + Address Library | `SkyrimSE.exe`, `skse64_loader.exe` | `Data/` (ESP, ESL, BSA, SKSE 插件) | xEdit / zEdit / Papyrus 编译器 |
| **2** | **辐射 4 (Fallout 4)** | Bethesda Creation Engine | **F4SE (Fallout 4 Script Extender)** | `Fallout4.exe`, `f4se_loader.exe` | `Data/` (BA2 归档, ESP) | Creation Kit / xEdit |
| **3** | **赛博朋克 2077 (Cyberpunk 2077)** | CDPR REDengine 4 | **CET (Cyber Engine Tweaks)** + RED4ext + REDmod | `Cyberpunk2077.exe`, `bin/x64/plugins/cyber_engine_tweaks.asi` | `bin/x64/plugins/` (Lua) / `r6/scripts/` / `archive/pc/mod/` | WolvenKit / Redscript / TweakXL |
| **4** | **巫师 3：狂猎 (The Witcher 3)** | CDPR REDengine 3 | **官方 Mods/ 架构** + Script Merger + REDkit | `witcher3.exe`, `content/content0` | `Mods/mod<Name>/` / `DLC/` | REDkit / QuickBMS / w3strings |
| **5** | **博德之门 3 (Baldur's Gate 3)** | Larian Divinity Engine 4.0 | **Norbyte BG3 Script Extender (DWrite.dll)** + Patch 7 | `bg3.exe`, `bin/DWrite.dll`, `Gustav.pak` | `Mods/<ModId>.pak` + `modsettings.lsx` | Divine Tool (lslib) / LSX 解析 |
| **6** | **艾尔登法环 (Elden Ring)** | FromSoftware 专有引擎 | **Mod Engine 2** + Seamless Co-op (`ersc.dll`) | `eldenring.exe`, `modengine2_launcher.exe` | `mod/` (非破坏性文件劫持) | Smithbox / WitchyBND / Yabber |
| **7** | **只狼：影逝二度 (Sekiro)** | FromSoftware 专有引擎 | **Mod Engine** (`dinput8.dll`) | `sekiro.exe`, `dinput8.dll` | `mods/` | Yabber / WitchyBND |
| **8** | **黑暗之魂 3 (Dark Souls III)** | FromSoftware 专有引擎 | **Mod Engine** / UXM (Unpack Dark Souls) | `DarkSoulsIII.exe`, `dinput8.dll` | `mod/` 或解包覆盖 | WitchyBND / Smithbox |
| **9** | **星露谷物语 (Stardew Valley)** | MonoGame / .NET | **SMAPI (Stardew Modding API)** | `Stardew Valley.exe`, `StardewModdingAPI.exe` | `Mods/<ModId>/` (带 `manifest.json`) | ilspycmd / dnSpy / C# 原生编译 |
| **10** | **泰拉瑞亚 (Terraria)** | .NET / XNA / FNA | **tModLoader (官方独立)** 或 **BepInEx 底层注入** | `Terraria.exe`, `tModLoader.dll`, `winhttp.dll` | `ModLoader/Mods/` 或 `BepInEx/plugins/` | Roslyn / csc.exe 编译 C# 插件 |
| **11** | **黑神话：悟空 (Black Myth: Wukong)** | Unreal Engine 5 (IoStore) | **UE4SS** (Lua 脚本) + loose pak 覆盖 | `b1.exe`, `Content/Paks/*.ucas/*.utoc` | `Content/Paks/~mods/*.pak` | CUE4Parse / repak / FModel |
| **12** | **幻兽帕鲁 (Palworld)** | Unreal Engine 5 | **UE4SS** + loose pak | `Palworld.exe`, `ue4ss/UE4SS.dll` | `Content/Paks/~mods/` + `ue4ss/Mods/` | FModel / CUE4Parse / UAssetGUI |
| **13** | **生化危机 4 重制版 / 2 / 3 / 8** | Capcom RE Engine | **REFramework (`dinput8.dll`)** + Fluffy Mod Manager | `re4.exe`, `re_chunk_000.pak`, `dinput8.dll` | `reframework/autorun/*.lua` 或 PAK | FirstNatives / RE Tool / Lua 运行时 |
| **14** | **怪物猎人：崛起 / 荒野** | Capcom RE Engine | **REFramework** + Fluffy Mod Manager | `MonsterHunterRise.exe`, `MonsterHunterWilds.exe` | `reframework/autorun/` | REFramework ImGui 调试 / Lua |
| **15** | **怪物猎人：世界 (Monster Hunter: World)** | Capcom MT Framework | **Stracker's Loader** (`dinput8.dll`) | `MonsterHunterWorld.exe`, `chunkG0.bin` | `nativePC/` (免解包文件覆盖) | WorldChunkTool / Cirilla |
| **16** | **骑马与砍杀 2：霸主 (Bannerlord)** | TaleWorlds Engine | **Harmony + ButterLib + UIExtenderEx + MCM** | `Bannerlord.exe`, `Modules/Native` | `Modules/<ModId>/SubModule.xml` | dnSpy / Roslyn / C# 程序集 |
| **17** | **空洞骑士 (Hollow Knight)** | Unity (Mono) | **BepInEx 5** / Scarab Modloader | `hollow_knight.exe`, `Assembly-CSharp.dll` | `BepInEx/plugins/` 或 `Mods/` | ilspycmd / dnSpy / HarmonyLib |
| **18** | **木筏求生 (Raft) / 戴森球计划** | Unity (Mono) | **BepInEx 5 (Harmony)** | `Raft.exe`, `Raft_Data/Managed` | `BepInEx/plugins/<ModId>/` | ilspycmd / Roslyn 实时编译 DLL |
| **19** | **荒野大镖客 2 (RDR2)** | Rockstar RAGE Engine | **Script Hook RDR2** + Lenny's Mod Loader (LML) | `RDR2.exe`, `ScriptHookRDR2.dll`, `lml/` | `lml/` / `scripts/` | OpenIV / CodeWalker |
| **20** | **侠盗猎车手 5 (GTA V)** | Rockstar RAGE Engine | **Script Hook V** + OpenIV | `GTA5.exe`, `ScriptHookV.dll`, `dinput8.dll` | `scripts/` / `update/x64/dlcpacks/` | OpenIV / RPF 归档解包 |
| **21** | **星空 (Starfield)** | Bethesda Creation Engine 2 | **SFSE (Starfield Script Extender)** | `Starfield.exe`, `sfse_loader.exe` | `Data/` | xEdit (SF1Edit) / Creation Kit |
| **22** | **天国：拯救 (Kingdom Come: Deliverance)** | CryEngine | **官方 Mods/ 架构** (`mod.manifest`) | `KingdomCome.exe`, `Data/data0.pak` | `Mods/<ModId>/` | 7-Zip / RPG Table Editor |
| **23** | **模拟人生 4 (The Sims 4)** | Maxis 专有引擎 | **Mods/ 架构** (`.package` / `.ts4script`) | `TS4_x64.exe` | `Mods/` (支持深层目录) | Sims 4 Studio / uncompyle6 |
| **24** | **杀戮尖塔 (Slay the Spire)** | Java / LibGDX | **ModTheSpire** + BaseMod | `SlayTheSpire.exe`, `desktop-1.0.jar` | `mods/*.jar` | CFR / Procyon / Java 字节码 |

---

## 二、 架构设计与实现映射

在 AI Mod Builder 体系中，上述所有前置与生态均实现了代码级的闭环处理：

### 1. 前置生态智能感知 (`agmod/frameworks.py`)
* 启动或扫描游戏时，不仅根据引擎文件标记判定引擎，更会进一步检查该游戏对应的专属前置加载器。
* 例如：针对泰拉瑞亚，精准区分是**官方 tModLoader** 还是 **原版 BepInEx 底层注入**；针对星露谷，精准检测 **SMAPI** 是否存在。若缺失核心前置，直接在 UI 控制台与 Stage 2 提供直达官网的安装引导与一键链接。

### 2. 多语言/多引擎代码生成适配器 (`agmod/codegen.py`)
支持将逆向分析得出的符号与方法签名一键编译为对应生态的标准化脚本：
* **C# / Harmony**: 用于 Unity BepInEx、.NET/XNA (泰拉瑞亚/星露谷)、骑砍2 (Bannerlord)；
* **Lua (UE4SS)**: 用于虚幻 4 / 虚幻 5 游戏的 UObject/UFunction 钩子；
* **Lua (REFramework)**: 用于生化危机与怪物猎人游戏的 SDK 级钩子；
* **Lua (CET)**: 用于赛博朋克 2077 的 `Override(...)` 运行时方法覆写；
* **Papyrus**: 用于 B社上古卷轴/辐射系列的事件驱动脚本；
* **GDScript**: 用于 Godot 引擎节点的函数劫持。

### 3. 双轨部署机制 (Dual-Pathway Deployment)
对于具有多重生态的游戏提供双轨容灾机制：
* **官方推荐路径 (Official Loader Route)**：当检测到 tModLoader、SMAPI、Mod Engine 2 等官方/主流加载器时，将生成的模组及元数据（`manifest.json`、`mod.json`）直接规范化写入其指定目录；
* **独立底层注入路径 (Native Injection Fallback)**：对于原版客户端，在不破坏原版文件完整性的前提下，利用 Doorstop / BepInEx 挂载原生 DLL 插件，实现零依赖一键体验。
