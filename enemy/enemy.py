"""
enemy.py — Enemy entity and factory for Guildmaster.

Defines:
  - Enemy: full stat block for one enemy, using a slot-accumulation turn system
    where rolled dice are distributed to skill slots in order; skills fire only
    when all their slots are filled.
  - make_enemy(): factory that instantiates an Enemy from a data template dict.

Turn mechanic (slot-accumulation):
  Each turn the enemy rolls base_dice_count dice of base_dice_sides sides.
  Dice are distributed to skills in order (skill 0 → 1 → 2).  A skill fires
  only when all of its dice_slots have been filled — accumulated die values
  persist between turns.  After firing the skill's buffer clears and begins
  refilling next turn.

  Block expires (resets to 0) at the start of each enemy turn before new dice
  are rolled.  Enemy damage is the raw sum of accumulated dice — no stat
  modifiers are applied.
"""

from dataclasses import dataclass, field
from typing import Any, List, Tuple
import math
import random

from hero.hero_entity import Skill, Stat


def _load_status_effects(raw: list) -> list:
    if not raw:
        return []
    from combat.status_effects import StatusEffect
    return [StatusEffect.from_dict(d) for d in raw]


@dataclass
class Enemy:
    """Full stat block for one combat enemy."""

    enemy_id: str
    name: str
    archetype: str
    act: int

    # Ability scores — kept for stat-check compatibility; not used in combat math
    strength: int = 10
    dexterity: int = 10
    intelligence: int = 10
    charisma: int = 10
    constitution: int = 10

    max_health: int = 20
    current_health: int = 20

    skills: List[Skill] = field(default_factory=list)
    base_dice_count: int = 3
    base_dice_sides: int = 6  # die type per enemy (d6 common, d4 Goblin, d12 Ogre)

    # Per-skill accumulation buffers.  skill_buffers[i] holds die values inserted
    # into skill i's slots so far (not yet triggered).  Initialised in __post_init__.
    skill_buffers: List[List[int]] = field(default_factory=list)

    # Current block value — absorbs incoming hero damage before real HP.
    # Resets to 0 at the start of this enemy's next turn.
    block: int = 0

    # Active status effects (List[StatusEffect] typed as List to avoid circular import)
    status_effects: List[Any] = field(default_factory=list)

    def __post_init__(self) -> None:
        """Ensure one buffer list exists per skill."""
        if not self.skill_buffers:
            self.skill_buffers = [[] for _ in self.skills]

    # ------------------------------------------------------------------
    # Stat helpers (retained for stat-check compatibility)
    # ------------------------------------------------------------------

    def stat_modifier(self, stat: Stat) -> int:
        """Standard D&D modifier formula: floor(stat / 2) - 5."""
        mapping = {
            Stat.STR: self.strength,
            Stat.DEX: self.dexterity,
            Stat.INT: self.intelligence,
            Stat.CHA: self.charisma,
            Stat.CON: self.constitution,
        }
        return math.floor(mapping[stat] / 2) - 5

    @property
    def is_alive(self) -> bool:
        return self.current_health > 0

    # ------------------------------------------------------------------
    # Damage and block absorption
    # ------------------------------------------------------------------

    def apply_status(self, effect: Any) -> None:
        from combat.status_effects import apply_status
        self.status_effects = apply_status(self.status_effects, effect)

    def has_status(self, status_type: Any) -> bool:
        from combat.status_effects import has_status
        return has_status(self.status_effects, status_type)

    def get_status(self, status_type: Any) -> Any:
        from combat.status_effects import get_status
        return get_status(self.status_effects, status_type)

    def has_any_debuff(self) -> bool:
        from combat.status_effects import has_any_debuff
        return has_any_debuff(self.status_effects)

    def clear_status(self, status_type: Any) -> None:
        self.status_effects = [e for e in self.status_effects if e.status_type != status_type]

    def take_damage(self, amount: int) -> int:
        """
        Apply incoming damage, consuming block first.

        Returns the actual real-HP damage dealt (never exceeds current HP,
        never counts overkill).
        """
        blocked = min(self.block, amount)
        self.block -= blocked
        remaining = amount - blocked
        actual = min(remaining, self.current_health)
        self.current_health -= actual
        return actual

    # ------------------------------------------------------------------
    # Turn mechanic — slot-accumulation
    # ------------------------------------------------------------------

    def take_turn(self, rng: random.Random) -> List[Tuple[Skill, int]]:
        """
        Execute one enemy turn using the slot-accumulation system.

        Steps
        -----
        1. Expire block from the previous turn (reset to 0).
        2. Roll base_dice_count d<base_dice_sides>.
        3. Distribute rolled dice to skills in order (0, 1, 2 …).
           Each die fills the next open slot in the current skill.
           When a skill's slots are fully filled it triggers immediately and its
           buffer clears; remaining dice continue into the next skill.
        4. Return every (Skill, effectiveness) pair that triggered this turn.
           May be empty, one, or multiple — depends on encounter design.

        Dice that remain after all skills' slot budgets are exhausted for the
        turn are discarded (encounter dice counts are designed to prevent this
        being significant).
        """
        # Step 1 — expire block
        self.block = 0

        # Step 2 — roll
        die_queue: List[int] = [
            rng.randint(1, self.base_dice_sides)
            for _ in range(self.base_dice_count)
        ]

        # Step 3 — distribute dice to skills in slot order
        triggered: List[Tuple[Skill, int]] = []

        for i, skill in enumerate(self.skills):
            if not die_queue:
                break

            buffer = self.skill_buffers[i]
            slots_remaining = skill.dice_slots - len(buffer)

            to_insert = min(slots_remaining, len(die_queue))
            buffer.extend(die_queue[:to_insert])
            die_queue = die_queue[to_insert:]

            if len(buffer) >= skill.dice_slots:
                effectiveness = sum(buffer)
                triggered.append((skill, effectiveness))
                self.skill_buffers[i] = []

        return triggered

    # ------------------------------------------------------------------
    # Act scaling — HP only; tuning via raw encounter numbers
    # ------------------------------------------------------------------

    def scale_for_act(self, act: int) -> None:
        """
        Scale HP for the given act.  Dice counts and stats are not scaled —
        difficulty is tuned via raw numbers in each encounter definition.

        Act 1: ×1.0  |  Act 2: ×1.3  |  Act 3: ×1.6
        """
        multiplier = 1 + 0.3 * (act - 1)
        self.max_health = round(self.max_health * multiplier)
        self.current_health = round(self.current_health * multiplier)

    # ------------------------------------------------------------------
    # Serialization
    # ------------------------------------------------------------------

    def to_dict(self) -> dict:
        return {
            "enemy_id": self.enemy_id,
            "name": self.name,
            "archetype": self.archetype,
            "act": self.act,
            "strength": self.strength,
            "dexterity": self.dexterity,
            "intelligence": self.intelligence,
            "charisma": self.charisma,
            "constitution": self.constitution,
            "max_health": self.max_health,
            "current_health": self.current_health,
            "skills": [s.to_dict() for s in self.skills],
            "base_dice_count": self.base_dice_count,
            "base_dice_sides": self.base_dice_sides,
            "skill_buffers": [list(buf) for buf in self.skill_buffers],
            "block": self.block,
            "status_effects": [e.to_dict() for e in self.status_effects],
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Enemy":
        skills = [Skill.from_dict(s) for s in data.get("skills", [])]
        skill_buffers = [list(buf) for buf in data.get("skill_buffers", [])]
        if not skill_buffers:
            skill_buffers = [[] for _ in skills]
        return cls(
            enemy_id=data["enemy_id"],
            name=data["name"],
            archetype=data["archetype"],
            act=data["act"],
            strength=data.get("strength", 10),
            dexterity=data.get("dexterity", 10),
            intelligence=data.get("intelligence", 10),
            charisma=data.get("charisma", 10),
            constitution=data.get("constitution", 10),
            max_health=data.get("max_health", 20),
            current_health=data.get("current_health", 20),
            skills=skills,
            base_dice_count=data.get("base_dice_count", 3),
            base_dice_sides=data.get("base_dice_sides", 6),
            skill_buffers=skill_buffers,
            block=data.get("block", 0),
            status_effects=_load_status_effects(data.get("status_effects", [])),
        )


def make_enemy(template: dict, act: int) -> Enemy:
    """
    Instantiate and scale an Enemy from a data template dict.

    The template uses the same field names as Enemy.to_dict().  After
    construction the enemy is scaled for the given act via scale_for_act().
    Skill buffers always start empty regardless of what the template contains.
    """
    skills = [Skill.from_dict(s) for s in template.get("skills", [])]
    enemy = Enemy(
        enemy_id=template["enemy_id"],
        name=template["name"],
        archetype=template["archetype"],
        act=act,
        strength=template.get("strength", 10),
        dexterity=template.get("dexterity", 10),
        intelligence=template.get("intelligence", 10),
        charisma=template.get("charisma", 10),
        constitution=template.get("constitution", 10),
        max_health=template.get("max_health", 20),
        current_health=template.get("current_health", 20),
        skills=skills,
        base_dice_count=template.get("base_dice_count", 3),
        base_dice_sides=template.get("base_dice_sides", 6),
        skill_buffers=[[] for _ in skills],
        block=0,
        status_effects=[],
    )
    enemy.scale_for_act(act)
    return enemy
