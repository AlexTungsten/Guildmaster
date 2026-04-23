"""
combat_session.py — Step-by-step combat wrapper for the web UI.

Exposes the same round logic as CombatEngine but paused between:
  begin_round()   → applies SOT effects, rolls dice, returns state
  resolve_round() → executes assignments (manual or auto), enemy phase, EOT

The server holds one StepCombatSession in memory and drives it via REST calls.
"""

from __future__ import annotations

import math
import random
from typing import Dict, List, Optional, Tuple

from hero.hero_entity import HeroEntity, Skill, Stat
from enemy.enemy import Enemy
from combat.dice_pool_compositor import compose_pool, apply_status_modifiers, roll_pool, Die
from combat.dice_assignment_engine import assign_dice, SkillAssignment
from combat.skill_executor import execute_all_skills, SkillResult
from combat.status_effects import (
    StatusEffect, StatusType, tick_statuses,
    has_status, get_status,
)
from combat.combat_engine import (
    _apply_weak, _apply_vulnerable, _apply_barrier, _damage_hero, _apply_skill_status,
    FIREBALL_DAMAGE, FIREBALL_BURN_STACKS, BARRIER_ABSORPTION_BASE,
    CHAIN_LIGHTNING_DAMAGE, CHAIN_LIGHTNING_HITS,
    BLIZZARD_DAMAGE, BLIZZARD_TICKS,
    EARTHQUAKE_DAMAGE, METEOR_SINGLE_DAMAGE, METEOR_BURN_STACKS,
)

_PRAYER_EXCLUDED: frozenset = frozenset({"evasion"})

ARCHETYPE_COLORS: Dict[str, str] = {
    "barbarian": "#c0392b",
    "rogue":     "#8e44ad",
    "mage":      "#2980b9",
    "cleric":    "#d4ac0d",
}


# ---------------------------------------------------------------------------
# Session
# ---------------------------------------------------------------------------

