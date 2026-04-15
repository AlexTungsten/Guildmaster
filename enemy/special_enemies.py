"""
special_enemies.py — Enemy subclasses with unique combat mechanics.

Each class extends Enemy with behaviour that can't be expressed as pure
slot-accumulation data.

  WerewolfEnemy          — Pack Leader: spawns 2 Wolves at the start of turn 2.
  KoboldTinkererEnemy    — Turret: spawns a Turret when the Turret skill fires
                           (one at a time; replaces dead turrets).
  BanditLeaderEnemy      — Shadow Step: alternates normal/shadow turns.
                           Shadow turn: untargetable by single-target, 2x damage.
                           AOE still hits; first AOE hit strips the shadow.
  CursedKnightEnemy      — Bloodlust + combat timer (critical quest variant).
                           Flees after max_combat_turns; records damage dealt.
  CursedKnightBossEnemy  — Boss variant: full bloodlust with Werewolf transformation.
                           No flee timer; when bloodlust > current_hp → transform
                           next turn into Spiral Slash form (6d6).
  KoboldKingEnemy        — Absolute untargetable Phase 1 boss; buffs the Mech
                           each turn on a HP/dice_count/dice_tier cycle.
                           Phase transitions when all guards die OR turn 7 reached.
  MechEnemy              — Hidden Phase 2 boss; Spread passive distributes dice
                           1-1-1 / 2-1-1 / 2-2-1 across skills.
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass, field
from typing import Any, List, Optional, Tuple

from hero.hero_entity import Skill, Stat
from enemy.enemy import Enemy, make_enemy


# ---------------------------------------------------------------------------
# Werewolf — Pack Leader
# ---------------------------------------------------------------------------

@dataclass
class WerewolfEnemy(Enemy):
    """Spawns 2 Wolves at the start of its second turn (once only)."""

    pack_spawned: bool = False

    def take_turn(self, rng: random.Random) -> List[Tuple[Skill, int]]:
        triggered = super().take_turn(rng)

        # turns_taken was incremented by super(); turn 2 = turns_taken == 2
        if self.turns_taken == 2 and not self.pack_spawned:
            self.pack_spawned = True
            for _ in range(2):
                wolf = _make_wolf(self.act)
                wolf.owner_ref = self
                wolf.acts_this_turn = True   # Wolves act this same round
                self.spawn_queue.append(wolf)

        return triggered


# ---------------------------------------------------------------------------
# Kobold Tinkerer — Turret spawn
# ---------------------------------------------------------------------------

@dataclass
class KoboldTinkererEnemy(Enemy):
    """Spawns a Turret when the Turret skill fires; only one Turret at a time."""

    # Reference to the currently active Turret (None if not spawned / dead)
    active_turret: Optional[Any] = field(default=None, compare=False, repr=False)

    def take_turn(self, rng: random.Random) -> List[Tuple[Skill, int]]:
        triggered = super().take_turn(rng)

        # Check if Turret skill fired
        remaining = []
        for skill, eff in triggered:
            if skill.special == "spawn_turret":
                # Only spawn if no turret alive
                if self.active_turret is None or not self.active_turret.is_alive:
                    turret = _make_turret(hp=max(1, eff), act=self.act, owner=self)
                    self.active_turret = turret
                    self.spawn_queue.append(turret)  # acts NEXT turn
                # Turret skill has no direct combat effect
            else:
                remaining.append((skill, eff))

        return remaining

    def on_damage_taken(self, amount: int) -> None:
        pass  # nothing extra for tinkerer


# ---------------------------------------------------------------------------
# Bandit Leader — Shadow Step
# ---------------------------------------------------------------------------

@dataclass
class BanditLeaderEnemy(Enemy):
    """
    Alternates normal and shadow turns.

    Shadow turn: untargetable by single-target skills, all damage dealt x2.
    If hit by AOE during a shadow turn the shadow is stripped (leader acts
    normally that turn).

    Turn 1 = normal (player gets a free round).
    Turn 2 = shadow, turn 3 = normal, etc.
    """

    # Toggled at END of each turn to prepare the next round's state
    is_shadow_turn: bool = False
    # Set True when hit by AOE during shadow turn; cleared after leader acts
    shadow_stripped: bool = False

    @property
    def untargetable(self) -> bool:
        """True when single-target heroes cannot select this enemy."""
        return self.is_shadow_turn and not self.shadow_stripped

    def on_damage_taken(self, amount: int) -> None:
        """Strip shadow if hit while in shadow mode."""
        if self.is_shadow_turn and amount > 0:
            self.shadow_stripped = True

    def take_turn(self, rng: random.Random) -> List[Tuple[Skill, int]]:
        triggered = super().take_turn(rng)

        # Apply 2x damage multiplier if shadow is active and NOT stripped
        acting_in_shadow = self.is_shadow_turn and not self.shadow_stripped
        if acting_in_shadow:
            triggered = [(sk, eff * 2) for sk, eff in triggered]

        # Toggle shadow for next round, reset strip flag
        self.is_shadow_turn = not self.is_shadow_turn
        self.shadow_stripped = False

        return triggered


# ---------------------------------------------------------------------------
# Cursed Knight — Bloodlust + combat timer (critical quest variant)
# ---------------------------------------------------------------------------

@dataclass
class CursedKnightEnemy(Enemy):
    """
    Critical quest variant of the Cursed Knight.

    Bloodlust:
      - Drops by damage taken.
      - Rises by damage dealt (updated in combat engine via gain_bloodlust()).
      - Capped at bloodlust_max = floor(current_hp * 0.75).
      - No transformation in this variant.

    Combat timer:
      - Flees after max_combat_turns (default 2) regardless of HP.
      - Sets fled=True and current_health=0 so combat engine removes it.

    carry_forward:
      - damage_taken_this_encounter is read by the ActRunState / QuestExecutor
        after combat to deduct from boss HP.
    """

    bloodlust_current: int = 125
    max_combat_turns: int = 2        # flee after this many turns
    damage_taken_this_encounter: int = 0

    @property
    def bloodlust_max(self) -> int:
        return int(self.current_health * 0.75)

    def on_damage_taken(self, amount: int) -> None:
        self.bloodlust_current = max(0, self.bloodlust_current - amount)
        self.damage_taken_this_encounter += amount

    def gain_bloodlust(self, amount: int) -> None:
        """Called by the combat engine when this enemy's skill deals damage."""
        cap = self.bloodlust_max
        self.bloodlust_current = min(cap, self.bloodlust_current + amount)

    def take_turn(self, rng: random.Random) -> List[Tuple[Skill, int]]:
        triggered = super().take_turn(rng)

        # Flee check (critical quest timer)
        if self.max_combat_turns > 0 and self.turns_taken >= self.max_combat_turns:
            self.fled = True
            self.current_health = 0

        return triggered


