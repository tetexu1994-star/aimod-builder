"""Feature inspector and modding strategy advisor.

Aggregates engine detection, structure scanning, and modding route recommendations
into a single call, drastically reducing agent roundtrips.
"""
from __future__ import annotations

import glob
import os

from . import rea, symbols
from .evidence import normalize_hook_target
from .registry import detect_engine, get_adapter


def inspect_feature(game_dir: str, keyword: str) -> dict:
    """Inspect game structures for a desired feature and suggest the best modding path."""
    engine_info = detect_engine(game_dir)
    if engine_info is None:
        return {
            "success": False,
            "error": "Engine could not be detected. Check that game_dir is valid.",
            "game_dir": game_dir,
        }

    engine_id = engine_info["id"]
    keyword_lower = keyword.lower()
    observed = symbols.collect_symbol_evidence(game_dir, engine_id, keyword)
    matches: list[str] = [item["symbol"] for item in observed.get("candidates", [])]
    candidates = observed.get("candidates") or [{}]
    symbol_evidence = {
        "source": candidates[0].get("source", "artifact_scan") if matches else "none",
        "status": observed.get("status", "unknown"),
        "verified": False,
        "observations": observed.get("candidates", []),
        "normalized_targets": [item["hook_target"] for item in observed.get("candidates", []) if item.get("hook_target")],
        "errors": observed.get("errors", []),
    }
    recommended_route = {}

    if engine_id == "unity":
        # Check for Assembly-CSharp.dll
        csharp_dlls = glob.glob(os.path.join(game_dir, "*_Data", "Managed", "Assembly-CSharp.dll"))
        if csharp_dlls:
            dll_path = csharp_dlls[0]
            try:
                # Fast member search with REA without full decompile
                if not matches:
                    matches = rea.fast_search_members(dll_path, keyword_lower, limit=20)
                    symbol_evidence.update({
                        "source": "rea_fast_search",
                        "status": "observed" if matches else "unknown",
                        "observations": [{"symbol": item, "source": "rea_fast_search", "status": "observed"} for item in matches],
                        "normalized_targets": [
                            target for target in (
                                normalize_hook_target(item, engine_id, source="rea_fast_search", status="observed", confidence=0.82)
                                for item in matches
                            ) if target
                        ],
                    })
            except Exception:
                pass

        recommended_route = {
            "type": "unity_bepinex_or_memory",
            "runtime_hack": f"Use scan_start(pid, current_{keyword_lower}_val) -> change in game -> scan_next(pid, new_val) -> write_memory",
            "persistent_mod": "Use install_bepinex(game_dir) -> scaffold_mod(...) with a Harmony Patch on the matching method/getter.",
        }

    elif engine_id == "unreal":
        variant = engine_info.get("variant", "")
        if variant == "ue5":
            recommended_route = {
                "type": "unreal_loose_pak",
                "runtime_hack": "Use scan_start on process memory for temporary scalar values only.",
                "persistent_mod": (
                    "Use scaffold_unreal_pak_mod/build_unreal_pak_mod for a loose .pak override after "
                    "FModel/CUE4Parse extraction; verify the game loads Content/Paks/~mods before install."
                ),
            }
        else:
            recommended_route = {
                "type": "unreal_ue4ss_lua",
                "runtime_hack": "Use scan_start on process memory for raw scalar values.",
                "persistent_mod": (
                    f"Use scaffold_ue4ss_mod(...) to create a Lua hook in scripts/main.lua. "
                    f"Look for UProperty or UFunction related to '{keyword}' (e.g. Set{keyword.capitalize()} or Get{keyword.capitalize()})."
                ),
            }

    elif engine_id == "dotnet-xna":
        recommended_route = {
            "type": "tmodloader",
            "persistent_mod": "Use scaffold_tmod_mod(...) and override ModPlayer / GlobalItem hooks in C#.",
        }

    else:
        adapter = get_adapter(engine_id)
        recommended_route = {
            "type": "generic_catalog",
            "guidance": getattr(adapter, "mod_framework", "Check engine documentation"),
        }

    return {
        "success": True,
        "engine": engine_info,
        "keyword": keyword,
        "symbol_matches": matches[:15],
        "symbol_evidence": symbol_evidence,
        "recommended_strategy": recommended_route,
    }