class StepCombatSession:
    def __init__(
        self,
        heroes: List[HeroEntity],
        enemies: List[Enemy],
        seed: Optional[int] = None,
    ):
        self.heroes: List[HeroEntity] = list(heroes)
        self.enemies: List[Enemy] = list(enemies)
        self.rng = random.Random(seed)

        self.round_number: int = 0
        # "ready" → begin_round → "assigning" → resolve_round → "ready" | "done"
        self.status: str = "ready"
        self.winner: Optional[str] = None  # "heroes" | "enemies"

        # Cross-round engine state
        self.barrier: List[int] = [0]
        self.barrier_expire_round: int = -1
        self.prev_bl_active: Dict[str, bool] = {}
        self.prev_bl_tracked: Dict[str, int] = {}
        self.prev_bl_cap: Dict[str, int] = {}
        self.howl_carry: int = 0

        # Per-round state (set by begin_round, consumed by resolve_round)
        self._rolled_by_hero: Dict[str, List[int]] = {}
        self._pools_by_hero: Dict[str, List[Die]] = {}

        # Combat log (all rounds)
        self.log: List[dict] = []

        for hero in self.heroes:
            hero.reset_combat_state()
        self._add_log("Combat started!", "info")

    # ------------------------------------------------------------------
    # Log helpers
    # ------------------------------------------------------------------

    def _add_log(self, text: str, log_type: str = "info") -> None:
        self.log.append({"round": self.round_number, "text": text, "type": log_type})

    # ------------------------------------------------------------------
    # Phase 1: SOT + dice roll
    # ------------------------------------------------------------------

    def begin_round(self) -> dict:
        """Apply SOT effects for all living heroes and roll their dice."""
        if self.status == "done":
            return self.get_state()

        self.round_number += 1
        self._rolled_by_hero = {}
        self._pools_by_hero = {}
        self._add_log(f"━━━ Round {self.round_number} ━━━", "round")

        # Expire barrier at start of round
        if self.round_number >= self.barrier_expire_round:
            if self.barrier[0] > 0:
                self._add_log("Party barrier expired.", "info")
            self.barrier[0] = 0

        for hero in self.heroes:
            if hero.current_health <= 0:
                continue

            hid = hero.hero_id
            has_lucky      = hero.has_passive("lucky_roll")
            lucky_upgraded = has_lucky and hero.level5_upgrade == "lucky_roll_upgrade"
            has_tc         = hero.has_passive("thousand_cuts")
            has_iron_will  = hero.has_passive("iron_will")
            has_divine_ovf = hero.has_passive("divine_overflow")
            divine_ovf_upg = has_divine_ovf and hero.level5_upgrade == "divine_overflow_upgrade"

            # SOT: Iron Will
            if has_iron_will and hero.temp_hp > 0:
                conv = math.floor(hero.temp_hp / 2)
                hero.temp_hp -= conv
                hero.current_health = min(hero.max_health, hero.current_health + conv)
                self._add_log(f"{hero.name}: Iron Will converts {conv} temp HP → real HP.", "heal")

            # SOT: Bloodletting carry-over
            if self.prev_bl_active.get(hid):
                amount = min(
                    self.prev_bl_tracked.get(hid, 0),
                    self.prev_bl_cap.get(hid, 0),
                )
                if amount > 0:
                    hero.apply_temp_hp(amount)
                    self._add_log(f"{hero.name}: Bloodletting grants {amount} temp HP.", "heal")

            # SOT: Regeneration tick
            if hero.regen_remaining > 0:
                heal = min(hero.regen_value, hero.max_health - hero.current_health)
                hero.current_health += heal
                hero.regen_remaining -= 1
                self._add_log(
                    f"{hero.name}: Regen restores {heal} HP ({hero.regen_remaining} turn(s) left).",
                    "heal",
                )
                if has_divine_ovf and heal > 0:
                    self._divine_overflow_heal(hero, heal, divine_ovf_upg)

            # SOT: Blizzard tick
            if hero.blizzard_ticks_remaining > 0:
                live = [e for e in self.enemies if e.is_alive and not e.hidden]
                bdmg = hero.blizzard_stored_damage
                for e in live:
                    if not getattr(e, "absolute_untargetable", False):
                        e.take_damage(bdmg)
                hero.blizzard_ticks_remaining -= 1
                self._add_log(f"{hero.name}: Blizzard ticks {bdmg} to all enemies.", "damage")

            # SOT: Battle Hymn advantage flag
            if hero.advantage_next_turn:
                hero.apply_status(StatusEffect(status_type=StatusType.ADVANTAGE, duration=1))
                hero.advantage_next_turn = False
                self._add_log(f"{hero.name}: Battle Hymn grants Advantage this turn.", "info")

            # Build & modify pool
            pool = compose_pool(hero)
            pool = apply_status_modifiers(pool, hero.status_effects, self.rng)

            # Roll
            rolled = roll_pool(
                pool, hero.status_effects, self.rng,
                has_lucky_roll=has_lucky,
                lucky_roll_upgraded=lucky_upgraded,
                has_thousand_cuts=has_tc,
            )
            self._rolled_by_hero[hid] = rolled
            self._pools_by_hero[hid] = pool
            self._add_log(
                f"{hero.name} rolls [{', '.join(str(d) for d in rolled)}].",
                "roll",
            )

        self.status = "assigning"
        return self.get_state()

    # ------------------------------------------------------------------
    # Phase 2: Execute (hero + enemy) + EOT
    # ------------------------------------------------------------------

    def resolve_round(self, manual_assignments: Optional[dict] = None) -> dict:
        """
        Execute one round.
        manual_assignments: {hero_id: {str(skill_index): [die_values, ...]}}
        Pass None to auto-assign all heroes.
        """
        if self.status != "assigning":
            return self.get_state()

        bl_active: Dict[str, bool] = {}
        bl_tracked: Dict[str, int] = {}
        bl_cap: Dict[str, int] = {}
        round_self_damage: Dict[str, int] = {}
        howl_bonus = self.howl_carry
        new_howl = 0

        # ══════════════════════════════════════════════════════════════
        # HERO PHASE
        # ══════════════════════════════════════════════════════════════
        for hero in self.heroes:
            if hero.current_health <= 0:
                continue

            hid = hero.hero_id
            rolled = self._rolled_by_hero.get(hid, [])
            pool   = self._pools_by_hero.get(hid, [])

            has_blood_rage = hero.has_passive("blood_rage")
            has_venomous   = hero.has_passive("venomous")
            venomous_upg   = has_venomous and hero.level5_upgrade == "venomous_upgrade"
            has_divine_ovf = hero.has_passive("divine_overflow")
            divine_ovf_upg = has_divine_ovf and hero.level5_upgrade == "divine_overflow_upgrade"
            has_prayer     = hero.has_passive("prayer")
            has_arc_flow   = hero.has_passive("arcane_flow")
            has_spellweave = hero.has_passive("spellweave")
            spell_upg      = has_spellweave and hero.level5_upgrade == "spellweave_upgrade"

            locked_dice  = [d for d in pool if d.is_locked]
            normal_dice  = [d for d in pool if not d.is_locked]
            rolled_locked = rolled[:len(locked_dice)]
            rolled_normal = rolled[len(locked_dice):]

            # Build SkillAssignments from manual input or auto-assign
            if manual_assignments and hid in manual_assignments:
                assignments = self._build_manual_assignments(hero, manual_assignments[hid])
            else:
                assignments = assign_dice(hero, rolled_locked, rolled_normal)

            # Bloodletting detection (before skills fire)
            for asgn in assignments:
                sk = asgn.skill
                if sk.special == "bloodletting" and asgn.is_active:
                    bl_active[hid] = True
                    bl_tracked[hid] = 0
                    raw = sum(asgn.assigned_dice) + hero.effective_modifier(sk.associated_stat)
                    bl_cap[hid] = max(0, raw)

            # ── CHARGE PHASE ─────────────────────────────────────────────
            charged_fired = False
            for asgn in assignments:
                sk = asgn.skill
                if sk.charge_cost <= 0 or not asgn.is_active:
                    continue

                added = sum(asgn.assigned_dice)
                effective_cost = (
                    math.ceil(sk.charge_cost / 2)
                    if has_arc_flow else sk.charge_cost
                )

                if hero.prepared_charges > 0 and hero.level5_upgrade == "prepared":
                    self._fire_charged_spell(hero, sk, has_spellweave, spell_upg)
                    hero.prepared_charges -= 1
                    sk.current_charge = 0
                    charged_fired = True
                else:
                    sk.current_charge += added
                    if sk.current_charge >= effective_cost:
                        self._fire_charged_spell(hero, sk, has_spellweave, spell_upg)
                        sk.current_charge = 0
                        charged_fired = True

                asgn.assigned_dice = []  # consumed by charge system

            # ── EXECUTE normal skills ─────────────────────────────────────
            results = execute_all_skills(hero, assignments)

            # Blade Dance pre-pass
            bd = next((r for r in results if r.special == "blade_dance"), None)
            if bd is not None:
                dice_elsewhere = sum(
                    sum(a.assigned_dice)
                    for a in assignments
                    if a.skill.special != "blade_dance" and a.is_active
                )
                bd.dice_spent_elsewhere = dice_elsewhere
                bd.effectiveness = max(0, dice_elsewhere * hero.effective_modifier(Stat.DEX))

            for result in results:
                sk = result.skill

                if result.effectiveness <= 0 and result.hit_count == 0:
                    if result.special not in (
                        "evasion", "primal_roar", "battle_hymn", "blessing", "fortify"
                    ):
                        continue

                # ── DEFEND ───────────────────────────────────────────────
                if result.effect_type == "defend":
                    if sk.special == "barrier":
                        self.barrier[0] = result.effectiveness
                        self.barrier_expire_round = self.round_number + 1
                    self._add_log(f"{hero.name}: {sk.name}.", "hero")
                    continue

                # ── SELF ─────────────────────────────────────────────────
                if result.effect_type == "self":
                    self._apply_self_skill(hero, sk, result, bl_active, bl_tracked, round_self_damage)
                    if has_prayer and sk.special not in _PRAYER_EXCLUDED:
                        hero.prayer_stacks += 1
                        if hero.prayer_stacks >= 10 and not hero.prayer_aoe_unlocked:
                            hero.prayer_aoe_unlocked = True
                            self._add_log(f"{hero.name}: Prayer unlocks AOE on all skills!", "info")
                    continue

                # ── HEAL ─────────────────────────────────────────────────
                if result.effect_type == "heal":
                    if sk.special == "regeneration":
                        target = self._lowest_hp_ally()
                        if target:
                            target.regen_value = result.effectiveness
                            target.regen_remaining = 3
                            self._add_log(
                                f"{hero.name}: Regeneration → {target.name} "
                                f"({result.effectiveness}/turn × 3).",
                                "heal",
                            )
                    else:
                        target = self._lowest_hp_ally()
                        if target:
                            actual = min(result.effectiveness, target.max_health - target.current_health)
                            target.current_health += actual
                            self._add_log(f"{hero.name}: {sk.name} heals {target.name} for {actual}.", "heal")
                            if has_divine_ovf and actual > 0:
                                self._divine_overflow_heal(hero, actual, divine_ovf_upg)
                    if has_prayer:
                        hero.prayer_stacks += 1
                        if hero.prayer_stacks >= 10 and not hero.prayer_aoe_unlocked:
                            hero.prayer_aoe_unlocked = True
                    continue

                # ── CLEANSE ──────────────────────────────────────────────
                if result.effect_type == "cleanse":
                    cha_mod = hero.effective_modifier(Stat.CHA)
                    num_targets = math.ceil(result.effectiveness / 2)
                    ally_targets = sorted(
                        [h for h in self.heroes if h.current_health > 0],
                        key=lambda h: h.current_health,
                    )[:num_targets]
                    names = []
                    for ally in ally_targets:
                        remaining = cha_mod
                        for debuff in list(ally.status_effects):
                            if remaining <= 0:
                                break
                            if not debuff.is_debuff():
                                continue
                            if debuff.status_type == StatusType.POISON:
                                rm = min(remaining, debuff.potency)
                                debuff.potency -= rm; remaining -= rm
                                if debuff.potency <= 0:
                                    ally.clear_status(debuff.status_type)
                            elif debuff.status_type == StatusType.BURN:
                                rm = min(remaining, debuff.stacks)
                                debuff.stacks -= rm; remaining -= rm
                                if debuff.stacks <= 0:
                                    ally.clear_status(debuff.status_type)
                            else:
                                rm = min(remaining, debuff.duration)
                                debuff.duration -= rm; remaining -= rm
                                if debuff.duration <= 0:
                                    ally.clear_status(debuff.status_type)
                        names.append(ally.name)
                    self._add_log(f"{hero.name}: {sk.name} cleanses {', '.join(names)}.", "heal")
                    if has_prayer:
                        hero.prayer_stacks += 1
                    continue

                # ── BUFF ─────────────────────────────────────────────────
                if result.effect_type == "buff":
                    self._apply_buff_skill(hero, sk, result)
                    if has_prayer:
                        hero.prayer_stacks += 1
                        if hero.prayer_stacks >= 10 and not hero.prayer_aoe_unlocked:
                            hero.prayer_aoe_unlocked = True
                    continue

                # ── DAMAGE / AOE ─────────────────────────────────────────
                living_now = [e for e in self.enemies if e.is_alive and not e.hidden]
                if not living_now:
                    break

                targetable = [
                    e for e in living_now
                    if not getattr(e, "untargetable", False)
                    and not getattr(e, "absolute_untargetable", False)
                ] or living_now

                taunting   = [e for e in targetable if has_status(e.status_effects, StatusType.TAUNT)]
                prayer_aoe = has_prayer and hero.prayer_aoe_unlocked

                # Blood Cleave self-cost
                if sk.special == "blood_cleave":
                    cost = max(1, int(hero.current_health * 0.05))
                    temp_abs = min(hero.temp_hp, cost)
                    hero.temp_hp -= temp_abs
                    actual = min(cost - temp_abs, hero.current_health - 1)
                    hero.current_health -= actual
                    round_self_damage[hid] = round_self_damage.get(hid, 0) + cost

                # Spellweave arcane tracking
                if sk.element == "arcane" and sk.charge_cost == 0:
                    hero.arcane_bolt_cast_this_combat = True

                pick = taunting or targetable

                if sk.special == "eviscerate":
                    target = self.rng.choice(pick)
                    base_hit = result.per_hit_damage
                    per_hit = (base_hit + 2) if target.has_any_debuff() else base_hit
                    per_hit += hero.blood_rage_stacks
                    per_hit = _apply_weak(per_hit, hero.status_effects)
                    total = 0
                    for _ in range(result.hit_count):
                        hit = _apply_vulnerable(per_hit, target.status_effects)
                        total += target.take_damage(hit)
                    self._add_log(
                        f"{hero.name}: Eviscerate hits {target.name} "
                        f"{result.hit_count}× for {total} total.",
                        "damage",
                    )

                elif result.hits_all or prayer_aoe:
                    aoe = [e for e in living_now if not getattr(e, "absolute_untargetable", False)]
                    total = 0
                    for e in aoe:
                        dmg = _apply_weak(result.effectiveness + hero.blood_rage_stacks, hero.status_effects)
                        dmg = _apply_vulnerable(dmg, e.status_effects)
                        total += e.take_damage(dmg)
                    self._add_log(
                        f"{hero.name}: {sk.name} hits all enemies for {result.effectiveness} each.",
                        "damage",
                    )
                    _apply_skill_status(sk.special, result.effectiveness, aoe,
                                        venomous=has_venomous, venomous_upgraded=venomous_upg)

                else:
                    target = self.rng.choice(pick)
                    dmg = _apply_weak(result.effectiveness + hero.blood_rage_stacks, hero.status_effects)
                    dmg = _apply_vulnerable(dmg, target.status_effects)
                    real = target.take_damage(dmg)
                    self._add_log(f"{hero.name}: {sk.name} hits {target.name} for {real}.", "damage")
                    _apply_skill_status(sk.special, result.effectiveness, [target],
                                        venomous=has_venomous, venomous_upgraded=venomous_upg)

            # ── EOT: Blood Rage ──────────────────────────────────────────
            if has_blood_rage:
                cost = max(1, math.floor(hero.current_health * 0.05))
                temp_abs = min(hero.temp_hp, cost)
                hero.temp_hp -= temp_abs
                actual = min(cost - temp_abs, hero.current_health - 1)
                hero.current_health -= actual
                round_self_damage[hid] = round_self_damage.get(hid, 0) + cost
                hero.blood_rage_stacks += 1
                self._add_log(
                    f"{hero.name}: Blood Rage costs {cost} HP (stacks: {hero.blood_rage_stacks}).",
                    "info",
                )
                if hero.level5_upgrade == "blood_rage_upgrade":
                    hero.apply_status(StatusEffect(status_type=StatusType.ADVANTAGE, duration=999))

            # ── EOT: Evasion expires ─────────────────────────────────────
            hero.evasion_active = False
            hero.evasion_value = 0

            # ── EOT: tick statuses ───────────────────────────────────────
            hero.status_effects, dmg_events = tick_statuses(hero.status_effects)
            for _, dmg in dmg_events:
                real = _damage_hero(hero, dmg, self.barrier)
                if real > 0:
                    self._add_log(f"{hero.name} takes {real} status damage.", "enemy_damage")
                if bl_active.get(hid):
                    bl_tracked[hid] = bl_tracked.get(hid, 0) + real

        # Self-damage feeds Bloodletting
        for hid2, self_dmg in round_self_damage.items():
            if bl_active.get(hid2):
                bl_tracked[hid2] = bl_tracked.get(hid2, 0) + self_dmg

        # ══════════════════════════════════════════════════════════════
        # ENEMY PHASE
        # ══════════════════════════════════════════════════════════════
        for e in list(self.enemies):
            if e.owner_ref is not None and not e.owner_ref.is_alive:
                e.current_health = 0

        same_turn_spawns: List[Enemy] = []

        for enemy in [e for e in self.enemies if e.is_alive and not e.hidden]:
            if not enemy.is_alive:
                continue
            living_now = [h for h in self.heroes if h.current_health > 0]
            if not living_now:
                break

            triggered = enemy.take_turn(self.rng)

            for new_entity in enemy.spawn_queue:
                self.enemies.append(new_entity)
                if new_entity.acts_this_turn:
                    same_turn_spawns.append(new_entity)
                    new_entity.acts_this_turn = False
            enemy.spawn_queue.clear()

            self._process_enemy_skills(enemy, triggered, living_now, bl_active, bl_tracked, howl_bonus)

            for skill, _ in triggered:
                if skill.special == "howl":
                    new_howl += 1

            enemy.status_effects, dmg_events = tick_statuses(enemy.status_effects)
            for _, dmg in dmg_events:
                enemy.take_damage(dmg)

            if enemy.flee_after_turns > 0 and enemy.turns_taken >= enemy.flee_after_turns:
                enemy.fled = True
                enemy.current_health = 0
                self._add_log(f"{enemy.name} flees!", "info")

        for entity in same_turn_spawns:
            if not entity.is_alive:
                continue
            living_now = [h for h in self.heroes if h.current_health > 0]
            if not living_now:
                break
            triggered = entity.take_turn(self.rng)
            entity.spawn_queue.clear()
            self._process_enemy_skills(entity, triggered, living_now, bl_active, bl_tracked, howl_bonus)
            entity.status_effects, dmg_events = tick_statuses(entity.status_effects)
            for _, dmg in dmg_events:
                entity.take_damage(dmg)

        # Carry BL state forward
        self.prev_bl_active  = dict(bl_active)
        self.prev_bl_tracked = dict(bl_tracked)
        self.prev_bl_cap     = dict(bl_cap)
        self.howl_carry      = new_howl

        # Win / loss check
        live_h = [h for h in self.heroes  if h.current_health > 0]
        live_e = [e for e in self.enemies if e.is_alive and not e.hidden]

        if not live_e:
            self.status = "done"
            self.winner = "heroes"
            self._add_log("⚔️  Victory! All enemies defeated.", "victory")
        elif not live_h:
            self.status = "done"
            self.winner = "enemies"
            self._add_log("💀  Defeat! All heroes have fallen.", "defeat")
        else:
            self.status = "ready"

        return self.get_state()

    # ------------------------------------------------------------------
    # Convenience: roll + auto-assign + resolve in one call
    # ------------------------------------------------------------------

    def auto_turn(self) -> dict:
        self.begin_round()
        return self.resolve_round(manual_assignments=None)

    # ------------------------------------------------------------------
    # State serialization
    # ------------------------------------------------------------------

    def get_state(self) -> dict:
        return {
            "round":      self.round_number,
            "status":     self.status,
            "winner":     self.winner,
            "barrier_hp": self.barrier[0],
            "heroes":     [self._serialize_hero(h) for h in self.heroes],
            "enemies":    [self._serialize_enemy(e) for e in self.enemies if not e.hidden],
            "log":        self.log[-100:],
        }

    def _serialize_hero(self, hero: HeroEntity) -> dict:
        rolled = self._rolled_by_hero.get(hero.hero_id, [])
        pool   = self._pools_by_hero.get(hero.hero_id, [])
        locked_count = sum(1 for d in pool if d.is_locked)

        arch_key = hero.archetype.lower()
        color = ARCHETYPE_COLORS.get(arch_key, "#27ae60")

        return {
            "id":          hero.hero_id,
            "name":        hero.name,
            "archetype":   hero.archetype,
            "color":       color,
            "current_health": max(0, hero.current_health),
            "max_health":     hero.max_health,
            "temp_hp":        hero.temp_hp,
            "level":          hero.level,
            "is_alive":       hero.current_health > 0,
            "status_effects": [self._serialize_status(e) for e in hero.status_effects],
            "skills":         [
                self._serialize_hero_skill(sk, i)
                for i, sk in enumerate(hero.skills)
                if sk is not None
            ],
            "rolled_dice":    rolled,
            "locked_count":   locked_count,
            "base_dice_sides": hero.base_dice_sides,
            "stats": {
                "STR": hero.effective_stat(Stat.STR),
                "DEX": hero.effective_stat(Stat.DEX),
                "INT": hero.effective_stat(Stat.INT),
                "CHA": hero.effective_stat(Stat.CHA),
                "CON": hero.effective_stat(Stat.CON),
            },
            "passives":          [p.get("name", p.get("passive_id", "")) for p in hero.passives],
            "blood_rage_stacks": hero.blood_rage_stacks,
            "prayer_stacks":     hero.prayer_stacks,
            "prayer_aoe":        hero.prayer_aoe_unlocked,
            "exhaustion":        round(hero.exhaustion, 1),
        }

    def _serialize_hero_skill(self, skill: Skill, index: int) -> dict:
        return {
            "index":          index,
            "name":           skill.name,
            "description":    skill.description,
            "dice_slots":     skill.dice_slots,
            "effect_type":    skill.effect_type,
            "special":        skill.special,
            "charge_cost":    skill.charge_cost,
            "current_charge": skill.current_charge,
            "element":        skill.element,
            "stat":           skill.associated_stat.value,
        }

    def _serialize_enemy(self, enemy: Enemy) -> dict:
        intent = self._compute_intent(enemy)
        return {
            "id":          f"{enemy.enemy_id}_{id(enemy)}",
            "name":        enemy.name,
            "enemy_id":    enemy.enemy_id,
            "current_health": max(0, enemy.current_health),
            "max_health":     enemy.max_health,
            "block":          enemy.block,
            "is_alive":       enemy.is_alive,
            "status_effects": [self._serialize_status(e) for e in enemy.status_effects],
            "skills": [
                {
                    "name":     sk.name,
                    "description": sk.description,
                    "effect_type": sk.effect_type,
                    "dice_slots":  sk.dice_slots,
                    "special":     sk.special,
                    "buffered":    len(enemy.skill_buffers[i]) if i < len(enemy.skill_buffers) else 0,
                }
                for i, sk in enumerate(enemy.skills)
            ],
            "intent": intent,
        }

    def _compute_intent(self, enemy: Enemy) -> str:
        if not enemy.skills:
            return "—"
        # Find the skill closest to firing
        best = None
        best_pct = -1.0
        for i, sk in enumerate(enemy.skills):
            buf = enemy.skill_buffers[i] if i < len(enemy.skill_buffers) else []
            pct = len(buf) / max(sk.dice_slots, 1)
            if pct > best_pct:
                best_pct = pct
                best = (sk, len(buf), sk.dice_slots)
        if best:
            sk, filled, total = best
            remaining = total - filled
            if remaining == 0:
                return f"{sk.name} (ready!)"
            return f"{sk.name} ({remaining} die away)"
        return "—"

    def _serialize_status(self, effect) -> dict:
        return {
            "type":      effect.status_type.value,
            "name":      effect.status_type.name.replace("_", " ").title(),
            "duration":  effect.duration,
            "stacks":    effect.stacks,
            "is_debuff": effect.is_debuff(),
        }

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _build_manual_assignments(
        self, hero: HeroEntity, hero_data: dict
    ) -> List[SkillAssignment]:
        """Convert {str(skill_idx): [die_values]} → List[SkillAssignment]."""
        result = []
        for i, skill in enumerate(hero.skills):
            if skill is None:
                continue
            values = hero_data.get(str(i), [])
            result.append(SkillAssignment(skill=skill, assigned_dice=list(values)))
        return result

    def _lowest_hp_ally(self) -> Optional[HeroEntity]:
        living = [h for h in self.heroes if h.current_health > 0]
        return min(living, key=lambda h: h.current_health) if living else None

    def _divine_overflow_heal(self, cleric: HeroEntity, heal_amount: int, upgraded: bool) -> None:
        overflow = math.floor(heal_amount / 2)
        if overflow <= 0:
            return
        living = [h for h in self.heroes if h.current_health > 0]
        if not living:
            return
        lowest = min(living, key=lambda h: h.current_health)
        actual = min(overflow, lowest.max_health - lowest.current_health)
        lowest.current_health += actual
        if actual > 0:
            self._add_log(f"Divine Overflow: {lowest.name} +{actual} HP.", "heal")
        if upgraded and lowest.status_effects:
            debuffs = [e for e in lowest.status_effects if e.is_debuff()]
            if debuffs:
                lowest.status_effects.remove(debuffs[0])

    def _fire_charged_spell(
        self, hero: HeroEntity, skill: Skill, has_spellweave: bool, spell_upg: bool
    ) -> None:
        special = skill.special
        living = [
            e for e in self.enemies
            if e.is_alive and not e.hidden and not getattr(e, "absolute_untargetable", False)
        ]

        # Spellweave tracking
        if has_spellweave and skill.element and skill.element != "arcane":
            if skill.element not in hero.convergence_elements:
                hero.convergence_elements.append(skill.element)
            if len(hero.convergence_elements) >= 3:
                self._fire_convergence(hero, spell_upg)
                hero.convergence_elements.clear()

        if special == "fireball_charge":
            for e in living:
                e.take_damage(FIREBALL_DAMAGE)
                e.apply_status(StatusEffect(status_type=StatusType.BURN, stacks=FIREBALL_BURN_STACKS))
            self._add_log(
                f"{hero.name}: 🔥 Fireball! {FIREBALL_DAMAGE} to all + Burn × {FIREBALL_BURN_STACKS}.",
                "damage",
            )
        elif special == "barrier_charge":
            int_mod = hero.effective_modifier(Stat.INT)
            self.barrier[0] = BARRIER_ABSORPTION_BASE + int_mod
            self.barrier_expire_round = self.round_number + 2
            self._add_log(
                f"{hero.name}: 🛡️ Barrier absorbs up to {self.barrier[0]} damage (expires next round).",
                "heal",
            )
        elif special == "chain_lightning_charge":
            for _ in range(CHAIN_LIGHTNING_HITS):
                if living:
                    t = self.rng.choice(living)
                    t.take_damage(CHAIN_LIGHTNING_DAMAGE)
                    t.apply_status(StatusEffect(status_type=StatusType.PARALYZE, stacks=1))
            self._add_log(
                f"{hero.name}: ⚡ Chain Lightning strikes {CHAIN_LIGHTNING_HITS} times!",
                "damage",
            )
        elif special == "blizzard_charge":
            for e in living:
                e.take_damage(BLIZZARD_DAMAGE)
                e.apply_status(StatusEffect(status_type=StatusType.DOWNGRADE, duration=1))
            hero.blizzard_stored_damage  = BLIZZARD_DAMAGE
            hero.blizzard_ticks_remaining = BLIZZARD_TICKS
            self._add_log(
                f"{hero.name}: ❄️  Blizzard deals {BLIZZARD_DAMAGE} to all + ticks for {BLIZZARD_TICKS} turns.",
                "damage",
            )
        elif special == "earthquake_charge":
            for e in living:
                e.take_damage(EARTHQUAKE_DAMAGE)
                e.apply_status(StatusEffect(status_type=StatusType.DISADVANTAGE, duration=1))
            self._add_log(f"{hero.name}: 🌍 Earthquake hits all for {EARTHQUAKE_DAMAGE}!", "damage")
        elif special == "meteor_charge":
            if living:
                primary = self.rng.choice(living)
                primary.take_damage(METEOR_SINGLE_DAMAGE)
            for e in living:
                e.apply_status(StatusEffect(status_type=StatusType.BURN, stacks=METEOR_BURN_STACKS))
            self._add_log(
                f"{hero.name}: ☄️  Meteor! {METEOR_SINGLE_DAMAGE} to primary + Burn × {METEOR_BURN_STACKS} all.",
                "damage",
            )

    def _fire_convergence(self, hero: HeroEntity, spell_upg: bool) -> None:
        living = [
            e for e in self.enemies
            if e.is_alive and not e.hidden and not getattr(e, "absolute_untargetable", False)
        ]
        arcane_bonus = (10 if spell_upg else 5) if hero.arcane_bolt_cast_this_combat else 0
        self._add_log(f"{hero.name}: ✨ Spellweave Convergence fires!", "info")
        for element in hero.convergence_elements:
            if element == "fire":
                dmg = (15 if spell_upg else 10) + arcane_bonus
                for e in living:
                    e.take_damage(dmg)
            elif element == "lightning":
                for e in living:
                    e.apply_status(StatusEffect(
                        status_type=StatusType.PARALYZE,
                        stacks=3 if spell_upg else 2,
                    ))
            elif element == "ice":
                for e in living:
                    e.apply_status(StatusEffect(
                        status_type=StatusType.DOWNGRADE,
                        duration=2 if spell_upg else 1,
                    ))
            elif element == "earth":
                for e in living:
                    e.apply_status(StatusEffect(
                        status_type=StatusType.DISADVANTAGE,
                        duration=2 if spell_upg else 1,
                    ))

    def _apply_self_skill(
        self,
        hero: HeroEntity,
        sk: Skill,
        result: SkillResult,
        bl_active: dict,
        bl_tracked: dict,
        round_self_damage: dict,
    ) -> None:
        eff = result.effectiveness
        if sk.special == "primal_roar":
            hero.add_temp_hp(eff)
            for e in self.enemies:
                if e.is_alive and not e.hidden:
                    e.apply_status(StatusEffect(status_type=StatusType.WEAK, duration=1))
            self._add_log(f"{hero.name}: Primal Roar +{eff} temp HP, enemies Weakened.", "hero")

        elif sk.special == "second_wind":
            if not hero.second_wind_used:
                exh_level = hero.exhaustion_level()
                hero.exhaustion = max(0.0, hero.exhaustion - eff)
                con_mod = hero.effective_modifier(Stat.CON)
                temp_gain = exh_level * eff
                hp_gain = max(0, exh_level * con_mod)
                hero.add_temp_hp(temp_gain)
                hero.current_health = min(hero.max_health, hero.current_health + hp_gain)
                hero.second_wind_used = True
                if bl_active.get(hero.hero_id):
                    bl_tracked[hero.hero_id] = bl_tracked.get(hero.hero_id, 0) + temp_gain
                self._add_log(
                    f"{hero.name}: Second Wind — +{temp_gain} temp HP, +{hp_gain} HP.",
                    "heal",
                )

        elif sk.special == "evasion":
            hero.evasion_value = eff
            hero.evasion_active = True
            self._add_log(f"{hero.name}: Evasion active — reduces incoming damage by {eff}.", "hero")

    def _apply_buff_skill(self, hero: HeroEntity, sk: Skill, result: SkillResult) -> None:
        eff = result.effectiveness
        living_allies = [h for h in self.heroes if h.current_health > 0]

        if sk.special == "blessing":
            target = self._lowest_hp_ally()
            if target:
                target.apply_status(StatusEffect(status_type=StatusType.UPGRADE, duration=1))
                self._add_log(f"{hero.name}: Blessing — {target.name}'s dice upgraded this turn.", "hero")

        elif sk.special == "battle_hymn":
            for ally in living_allies:
                ally.advantage_next_turn = True
            self._add_log(f"{hero.name}: Battle Hymn — all allies gain Advantage next turn.", "hero")

        elif sk.special == "fortify":
            target = self._lowest_hp_ally()
            if target:
                target.block = eff
                con_mod = hero.effective_modifier(Stat.CON)
                target.retaliate_value = max(0, con_mod)
                target.retaliate_active = True
                target.retaliate_consumed = False
                self._add_log(f"{hero.name}: Fortify — {target.name} gains {eff} block.", "hero")

    def _process_enemy_skills(
        self,
        enemy: Enemy,
        triggered: list,
        living_now: List[HeroEntity],
        bl_active: dict,
        bl_tracked: dict,
        howl_bonus: int,
    ) -> None:
        shadow_mult = getattr(enemy, "shadow_damage_multiplier", 1.0)

        for skill, effectiveness in triggered:
            if shadow_mult != 1.0:
                effectiveness = int(effectiveness * shadow_mult)
            if effectiveness <= 0:
                continue
            if skill.special in ("howl", "phase_advance", "spawn_turret"):
                continue

            # Cannon Barrage (Mech)
            if skill.special == "cannon_barrage":
                n = len(living_now)
                if n > 0:
                    per = effectiveness // n
                    rem = effectiveness % n
                    for j, th in enumerate(living_now):
                        dmg = _apply_weak(per + (rem if j == 0 else 0) + howl_bonus, enemy.status_effects)
                        dmg = _apply_vulnerable(dmg, th.status_effects)
                        real = _damage_hero(th, dmg, self.barrier)
                        if real > 0:
                            self._add_log(f"{enemy.name}: Cannon Barrage → {th.name} for {real}.", "enemy_damage")
                        if bl_active.get(th.hero_id):
                            bl_tracked[th.hero_id] = bl_tracked.get(th.hero_id, 0) + real
                continue

            if skill.special == "oil_trap":
                for th in list(living_now):
                    th.apply_status(StatusEffect(status_type=StatusType.WEAK, duration=2))
                    th.apply_status(StatusEffect(status_type=StatusType.VULNERABLE, duration=1))
                    th.apply_status(StatusEffect(status_type=StatusType.PARALYZE, duration=1, stacks=1))
                self._add_log(f"{enemy.name}: Oil Trap — all heroes Weakened, Vulnerable, Paralyzed!", "enemy_damage")
                continue

            if skill.special == "golden_explosion":
                for th in list(living_now):
                    real = _damage_hero(th, effectiveness, self.barrier)
                    if real > 0:
                        self._add_log(f"{enemy.name}: Golden Explosion → {th.name} for {real}.", "enemy_damage")
                    if bl_active.get(th.hero_id):
                        bl_tracked[th.hero_id] = bl_tracked.get(th.hero_id, 0) + real
                continue

            if skill.effect_type == "defend":
                enemy.block += effectiveness
                if skill.special == "trap":
                    enemy.retaliate_active = True
                if skill.special in ("paralyze_all", "paralyze_all_2"):
                    stacks = 2 if skill.special == "paralyze_all_2" else 1
                    for th in list(living_now):
                        th.apply_status(StatusEffect(
                            status_type=StatusType.PARALYZE, duration=1, stacks=stacks
                        ))
                self._add_log(f"{enemy.name}: {skill.name} (block +{effectiveness}).", "enemy")

            elif skill.effect_type == "aoe" or skill.special == "golden_wave":
                targets = living_now
                if skill.special == "golden_wave":
                    targets = self.rng.sample(living_now, min(2, len(living_now)))
                total = 0
                for th in targets:
                    dmg = _apply_weak(effectiveness + howl_bonus, enemy.status_effects)
                    dmg = _apply_vulnerable(dmg, th.status_effects)
                    real = _damage_hero(th, dmg, self.barrier)
                    total += real
                    if bl_active.get(th.hero_id):
                        bl_tracked[th.hero_id] = bl_tracked.get(th.hero_id, 0) + real
                label = "all heroes" if skill.effect_type == "aoe" else f"{len(targets)} heroes"
                self._add_log(f"{enemy.name}: {skill.name} hits {label} for {total} total.", "enemy_damage")
                _apply_skill_status(skill.special, effectiveness, list(targets))

            else:
                th = self.rng.choice(living_now)
                dmg = _apply_weak(effectiveness + howl_bonus, enemy.status_effects)
                dmg = _apply_vulnerable(dmg, th.status_effects)
                real = _damage_hero(th, dmg, self.barrier)
                if real > 0:
                    self._add_log(f"{enemy.name}: {skill.name} → {th.name} for {real}.", "enemy_damage")
                _apply_skill_status(skill.special, effectiveness, [th])
                if bl_active.get(th.hero_id):
                    bl_tracked[th.hero_id] = bl_tracked.get(th.hero_id, 0) + real
                if hasattr(enemy, "gain_bloodlust"):
                    enemy.gain_bloodlust(real)