# ---------------------------------------------------------------------------
# Cursed Knight Boss — Bloodlust + Werewolf transformation
# ---------------------------------------------------------------------------

@dataclass
class CursedKnightBossEnemy(Enemy):
    """
    Boss fight variant of the Cursed Knight.

    Bloodlust:
      - Drops by damage taken (via on_damage_taken hook).
      - Rises by damage dealt (via gain_bloodlust() called from the engine).
      - Capped at floor(current_hp * 0.75); recalculates as HP changes.

    Transformation trigger:
      - End of turn: if bloodlust_current > current_hp and not yet transformed
        → _transform_next_turn = True.
      - Start of NEXT turn: transform into Werewolf form (6d6, Spiral Slash only).
      - After transformation bloodlust is frozen (no further updates).
    """

    bloodlust_current: int = 125
    transformed: bool = False
    _transform_next_turn: bool = field(default=False, compare=False, repr=False)

    @property
    def bloodlust_max(self) -> int:
        return int(self.current_health * 0.75)

    def on_damage_taken(self, amount: int) -> None:
        if not self.transformed:
            self.bloodlust_current = max(0, self.bloodlust_current - amount)

    def gain_bloodlust(self, amount: int) -> None:
        """Called by the combat engine when this boss's skills deal damage."""
        if not self.transformed:
            self.bloodlust_current = min(self.bloodlust_max, self.bloodlust_current + amount)

    def take_turn(self, rng: random.Random) -> List[Tuple[Skill, int]]:
        # Apply scheduled transformation at the start of this turn
        if self._transform_next_turn and not self.transformed:
            self._do_transform()

        triggered = super().take_turn(rng)

        # End-of-turn bloodlust check
        if not self.transformed and self.bloodlust_current > self.current_health:
            self._transform_next_turn = True

        return triggered

    def _do_transform(self) -> None:
        """Swap into Werewolf boss form: 6d6, Spiral Slash (6 slots, AOE, 2 Bleed)."""
        self.transformed = True
        self._transform_next_turn = False
        self.base_dice_count = 6
        self.base_dice_sides = 6
        spiral_slash = Skill(
            name="Spiral Slash",
            description="",
            associated_stat=Stat.STR,
            dice_slots=6,
            effect_type="aoe",
            special="bleed2",  # 2 Bleed applied to all heroes
        )
        self.skills = [spiral_slash]
        self.skill_buffers = [[]]


