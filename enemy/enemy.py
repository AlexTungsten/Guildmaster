"""
enemy.py — Enemy entity and factory for Guildmaster.

Defines:
  - AttackPattern: a cycling sequence of skill indices that determines which
    skill an enemy uses each combat round.
  - Enemy: the full stat block for one enemy, mirroring HeroEntity's structure
    but without exhaustion, XP, or behavior profiles.
  - make_enemy(): factory that instantiates an Enemy from a data template and
    scales its stats for the current act.
"""

from dataclasses import dataclass, field
from typing import List, Dict, Any
import math
import random

from hero.hero_entity import Skill, Stat


@dataclass
class AttackPattern:
    """
    Cyclic schedule of skill indices that the enemy rotates through each round.

    For example, skill_indices=[0, 1, 0, 2] means the enemy alternates using
    skills 0, 1, 0, 2 then loops back to the start.
    """
    skill_indices: List[int]
    _round: int = field(default=0, repr=False)  # Internal counter for the current position

    def next_skill_index(self) -> int:
        """
        Return the skill index for the current round and advance the counter.

        Falls back to index 0 if the pattern list is somehow empty.
        """
        if not self.skill_indices:
            return 0
        # Wrap around using modulo so the pattern cycles indefinitely
        index = self.skill_indices[self._round % len(self.skill_indices)]
        self._round += 1
        return index


@dataclass
class Enemy:
    """
    Full stat block for one combat enemy.

    Stats use the same D&D-style scale as HeroEntity (base 10 = modifier 0).
    Enemies do not have exhaustion, behavior profiles, or skill slots — they
    use their AttackPattern and a flat dice count instead.
    """
    enemy_id: str
    name: str
    archetype: str
    act: int   # The act this enemy was created for (used by scale_for_act)

    # Base ability scores — default 10 (neutral modifier)
    strength: int = 10
    dexterity: int = 10
    intelligence: int = 10
    charisma: int = 10
    constitution: int = 10

    max_health: int = 20
    current_health: int = 20

    skills: List[Skill] = field(default_factory=list)
    base_dice_count: int = 3   # Dice rolled for every attack (no locked dice mechanic)
    pattern: AttackPattern = field(default_factory=lambda: AttackPattern([0]))

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
        """True when the enemy still has health remaining."""
        return self.current_health > 0

    def take_damage(self, amount: int) -> None:
        """Reduce current health by amount, clamped to 0 (never goes negative)."""
        self.current_health = max(0, self.current_health - amount)

    def scale_for_act(self, act: int) -> None:
        """
        Multiply all stats and health by an act-based multiplier.

        Act 1: x1.0 (no change)
        Act 2: x1.3
        Act 3: x1.6

        Also adds (act - 1) extra dice to base_dice_count so later-act
        enemies roll more dice and hit harder.
        """
        multiplier = 1 + 0.3 * (act - 1)
        self.strength = round(self.strength * multiplier)
        self.dexterity = round(self.dexterity * multiplier)
        self.intelligence = round(self.intelligence * multiplier)
        self.charisma = round(self.charisma * multiplier)
        self.constitution = round(self.constitution * multiplier)
        self.max_health = round(self.max_health * multiplier)
        self.current_health = round(self.current_health * multiplier)
        self.base_dice_count += act - 1   # e.g., act 2 adds 1 extra die

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
            "pattern": {
                "skill_indices": self.pattern.skill_indices,
                "_round": self.pattern._round,
            },
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Enemy":
        """Reconstruct an Enemy from a serialized dict."""
        skills = [Skill.from_dict(s) for s in data.get("skills", [])]
        pattern_data = data.get("pattern", {"skill_indices": [0], "_round": 0})
        pattern = AttackPattern(
            skill_indices=pattern_data.get("skill_indices", [0]),
            _round=pattern_data.get("_round", 0),
        )
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
            pattern=pattern,
        )


def make_enemy(template: dict, act: int) -> Enemy:
    """
    Instantiate and scale an Enemy from a data template dict.

    The template uses the same field names as Enemy.to_dict().  After
    construction the enemy is scaled for the given act via scale_for_act().
    """
    skills = [Skill.from_dict(s) for s in template.get("skills", [])]
    pattern_data = template.get("pattern", {"skill_indices": [0]})
    pattern = AttackPattern(
        skill_indices=pattern_data.get("skill_indices", [0]),
        _round=0,   # Always start from the first skill in the pattern
    )
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
        pattern=pattern,
    )
    # Apply act scaling after construction so base values in the template remain unmodified
    enemy.scale_for_act(act)
    return enemy
