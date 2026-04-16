"""
combat_engine.py — Turn-based combat simulator for Guildmaster.

Hero turn resolution order (per spec):
  SOT 1.  Advantage/Disadvantage and Upgrade/Downgrade cancellations (handled at application)
  SOT 2.  Iron Will: convert half temp HP to real HP (if passive active)
  SOT 3.  Bloodletting: apply tracked damage from previous turn as temp HP
  SOT 4.  Regeneration tick: apply regen_value to self if regen_remaining > 0
  SOT 5.  Blizzard tick: apply stored AOE damage if ticks_remaining > 0
  SOT 6.  Advantage from Battle Hymn: convert advantage_next_turn flag to status
  BUILD   Compose dice pool
  MOD     Apply Upgrade/Downgrade tier changes and Bleed die-discard
  ROLL    Roll dice (Advantage/Disadvantage), Lucky Roll / Thousand Cuts, Paralyze
  ASSIGN  Distribute dice to skill slots per behavior profile
  CHARGE  Accumulate dice into charge-based skills; fire when threshold met
  EXEC    Execute normal skills (damage, heal, cleanse, defend, self, buff)
  EOT 1.  Blood Rage: HP cost + damage stack gain
  EOT 2.  Evasion: expire
  EOT 3.  Hero block expiry check (Fortify block clears at Cleric's next turn)
  EOT 4.  tick_statuses: Burn damage, Poison damage, Bleed count -1, expire effects
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

from hero.hero_entity import HeroEntity, HeroStatus, Skill, Stat
from enemy.enemy import Enemy
from combat.dice_pool_compositor import compose_pool, apply_status_modifiers, roll_pool, Die
from combat.dice_assignment_engine import assign_dice, SkillAssignment
from combat.skill_executor import execute_all_skills, SkillResult
from combat.status_effects import (
    StatusEffect, StatusType, apply_status, tick_statuses,
    has_status, get_status, has_any_debuff,
)
from game_runtime.event_bus import EventBus


# ---------------------------------------------------------------------------
# Mage spell fixed-effect constants (tunable)
# ---------------------------------------------------------------------------
FIREBALL_DAMAGE: int = 15
FIREBALL_BURN_STACKS: int = 2
BARRIER_ABSORPTION_BASE: int = 20
CHAIN_LIGHTNING_DAMAGE: int = 10
CHAIN_LIGHTNING_HITS: int = 3
CHAIN_LIGHTNING_PARALYZE: int = 1
BLIZZARD_DAMAGE: int = 12
BLIZZARD_TICKS: int = 2
EARTHQUAKE_DAMAGE: int = 18
METEOR_SINGLE_DAMAGE: int = 30
METEOR_BURN_STACKS: int = 3


# ---------------------------------------------------------------------------
# Result types
# ---------------------------------------------------------------------------

@dataclass
class CombatRound:
    """Snapshot of one round of combat."""
    round_number: int
    hero_results: List[SkillResult]
    enemy_results: List[SkillResult]
    hero_damage_taken: int
    enemy_damage_dealt: int
    hero_hp_after: dict = field(default_factory=dict)   # hero_id -> current_health
    enemy_hp_after: List[int] = field(default_factory=list)


@dataclass
class CombatResult:
    """Aggregate result of a full combat encounter."""
    victory: bool
    rounds: List[CombatRound]
    heroes_survived: List[str]
    total_hero_damage_taken: int
    enemies_final: List[Enemy] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Damage application helpers
# ---------------------------------------------------------------------------

def _apply_weak(damage: int, attacker_effects: List[StatusEffect]) -> int:
    """Reduce damage by 25% if the attacker is Weak."""
    if has_status(attacker_effects, StatusType.WEAK):
        return max(1, int(damage * 0.75))
    return damage


def _apply_vulnerable(damage: int, target_effects: List[StatusEffect]) -> int:
    """Increase damage by 50% (or 100% with Venomous upgrade) if target is Vulnerable."""
    vuln = get_status(target_effects, StatusType.VULNERABLE)
    if vuln:
        # venomous_upgrade flag stored in potency field of the effect (potency=2 = doubled)
        multiplier = 2.0 if vuln.potency == 2 else 1.5
        return int(damage * multiplier)
    return damage


def _apply_barrier(amount: int, barrier: List[int]) -> Tuple[int, int]:
    """
    Absorb amount through the party barrier (barrier[0] = remaining hp).
    Returns (damage_after_barrier, new_barrier_remaining).
    """
    absorbed = min(barrier[0], amount)
    barrier[0] -= absorbed
    return amount - absorbed, barrier[0]


def _damage_hero(
    hero: HeroEntity,
    raw_amount: int,
    barrier: List[int],
) -> int:
    """
    Apply damage to a hero through Barrier → Hero block/evasion → Temp HP → Real HP.
    Returns real HP lost.
    """
    after_barrier, _ = _apply_barrier(raw_amount, barrier)
    return hero.absorb_damage(after_barrier)


def _apply_skill_status(
    special: Optional[str],
    effectiveness: int,
    targets: List,
    venomous: bool = False,
    venomous_upgraded: bool = False,
) -> None:
    """
    Apply status effects encoded in a skill's special tag.
    venomous=True adds +1 duration to all debuffs.
    venomous_upgraded=True doubles potency values.
    """
    if special is None:
        return

    extra_dur = 1 if venomous else 0

    if special == "poison":
        potency = effectiveness * (2 if venomous_upgraded else 1)
        effect = StatusEffect(status_type=StatusType.POISON, duration=2 + extra_dur, potency=potency)
        for t in targets:
            t.apply_status(effect)

    elif special == "weak":
        effect = StatusEffect(status_type=StatusType.WEAK, duration=1 + extra_dur)
        for t in targets:
            t.apply_status(effect)

    elif special == "vulnerable":
        dur = 1 + extra_dur
        potency_val = 2 if venomous_upgraded else 0  # potency=2 signals doubled multiplier
        effect = StatusEffect(status_type=StatusType.VULNERABLE, duration=dur, potency=potency_val)
        for t in targets:
            t.apply_status(effect)

    elif special == "taunt":
        effect = StatusEffect(status_type=StatusType.TAUNT, duration=1)
        for t in targets:
            t.apply_status(effect)

    elif special == "burn":
        effect = StatusEffect(status_type=StatusType.BURN, stacks=2)
        for t in targets:
            t.apply_status(effect)

    elif special == "bleed":
        effect = StatusEffect(status_type=StatusType.BLEED, duration=1 + extra_dur)
        for t in targets:
            t.apply_status(effect)

    elif special == "bleed2":
        for t in targets:
            t.apply_status(StatusEffect(status_type=StatusType.BLEED, duration=1))
            t.apply_status(StatusEffect(status_type=StatusType.BLEED, duration=1))


# ---------------------------------------------------------------------------
# Combat engine
# ---------------------------------------------------------------------------

class CombatEngine:
    def __init__(self, event_bus: EventBus):
        self._event_bus = event_bus

    def simulate(
        self,
        heroes: List[HeroEntity],
        enemies: List[Enemy],
        max_rounds: int = 50,
    ) -> CombatResult:
        return self._run(heroes, enemies, max_rounds, publish_events=True, seed=None)

    def pre_simulate(
        self,
        heroes: List[HeroEntity],
        enemies: List[Enemy],
    ) -> CombatResult:
        return self._run(heroes, enemies, max_rounds=50, publish_events=False, seed=42)

    # ------------------------------------------------------------------
    def _run(
        self,
        heroes: List[HeroEntity],
        enemies: List[Enemy],
        max_rounds: int,
        publish_events: bool,
        seed: Optional[int],
    ) -> CombatResult:

        rng = random.Random(seed) if seed is not None else random.Random()
        enemies = list(enemies)

        # Reset per-combat hero state
        for hero in heroes:
            hero.reset_combat_state()

        rounds: List[CombatRound] = []
        total_hero_damage_taken = 0

        # Bloodletting cross-round state
        prev_bl_active: Dict[str, bool] = {}
        prev_bl_tracked: Dict[str, int] = {}
        prev_bl_cap: Dict[str, int] = {}

        # Mage Barrier: [remaining_hp], expires at start of barrier_expire_round
        barrier: List[int] = [0]
        barrier_expire_round: int = -1

        # Howl bonus carried from previous round
        howl_carry: int = 0

        for round_number in range(1, max_rounds + 1):
            living_heroes = [h for h in heroes if h.current_health > 0]
            living_enemies = [e for e in enemies if e.is_alive and not e.hidden]
            if not living_heroes or not living_enemies:
                break

            # Expire barrier at start of its expiry round
            if round_number >= barrier_expire_round:
                barrier[0] = 0

            bl_active: Dict[str, bool] = {}
            bl_tracked: Dict[str, int] = {}
            bl_cap: Dict[str, int] = {}

            all_hero_results: List[SkillResult] = []
            all_enemy_results: List[SkillResult] = []
            enemy_damage_dealt = 0
            hero_damage_taken = 0
            round_self_damage: Dict[str, int] = {}

            # ==============================================================
            # HERO PHASE
            # ==============================================================
            for hero in living_heroes:
                if hero.current_health <= 0:
                    continue

                # ── Passive / passive-flag detection ─────────────────────
                has_lucky      = hero.has_passive("lucky_roll")
                lucky_upgraded = has_lucky and hero.level5_upgrade == "lucky_roll_upgrade"
                has_tc         = hero.has_passive("thousand_cuts")
                has_blood_rage = hero.has_passive("blood_rage")
                has_iron_will  = hero.has_passive("iron_will")
                has_venomous   = hero.has_passive("venomous")
                venomous_upg   = has_venomous and hero.level5_upgrade == "venomous_upgrade"
                has_divine_ovf = hero.has_passive("divine_overflow")
                divine_ovf_upg = has_divine_ovf and hero.level5_upgrade == "divine_overflow_upgrade"
                has_prayer     = hero.has_passive("prayer")
                has_arc_flow   = hero.has_passive("arcane_flow")
                arc_flow_upg   = has_arc_flow and hero.level5_upgrade == "arcane_flow_upgrade"
                has_spellweave = hero.has_passive("spellweave")
                spell_upg      = has_spellweave and hero.level5_upgrade == "spellweave_upgrade"
                has_iron_will_upg = has_iron_will and hero.level5_upgrade == "iron_will_upgrade"

                # ── SOT: Iron Will (temp HP → real HP) ───────────────────
                if has_iron_will and hero.temp_hp > 0:
                    conversion = math.floor(hero.temp_hp / 2)
                    hero.temp_hp -= conversion
                    hero.current_health = min(hero.max_health, hero.current_health + conversion)

                # ── SOT: Bloodletting conversion from previous turn ───────
                hid = hero.hero_id
                if prev_bl_active.get(hid):
                    amount = min(prev_bl_tracked.get(hid, 0), prev_bl_cap.get(hid, 0))
                    if amount > 0:
                        hero.apply_temp_hp(amount)

                # ── SOT: Regeneration tick ────────────────────────────────
                if hero.regen_remaining > 0:
                    heal_amt = min(hero.regen_value, hero.max_health - hero.current_health)
                    hero.current_health += heal_amt
                    hero.regen_remaining -= 1
                    if has_divine_ovf and heal_amt > 0:
                        self._divine_overflow_heal(hero, heroes, heal_amt, divine_ovf_upg)

                # ── SOT: Blizzard tick (Mage only) ────────────────────────
                if hero.blizzard_ticks_remaining > 0:
                    living_now = [e for e in enemies if e.is_alive and not e.hidden]
                    bliz_dmg = hero.blizzard_stored_damage
                    for e in living_now:
                        if not getattr(e, "absolute_untargetable", False):
                            e.take_damage(bliz_dmg)
                            enemy_damage_dealt += bliz_dmg
                    hero.blizzard_ticks_remaining -= 1

                # ── SOT: Battle Hymn advantage flag ──────────────────────
                if hero.advantage_next_turn:
                    hero.apply_status(StatusEffect(status_type=StatusType.ADVANTAGE, duration=1))
                    hero.advantage_next_turn = False

                # ── Build & modify dice pool ──────────────────────────────
                pool = compose_pool(hero)
                pool = apply_status_modifiers(pool, hero.status_effects, rng)

                # ── Roll ──────────────────────────────────────────────────
                rolled = roll_pool(
                    pool, hero.status_effects, rng,
                    has_lucky_roll=has_lucky,
                    lucky_roll_upgraded=lucky_upgraded,
                    has_thousand_cuts=has_tc,
                )

                locked_dice  = [d for d in pool if d.is_locked]
                normal_dice  = [d for d in pool if not d.is_locked]
                rolled_locked = rolled[: len(locked_dice)]
                rolled_normal = rolled[len(locked_dice):]

                # ── Assign dice to skill slots ────────────────────────────
                assignments = assign_dice(hero, rolled_locked, rolled_normal)

                # ── Detect Bloodletting (must happen before skills fire) ──
                for assignment in assignments:
                    sk = assignment.skill
                    if sk.special == "bloodletting" and assignment.is_active:
                        bl_active[hid] = True
                        bl_tracked[hid] = 0
                        raw_eff = sum(assignment.assigned_dice) + hero.effective_modifier(sk.associated_stat)
                        bl_cap[hid] = max(0, raw_eff)

                # ── CHARGE PHASE: accumulate dice for charge-based skills ─
                arcane_flow_bonus_used = False
                charged_spell_fired_this_turn = False

                for assignment in assignments:
                    sk = assignment.skill
                    if sk.charge_cost <= 0 or not assignment.is_active:
                        continue

                    added = sum(assignment.assigned_dice)

                    # Arcane Flow: halve charge cost (rounded up)
                    effective_cost = sk.charge_cost
                    if has_arc_flow:
                        effective_cost = math.ceil(sk.charge_cost / 2)

                    # Prepared level-5: first N charges are free (fire immediately)
                    if hero.prepared_charges > 0 and hero.level5_upgrade == "prepared":
                        self._fire_charged_spell(
                            hero, sk, all_hero_results, enemies, heroes,
                            barrier, barrier_expire_round, round_number,
                            bl_active, bl_tracked, enemy_damage_dealt,
                            rng, has_spellweave, spell_upg,
                        )
                        hero.prepared_charges -= 1
                        sk.current_charge = 0
                        charged_spell_fired_this_turn = True
                    else:
                        sk.current_charge += added
                        if sk.current_charge >= effective_cost:
                            self._fire_charged_spell(
                                hero, sk, all_hero_results, enemies, heroes,
                                barrier, barrier_expire_round, round_number,
                                bl_active, bl_tracked, enemy_damage_dealt,
                                rng, has_spellweave, spell_upg,
                            )
                            sk.current_charge = 0
                            charged_spell_fired_this_turn = True

                    # Arcane Flow: grant bonus d12 once per turn when a spell fires
                    if charged_spell_fired_this_turn and has_arc_flow and not arcane_flow_bonus_used:
                        bonus_roll = rng.randint(1, 12)
                        # Add bonus roll to Arcane Bolt's effectiveness if it fires this turn
                        for res in all_hero_results:
                            if res.skill.special is None and res.effect_type == "damage" and res.skill in hero.skills:
                                res.effectiveness += bonus_roll
                                break
                        arcane_flow_bonus_used = True
                        if arc_flow_upg:
                            arcane_flow_bonus_used = False  # upgrade: no once-per-turn limit

                    # Clear dice so execute_all_skills won't double-process
                    assignment.assigned_dice = []

                # ── EXECUTE normal skills ─────────────────────────────────
                results = execute_all_skills(hero, assignments)

                # Pre-pass: compute Blade Dance dice_spent_elsewhere
                blade_dance_result = next(
                    (r for r in results if r.special == "blade_dance"), None
                )
                if blade_dance_result is not None:
                    dice_elsewhere = sum(
                        sum(a.assigned_dice)
                        for a in assignments
                        if a.skill.special != "blade_dance" and a.is_active
                    )
                    blade_dance_result.dice_spent_elsewhere = dice_elsewhere
                    dex_mod = hero.effective_modifier(Stat.DEX)
                    blade_dance_result.effectiveness = max(0, dice_elsewhere * dex_mod)

                # ── Process each skill result ─────────────────────────────
                for result in results:
                    if result.effectiveness <= 0 and result.hit_count == 0:
                        if result.special not in ("evasion", "primal_roar", "battle_hymn",
                                                   "blessing", "fortify", "battle_hymn"):
                            continue

                    sk = result.skill

                    # ── DEFEND skills ─────────────────────────────────────
                    if result.effect_type == "defend":
                        all_hero_results.append(result)

                        if sk.special == "barrier":
                            # Old non-charge Barrier (backward compat if charge_cost == 0)
                            barrier[0] = result.effectiveness
                            barrier_expire_round = round_number + 1
                        continue

                    # ── SELF skills ───────────────────────────────────────
                    if result.effect_type == "self":
                        all_hero_results.append(result)
                        self._apply_self_skill(
                            hero, sk, result, heroes, enemies,
                            bl_active, bl_tracked, round_self_damage,
                            hero_damage_taken, rng,
                        )
                        if has_prayer and sk.special not in _PRAYER_EXCLUDED:
                            hero.prayer_stacks += 1
                            if hero.prayer_stacks >= 10 and not hero.prayer_aoe_unlocked:
                                hero.prayer_aoe_unlocked = True
                        continue

                    # ── HEAL ──────────────────────────────────────────────
                    if result.effect_type == "heal":
                        all_hero_results.append(result)

                        if sk.special == "regeneration":
                            # Apply regen to lowest-HP ally
                            target = self._lowest_hp_ally(heroes)
                            if target:
                                target.regen_value = result.effectiveness
                                target.regen_remaining = 3
                        else:
                            # Instant heal to lowest-HP ally
                            target = self._lowest_hp_ally(heroes)
                            if target:
                                heal_amount = result.effectiveness
                                target.current_health = min(
                                    target.max_health,
                                    target.current_health + heal_amount,
                                )
                                if has_divine_ovf and heal_amount > 0:
                                    self._divine_overflow_heal(
                                        hero, heroes, heal_amount, divine_ovf_upg
                                    )

                        if has_prayer:
                            hero.prayer_stacks += 1
                            if hero.prayer_stacks >= 10 and not hero.prayer_aoe_unlocked:
                                hero.prayer_aoe_unlocked = True
                        continue

                    # ── CLEANSE ───────────────────────────────────────────
                    if result.effect_type == "cleanse":
                        all_hero_results.append(result)
                        stacks_to_remove = hero.effective_modifier(Stat.CHA)
                        num_targets = math.ceil(result.effectiveness / 2)
                        ally_targets = sorted(
                            [h for h in heroes if h.current_health > 0],
                            key=lambda h: h.current_health,
                        )[:num_targets]
                        for ally in ally_targets:
                            remaining = stacks_to_remove
                            debuffs = [e for e in ally.status_effects if e.is_debuff()]
                            for debuff in debuffs:
                                if remaining <= 0:
                                    break
                                if debuff.status_type == StatusType.POISON:
                                    removed = min(remaining, debuff.potency)
                                    debuff.potency = max(0, debuff.potency - removed)
                                    remaining -= removed
                                    if debuff.potency <= 0:
                                        ally.clear_status(debuff.status_type)
                                elif debuff.status_type == StatusType.BURN:
                                    removed = min(remaining, debuff.stacks)
                                    debuff.stacks -= removed
                                    remaining -= removed
                                    if debuff.stacks <= 0:
                                        ally.clear_status(debuff.status_type)
                                else:
                                    removed = min(remaining, debuff.duration)
                                    debuff.duration -= removed
                                    remaining -= removed
                                    if debuff.duration <= 0:
                                        ally.clear_status(debuff.status_type)
                        if has_prayer:
                            hero.prayer_stacks += 1
                            if hero.prayer_stacks >= 10 and not hero.prayer_aoe_unlocked:
                                hero.prayer_aoe_unlocked = True
                        continue

                    # ── BUFF skills (Blessing, Battle Hymn, Fortify) ──────
                    if result.effect_type == "buff":
                        all_hero_results.append(result)
                        self._apply_buff_skill(hero, sk, result, heroes, rng)
                        if has_prayer:
                            hero.prayer_stacks += 1
                            if hero.prayer_stacks >= 10 and not hero.prayer_aoe_unlocked:
                                hero.prayer_aoe_unlocked = True
                        continue

                    # ── DAMAGE / AOE ──────────────────────────────────────
                    living_now = [e for e in enemies if e.is_alive and not e.hidden]
                    if not living_now:
                        break

                    targetable = [
                        e for e in living_now
                        if not getattr(e, "untargetable", False)
                        and not getattr(e, "absolute_untargetable", False)
                    ]
                    if not targetable:
                        targetable = living_now

                    taunting = [e for e in targetable if has_status(e.status_effects, StatusType.TAUNT)]

                    # Prayer AOE conversion: if unlocked, all offensive skills hit all enemies
                    prayer_aoe = has_prayer and hero.prayer_aoe_unlocked
                    prayer_bonus = hero.blood_rage_stacks  # Blood Rage flat bonus

                    # Blood Cleave self-cost
                    if sk.special == "blood_cleave":
                        cost = max(1, int(hero.current_health * 0.05))
                        temp_abs = min(hero.temp_hp, cost)
                        hero.temp_hp -= temp_abs
                        real_cost = cost - temp_abs
                        actual = min(real_cost, hero.current_health - 1)
                        hero.current_health -= actual
                        hero_damage_taken += actual
                        round_self_damage[hid] = round_self_damage.get(hid, 0) + cost

                    all_hero_results.append(result)

                    # Arcane Bolt tracking (Spellweave)
                    if sk.element == "arcane" and sk.charge_cost == 0:
                        hero.arcane_bolt_cast_this_combat = True

                    # --- Eviscerate (multi-hit) ---
                    if sk.special == "eviscerate":
                        target = rng.choice(taunting if taunting else targetable)
                        base_hit = result.per_hit_damage
                        enhanced = target.has_any_debuff()
                        per_hit = (base_hit + 2) if enhanced else base_hit
                        per_hit += hero.blood_rage_stacks
                        per_hit = _apply_weak(per_hit, hero.status_effects)
                        for _ in range(result.hit_count):
                            hit_dmg = _apply_vulnerable(per_hit, target.status_effects)
                            ret_before = target.retaliate_active and target.block > 0
                            real = target.take_damage(hit_dmg)
                            enemy_damage_dealt += real
                            if ret_before:
                                hero, hero_damage_taken = self._apply_retaliate(
                                    target, hero, hero_damage_taken, bl_active, bl_tracked)

                    elif result.hits_all or prayer_aoe:
                        # AOE — skip absolute_untargetable
                        aoe_targets = [
                            e for e in living_now
                            if not getattr(e, "absolute_untargetable", False)
                        ]
                        for e in aoe_targets:
                            eff = result.effectiveness + hero.blood_rage_stacks
                            dmg = _apply_weak(eff, hero.status_effects)
                            dmg = _apply_vulnerable(dmg, e.status_effects)
                            ret_before = e.retaliate_active and e.block > 0
                            real = e.take_damage(dmg)
                            enemy_damage_dealt += real
                            if ret_before:
                                hero, hero_damage_taken = self._apply_retaliate(
                                    e, hero, hero_damage_taken, bl_active, bl_tracked)
                        _apply_skill_status(
                            sk.special, result.effectiveness, aoe_targets,
                            venomous=has_venomous, venomous_upgraded=venomous_upg,
                        )

                    else:
                        # Single-target
                        target = rng.choice(taunting if taunting else targetable)
                        eff = result.effectiveness + hero.blood_rage_stacks
                        dmg = _apply_weak(eff, hero.status_effects)
                        dmg = _apply_vulnerable(dmg, target.status_effects)
                        ret_before = target.retaliate_active and target.block > 0
                        real = target.take_damage(dmg)
                        enemy_damage_dealt += real
                        if ret_before:
                            hero, hero_damage_taken = self._apply_retaliate(
                                target, hero, hero_damage_taken, bl_active, bl_tracked)
                        _apply_skill_status(
                            sk.special, result.effectiveness, [target],
                            venomous=has_venomous, venomous_upgraded=venomous_upg,
                        )

                # ── EOT: Blood Rage ───────────────────────────────────────
                if has_blood_rage:
                    cost = max(1, math.floor(hero.current_health * 0.05))
                    temp_abs = min(hero.temp_hp, cost)
                    hero.temp_hp -= temp_abs
                    overflow = cost - temp_abs
                    actual_real = min(overflow, hero.current_health - 1)
                    hero.current_health -= actual_real
                    hero_damage_taken += actual_real
                    round_self_damage[hid] = round_self_damage.get(hid, 0) + cost
                    hero.blood_rage_stacks += 1
                    # Level-5 Blood Rage upgrade: gain permanent Advantage
                    if hero.level5_upgrade == "blood_rage_upgrade":
                        hero.apply_status(StatusEffect(status_type=StatusType.ADVANTAGE, duration=999))

                # ── EOT: Evasion expires ──────────────────────────────────
                hero.evasion_active = False
                hero.evasion_value = 0

                # ── EOT: tick statuses, Burn/Poison damage ────────────────
                hero.status_effects, dmg_events = tick_statuses(hero.status_effects)
                for _, dmg in dmg_events:
                    real = _damage_hero(hero, dmg, barrier)
                    hero_damage_taken += real
                    if bl_active.get(hid):
                        bl_tracked[hid] = bl_tracked.get(hid, 0) + real

            # Accumulate Blood Cleave / Blood Rage self-damage into Bloodletting
            for hid2, self_dmg in round_self_damage.items():
                if bl_active.get(hid2):
                    bl_tracked[hid2] = bl_tracked.get(hid2, 0) + self_dmg

            # ==============================================================
            # ENEMY PHASE
            # ==============================================================

            # Remove spawned entities whose owner has died
            for e in list(enemies):
                if e.owner_ref is not None and not e.owner_ref.is_alive:
                    e.current_health = 0

            round_howl_bonus = howl_carry
            new_howl = 0
            enemy_phase_dmg_ref: List[int] = [0]

            living_enemies = [e for e in enemies if e.is_alive and not e.hidden]
            same_turn_spawns: List[Enemy] = []

            for enemy in living_enemies:
                if not enemy.is_alive:
                    continue

                living_now = [h for h in heroes if h.current_health > 0]
                if not living_now:
                    break

                triggered = enemy.take_turn(rng)

                for new_entity in enemy.spawn_queue:
                    enemies.append(new_entity)
                    if new_entity.acts_this_turn:
                        same_turn_spawns.append(new_entity)
                        new_entity.acts_this_turn = False
                enemy.spawn_queue.clear()

                self._process_enemy_skills(
                    enemy, triggered, living_now,
                    barrier, bl_active, bl_tracked,
                    round_howl_bonus, all_enemy_results,
                    hero_damage_taken_ref=enemy_phase_dmg_ref,
                    rng=rng,
                    publish_events=publish_events,
                    heroes=heroes,
                )

                for skill, _ in triggered:
                    if skill.special == "howl":
                        new_howl += 1

                enemy.status_effects, dmg_events = tick_statuses(enemy.status_effects)
                for _, dmg in dmg_events:
                    enemy.take_damage(dmg)

                flee_turns = enemy.flee_after_turns
                if flee_turns > 0 and enemy.turns_taken >= flee_turns:
                    enemy.fled = True
                    enemy.current_health = 0

            for entity in same_turn_spawns:
                if not entity.is_alive:
                    continue
                living_now = [h for h in heroes if h.current_health > 0]
                if not living_now:
                    break
                triggered = entity.take_turn(rng)
                entity.spawn_queue.clear()
                self._process_enemy_skills(
                    entity, triggered, living_now,
                    barrier, bl_active, bl_tracked,
                    round_howl_bonus, all_enemy_results,
                    hero_damage_taken_ref=enemy_phase_dmg_ref,
                    rng=rng,
                    publish_events=publish_events,
                    heroes=heroes,
                )
                entity.status_effects, dmg_events = tick_statuses(entity.status_effects)
                for _, dmg in dmg_events:
                    entity.take_damage(dmg)

            hero_damage_taken += enemy_phase_dmg_ref[0]
            total_hero_damage_taken += hero_damage_taken

            # Carry Bloodletting state forward
            prev_bl_active = dict(bl_active)
            prev_bl_tracked = dict(bl_tracked)
            prev_bl_cap = dict(bl_cap)
            howl_carry = new_howl

            rounds.append(CombatRound(
                round_number=round_number,
                hero_results=all_hero_results,
                enemy_results=all_enemy_results,
                hero_damage_taken=hero_damage_taken,
                enemy_damage_dealt=enemy_damage_dealt,
                hero_hp_after={h.hero_id: h.current_health for h in heroes},
                enemy_hp_after=[e.current_health for e in enemies],
            ))

            if publish_events:
                self._event_bus.publish("combat.round_complete", round_number)

            living_heroes = [h for h in heroes if h.current_health > 0]
            living_enemies = [e for e in enemies if e.is_alive and not e.hidden]
            if not living_enemies or not living_heroes:
                break

        living_heroes = [h for h in heroes if h.current_health > 0]
        living_enemies = [e for e in enemies if e.is_alive and not e.hidden]
        victory = len(living_enemies) == 0 and len(living_heroes) > 0
        heroes_survived = [h.hero_id for h in living_heroes]

        if publish_events:
            if victory:
                self._event_bus.publish("combat.victory", None)
            else:
                self._event_bus.publish("combat.defeat", None)

        return CombatResult(
            victory=victory,
            rounds=rounds,
            heroes_survived=heroes_survived,
            total_hero_damage_taken=total_hero_damage_taken,
            enemies_final=enemies,
        )

    # ------------------------------------------------------------------
    # Charged spell firing
    # ------------------------------------------------------------------

    def _fire_charged_spell(
        self,
        hero: HeroEntity,
        skill: Skill,
        all_hero_results: list,
        enemies: list,
        heroes: list,
        barrier: List[int],
        barrier_expire_round: int,
        round_number: int,
        bl_active: dict,
        bl_tracked: dict,
        enemy_damage_dealt_ref: int,
        rng: random.Random,
        has_spellweave: bool,
        spell_upg: bool,
    ) -> None:
        """Fire a fully-charged Mage spell with its fixed effect."""
        from combat.skill_executor import SkillResult as SR

        special = skill.special
        living = [e for e in enemies if e.is_alive and not e.hidden
                  and not getattr(e, "absolute_untargetable", False)]

        result = SR(
            skill=skill,
            effectiveness=0,
            effect_type=skill.effect_type,
            hits_all=(skill.effect_type == "aoe"),
            special=special,
        )
        all_hero_results.append(result)

        # Track element for Spellweave
        if has_spellweave and skill.element and skill.element != "arcane":
            if skill.element not in hero.convergence_elements:
                hero.convergence_elements.append(skill.element)
            if len(hero.convergence_elements) >= 3:
                self._fire_convergence(hero, enemies, heroes, barrier, spell_upg, rng)
                hero.convergence_elements.clear()

        if special == "fireball_charge":
            dmg = FIREBALL_DAMAGE
            for e in living:
                e.take_damage(dmg)
            burn = FIREBALL_BURN_STACKS
            for e in living:
                e.apply_status(StatusEffect(status_type=StatusType.BURN, stacks=burn))

        elif special == "barrier_charge":
            int_mod = hero.effective_modifier(Stat.INT)
            barrier[0] = BARRIER_ABSORPTION_BASE + int_mod
            # expires next round (stored as barrier_expire_round)

        elif special == "chain_lightning_charge":
            if living:
                hits = CHAIN_LIGHTNING_HITS if not spell_upg else CHAIN_LIGHTNING_HITS
                paralyze_count = 1 if not spell_upg else 1  # upgrade doubles other effects
                for _ in range(hits):
                    target = rng.choice(living)
                    target.take_damage(CHAIN_LIGHTNING_DAMAGE)
                    target.apply_status(StatusEffect(
                        status_type=StatusType.PARALYZE, stacks=paralyze_count
                    ))

        elif special == "blizzard_charge":
            dmg = BLIZZARD_DAMAGE
            for e in living:
                e.take_damage(dmg)
                e.apply_status(StatusEffect(status_type=StatusType.DOWNGRADE, duration=1))
            hero.blizzard_stored_damage = dmg
            hero.blizzard_ticks_remaining = BLIZZARD_TICKS

        elif special == "earthquake_charge":
            for e in living:
                e.take_damage(EARTHQUAKE_DAMAGE)
                e.apply_status(StatusEffect(status_type=StatusType.DISADVANTAGE, duration=1))

        elif special == "meteor_charge":
            if living:
                primary = rng.choice(living)
                primary.take_damage(METEOR_SINGLE_DAMAGE)
            burn = METEOR_BURN_STACKS
            for e in living:
                e.apply_status(StatusEffect(status_type=StatusType.BURN, stacks=burn))

    def _fire_convergence(
        self,
        hero: HeroEntity,
        enemies: list,
        heroes: list,
        barrier: List[int],
        spell_upg: bool,
        rng: random.Random,
    ) -> None:
        """Fire the Spellweave elemental convergence spell."""
        living = [e for e in enemies if e.is_alive and not e.hidden
                  and not getattr(e, "absolute_untargetable", False)]

        bonus_damage = 10 if spell_upg else 5
        arcane_bonus = bonus_damage if hero.arcane_bolt_cast_this_combat else 0

        for element in hero.convergence_elements:
            if element == "fire":
                dmg = (15 if spell_upg else 10) + arcane_bonus
                for e in living:
                    e.take_damage(dmg)
            elif element == "lightning":
                stacks = 3 if spell_upg else 2
                for e in living:
                    e.apply_status(StatusEffect(status_type=StatusType.PARALYZE, stacks=stacks))
            elif element == "ice":
                dur = 2 if spell_upg else 1
                for e in living:
                    e.apply_status(StatusEffect(status_type=StatusType.DOWNGRADE, duration=dur))
            elif element == "earth":
                dur = 2 if spell_upg else 1
                for e in living:
                    e.apply_status(StatusEffect(status_type=StatusType.DISADVANTAGE, duration=dur))

    # ------------------------------------------------------------------
    # Self-targeting skill handler
    # ------------------------------------------------------------------

    def _apply_self_skill(
        self,
        hero: HeroEntity,
        sk: Skill,
        result: SkillResult,
        heroes: list,
        enemies: list,
        bl_active: dict,
        bl_tracked: dict,
        round_self_damage: dict,
        hero_damage_taken: int,
        rng: random.Random,
    ) -> None:
        """Handle self-targeting skills: primal_roar, second_wind, evasion."""
        special = sk.special
        eff = result.effectiveness

        if special == "primal_roar":
            hero.add_temp_hp(eff)
            living_enemies = [e for e in enemies if e.is_alive and not e.hidden]
            for e in living_enemies:
                e.apply_status(StatusEffect(status_type=StatusType.WEAK, duration=1))

        elif special == "second_wind":
            if hero.second_wind_used:
                return
            exh_level = hero.exhaustion_level()  # evaluated BEFORE reduction
            hero.exhaustion = max(0.0, hero.exhaustion - eff)
            con_mod = hero.effective_modifier(Stat.CON)
            temp_gain = exh_level * eff
            hp_gain = exh_level * con_mod
            hero.add_temp_hp(temp_gain)
            hero.current_health = min(hero.max_health, hero.current_health + max(0, hp_gain))
            hero.second_wind_used = True
            # Temp HP feeds Bloodletting if active
            if bl_active.get(hero.hero_id):
                bl_tracked[hero.hero_id] = bl_tracked.get(hero.hero_id, 0) + temp_gain

        elif special == "evasion":
            hero.evasion_value = eff
            hero.evasion_active = True

    # ------------------------------------------------------------------
    # Buff skill handler (Blessing, Battle Hymn, Fortify)
    # ------------------------------------------------------------------

    def _apply_buff_skill(
        self,
        hero: HeroEntity,
        sk: Skill,
        result: SkillResult,
        heroes: list,
        rng: random.Random,
    ) -> None:
        """Handle buff skills targeting allies."""
        special = sk.special
        eff = result.effectiveness
        living_allies = [h for h in heroes if h.current_health > 0]

        if special == "blessing":
            # Apply Upgrade to lowest-HP ally (autoplay) or player-selected (manual)
            target = self._lowest_hp_ally(heroes)
            if target:
                target.apply_status(StatusEffect(status_type=StatusType.UPGRADE, duration=1))

        elif special == "battle_hymn":
            # All allies gain Advantage on their NEXT turn
            for ally in living_allies:
                ally.advantage_next_turn = True

        elif special == "fortify":
            # Apply block + retaliate to lowest-HP ally
            target = self._lowest_hp_ally(heroes)
            if target:
                target.block = eff
                con_mod = hero.effective_modifier(Stat.CON)
                target.retaliate_value = max(0, con_mod)
                target.retaliate_active = True
                target.retaliate_consumed = False

    # ------------------------------------------------------------------
    # Divine Overflow helper
    # ------------------------------------------------------------------

    def _divine_overflow_heal(
        self,
        cleric: HeroEntity,
        heroes: list,
        heal_amount: int,
        upgraded: bool,
    ) -> None:
        """Apply overflow healing to the lowest-HP unit on the field."""
        overflow = math.floor(heal_amount / 2)
        if overflow <= 0:
            return
        # Find lowest-HP unit among living heroes (including cleric)
        living = [h for h in heroes if h.current_health > 0]
        if not living:
            return
        lowest = min(living, key=lambda h: h.current_health)
        lowest.current_health = min(lowest.max_health, lowest.current_health + overflow)

        # Upgraded: also cleanse oldest debuff from overflow target
        if upgraded and lowest.status_effects:
            debuffs = [e for e in lowest.status_effects if e.is_debuff()]
            if debuffs:
                oldest = debuffs[0]
                lowest.status_effects.remove(oldest)

    # ------------------------------------------------------------------
    # Retaliate helper
    # ------------------------------------------------------------------

    def _apply_retaliate(
        self,
        enemy: Enemy,
        hero: HeroEntity,
        hero_damage_taken: int,
        bl_active: Dict[str, bool],
        bl_tracked: Dict[str, int],
    ) -> Tuple[HeroEntity, int]:
        """
        Trigger retaliate on an enemy that was hit while its block was active.
        Returns updated (hero, hero_damage_taken).
        """
        ret_dmg = enemy.retaliate_damage
        if ret_dmg > 0:
            actual = min(ret_dmg, hero.current_health)
            hero.current_health -= actual
            hero_damage_taken += actual
            if bl_active.get(hero.hero_id):
                bl_tracked[hero.hero_id] = bl_tracked.get(hero.hero_id, 0) + actual
        bleed = StatusEffect(status_type=StatusType.BLEED, duration=1)
        hero.apply_status(bleed)
        enemy.retaliate_active = False
        return hero, hero_damage_taken

    # ------------------------------------------------------------------
    # Hero retaliate (Fortify)
    # ------------------------------------------------------------------

    def _maybe_hero_retaliate(
        self,
        hero: HeroEntity,
        attacker: Enemy,
    ) -> None:
        """
        If a hero has an active, unconsumed retaliate from Fortify,
        trigger it against the attacking enemy.  Bypasses enemy block and temp HP.
        """
        if hero.retaliate_active and not hero.retaliate_consumed and hero.retaliate_value > 0:
            dmg = hero.retaliate_value
            actual = min(dmg, attacker.current_health)
            attacker.current_health -= actual
            hero.retaliate_consumed = True
            hero.retaliate_active = False

    # ------------------------------------------------------------------
    # Enemy skill processing
    # ------------------------------------------------------------------

    def _process_enemy_skills(
        self,
        enemy: Enemy,
        triggered: list,
        living_now: List[HeroEntity],
        barrier: List[int],
        bl_active: Dict[str, bool],
        bl_tracked: Dict[str, int],
        round_howl_bonus: int,
        all_enemy_results: list,
        hero_damage_taken_ref: List[int],
        rng: random.Random,
        publish_events: bool,
        heroes: List[HeroEntity] = None,
    ) -> None:
        """
        Resolve one enemy's triggered skill list against the hero party.
        Mutates hero HP, status effects, all_enemy_results, and hero_damage_taken_ref[0].
        """
        from combat.skill_executor import SkillResult as SR

        shadow_mult = getattr(enemy, "shadow_damage_multiplier", 1.0)

        for skill, effectiveness in triggered:
            effectiveness = int(effectiveness * shadow_mult) if shadow_mult != 1.0 else effectiveness

            enemy_result = SR(
                skill=skill,
                effectiveness=effectiveness,
                effect_type=skill.effect_type,
                hits_all=(skill.effect_type == "aoe" or skill.special == "golden_explosion"),
            )
            all_enemy_results.append(enemy_result)

            if effectiveness <= 0:
                continue

            if skill.special in ("howl", "phase_advance", "spawn_turret"):
                continue

            # Mech: Cannon Barrage
            if skill.special == "cannon_barrage":
                n = len(living_now)
                if n > 0:
                    per_hero = effectiveness // n
                    remainder = effectiveness % n
                    for j, target_hero in enumerate(living_now):
                        dmg = per_hero + (remainder if j == 0 else 0)
                        dmg = _apply_weak(dmg + round_howl_bonus, enemy.status_effects)
                        dmg = _apply_vulnerable(dmg, target_hero.status_effects)
                        real = _damage_hero(target_hero, dmg, barrier)
                        hero_damage_taken_ref[0] += real
                        self._maybe_hero_retaliate(target_hero, enemy)
                        if bl_active.get(target_hero.hero_id):
                            bl_tracked[target_hero.hero_id] = bl_tracked.get(target_hero.hero_id, 0) + real
                continue

            # Mech: Oil Trap
            if skill.special == "oil_trap":
                for target_hero in list(living_now):
                    target_hero.apply_status(StatusEffect(status_type=StatusType.WEAK, duration=2))
                    target_hero.apply_status(StatusEffect(status_type=StatusType.VULNERABLE, duration=1))
                    target_hero.apply_status(StatusEffect(status_type=StatusType.PARALYZE, duration=1, stacks=1))
                continue

            # Boss: golden_explosion
            if skill.special == "golden_explosion":
                for target_hero in list(living_now):
                    real = _damage_hero(target_hero, effectiveness, barrier)
                    hero_damage_taken_ref[0] += real
                    self._maybe_hero_retaliate(target_hero, enemy)
                    if bl_active.get(target_hero.hero_id):
                        bl_tracked[target_hero.hero_id] = bl_tracked.get(target_hero.hero_id, 0) + real
                continue

            if skill.effect_type == "defend":
                enemy.block += effectiveness
                if skill.special == "trap":
                    enemy.retaliate_active = True
                if skill.special in ("paralyze_all", "paralyze_all_2"):
                    stacks = 2 if skill.special == "paralyze_all_2" else 1
                    para = StatusEffect(status_type=StatusType.PARALYZE, duration=1, stacks=stacks)
                    for target_hero in list(living_now):
                        target_hero.apply_status(para)

            elif skill.effect_type == "aoe":
                for target_hero in list(living_now):
                    dmg = _apply_weak(effectiveness + round_howl_bonus, enemy.status_effects)
                    dmg = _apply_vulnerable(dmg, target_hero.status_effects)
                    real = _damage_hero(target_hero, dmg, barrier)
                    hero_damage_taken_ref[0] += real
                    self._maybe_hero_retaliate(target_hero, enemy)
                    if bl_active.get(target_hero.hero_id):
                        bl_tracked[target_hero.hero_id] = bl_tracked.get(target_hero.hero_id, 0) + real
                    if enemy.gold_steal and real > 0 and publish_events:
                        self._event_bus.publish("gold.stolen", {"amount": 5, "by": enemy.enemy_id})
                _apply_skill_status(skill.special, effectiveness, list(living_now))
                if hasattr(enemy, "gain_bloodlust"):
                    enemy.gain_bloodlust(effectiveness * len(living_now))

            elif skill.special == "golden_wave":
                num_targets = min(2, len(living_now))
                targets = rng.sample(living_now, num_targets)
                for target_hero in targets:
                    dmg = _apply_weak(effectiveness + round_howl_bonus, enemy.status_effects)
                    dmg = _apply_vulnerable(dmg, target_hero.status_effects)
                    real = _damage_hero(target_hero, dmg, barrier)
                    hero_damage_taken_ref[0] += real
                    self._maybe_hero_retaliate(target_hero, enemy)
                    if bl_active.get(target_hero.hero_id):
                        bl_tracked[target_hero.hero_id] = bl_tracked.get(target_hero.hero_id, 0) + real

            else:
                # Single-target
                target_hero = rng.choice(living_now)
                dmg = _apply_weak(effectiveness + round_howl_bonus, enemy.status_effects)
                dmg = _apply_vulnerable(dmg, target_hero.status_effects)
                real = _damage_hero(target_hero, dmg, barrier)
                hero_damage_taken_ref[0] += real
                self._maybe_hero_retaliate(target_hero, enemy)
                if bl_active.get(target_hero.hero_id):
                    bl_tracked[target_hero.hero_id] = bl_tracked.get(target_hero.hero_id, 0) + real
                _apply_skill_status(skill.special, effectiveness, [target_hero])
                if enemy.gold_steal and real > 0 and publish_events:
                    self._event_bus.publish("gold.stolen", {"amount": 5, "by": enemy.enemy_id})
                if hasattr(enemy, "gain_bloodlust"):
                    enemy.gain_bloodlust(real)

    # ------------------------------------------------------------------
    # Utility
    # ------------------------------------------------------------------

    def _lowest_hp_ally(self, heroes: list) -> Optional[HeroEntity]:
        """Return the living hero with the lowest current HP."""
        living = [h for h in heroes if h.current_health > 0]
        if not living:
            return None
        return min(living, key=lambda h: h.current_health)


# Skills that do NOT count as non-attack for Prayer
_PRAYER_EXCLUDED: frozenset = frozenset({"evasion"})
