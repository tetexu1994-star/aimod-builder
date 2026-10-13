"""Comprehensive engine catalog.

Each entry: how to detect the engine (glob markers relative to the game dir),
which pre-requisite mod framework it uses (前置), how to "read" its structures,
and concrete game examples. The specialized Unity / .NET-XNA adapters live in
adapters/; everything here is wired through CatalogAdapter.

Detection is best-effort by file markers — the agent should confirm the
detected engine with the user before acting.
"""

ENGINE_CATALOG = [
    {
        "id": "unreal",
        "name": "Unreal Engine (UE4 / UE5)",
        "family": "unreal",
        "markers": ["*.uproject", "Content/Paks/*.pak", "Content/Paks/*.utoc", "Content/Paks/*.ucas"],
        "mod_framework": "UE4SS / RE-UE4SS (Lua 脚本) + pak 覆盖 (repak/UnrealPak) + FModel/UAssetGUI 改资源",
        "structure": "反射 dump（UE4SS dumper / Dumper-7）拿 UClass/UProperty",
        "examples": "霍格沃茨之遗(UE4SS+蓝图mod)、铁拳8、大部分 UE5 3A 用 pak mod",
    },
    {
        "id": "re-engine",
        "name": "Capcom RE Engine (怪猎崛起/荒野、生化危机、鬼泣5、街霸6、龙之信条2)",
        "family": "re-engine",
        "markers": ["re_chunk_000.pak", "*.pak.patch_000", "re8.exe", "MonsterHunterRise.exe", "MonsterHunterWilds.exe", "re4.exe"],
        "mod_framework": "REFramework (Lua 脚本 + DLL 插件) + Fluffy Mod Manager 装 PAK mod",
        "structure": "REFramework 游戏对象浏览/Lua；.pak 用 FirstNatives / RE Tool 解包",
        "examples": "怪猎崛起/荒野=REFramework+PAK；生化危机4重制=REFramework+Fluffy",
    },
    {
        "id": "mt-framework",
        "name": "Capcom MT Framework (怪物猎人世界等)",
        "family": "mt-framework",
        "markers": ["chunkG0.bin", "chunk0.bin", "MonsterHunterWorld.exe"],
        "mod_framework": "Stracker's Loader + nativePC 文件覆盖；REFramework 可加 Lua",
        "structure": "nativePC 文件覆盖；REFramework Lua 脚本",
        "examples": "怪物猎人世界=Stracker's Loader + nativePC",
    },
    {
        "id": "godot",
        "name": "Godot (3.x / 4.x)",
        "family": "godot",
        "markers": ["*.pck", "*.godot"],
        "mod_framework": "GDExtension (C++) / .pck 解包改 GDScript",
        "structure": "gdunpack / godotpcktool 解包 .pck",
        "examples": "",
    },
    {
        "id": "source",
        "name": "Source / Source 2",
        "family": "source",
        "markers": ["gameinfo.txt", "*.vpk"],
        "mod_framework": "SourceMod / MetaMod (Source 1)；VScript/Lua (Source 2)",
        "structure": "VPK 工具（GCFScape / VPKEdit）+ Source SDK",
        "examples": "CS:GO/TF2=SourceMod；CS2/半条命Alyx=VScript",
    },
    {
        "id": "bethesda",
        "name": "Bethesda Creation Engine (上古卷轴/辐射/星空)",
        "family": "bethesda",
        "markers": ["*.esm", "*.esp", "*.esl"],
        "mod_framework": "SKSE / F4SE / SFSE + Papyrus 脚本",
        "structure": "xEdit / zEdit 解析 ESM/ESP 记录",
        "examples": "天际=SKSE+MO2/Vortex；辐射4=F4SE；星空=SFSE",
    },
    {
        "id": "fromsoftware",
        "name": "FromSoftware (艾尔登法环/只狼/黑魂/装甲核心)",
        "family": "fromsoftware",
        "markers": ["*.dcx", "*.bdt", "*.bhd", "Data0.bdt"],
        "mod_framework": "ModEngine2（文件覆盖加载）",
        "structure": "WitchyBND / Smithbox 解 BND/BHD/DCX",
        "examples": "法环/只狼=ModEngine2；装甲核心6=ModEngine2",
    },
    {
        "id": "rage",
        "name": "Rockstar RAGE (GTA V / RDR2)",
        "family": "rage",
        "markers": ["*.rpf", "update/update.rpf"],
        "mod_framework": "Script Hook V / RAGE Plugin Hook",
        "structure": "OpenIV 解 RPF 归档",
        "examples": "GTA5=ScriptHookV+RPH；RDR2=ScriptHookRDR2",
    },
    {
        "id": "redengine",
        "name": "CDPR REDengine (巫师3 / 赛博朋克2077)",
        "family": "redengine",
        "markers": ["*.archive", "*.bundle", "*.blob"],
        "mod_framework": "RED4ext + Redscript + CET (2077)；WitcherScript (巫师3)",
        "structure": "WolvenKit 解 REDengine 归档",
        "examples": "赛博朋克2077=RED4ext+CET+ArchiveXL；巫师3=WitcherScript",
    },
    {
        "id": "minecraft-java",
        "name": "Minecraft (Java)",
        "family": "minecraft",
        "markers": ["versions", "launcher_profiles.json", "libraries"],
        "mod_framework": "Fabric / Forge / NeoForge + Mixin 字节码注入",
        "structure": "Vineflower / CFR 反编译客户端 jar + Mojang mappings",
        "examples": "Fabric(轻量)/Forge/NeoForge，Mixin 注入",
    },
    {
        "id": "gamemaker",
        "name": "GameMaker",
        "family": "gamemaker",
        "markers": ["data.win", "options.ini"],
        "mod_framework": "UndertaleModTool (UTMT)",
        "structure": "UndertaleModTool 解析 data.win",
        "examples": "Undertale/传说之下=Deltarune 用 UTMT",
    },
    {
        "id": "rpgmaker",
        "name": "RPG Maker (MV / MZ / VX Ace)",
        "family": "rpgmaker",
        "markers": ["Game.rpgproject", "www/data", "data/System.json"],
        "mod_framework": "插件 .js (MV/MZ)；Ruby 脚本 (VX Ace)",
        "structure": "直接读 data/*.json (MV/MZ) 或 ruby 脚本",
        "examples": "",
    },
    {
        "id": "idtech",
        "name": "id Tech / DOOM / Quake",
        "family": "idtech",
        "markers": ["*.wad", "*.pk3", "*.pk4", "*.iwad"],
        "mod_framework": "source port（GZDoom 等）",
        "structure": "WAD / PK3 工具",
        "examples": "DOOM=GZDoom 加载 WAD/PK3",
    },
    {
        "id": "electron",
        "name": "Electron / Web 游戏",
        "family": "electron",
        "markers": ["resources/app.asar", "resources/app"],
        "mod_framework": "解包 app.asar 改 JS",
        "structure": "asar 解包 / rea analyze-javascript-application",
        "examples": "Rebirth Hoarder 等 Electron 游戏=改 app.asar",
    },
    {
        "id": "renpy",
        "name": "Ren'Py 视觉小说",
        "family": "renpy",
        "markers": ["*.rpa", "*.rpyc", "renpy"],
        "mod_framework": "unrpa 解包 + 改 .rpy 脚本",
        "structure": "unrpa / rpatool 解 .rpa",
        "examples": "",
    },
]

# Generic native / custom engines (no reliable file marker): the fallback path
# is Cheat Engine / Ghidra / IDA / Frida, which the memory + scan tools already
# support. Listed here only for documentation, not auto-detection.
NATIVE_FALLBACK = {
    "id": "native",
    "name": "自定义 / 原生引擎（无识别标记）",
    "family": "native",
    "mod_framework": "DLL 注入 + Cheat Engine / Frida",
    "structure": "Ghidra / IDA 反汇编 + 值扫描",
}