# ---------------------------------------------------------------------------
# Kobold King — Absolute untargetable; buffs the Mech each turn
# ---------------------------------------------------------------------------

_MECH_DICE_TIER_UP = {8: 10, 10: 12}  # d8→d10→d12 cap


@dataclass
class KoboldKingEnemy(Enemy):
    """
    Phase 1 boss entity — absolute untargetable, buffs the Mech each turn.

    Buff cycle (turns 1–6, looping HP/dice_count/dice_tier):
      Turn 1: +25 HP to Mech
      Turn 2: +1 die to Mech
      Turn 3: +1 dice tier to Mech (d8→d10→d12, capped)
      Turns 4–6: repeat the cycle
      Turn 7: no buff, trigger phase transition regardless of guard state

    Phase transition conditions (whichever comes first):
      - All 4 guards have 0 HP
      - phase1_turn reaches 7

    On transition:
      - Sets own current_health = 0 (removed from field).
      - Sets mech_ref.hidden = False (Mech becomes active next turn).
    """

    mech_ref: Optional[Any] = field(default=None, compare=False, repr=False)
    guards: List[Any] = field(default_factory=list, compare=False, repr=False)
    phase1_turn: int = 0
    buff_cycle_index: int = 0
    phase_ended: bool = False

    def __post_init__(self) -> None:
        super().__post_init__()
        self.absolute_untargetable = True
        self.skill_buffers = []

    def take_turn(self, rng: random.Random) -> List[Tuple[Skill, int]]:
        # King does not use the slot system — custom turn logic
        self.turns_taken += 1
        self.phase1_turn += 1
        self.block = 0
        self.retaliate_active = False

        if self.phase_ended:
            return []

        # Apply buff on turns 1–6 (turn 7 is the forced reveal with no buff)
        if self.phase1_turn <= 6 and self.mech_ref is not None:
            cycle = self.buff_cycle_index % 3
            if cycle == 0:  # HP buff
                self.mech_ref.max_health += 25
                self.mech_ref.current_health += 25
            elif cycle == 1:  # Dice count (cap 5)
                self.mech_ref.base_dice_count = min(5, self.mech_ref.base_dice_count + 1)
            else:  # Dice tier upgrade
                self.mech_ref.base_dice_sides = _MECH_DICE_TIER_UP.get(
                    self.mech_ref.base_dice_sides, self.mech_ref.base_dice_sides
                )
            self.buff_cycle_index += 1

        # Check phase transition (buff was applied above before checking)
        if self.phase1_turn >= 7 or self._all_guards_dead():
            self._trigger_phase_transition()

        return []

    def _all_guards_dead(self) -> bool:
        return bool(self.guards) and all(not g.is_alive for g in self.guards)

    def _trigger_phase_transition(self) -> None:
        if self.phase_ended:
            return
        self.phase_ended = True
        self.current_health = 0          # Remove King from field
        if self.mech_ref is not None:
            self.mech_ref.hidden = False  # Reveal Mech (acts next turn)