def analyze_reverse_engineering_context(game_dir: str, user_prompt: str) -> dict:
    """Analyze binary targets, symbols, and safe boundary scope via reverse engineering.

    Grounded symbol extraction and boundary constraint analysis prevents crashes and
    accelerates AI mod creation for AAA engines (Unreal Engine 5, Unity, RE-Engine).
    """
    engine_info = detect_engine(game_dir) or {}
    engine_id = engine_info.get("engine_id") or engine_info.get("id", "generic")
    engine_name = engine_info.get("engine_name") or engine_info.get("name", "通用引擎")

    prompt_low = (user_prompt or "").lower()

    # 1. Classify feature category & parameters
    if any(k in prompt_low for k in ["速", "快", "speed", "run", "dash", "walk", "疾"]):
        category = "movement_speed"
        term = "speed"
        param_label = "移速倍率"
        safe_range = [1.0, 5.0]
        step = 0.1
        default_val = 2.0
        boundary_warning = "物理边界保护：建议范围 [1.0x ~ 5.0x]，超过 5.0 倍可能发生高速碰撞穿模或掉落地图边界"
        exception_guards = [
            "严格限定倍率 > 0.0，避免物理反向速度或除以零异常",
            "连续碰撞检测 (CCD) 保障，防止穿过动态障碍物",
            "切图/复活时状态机自动重置为标准基准速度",
        ]
    elif any(k in prompt_low for k in ["跳", "jump", "air", "跃"]):
        category = "jump_mobility"
        term = "jump"
        param_label = "跳跃次数/腾空力"
        safe_range = [1.0, 3.0]
        step = 0.5
        default_val = 2.0
        boundary_warning = "重力边界保护：建议滞空段数 [1 ~ 3段]，避免超出高空摄像机边界或触发未加载区块"
        exception_guards = [
            "限制跳跃段数上限 <= 5，防止物理堆叠导致无限滞空卡死",
            "落地/受击硬直时重置跳跃计数器",
        ]
    elif any(k in prompt_low for k in ["血", "命", "hp", "health", "无敌", "护盾", "防", "减免"]):
        category = "combat_defense"
        term = "health"
        param_label = "伤害减免比例 (%)"
        safe_range = [50.0, 100.0]
        step = 5.0
        default_val = 100.0
        boundary_warning = "生命边界保护：减伤比例 [50% ~ 100%]，全额免伤可抵御即死判定外的全部攻击"
        exception_guards = [
            "拦截伤害计算前缀 (Prefix)，当伤害为 0 时抑制受击硬直动画中断",
            "防负数溢出：保证计算后 Health >= 1，杜绝负数触发 Death 状态机误判",
            "剧情强制杀伤事件白名单旁路，防止剧情杀卡关",
        ]
    elif any(k in prompt_low for k in ["攻", "攻击", "伤害", "秒杀", "attack", "damage", "暴击", "威力", "增加伤害"]):
        category = "combat_offense"
        term = "damage"
        param_label = "攻击倍率"
        safe_range = [1.5, 10.0]
        step = 0.5
        default_val = 3.0
        boundary_warning = "伤害数值保护：建议倍率 [1.5x ~ 10.0x]，避免数值超出 32 位带符号整型上限"
        exception_guards = [
            "输出截断保护：单次伤害上限设为 999,999,999，杜绝溢出反转为负数回血",
            "浮点转整型四舍五入防截断除零",
        ]
    elif any(k in prompt_low for k in ["钱", "金", "coin", "gold", "money", "drop", "爆率"]):
        category = "economy"
        term = "gold"
        param_label = "金钱/掉落倍率"
        safe_range = [2.0, 20.0]
        step = 1.0
        default_val = 5.0
        boundary_warning = "经济系统保护：倍率 [2x ~ 20x]，保证正常升级节奏同时防止背包数据溢出"
        exception_guards = [
            "货币累加溢出守卫：Clamp(val, 0, INT_MAX)",
            "网络同步旁路隔离，防止单机改动影响多人会话校验",
        ]
    else:
        category = "generic_enhancement"
        term = "custom"
        param_label = "增强强度"
        safe_range = [1.0, 10.0]
        step = 1.0
        default_val = 2.0
        boundary_warning = "动态参数边界：推荐调节范围 [1.0 ~ 10.0]，适度增强游戏乐趣"
        exception_guards = [
            "空指针保护：执行前校验目标实例非空 (IsValid / ReferenceEquals)",
            "异常捕获保护：注入逻辑置于安全沙箱中，异常时自动静默回退",
        ]

    # 2. Identify target binary and real reverse engineered symbols
    matched_symbols = []
    target_binary = "Game Executable"
    evidence_source = "heuristic"
    evidence_status = "suggested"
    evidence_confidence = 0.35
    observed = symbols.collect_symbol_evidence(game_dir, engine_id, term)
    if observed.get("candidates"):
        matched_symbols = [item["symbol"] for item in observed["candidates"]]
        evidence_source = observed["candidates"][0].get("source", "artifact_scan")
        evidence_status = "observed"
        evidence_confidence = max(0.55, min(0.9, max(item.get("confidence", 0.55) for item in observed["candidates"])))
        target_binary = observed["candidates"][0].get("path", target_binary)

    if engine_id == "unreal":
        all_shippings = glob.glob(os.path.join(game_dir, "*", "Binaries", "Win64", "*-Shipping.exe"))
        if not all_shippings:
            all_shippings = glob.glob(os.path.join(game_dir, "Binaries", "Win64", "*.exe"))
        if not all_shippings:
            all_shippings = glob.glob(os.path.join(game_dir, "*.exe"))

        # Filter out crash reporter and auxiliary engine tools
        shippings = [p for p in all_shippings if "crashreport" not in os.path.basename(p).lower()]
        if not shippings:
            shippings = all_shippings

        target_binary = os.path.basename(shippings[0]) if shippings else "Engine/Binaries/Win64/*-Shipping.exe"

        symbols_map = {
            "movement_speed": ["UCharacterMovementComponent:SetMaxWalkSpeed", "UCharacterMovementComponent:MaxWalkSpeed", "ACharacter:AddMovementInput"],
            "jump_mobility": ["ACharacter:JumpMaxCount", "UCharacterMovementComponent:JumpZVelocity", "ACharacter:CanJump"],
            "combat_defense": ["ACharacter:TakeDamage", "UDamageType:ApplyDamage", "APawn:ReceiveDamage"],
            "combat_offense": ["AWeapon:CalculateDamage", "ACharacter:DealDamage", "UAttackComponent:ExecuteAttack"],
            "economy": ["UInventoryComponent:AddCurrency", "AItemDrop:SpawnLoot", "UWalletComponent:AddGold"],
            "generic_enhancement": ["ACharacter:Tick", "APlayerController:ClientRestart", "UGameplayStatics:SetGlobalTimeDilation"],
        }
        if not matched_symbols:
            matched_symbols = symbols_map.get(category, symbols_map["generic_enhancement"])
        if engine_info.get("variant") == "ue5":
            strategy = "UE5 IoStore 不默认走 UE4SS Hook；先用 FModel/CUE4Parse 定位资源，再验证 loose .pak 覆盖路径"
        else:
            strategy = f"通过 UE4SS (Lua Hooking) 拦截 {matched_symbols[0]}，在虚幻引擎 UObject 运行时安全重载目标属性"

    elif engine_id == "unity":
        is_il2cpp = bool(
            os.path.exists(os.path.join(game_dir, "GameAssembly.dll"))
            or glob.glob(os.path.join(game_dir, "*_Data", "il2cpp_data"))
            or glob.glob(os.path.join(game_dir, "*_data", "il2cpp_data"))
        )

        csharp_dlls = (
            glob.glob(os.path.join(game_dir, "*_Data", "Managed", "Assembly-CSharp*.dll"))
            + glob.glob(os.path.join(game_dir, "*_data", "Managed", "Assembly-CSharp*.dll"))
            + glob.glob(os.path.join(game_dir, "BepInEx", "interop", "*.dll"))
            + glob.glob(os.path.join(game_dir, "MelonLoader", "Il2CppAssemblies", "*.dll"))
            + glob.glob(os.path.join(game_dir, "DummyDll", "Assembly-CSharp*.dll"))
        )

        unity_types = {
            "movement_speed": ["Player", "PlayerController", "CharacterMotor", "PlayerMovement", "Movement"],
            "jump_mobility": ["Player", "PlayerController", "CharacterMotor", "Movement", "HeroController"],
            "combat_defense": ["Player", "PlayerStats", "PlayerHealth", "Health", "Stats", "Combat"],
            "combat_offense": ["Player", "PlayerStats", "Weapon", "PlayerAttack", "Combat", "Damage"],
            "economy": ["Player", "PlayerInventory", "Inventory", "EconomyManager", "Wallet", "Farmer"],
            "generic_enhancement": ["Player", "PlayerController", "GameManager", "Stats"],
        }
        cand_types = unity_types.get(category, ["Player", "Character", "GameManager"])
        if is_il2cpp:
            target_binary = "GameAssembly.dll (IL2CPP + global-metadata.dat)"
            if csharp_dlls and not matched_symbols:
                for dll_p in csharp_dlls[:2]:
                    try:
                        real_found = rea.fast_search_members(dll_p, term, candidate_types=cand_types, limit=5)
                        if real_found:
                            matched_symbols = real_found
                            evidence_source = "rea_il2cpp_interop_search"
                            evidence_status = "observed"
                            evidence_confidence = 0.88
                            break
                    except Exception:
                        pass
        elif csharp_dlls:
            target_binary = os.path.basename(csharp_dlls[0])
            if not matched_symbols:
                for dll_p in csharp_dlls[:2]:
                    try:
                        real_found = rea.fast_search_members(dll_p, term, candidate_types=cand_types, limit=5)
                        if real_found:
                            matched_symbols = real_found
                            evidence_source = "rea_managed_search"
                            evidence_status = "observed"
                            evidence_confidence = 0.92
                            break
                    except Exception:
                        pass
        else:
            target_binary = "UnityPlayer.dll"

        if not matched_symbols:
            symbols_map = {
                "movement_speed": ["PlayerController.MoveSpeed", "CharacterMotor.movement", "PlayerMovement.speed"],
                "jump_mobility": ["HeroController.CanDoubleJump", "PlayerController.Jump", "CharacterController.JumpHeight"],
                "combat_defense": ["PlayerData.TakeDamage", "Health.ApplyDamage", "PlayerHealth.ReceiveDamage"],
                "combat_offense": ["Weapon.CalculateDamage", "PlayerAttack.DamageMultiplier", "Combat.DealDamage"],
                "economy": ["CurrencyManager.AddGeo", "Inventory.AddGold", "EconomyManager.AddCoins"],
                "generic_enhancement": ["GameManager.Update", "PlayerController.Update", "Time.timeScale"],
            }
            matched_symbols = symbols_map.get(category, symbols_map["generic_enhancement"])

        if is_il2cpp:
            strategy = f"通过 Cpp2IL / Il2CppDumper 逆向提取符号表，利用 BepInEx-IL2CPP / MelonLoader 拦截 {matched_symbols[0]}"
            exception_guards.extend([
                "IL2CPP 运行时类型安全：IL2CPP 剥离了反射，必须通过 Cpp2IL 生成的 DummyDll 或偏移地址进行挂钩",
                "IL2CPP 垃圾回收驻留：传递给原生 C++ 指针的托管委托必须保活，防止 GC 回收触发 AccessViolation 闪退",
            ])
        else:
            strategy = f"通过 BepInEx 6 / HarmonyX 对 {matched_symbols[0]} 部署前缀/后缀补丁，在托管运行时热重载参数"
            exception_guards.extend([
                "UnityEngine.Object 生命周期守卫：必须使用 obj != null（触发底层 C++ 原生存活校验），禁止使用 ReferenceEquals",
                "物理穿模防护：刚体/控制器速度需在 FixedUpdate 中限制在安全阈值，防止高速碰撞穿透 BoxCollider 坠落虚空",
                "Harmony 前缀补丁保护：Prefix 方法内应加入 try-catch 包裹，return true 保证游戏原逻辑不被截断",
            ])

    elif engine_id == "re-engine":
        target_binary = "reframework/autorun"
        symbols_map = {
            "movement_speed": ["via.motion.MotionHelper.set_Speed", "app.PlayerSpeedManager.set_Speed"],
            "jump_mobility": ["app.PlayerJumpController.set_JumpCount", "via.motion.JumpAction"],
            "combat_defense": ["app.DamageCalculator.calculatePlayerDamage", "app.HitController.damage"],
            "combat_offense": ["app.PlayerAttack.calcDamage", "app.Weapon.get_AttackPower"],
            "economy": ["app.RewardManager.addReward", "app.ItemDropManager.get_DropRate"],
            "generic_enhancement": ["via.hid.GamePad.update", "app.GameManager.update"],
        }
    elif engine_id in {"dotnet-xna", "dotnet", "tmodloader"}:
        exes = sorted(f for f in os.listdir(game_dir) if f.lower().endswith(".exe")) if os.path.isdir(game_dir) else []
        is_stardew = any("stardew" in f.lower() for f in exes) or "stardew" in game_dir.lower()
        if is_stardew:
            target_binary = "Stardew Valley.exe"
            symbols_map = {
                "movement_speed": ["StardewValley.Farmer.speed", "StardewValley.Farmer.addedSpeed"],
                "jump_mobility": ["StardewValley.Farmer.movementDirections"],
                "combat_defense": ["StardewValley.Farmer.health", "StardewValley.Farmer.stamina"],
                "combat_offense": ["StardewValley.Tools.MeleeWeapon.doDamage"],
                "economy": ["StardewValley.Farmer.money", "StardewValley.Farmer.totalMoneyEarned"],
                "generic_enhancement": ["StardewValley.Game1.Update", "StardewValley.Farmer.Update"],
            }
            strategy = "通过 SMAPI Mod API 监听游戏生命周期并修改 Farmer 对象状态"
            exception_guards.extend([
                "MonoGame / .NET CLR 运行时安全：禁止使用 UnityEngine 命名空间",
                "SMAPI 生命周期约束：在 GameLoop.UpdateTicked 或 DayStarted 事件中进行状态更新",
            ])
        else:
            target_binary = "Terraria.exe"
            symbols_map = {
                "movement_speed": ["Terraria.Player.moveSpeed", "Terraria.Player.maxRunSpeed", "Terraria.Player.runAcceleration"],
                "jump_mobility": ["Terraria.Player.jumpSpeedBoost", "Terraria.Player.doubleJumpCloud", "Terraria.Player.jumpHeight"],
                "combat_defense": ["Terraria.Player.statLife", "Terraria.Player.immune", "Terraria.Player.statDefense"],
                "combat_offense": ["Terraria.Player.GetTotalDamage", "Terraria.Item.damage", "Terraria.Player.meleeDamage"],
                "economy": ["Terraria.Player.BuyItem", "Terraria.Item.value", "Terraria.Player.SellItem"],
                "generic_enhancement": ["Terraria.Player.Update", "Terraria.Main.Update", "Terraria.Item.SetDefaults"],
            }
            strategy = "通过 BepInEx 门禁或 tModLoader 挂载 Terraria.Player / Terraria.Main，在托管 Update 循环中执行安全调优"
            exception_guards.extend([
                ".NET Framework 4.0 托管运行时安全：纯原生 CLR 程序集，严禁引入 UnityEngine",
                "生命周期守卫：使用 Environment.TickCount 或游戏 Update 节流防死循环卡顿",
            ])

        # Attempt real REA managed member fast search if executable exists
        exe_path = os.path.join(game_dir, target_binary)
        if os.path.isfile(exe_path) and not matched_symbols:
            try:
                dotnet_types = {
                    "movement_speed": ["Player", "Farmer", "Main"],
                    "jump_mobility": ["Player", "Farmer"],
                    "combat_defense": ["Player", "Farmer", "Item"],
                    "combat_offense": ["Player", "Item", "Farmer", "MeleeWeapon"],
                    "economy": ["Player", "Farmer", "Item"],
                    "generic_enhancement": ["Player", "Farmer", "Main", "Game1"],
                }
                found_rea = rea.fast_search_members(exe_path, term, candidate_types=dotnet_types.get(category), limit=5)
                if found_rea:
                    matched_symbols = found_rea
                    evidence_source = "rea_managed_assembly_search"
                    evidence_status = "observed"
                    evidence_confidence = 0.92
            except Exception:
                pass

        if not matched_symbols:
            matched_symbols = symbols_map.get(category, symbols_map["generic_enhancement"])

    else:
        symbols_map = {
            "movement_speed": ["Player.Speed", "Character.MoveSpeed"],
            "jump_mobility": ["Player.JumpPower", "Character.DoubleJump"],
            "combat_defense": ["Player.DamageReduction", "Actor.TakeDamage"],
            "combat_offense": ["Player.AttackDamage", "Weapon.BaseDamage"],
            "economy": ["Economy.AddCurrency", "Inventory.Gold"],
            "generic_enhancement": ["GameEngine.Update", "Actor.Tick"],
        }
        if not matched_symbols:
            matched_symbols = symbols_map.get(category, symbols_map["generic_enhancement"])
        strategy = f"在通用模块中拦截 {matched_symbols[0]} 完成安全调优"

    return {
        "engine_id": engine_id,
        "engine_name": engine_name,
        "category": category,
        "target_binary": target_binary,
        "matched_symbols": matched_symbols,
        "symbol_evidence": {
            "source": evidence_source,
            "status": evidence_status,
            "verified": evidence_status == "verified",
            "observations": observed.get("candidates", []),
            "normalized_targets": [item["hook_target"] for item in observed.get("candidates", []) if item.get("hook_target")],
            "errors": observed.get("errors", []),
        },
        "primary_hook": matched_symbols[0] if matched_symbols else "",
        "boundary_scope": {
            "param_label": param_label,
            "safe_min": safe_range[0],
            "safe_max": safe_range[1],
            "step": step,
            "default_val": default_val,
            "boundary_warning": boundary_warning,
        },
        "exception_guards": exception_guards,
        "implementation_strategy": strategy,
        "confidence": evidence_confidence,
    }


