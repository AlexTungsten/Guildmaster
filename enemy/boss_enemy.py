"""
boss_enemy.py — Boss enemy with phase-based skill progression.

BossEnemy extends Enemy with:
  - Multi-phase skill sets that swap when Skill 3 (the accumulation skill) fires.
  - Skill 3 uses a Mage-refresh-like accumulation: overflow dice from Skills 1 & 2
    plus the Steal skill's effectiveness feed into a progress counter.
  - Permanent buffs that stack across phases: extra dice, dice tier upgrades,
    and permanent Advantage.

Phase transitions are triggered exclusively by Skill 3 firing (progress >= cost).
Upgraded skills apply immediately. All permanent buffs persist into later phases.

Designed for Baron Midas (Act 1 boss) but generic enough for future bosses.
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from hero.hero_entity import Skill, Stat
from enemy.enemy import Enemy


@dataclass
class PhaseDefinition:
    """One phase of a boss encounter: its skill set and Skill 3 accumulation cost."""
    phase: int
    skills: List[Skill]
    accumulation_cost: int  # Total roll needed for Skill 3 to fire


@dataclass
class BossEnemy(Enemy):
    """
    A boss enemy with phase-based skill progression.

    Overrides take_turn() to implement:
      1. Roll dice (respecting permanent buffs: extra dice, upgraded sides, Advantage).
      2. Fill Skill 1 slots, then Skill 2 slots.
      3. Overflow dice values accumulate into Skill 3 progress.
      4. Steal's effectiveness (when it fires) also reduces Skill 3 remaining cost.
      5. When Skill 3 progress >= cost: fire Skill 3, advance phase, apply buffs.
    """

    # Phase system
    phase_definitions: List[PhaseDefinition] = field(default_factory=list)
    current_phase: int = 1

    # Skill 3 accumulation (like Mage refresh but fed by overflow + Steal)
    skill3_progress: int = 0
    skill3_cost: int = 15  # Current phase's accumulation cost

    # Permanent buffs that stack across phases
    bonus_dice: int = 0          # Extra dice gained from phase transitions
    dice_sides_override: int = 0  # 0 = use base_dice_sides; >0 = override (e.g. d8)
    has_permanent_advantage: bool = False

    # Gold stolen during the act (determines bonus HP at fight start)
    gold_stolen: int = 0

    def __post_init__(self) -> None:
        """Initialize skill buffers and apply gold-stolen HP bonus."""
        if not self.skill_buffers:
            self.skill_buffers = [[] for _ in self.skills]
        # Apply gold stolen as bonus HP (capped externally before construction)
        if self.gold_stolen > 0:
            self.max_health += self.gold_stolen
            self.current_health += self.gold_stolen

    @property
    def effective_dice_count(self) -> int:
        """Total dice per turn including permanent bonus dice."""
        return self.base_dice_count + self.bonus_dice

    @property
    def effective_dice_sides(self) -> int:
        """Die type respecting permanent upgrades."""
        if self.dice_sides_override > 0:
            return self.dice_sides_override
        return self.base_dice_sides

    def _roll_dice(self, rng: random.Random) -> List[int]:
        """Roll dice respecting permanent Advantage."""
        count = self.effective_dice_count
        sides = self.effective_dice_sides
        if self.has_permanent_advantage:
            # Roll twice, keep best for each die
            return [
                max(rng.randint(1, sides), rng.randint(1, sides))
                for _ in range(count)
            ]
        return [rng.randint(1, sides) for _ in range(count)]

    def _advance_phase(self) -> Optional[Skill]:
        """
        Advance to the next phase, apply permanent buffs, swap skills.

        Returns the Skill 3 that triggered (for the combat engine to process).
        """
        fired_skill = self.skills[2] if len(self.skills) > 2 else None

        # Apply permanent buffs based on which phase just completed
        if self.current_phase == 1:
            self.bonus_dice += 1
        elif self.current_phase == 2:
            self.dice_sides_override = 8
        elif self.current_phase == 3:
            self.has_permanent_advantage = True

        # Advance to next phase
        next_phase_num = self.current_phase + 1
        next_phase = None
        for pd in self.phase_definitions:
            if pd.phase == next_phase_num:
                next_phase = pd
                break

        if next_phase is not None:
            self.current_phase = next_phase_num
            self.skills = list(next_phase.skills)
            self.skill3_cost = next_phase.accumulation_cost
            self.skill3_progress = 0
            # Reset skill buffers for new skill set
            self.skill_buffers = [[] for _ in self.skills]

        return fired_skill

    def take_turn(self, rng: random.Random) -> List[Tuple[Skill, int]]:
        """
        Execute one boss turn with the phase-accumulation system.

        Steps:
          1. Expire block from previous turn.
          2. Roll dice (with permanent buffs applied).
          3. Fill Skill 1 slots, then Skill 2 slots.
          4. If Skill 1 (Steal/Golden Wave) fires: its effectiveness also
             reduces Skill 3's remaining cost.
          5. Overflow dice values accumulate into Skill 3 progress.
          6. If Skill 3 progress >= cost: fire Skill 3, advance phase.

        Returns list of (Skill, effectiveness) pairs that triggered.
        """
        # Step 1 — expire block
        self.block = 0

        # Step 2 — roll
        die_values = self._roll_dice(rng)

        # Step 3 — distribute to Skill 1 and Skill 2 in order
        triggered: List[Tuple[Skill, int]] = []
        steal_effectiveness = 0
        die_queue = list(die_values)

        for i in range(min(2, len(self.skills))):
            if not die_queue:
                break
            skill = self.skills[i]
            buffer = self.skill_buffers[i]
            slots_remaining = skill.dice_slots - len(buffer)

            to_insert = min(slots_remaining, len(die_queue))
            buffer.extend(die_queue[:to_insert])
            die_queue = die_queue[to_insert:]

            if len(buffer) >= skill.dice_slots:
                effectiveness = sum(buffer)
                triggered.append((skill, effectiveness))
                self.skill_buffers[i] = []

                # Track Steal/Golden Wave effectiveness for Skill 3 cost reduction
                if skill.special in ("gold_steal", "golden_wave"):
                    steal_effectiveness += effectiveness

        # Step 4 — overflow dice go to Skill 3 progress
        overflow = sum(die_queue)
        self.skill3_progress += overflow

        # Step 5 — Steal effectiveness also reduces Skill 3 cost
        self.skill3_progress += steal_effectiveness

        # Step 6 — check if Skill 3 fires
        if len(self.skills) > 2 and self.skill3_progress >= self.skill3_cost:
            skill3 = self.skills[2]
            skill3_effectiveness = self.skill3_progress

            # For Golden Explosion (Phase 4 Skill 3): fixed 30 damage to all
            if skill3.special == "golden_explosion":
                triggered.append((skill3, 30))
            else:
                triggered.append((skill3, skill3_effectiveness))

            # Advance phase (applies permanent buffs + swaps skills)
            self._advance_phase()

        return triggered

    # ------------------------------------------------------------------
    # Serialization
    # ------------------------------------------------------------------

    def to_dict(self) -> dict:
        base = super().to_dict()
        base["is_boss"] = True
        base["current_phase"] = self.current_phase
        base["skill3_progress"] = self.skill3_progress
        base["skill3_cost"] = self.skill3_cost
        base["bonus_dice"] = self.bonus_dice
        base["dice_sides_override"] = self.dice_sides_override
        base["has_permanent_advantage"] = self.has_permanent_advantage
        base["gold_stolen"] = self.gold_stolen
        base["phase_definitions"] = [
            {
                "phase": pd.phase,
                "skills": [s.to_dict() for s in pd.skills],
                "accumulation_cost": pd.accumulation_cost,
            }
            for pd in self.phase_definitions
        ]
        return base
