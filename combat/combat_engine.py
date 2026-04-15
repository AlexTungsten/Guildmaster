"""
combat_engine.py — Turn-based combat simulator for Guildmaster.

Each round:
  Hero phase — for every living hero:
    1. Start-of-turn: apply status modifiers to dice pool (Upgrade/Downgrade/Bleed).
    2. Roll dice pool (Advantage / Disadvantage / Lucky Roll / Paralyze).
    3. Assign dice to skills (behavior profile or player input).
    4. For each skill that fires:
       - Defend skills: activate passives (Bloodletting), apply Barrier (Mage).
       - Damage/AOE: check Weak on attacker, Vulnerable on target.
         Eviscerate: multi-hit, Vulnerable per hit, enhanced if target has debuff.
       - Heal: restore HP to lowest-HP ally.
       - Cleanse: remove status stacks from allies.
       - Cooldown skills (Mage): dice go to refresh progress if on cooldown.
    5. Apply skill status effects to targets (poison, weak, taunt …).
    6. End-of-turn: Burn/Poison deal damage, all durations tick.

  Enemy phase — for every living enemy:
    1. take_turn() rolls dice and returns triggered (skill, effectiveness) pairs.
    2. Defend: add block. Damage: apply Weak/Vulnerable, Barrier absorption.
    3. Apply skill status effects to targeted heroes.
    4. End-of-turn: tick enemy statuses.

Supports simulate() (live, with events) and pre_simulate() (seeded, no events).
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
    enemy_hp_after: List[int] = field(default_factory=list)  # positional (avoids duplicate enemy_id issues)


@dataclass
class CombatResult:
    """Aggregate result of a full combat encounter."""
    victory: bool
    rounds: List[CombatRound]
    heroes_survived: List[str]
    total_hero_damage_taken: int
    enemies_final: List[Enemy] = field(default_factory=list)
    # Full enemy list at end of combat (includes all spawned entities in append order).
    # enemies_final[:len(round.enemy_hp_after)] gives the correct enemy set for any round.


# ---------------------------------------------------------------------------
# Damage application helpers
# ---------------------------------------------------------------------------

def _apply_weak(damage: int, attacker_effects: List[StatusEffect]) -> int:
    """Reduce damage by 25% if the attacker is Weak."""
    if has_status(attacker_effects, StatusType.WEAK):
        return max(1, int(damage * 0.75))
    return damage


def _apply_vulnerable(damage: int, target_effects: List[StatusEffect]) -> int:
    """Increase damage by 50% (last multiplier) if target is Vulnerable."""
    if has_status(target_effects, StatusType.VULNERABLE):
        return int(damage * 1.5)
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
    Apply damage to a hero through Barrier → Temp HP → Real HP.
    Returns real HP lost.
    """
    after_barrier, _ = _apply_barrier(raw_amount, barrier)
    return hero.absorb_damage(after_barrier)


