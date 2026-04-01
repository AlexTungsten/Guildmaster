"""
hero_entity.py — Core data model for a Guildmaster hero.

Defines:
  - Stat / HeroStatus enums
  - Skill dataclass (a hero's learnable abilities)
  - HeroEntity dataclass — the full stat block, exhaustion state, XP, and
    inventory for a single hero

All mutation methods live on HeroEntity so that callers never reach directly
into the fields for game-logic changes (they do for rendering/serialization).
"""

import random
from dataclasses import dataclass, field
from enum import Enum
from math import floor
from typing import Any, List, Optional


class Stat(Enum):
    """The five D&D-style ability scores used by heroes and enemies."""
    STR = "strength"
    DEX = "dexterity"
    INT = "intelligence"
    CHA = "charisma"
    CON = "constitution"


class HeroStatus(Enum):
    """Lifecycle state of a hero; governs what actions are permitted."""
    IDLE = "idle"
    TRAVELING = "traveling"
    ON_QUEST = "on_quest"
    IN_COMBAT = "in_combat"
    DEAD = "dead"


@dataclass
class Skill:
    """A learnable ability that occupies one of a hero's three skill slots."""
    name: str
    description: str
    associated_stat: Stat   # Stat modifier added to this skill's effectiveness roll
    dice_slots: int          # How many dice from the pool are reserved for this skill
    effect_type: str         # e.g. "damage", "heal", "aoe" — drives combat resolution

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "description": self.description,
            "associated_stat": self.associated_stat.value,
            "dice_slots": self.dice_slots,
            "effect_type": self.effect_type,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Skill":
        return cls(
            name=data["name"],
            description=data["description"],
            associated_stat=Stat(data["associated_stat"]),
            dice_slots=data["dice_slots"],
            effect_type=data["effect_type"],
        )


