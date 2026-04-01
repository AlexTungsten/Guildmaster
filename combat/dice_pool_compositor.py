"""
dice_pool_compositor.py — Builds and rolls a hero's dice pool for combat.

The dice system works as follows:
  - Each hero starts with base_dice_count dice (default 4).
  - Exhaustion locks some of those dice: locked dice are d4s (range 1–4)
    instead of the normal d10s (range 1–10).
  - Locked dice always appear first in the pool so the assignment engine can
    consume them before the higher-value normal dice.

This module is intentionally stateless: compose_pool() and roll_pool() take
inputs and return new objects, making them easy to unit-test or use in
pre-simulation without side effects.
"""

import random
from dataclasses import dataclass, field
from typing import List

from hero.hero_entity import HeroEntity


@dataclass
class Die:
    """A single die with a fixed number of sides."""
    sides: int
    is_locked: bool = False   # True when this die is a d4 due to exhaustion

    def roll(self) -> int:
        """Return a uniformly random result in [1, sides]."""
        return random.randint(1, self.sides)

    def __repr__(self) -> str:
        locked_str = "[LOCKED]" if self.is_locked else ""
        return f"d{self.sides}{locked_str}"


def compose_pool(hero: HeroEntity) -> List[Die]:
    """
    Build the hero's full dice pool for one combat turn.

    Locked dice (d4, is_locked=True) come first; normal dice (d10) follow.
    If exhaustion has locked more dice than the hero has in their pool,
    normal_count is clamped to 0 so we never produce a negative count.
    """
    locked_count = hero.locked_dice_count()
    normal_count = hero.base_dice_count - locked_count
    if normal_count < 0:
        normal_count = 0   # Full exhaustion can consume the entire pool

    pool: List[Die] = []
    # Add locked dice first — they will be assigned to skills in priority order
    for _ in range(locked_count):
        pool.append(Die(sides=4, is_locked=True))
    # Add normal d10 dice after the locked dice
    for _ in range(normal_count):
        pool.append(Die(sides=10, is_locked=False))
    return pool


def roll_pool(pool: List[Die]) -> List[int]:
    """
    Roll every die in the pool and return the results as a plain list of ints.

    Order is preserved: results[i] corresponds to pool[i].
    """
    return [die.roll() for die in pool]