def _apply_skill_status(
    special: Optional[str],
    effectiveness: int,
    targets: List,   # List[HeroEntity] or List[Enemy]
) -> None:
    """
    Apply status effects encoded in a skill's special tag to a list of targets.
    Called after damage is dealt so Vulnerable etc. are already resolved.
    """
    if special is None:
        return

    from combat.status_effects import StatusEffect, StatusType

    if special == "poison":
        effect = StatusEffect(
            status_type=StatusType.POISON,
            duration=2,
            potency=effectiveness,
        )
        for t in targets:
            t.apply_status(effect)

    elif special == "weak":
        effect = StatusEffect(status_type=StatusType.WEAK, duration=1)
        for t in targets:
            t.apply_status(effect)

    elif special == "vulnerable":
        effect = StatusEffect(status_type=StatusType.VULNERABLE, duration=1)
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
        effect = StatusEffect(status_type=StatusType.BLEED, duration=1)
        for t in targets:
            t.apply_status(effect)

    elif special == "bleed2":
        # Apply 2 stacks of Bleed (Spiral Slash boss form)
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

        # enemies is mutated during combat (spawned entities appended)
        enemies = list(enemies)

        rounds: List[CombatRound] = []
        total_hero_damage_taken = 0

        # Bloodletting cross-round state
        prev_bl_active: Dict[str, bool] = {}
        prev_bl_tracked: Dict[str, int] = {}
        prev_bl_cap: Dict[str, int] = {}

        # Mage Barrier: [remaining_hp], expires at start of barrier_expire_round
        barrier: List[int] = [0]
        barrier_expire_round: int = -1

        # Howl: bonus carried from previous round (wolves howl → bonus next round)
        howl_carry: int = 0

        for round_number in range(1, max_rounds + 1):
            living_heroes = [h for h in heroes if h.current_health > 0]
            living_enemies = [e for e in enemies if e.is_alive and not e.hidden]
            if not living_heroes or not living_enemies:
                break

            # --- Expire barrier at the start of its expiry round ---
            if round_number >= barrier_expire_round:
                barrier[0] = 0

            # --- Apply Bloodletting temp-HP conversion from previous round ---
            for hero in heroes:
                hid = hero.hero_id
                if prev_bl_active.get(hid):
                    amount = min(prev_bl_tracked.get(hid, 0), prev_bl_cap.get(hid, 0))
                    if amount > 0:
                        hero.apply_temp_hp(amount)

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
                has_lucky = hero.has_passive("lucky_roll")

                # 1. Build pool, apply Upgrade/Downgrade/Bleed
                pool = compose_pool(hero)
                pool = apply_status_modifiers(pool, hero.status_effects, rng)

                # 2. Roll (Advantage / Disadvantage / Lucky Roll / Paralyze)
                rolled = roll_pool(pool, hero.status_effects, rng, has_lucky_roll=has_lucky)

                # Split locked vs normal for assign_dice
                locked_dice = [d for d in pool if d.is_locked]
                normal_dice = [d for d in pool if not d.is_locked]
                rolled_locked = rolled[: len(locked_dice)]
                rolled_normal = rolled[len(locked_dice):]

                # 3. Assign dice to skills
                assignments = assign_dice(hero, rolled_locked, rolled_normal)

                # 4. Detect Bloodletting before firing skills
                for assignment in assignments:
                    sk = assignment.skill
                    if sk.special == "bloodletting" and assignment.is_active:
                        bl_active[hero.hero_id] = True
                        bl_tracked[hero.hero_id] = 0
                        raw_eff = sum(assignment.assigned_dice) + hero.effective_modifier(sk.associated_stat)
                        bl_cap[hero.hero_id] = max(0, raw_eff)

                # 5. Handle Mage cooldown refresh before executing
                for assignment in assignments:
                    sk = assignment.skill
                    if sk.on_cooldown and assignment.is_active:
                        sk.refresh_progress += sum(assignment.assigned_dice)
                        if sk.refresh_progress >= sk.refresh_cost:
                            sk.on_cooldown = False
                            sk.refresh_progress = 0
                        # Dice consumed toward refresh — skip normal execution
                        assignment.assigned_dice = []

                # 6. Execute skills
                results = execute_all_skills(hero, assignments)

                # 7. Apply each skill result
                for result in results:
                    if result.effectiveness <= 0 and result.hit_count == 0:
                        continue

                    sk = result.skill

                    # --- Defend / passive skills ---
                    if result.effect_type == "defend":
                        all_hero_results.append(result)

                        # Mage Barrier
                        if sk.special == "barrier":
                            barrier[0] = result.effectiveness
                            barrier_expire_round = round_number + 1
                            self._maybe_cooldown(hero, sk)

                        continue  # no outgoing damage

                    # --- Heal ---
                    if result.effect_type == "heal":
                        all_hero_results.append(result)
                        targets = [h for h in heroes if h.current_health > 0]
                        if targets:
                            target = min(targets, key=lambda h: h.current_health)
                            heal_amount = result.effectiveness
                            target.current_health = min(
                                target.max_health,
                                target.current_health + heal_amount,
                            )
                        continue

                    # --- Cleanse ---
                    if result.effect_type == "cleanse":
                        all_hero_results.append(result)
                        stacks_to_remove = hero.effective_modifier(Stat.CHA)
                        num_targets = math.ceil(result.effectiveness / 2)
                        ally_targets = [h for h in heroes if h.current_health > 0][:num_targets]
                        for ally in ally_targets:
                            remaining = stacks_to_remove
                            debuffs = [e for e in ally.status_effects if e.is_debuff()]
                            for debuff in debuffs:
                                if remaining <= 0:
                                    break
                                if debuff.status_type == StatusType.POISON:
                                    removed = min(remaining, debuff.stacks if debuff.stacks else debuff.potency)
                                    debuff.potency = max(0, debuff.potency - remaining)
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
                        continue

                    # --- Damage / AOE skills ---
                    # Exclude dead and hidden entities; heroes cannot see/target hidden enemies
                    living_now = [e for e in enemies if e.is_alive and not e.hidden]
                    if not living_now:
                        break

                    # absolute_untargetable (Kobold King) blocks all targeting including AOE
                    # untargetable (BanditLeader shadow) blocks single-target only
                    targetable = [
                        e for e in living_now
                        if not getattr(e, "untargetable", False)
                        and not getattr(e, "absolute_untargetable", False)
                    ]
                    if not targetable:
                        targetable = living_now  # fall back if all untargetable (shouldn't happen)

                    taunting = [e for e in targetable if has_status(e.status_effects, StatusType.TAUNT)]

                    # Blood Cleave self-cost
                    if sk.special == "blood_cleave":
                        cost = max(1, int(hero.current_health * 0.05))
                        temp_abs = min(hero.temp_hp, cost)
                        hero.temp_hp -= temp_abs
                        real_cost = cost - temp_abs
                        actual = min(real_cost, hero.current_health - 1)
                        hero.current_health -= actual
                        hero_damage_taken += actual
                        round_self_damage[hero.hero_id] = round_self_damage.get(hero.hero_id, 0) + cost

                    all_hero_results.append(result)

                    # --- Eviscerate (multi-hit) ---
                    if sk.special == "eviscerate":
                        target = rng.choice(taunting if taunting else targetable)
                        base_hit = result.per_hit_damage
                        enhanced = target.has_any_debuff()
                        per_hit = (base_hit + 2) if enhanced else base_hit
                        per_hit = _apply_weak(per_hit, hero.status_effects)
                        for _ in range(result.hit_count):
                            hit_dmg = _apply_vulnerable(per_hit, target.status_effects)
                            ret_before = target.retaliate_active and target.block > 0
                            real = target.take_damage(hit_dmg)
                            enemy_damage_dealt += real
                            if ret_before:
                                hero, hero_damage_taken = self._apply_retaliate(
                                    target, hero, hero_damage_taken, bl_active, bl_tracked)

                    elif result.hits_all:
                        # AOE bypasses conditional untargetable (BanditLeader shadow) and taunt,
                        # but NOT absolute_untargetable (Kobold King).
                        for e in living_now:
                            if getattr(e, "absolute_untargetable", False):
                                continue
                            dmg = _apply_weak(result.effectiveness, hero.status_effects)
                            dmg = _apply_vulnerable(dmg, e.status_effects)
                            ret_before = e.retaliate_active and e.block > 0
                            real = e.take_damage(dmg)
                            enemy_damage_dealt += real
                            if ret_before:
                                hero, hero_damage_taken = self._apply_retaliate(
                                    e, hero, hero_damage_taken, bl_active, bl_tracked)
                        _apply_skill_status(sk.special, result.effectiveness, living_now)

                    else:
                        # Single-target
                        target = rng.choice(taunting if taunting else targetable)
                        dmg = _apply_weak(result.effectiveness, hero.status_effects)
                        dmg = _apply_vulnerable(dmg, target.status_effects)
                        ret_before = target.retaliate_active and target.block > 0
                        real = target.take_damage(dmg)
                        enemy_damage_dealt += real
                        if ret_before:
                            hero, hero_damage_taken = self._apply_retaliate(
                                target, hero, hero_damage_taken, bl_active, bl_tracked)
                        _apply_skill_status(sk.special, result.effectiveness, [target])

                    # Put skill on cooldown after firing (Mage)
                    self._maybe_cooldown(hero, sk)

                # 8. Hero end-of-turn: tick statuses, deal Burn/Poison damage
                hero.status_effects, dmg_events = tick_statuses(hero.status_effects)
                for _, dmg in dmg_events:
                    real = _damage_hero(hero, dmg, barrier)
                    hero_damage_taken += real
                    if bl_active.get(hero.hero_id):
                        bl_tracked[hero.hero_id] = bl_tracked.get(hero.hero_id, 0) + real

            # Accumulate Blood Cleave self-damage into Bloodletting tracker
            for hid, self_dmg in round_self_damage.items():
                if bl_active.get(hid):
                    bl_tracked[hid] = bl_tracked.get(hid, 0) + self_dmg

            # ==============================================================
            # ENEMY PHASE
            # ==============================================================

            # Remove spawned entities whose owner has died
            for e in list(enemies):
                if e.owner_ref is not None and not e.owner_ref.is_alive:
                    e.current_health = 0

            # Howl bonus for this round (built from last round's howls)
            round_howl_bonus = howl_carry
            new_howl = 0

            # Single mutable ref shared across all _process_enemy_skills calls this round
            enemy_phase_dmg_ref: List[int] = [0]

            # Snapshot living enemies before iterating (spawns processed separately)
            living_enemies = [e for e in enemies if e.is_alive and not e.hidden]
            same_turn_spawns: List[Enemy] = []

            for enemy in living_enemies:
                if not enemy.is_alive:
                    continue

                living_now = [h for h in heroes if h.current_health > 0]
                if not living_now:
                    break

                triggered = enemy.take_turn(rng)

                # Process spawn queue (spawned entities)
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
                )

                # Collect howls for next round
                for skill, _ in triggered:
                    if skill.special == "howl":
                        new_howl += 1

                # Enemy end-of-turn: tick statuses, deal Burn/Poison damage
                enemy.status_effects, dmg_events = tick_statuses(enemy.status_effects)
                for _, dmg in dmg_events:
                    enemy.take_damage(dmg)

                # Flee check
                flee_turns = enemy.flee_after_turns
                if flee_turns > 0 and enemy.turns_taken >= flee_turns:
                    enemy.fled = True
                    enemy.current_health = 0

            # Process same-turn spawns (e.g. Werewolf wolves act on their spawn turn)
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

            # Carry howl forward
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
        Deals retaliate_damage directly to attacker's real HP (bypasses barrier/temp HP),
        applies 1 Bleed to the attacker, and consumes the retaliate.
        Returns updated (hero, hero_damage_taken).
        """
        ret_dmg = enemy.retaliate_damage
        if ret_dmg > 0:
            actual = min(ret_dmg, hero.current_health)
            hero.current_health -= actual
            hero_damage_taken += actual
            if bl_active.get(hero.hero_id):
                bl_tracked[hero.hero_id] = bl_tracked.get(hero.hero_id, 0) + actual
        # Apply 1 Bleed to hero
        bleed = StatusEffect(status_type=StatusType.BLEED, duration=1)
        hero.apply_status(bleed)
        enemy.retaliate_active = False
        return hero, hero_damage_taken

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
    ) -> None:
        """
        Resolve one enemy's triggered skill list against the hero party.
        Mutates hero HP, status effects, all_enemy_results, and hero_damage_taken_ref[0].
        """
        from combat.skill_executor import SkillResult as SR

        shadow_mult = getattr(enemy, "shadow_damage_multiplier", 1.0) if hasattr(enemy, "shadow_damage_multiplier") else 1.0

        for skill, effectiveness in triggered:
            # Apply shadow multiplier (BanditLeader shadow turn)
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

            # Howl and spawn skills have no direct hero-facing effect
            if skill.special in ("howl", "phase_advance", "spawn_turret"):
                continue

            # Mech: Cannon Barrage — total damage split evenly; remainder to first hero
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
                        if bl_active.get(target_hero.hero_id):
                            bl_tracked[target_hero.hero_id] = bl_tracked.get(target_hero.hero_id, 0) + real
                continue

            # Mech: Oil Trap — AOE status only (2 Weak, 1 Vulnerable, 1 Paralyze), no damage
            if skill.special == "oil_trap":
                for target_hero in list(living_now):
                    target_hero.apply_status(StatusEffect(status_type=StatusType.WEAK, duration=2))
                    target_hero.apply_status(StatusEffect(status_type=StatusType.VULNERABLE, duration=1))
                    target_hero.apply_status(StatusEffect(status_type=StatusType.PARALYZE, duration=1, stacks=1))
                continue

            # Boss: golden_explosion — flat damage to all heroes
            if skill.special == "golden_explosion":
                for target_hero in list(living_now):
                    real = _damage_hero(target_hero, effectiveness, barrier)
                    hero_damage_taken_ref[0] += real
                    if bl_active.get(target_hero.hero_id):
                        bl_tracked[target_hero.hero_id] = bl_tracked.get(target_hero.hero_id, 0) + real
                continue

            if skill.effect_type == "defend":
                enemy.block += effectiveness
                # Trap: arm retaliate
                if skill.special == "trap":
                    enemy.retaliate_active = True
                # Boss paralyze
                if skill.special in ("paralyze_all", "paralyze_all_2"):
                    stacks = 2 if skill.special == "paralyze_all_2" else 1
                    para = StatusEffect(status_type=StatusType.PARALYZE, duration=1, stacks=stacks)
                    for target_hero in list(living_now):
                        target_hero.apply_status(para)

            elif skill.effect_type in ("aoe", "buff") or skill.special == "bleed" and skill.effect_type == "aoe":
                # AOE damage (also covers enemy Poison Mist which is tagged aoe+poison)
                if skill.effect_type == "aoe":
                    for target_hero in list(living_now):
                        dmg = _apply_weak(effectiveness + round_howl_bonus, enemy.status_effects)
                        dmg = _apply_vulnerable(dmg, target_hero.status_effects)
                        real = _damage_hero(target_hero, dmg, barrier)
                        hero_damage_taken_ref[0] += real
                        if bl_active.get(target_hero.hero_id):
                            bl_tracked[target_hero.hero_id] = bl_tracked.get(target_hero.hero_id, 0) + real
                        # Gold steal
                        if enemy.gold_steal and real > 0 and publish_events:
                            self._event_bus.publish("gold.stolen", {"amount": 5, "by": enemy.enemy_id})
                    _apply_skill_status(skill.special, effectiveness, list(living_now))
                    # CursedKnight bloodlust gain
                    if hasattr(enemy, "gain_bloodlust"):
                        total_aoe = effectiveness * len(living_now)
                        enemy.gain_bloodlust(total_aoe)

            # Boss: golden_wave — two random heroes
            elif skill.special == "golden_wave":
                num_targets = min(2, len(living_now))
                targets = rng.sample(living_now, num_targets)
                for target_hero in targets:
                    dmg = _apply_weak(effectiveness + round_howl_bonus, enemy.status_effects)
                    dmg = _apply_vulnerable(dmg, target_hero.status_effects)
                    real = _damage_hero(target_hero, dmg, barrier)
                    hero_damage_taken_ref[0] += real
                    if bl_active.get(target_hero.hero_id):
                        bl_tracked[target_hero.hero_id] = bl_tracked.get(target_hero.hero_id, 0) + real

            else:
                # Single-target damage
                target_hero = rng.choice(living_now)
                dmg = _apply_weak(effectiveness + round_howl_bonus, enemy.status_effects)
                dmg = _apply_vulnerable(dmg, target_hero.status_effects)
                real = _damage_hero(target_hero, dmg, barrier)
                hero_damage_taken_ref[0] += real
                if bl_active.get(target_hero.hero_id):
                    bl_tracked[target_hero.hero_id] = bl_tracked.get(target_hero.hero_id, 0) + real
                _apply_skill_status(skill.special, effectiveness, [target_hero])
                # Gold steal
                if enemy.gold_steal and real > 0 and publish_events:
                    self._event_bus.publish("gold.stolen", {"amount": 5, "by": enemy.enemy_id})
                # CursedKnight bloodlust gain
                if hasattr(enemy, "gain_bloodlust"):
                    enemy.gain_bloodlust(real)

    # ------------------------------------------------------------------
    def _maybe_cooldown(self, hero: HeroEntity, skill: Skill) -> None:
        """
        Put skill on cooldown after firing, unless the Prepared passive protects it.
        Prepared: skill in slot 0 never triggers refresh cost.
        """
        if skill.refresh_cost <= 0:
            return
        if hero.has_passive("prepared"):
            slot_index = next(
                (i for i, s in enumerate(hero.skills) if s is skill), None
            )
            if slot_index == 0:
                return
        skill.on_cooldown = True
        skill.refresh_progress = 0