# ---------------------------------------------------------------------------
# Mech — Hidden Phase 2 boss; Spread passive dice distribution
# ---------------------------------------------------------------------------

@dataclass
class MechEnemy(Enemy):
    """
    Phase 2 boss entity with Spread passive dice distribution.

    Starts hidden=True and inactive during Phase 1.
    Revealed by KoboldKingEnemy._trigger_phase_transition().

    Spread passive:
      3 dice → 1-1-1 (1 die per skill)
      4 dice → 2-1-1 (2 to skill 1, 1 each to skills 2 & 3)
      5 dice → 2-2-1 (2 to skills 1 & 2, 1 to skill 3)

    Dice accumulate in buffers across turns; skills trigger when their
    slot requirement is met (same as standard slot-accumulation system).
    """

    def __post_init__(self) -> None:
        super().__post_init__()
        self.hidden = True  # Inactive during Phase 1

    def take_turn(self, rng: random.Random) -> List[Tuple[Skill, int]]:
        if self.hidden:
            return []

        self.turns_taken += 1
        self.block = 0
        self.retaliate_active = False

        # Roll dice pool
        die_count = self.base_dice_count
        die_values: List[int] = [
            rng.randint(1, self.base_dice_sides) for _ in range(die_count)
        ]

        # Bleed: discard 1 random die (minimum 1 kept)
        from combat.status_effects import has_status, StatusType
        if has_status(self.status_effects, StatusType.BLEED) and len(die_values) > 1:
            die_values.pop(rng.randrange(len(die_values)))
            die_count = len(die_values)

        # Spread allocation
        if die_count <= 3:
            alloc = [1, 1, 1]
        elif die_count == 4:
            alloc = [2, 1, 1]
        else:
            alloc = [2, 2, 1]

        triggered: List[Tuple[Skill, int]] = []
        die_idx = 0

        for i, skill in enumerate(self.skills):
            if i >= len(alloc):
                break
            allocated = alloc[i]
            new_dice = die_values[die_idx:die_idx + allocated]
            die_idx += allocated

            if i >= len(self.skill_buffers):
                self.skill_buffers.append([])
            buffer = self.skill_buffers[i]
            buffer.extend(new_dice)

            if len(buffer) >= skill.dice_slots:
                effectiveness = sum(buffer)
                triggered.append((skill, effectiveness))
                self.skill_buffers[i] = []

        return triggered


# ---------------------------------------------------------------------------
# Internal factories
# ---------------------------------------------------------------------------

def _make_wolf(act: int) -> Enemy:
    """Create a Wolf enemy instance for Pack Leader spawning."""
    import os, json
    _DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "data", "enemies")
    path = os.path.join(_DATA_DIR, "wolf.json")
    with open(path, "r") as f:
        template = json.load(f)
    return make_enemy(template, act)


def _make_turret(hp: int, act: int, owner: KoboldTinkererEnemy) -> Enemy:
    """Create a Turret with the given HP, owned by the given Tinkerer."""
    import os, json
    _DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "data", "enemies")
    path = os.path.join(_DATA_DIR, "turret.json")
    with open(path, "r") as f:
        template = json.load(f)
    turret = make_enemy(template, act)
    # Override HP with dice-result value (turret.json has a placeholder)
    turret.max_health = hp
    turret.current_health = hp
    turret.owner_ref = owner
    return turret
