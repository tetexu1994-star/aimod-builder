"""Feature inspector and modding strategy advisor.

Aggregates engine detection, structure scanning, and modding route recommendations
into a single call, drastically reducing agent roundtrips.
"""
from __future__ import annotations

import glob
import os

from . import rea
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
    matches: list[str] = []
    recommended_route = {}

    if engine_id == "unity":
        # Check for Assembly-CSharp.dll
        csharp_dlls = glob.glob(os.path.join(game_dir, "*_Data", "Managed", "Assembly-CSharp.dll"))
        if csharp_dlls:
            dll_path = csharp_dlls[0]
            try:
                # Fast member search with REA without full decompile
                matches = rea.fast_search_members(dll_path, keyword_lower, limit=20)
            except Exception:
                pass

        recommended_route = {
            "type": "unity_bepinex_or_memory",
            "runtime_hack": f"Use scan_start(pid, current_{keyword_lower}_val) -> change in game -> scan_next(pid, new_val) -> write_memory",
            "persistent_mod": "Use install_bepinex(game_dir) -> scaffold_mod(...) with a Harmony Patch on the matching method/getter.",
        }

    elif engine_id == "unreal":
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
    elif any(k in prompt_low for k in ["攻", "伤", "秒杀", "attack", "damage", "暴击", "力"]):
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

    if engine_id == "unreal":
        shippings = glob.glob(os.path.join(game_dir, "*", "Binaries", "Win64", "*-Shipping.exe"))
        if not shippings:
            shippings = glob.glob(os.path.join(game_dir, "Binaries", "Win64", "*.exe"))
        if not shippings:
            shippings = glob.glob(os.path.join(game_dir, "*.exe"))

        target_binary = os.path.basename(shippings[0]) if shippings else "Engine/Binaries/Win64/*-Shipping.exe"

        symbols_map = {
            "movement_speed": ["UCharacterMovementComponent:SetMaxWalkSpeed", "UCharacterMovementComponent:MaxWalkSpeed", "ACharacter:AddMovementInput"],
            "jump_mobility": ["ACharacter:JumpMaxCount", "UCharacterMovementComponent:JumpZVelocity", "ACharacter:CanJump"],
            "combat_defense": ["ACharacter:TakeDamage", "UDamageType:ApplyDamage", "APawn:ReceiveDamage"],
            "combat_offense": ["AWeapon:CalculateDamage", "ACharacter:DealDamage", "UAttackComponent:ExecuteAttack"],
            "economy": ["UInventoryComponent:AddCurrency", "AItemDrop:SpawnLoot", "UWalletComponent:AddGold"],
            "generic_enhancement": ["ACharacter:Tick", "APlayerController:ClientRestart", "UGameplayStatics:SetGlobalTimeDilation"],
        }
        matched_symbols = symbols_map.get(category, symbols_map["generic_enhancement"])
        strategy = f"通过 UE4SS (Lua Hooking) 拦截 {matched_symbols[0]}，在虚幻引擎 UObject 运行时安全重载目标属性"

    elif engine_id == "unity":
        csharp_dlls = glob.glob(os.path.join(game_dir, "*_Data", "Managed", "Assembly-CSharp.dll"))
        if csharp_dlls:
            target_binary = "Assembly-CSharp.dll"
            dll_p = csharp_dlls[0]
            try:
                real_found = rea.fast_search_members(dll_p, term, limit=5)
                if real_found:
                    matched_symbols = real_found
                    evidence_source = "rea_fast_search"
                    evidence_status = "observed"
                    evidence_confidence = 0.75
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
        strategy = f"通过 BepInEx / HarmonyX 为 {matched_symbols[0]} 创建动态挂钩，进行参数热注入"

    elif engine_id == "re-engine":
        target_binary = "reframework/autorun"
        symbols_map = {
            "movement_speed": ["sdk.hook('via.motion.MotionHelper', 'set_Speed')", "app.PlayerSpeedManager.set_Speed"],
            "jump_mobility": ["app.PlayerJumpController.set_JumpCount", "via.motion.JumpAction"],
            "combat_defense": ["app.DamageCalculator.calculatePlayerDamage", "sdk.hook('app.HitController', 'damage')"],
            "combat_offense": ["app.PlayerAttack.calcDamage", "sdk.hook('app.Weapon', 'get_AttackPower')"],
            "economy": ["app.RewardManager.addReward", "app.ItemDropManager.get_DropRate"],
            "generic_enhancement": ["sdk.hook('via.hid.GamePad', 'update')", "app.GameManager.update"],
        }
        matched_symbols = symbols_map.get(category, symbols_map["generic_enhancement"])
        strategy = f"通过 REFramework Lua API 挂载 {matched_symbols[0]}，利用 Capcom RE 运行时 SDK 完成注入"

    else:
        symbols_map = {
            "movement_speed": ["Player.Speed", "Character.MoveSpeed"],
            "jump_mobility": ["Player.JumpPower", "Character.DoubleJump"],
            "combat_defense": ["Player.DamageReduction", "Actor.TakeDamage"],
            "combat_offense": ["Player.AttackDamage", "Weapon.BaseDamage"],
            "economy": ["Economy.AddCurrency", "Inventory.Gold"],
            "generic_enhancement": ["GameEngine.Update", "Actor.Tick"],
        }
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