def get_reverse_engineering_overview(game_dir: str) -> dict:
    """Perform upfront reverse engineering scan on game files and return architecture overview."""
    engine_info = detect_engine(game_dir) or {}
    engine_id = engine_info.get("engine_id") or engine_info.get("id", "generic")
    engine_name = engine_info.get("engine_name") or engine_info.get("name", "通用引擎")
    variant = engine_info.get("variant", "")

    from . import process, llm
    exes = process.find_game_executables(game_dir)
    primary_exe = exes[0] if exes else "Game.exe"

    target_binary = primary_exe
    flavor = ""
    discovered_symbols = []

    if engine_id == "unity":
        is_il2cpp = bool(
            os.path.exists(os.path.join(game_dir, "GameAssembly.dll"))
            or glob.glob(os.path.join(game_dir, "*_Data", "il2cpp_data"))
            or glob.glob(os.path.join(game_dir, "*_data", "il2cpp_data"))
        )
        flavor = "Unity IL2CPP (原生 C++ 编译)" if is_il2cpp else "Unity Mono (托管 C# 程序集)"
        csharp_dlls = (
            glob.glob(os.path.join(game_dir, "*_Data", "Managed", "Assembly-CSharp*.dll"))
            + glob.glob(os.path.join(game_dir, "*_data", "Managed", "Assembly-CSharp*.dll"))
        )
        if csharp_dlls:
            target_binary = os.path.basename(csharp_dlls[0])
            try:
                for term in ("player", "movement", "game", "inventory", "item"):
                    found = rea.fast_search_members(csharp_dlls[0], term, limit=3)
                    for sym in found:
                        if sym not in discovered_symbols:
                            discovered_symbols.append(sym)
            except Exception:
                pass
        if not discovered_symbols:
            discovered_symbols = ["PlayerController", "PlayerMovement", "Inventory", "GameManager", "Time.timeScale"]

        injection_mode = "BepInEx-IL2CPP / Cpp2IL" if is_il2cpp else "HarmonyX / BepInEx 6 (前缀/后缀补丁)"
        safety_guards = [
            "空指针保护：必须通过 obj != null 触发底层 C++ 原生存活校验，严禁使用 ReferenceEquals",
            "物理防穿模：刚体与移动控制器速度在 FixedUpdate 中限制在安全阈值，防止穿透碰撞体",
            "时间缩放守卫：Time.timeScale 严格限制在 [0.01, 10.0]，杜绝除零或物理死锁",
            "Harmony 拦截保护：Prefix 必须使用 try-catch 包裹，return true 保证游戏原逻辑不被截断",
        ]

    elif engine_id == "unreal":
        flavor = f"Unreal Engine ({variant.upper() if variant else 'UE4/UE5'})"
        if variant == "ue5":
            injection_mode = "loose .pak 覆盖（IoStore 资源覆盖）"
            safety_guards = [
                "UE5 IoStore 边界保护：严禁直接修改只读 utoc/ucas 索引容器",
                "资源覆盖校验：使用 ~mods loose pak 规范，确保目标版本支持 Pak 文件重载",
            ]
        else:
            injection_mode = "UE4SS Lua 运行时挂钩"
            safety_guards = [
                "UObject 指针存活校验：执行前校验目标 Actor / Component 有效性",
                "UFunction 签名校验：严格遵循虚幻引擎反射元数据与参数规范",
            ]
        discovered_symbols = ["UCharacterMovementComponent", "ACharacter", "APlayerController", "UInventoryComponent", "UGameplayStatics"]

    elif engine_id == "godot":
        flavor = "Godot Engine (GDScript / PCK 补丁)"
        injection_mode = "PCK 资源热补丁 / GDScript 拦截"
        discovered_symbols = ["Player", "CharacterBody2D", "Movement", "Stats", "Inventory"]
        safety_guards = [
            "GDScript 强类型守卫：函数传参校验，防止空引用崩溃",
            "物理处理守卫：_physics_process 内部限制速度向量模长",
        ]

    elif engine_id == "re-engine":
        flavor = "Capcom RE-Engine"
        injection_mode = "REFramework Lua SDK 注入"
        discovered_symbols = ["via.motion.MotionHelper", "app.PlayerSpeedManager", "app.DamageCalculator", "via.hid.GamePad"]
        safety_guards = [
            "SDK 原生托管对象指针校验，防止悬挂引用闪退",
            "Lua Hook 异常安全沙箱静默隔离",
        ]

    else:
        flavor = engine_name
        injection_mode = "通用运行时注入"
        discovered_symbols = ["Player.Speed", "Player.Health", "Inventory.Items", "GameEngine.Update"]
        safety_guards = [
            "内存数值范围溢出拦截 (Clamp)",
            "主线程执行保护，防止跨线程竞态条件",
        ]

    cfg = llm.load_config()
    has_llm = bool(str(cfg.get("api_key") or "").strip() or "localhost" in cfg.get("api_endpoint", "") or "127.0.0.1" in cfg.get("api_endpoint", ""))
    provider = cfg.get("provider", "deepseek")
    model = cfg.get("model", "deepseek-chat")

    return {
        "game_name": os.path.basename(os.path.normpath(game_dir)),
        "game_dir": game_dir,
        "engine_id": engine_id,
        "engine_name": engine_name,
        "flavor": flavor,
        "target_binary": target_binary,
        "primary_exe": primary_exe,
        "executables": exes,
        "discovered_symbols": discovered_symbols[:10],
        "injection_mode": injection_mode,
        "safety_guards": safety_guards,
        "has_llm": has_llm,
        "llm_info": {
            "has_key": has_llm,
            "provider": provider,
            "model": model,
        },
    }