@dataclass
class HeroEntity:
    """
    Full representation of one hero in the guild.

    Base stats (strength, dexterity, …) represent the hero's permanent training.
    *_loss fields track irreversible stat degradation from critical failures.
    Exhaustion is a 0–100+ float; higher values lock dice and degrade stats.
    """

    hero_id: str
    name: str
    archetype: str

    # Base (permanent) ability scores — start at 10 (D&D-style "average")
    strength: int = 10
    dexterity: int = 10
    intelligence: int = 10
    charisma: int = 10
    constitution: int = 10

    # Permanent stat losses from death rolls or critical consequences
    strength_loss: int = 0
    dexterity_loss: int = 0
    intelligence_loss: int = 0
    charisma_loss: int = 0
    constitution_loss: int = 0

    level: int = 1
    xp: int = 0
    xp_to_next: int = 100   # XP threshold for the next level-up; scales by 1.5x each level

    max_health: int = 30
    current_health: int = 30

    # Exhaustion: 0 = fully rested, 100+ = critical / death-risk territory
    exhaustion: float = 0.0

    # Skill slots — None means the slot is empty
    skills: List[Optional[Skill]] = field(default_factory=lambda: [None, None, None])

    behavior_profile: str = "balanced"   # Controls dice assignment strategy in combat
    item_slots: int = 1
    equipped_items: List[Optional[Any]] = field(default_factory=lambda: [None])

    status: HeroStatus = HeroStatus.IDLE
    base_dice_count: int = 4   # Total dice in the hero's pool before exhaustion locks

    # ------------------------------------------------------------------
    # Internal stat helpers
    # ------------------------------------------------------------------

    def _stat_value(self, stat: Stat) -> int:
        """Return the raw (unmodified by loss) value for the given stat."""
        mapping = {
            Stat.STR: self.strength,
            Stat.DEX: self.dexterity,
            Stat.INT: self.intelligence,
            Stat.CHA: self.charisma,
            Stat.CON: self.constitution,
        }
        return mapping[stat]

    def _stat_loss_value(self, stat: Stat) -> int:
        """Return the accumulated permanent loss for the given stat."""
        mapping = {
            Stat.STR: self.strength_loss,
            Stat.DEX: self.dexterity_loss,
            Stat.INT: self.intelligence_loss,
            Stat.CHA: self.charisma_loss,
            Stat.CON: self.constitution_loss,
        }
        return mapping[stat]

    def _set_stat_loss(self, stat: Stat, value: int) -> None:
        """Write an updated permanent loss value back to the correct field."""
        if stat == Stat.STR:
            self.strength_loss = value
        elif stat == Stat.DEX:
            self.dexterity_loss = value
        elif stat == Stat.INT:
            self.intelligence_loss = value
        elif stat == Stat.CHA:
            self.charisma_loss = value
        elif stat == Stat.CON:
            self.constitution_loss = value

    # ------------------------------------------------------------------
    # Public stat accessors
    # ------------------------------------------------------------------

    def effective_stat(self, stat: Stat) -> int:
        """Base stat minus permanent losses; clamped to 0."""
        return max(0, self._stat_value(stat) - self._stat_loss_value(stat))

    def stat_modifier(self, stat: Stat) -> int:
        """D&D-style modifier: floor(effective / 2) - 5."""
        return floor(self.effective_stat(stat) / 2) - 5

    # ------------------------------------------------------------------
    # Exhaustion system
    # ------------------------------------------------------------------

    def exhaustion_level(self) -> int:
        """
        Convert the floating exhaustion score to a discrete 1–5 severity level.

        Level 1: < 20   — Rested (no penalty)
        Level 2: 20–39  — Tired (1 locked die, 1 stat penalty)
        Level 3: 40–59  — Weary (2 locked dice, 2 stat penalties)
        Level 4: 60–99  — Drained (3 locked dice, all stat penalties)
        Level 5: >= 100 — Critical (4 locked dice, all stats penalised, death risk)
        """
        if self.exhaustion >= 100:
            return 5
        elif self.exhaustion >= 60:
            return 4
        elif self.exhaustion >= 40:
            return 3
        elif self.exhaustion >= 20:
            return 2
        else:
            return 1

    def exhaustion_temp_reduction(self) -> int:
        """Flat point reduction applied to affected stats at exhaustion level >= 2."""
        if self.exhaustion_level() >= 2:
            return 2
        return 0

    def _exhaustion_affected_stats(self) -> List[Stat]:
        """
        Return the list of stats that suffer the exhaustion penalty.

        Higher exhaustion levels affect more stats, targeting the hero's
        strongest stats first (to punish their primary effectiveness).
        """
        level = self.exhaustion_level()
        if level == 1:
            return []  # No penalty at rested level
        all_stats = list(Stat)
        # Sort highest effective stat first so fatigue hits the hero's strengths
        sorted_stats = sorted(all_stats, key=lambda s: self.effective_stat(s), reverse=True)
        if level == 2:
            return sorted_stats[:1]   # Only the top stat is affected
        elif level == 3:
            return sorted_stats[:2]   # Top two stats affected
        else:
            return all_stats          # Level 4–5: all stats affected

    def effective_modifier(self, stat: Stat) -> int:
        """
        Modifier used during skill rolls, accounting for exhaustion penalties.

        If the stat is in the exhaustion-affected list, its effective value is
        reduced by exhaustion_temp_reduction() before the modifier calculation.
        """
        affected = self._exhaustion_affected_stats()
        reduction = self.exhaustion_temp_reduction()
        if stat in affected:
            # Apply the exhaustion flat reduction before converting to modifier
            return floor((self.effective_stat(stat) - reduction) / 2) - 5
        return self.stat_modifier(stat)

    def locked_dice_count(self) -> int:
        """
        Number of base dice replaced by locked d4s due to exhaustion.

        Locked dice roll d4 instead of d10, always appearing at the front of
        the dice pool before normal dice are assigned.
        """
        level = self.exhaustion_level()
        mapping = {1: 0, 2: 1, 3: 2, 4: 3, 5: 4}
        return mapping[level]

    def add_exhaustion(self, amount: float) -> None:
        """Accumulate exhaustion from quest activity, travel, or damage."""
        self.exhaustion += amount

    def recover_exhaustion(self, seconds: float = 1.0) -> None:
        """
        Tick-based exhaustion recovery — only applies when the hero is IDLE.

        Passes silently if the hero is on a quest, traveling, or in combat.
        """
        if self.status != HeroStatus.IDLE:
            return
        self.exhaustion = max(0.0, self.exhaustion - seconds)

    # ------------------------------------------------------------------
    # Progression
    # ------------------------------------------------------------------

    def gain_xp(self, amount: int) -> bool:
        """
        Award XP; returns True if a level-up occurred.

        On level-up the XP threshold scales by 1.5× so each subsequent level
        requires more experience.
        """
        self.xp += amount
        if self.xp >= self.xp_to_next:
            self.xp -= self.xp_to_next      # Carry over excess XP
            self.level += 1
            self.xp_to_next = int(self.xp_to_next * 1.5)
            return True
        return False

    def apply_permanent_stat_loss(self) -> Stat:
        """
        Randomly degrade one stat by 1 point permanently.

        Called on a failed death roll.  Returns the affected Stat so the
        caller can log or display what was lost.
        """
        stat = random.choice(list(Stat))
        self._set_stat_loss(stat, self._stat_loss_value(stat) + 1)
        return stat

    def death_roll(self) -> bool:
        """
        Roll against exhaustion to determine if the hero faces a permanent consequence.

        Returns True (death/consequence triggered) when the random 1–1000
        roll is less than the current exhaustion score.  At exhaustion 100+
        the risk is 10%+; lower exhaustion makes this very unlikely.
        """
        roll = random.randint(1, 1000)
        return roll < self.exhaustion

    # ------------------------------------------------------------------
    # Skills
    # ------------------------------------------------------------------

    def replace_skill(self, slot: int, new_skill: Skill) -> Optional[Skill]:
        """Swap the skill in the given slot (0–2) with new_skill; returns the displaced skill."""
        old = self.skills[slot]
        self.skills[slot] = new_skill
        return old

    # ------------------------------------------------------------------
    # Serialization
    # ------------------------------------------------------------------

    def to_dict(self) -> dict:
        return {
            "hero_id": self.hero_id,
            "name": self.name,
            "archetype": self.archetype,
            "strength": self.strength,
            "dexterity": self.dexterity,
            "intelligence": self.intelligence,
            "charisma": self.charisma,
            "constitution": self.constitution,
            "strength_loss": self.strength_loss,
            "dexterity_loss": self.dexterity_loss,
            "intelligence_loss": self.intelligence_loss,
            "charisma_loss": self.charisma_loss,
            "constitution_loss": self.constitution_loss,
            "level": self.level,
            "xp": self.xp,
            "xp_to_next": self.xp_to_next,
            "max_health": self.max_health,
            "current_health": self.current_health,
            "exhaustion": self.exhaustion,
            "skills": [s.to_dict() if s is not None else None for s in self.skills],
            "behavior_profile": self.behavior_profile,
            "item_slots": self.item_slots,
            "equipped_items": self.equipped_items,
            "status": self.status.value,
            "base_dice_count": self.base_dice_count,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "HeroEntity":
        """Reconstruct a HeroEntity from a previously serialized dict."""
        skills_raw = data.get("skills", [None, None, None])
        # Deserialize each skill slot; None means the slot is empty
        skills = [Skill.from_dict(s) if s is not None else None for s in skills_raw]
        return cls(
            hero_id=data["hero_id"],
            name=data["name"],
            archetype=data["archetype"],
            strength=data.get("strength", 10),
            dexterity=data.get("dexterity", 10),
            intelligence=data.get("intelligence", 10),
            charisma=data.get("charisma", 10),
            constitution=data.get("constitution", 10),
            strength_loss=data.get("strength_loss", 0),
            dexterity_loss=data.get("dexterity_loss", 0),
            intelligence_loss=data.get("intelligence_loss", 0),
            charisma_loss=data.get("charisma_loss", 0),
            constitution_loss=data.get("constitution_loss", 0),
            level=data.get("level", 1),
            xp=data.get("xp", 0),
            xp_to_next=data.get("xp_to_next", 100),
            max_health=data.get("max_health", 30),
            current_health=data.get("current_health", 30),
            exhaustion=data.get("exhaustion", 0.0),
            skills=skills,
            behavior_profile=data.get("behavior_profile", "balanced"),
            item_slots=data.get("item_slots", 1),
            equipped_items=data.get("equipped_items", [None]),
            status=HeroStatus(data.get("status", "idle")),
            base_dice_count=data.get("base_dice_count", 4),
        )
