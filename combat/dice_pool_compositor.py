"""
dice_pool_compositor.py — Builds and rolls a hero's dice pool for combat.

The dice system works as follows:
  - Each hero starts with base_dice_count dice.
  - Exhaustion locks some of those dice: locked dice use locked_dice_sides
    (d4 by default, d6 with Ironhide) instead of base_dice_sides.
  - Locked dice always appear first in the pool.

Status-effect modifiers applied before / during rolling (in order):
  1. Upgrade / Downgrade — raise or lower all die tiers (including locked dice).
     Upgrade also improves locked dice tier by one step.
  2. Bleed — discard 1 random die from the pool (minimum 1 die remains).
  3. Roll each die, applying Advantage (keep best of 2) or Disadvantage
     (keep worst of 2) per die.
  4. Lucky Roll passive (Rogue) — reroll the single lowest kept result.
  5. Paralyze — after rolling, set N dice results to 1 (all stacks expire EOT).
"""

import random
from dataclasses import dataclass
from typing import List, Optional, Tuple

from hero.hero_entity import HeroEntity


@dataclass
class Die:
    """A single die with a fixed number of sides."""
    sides: int
    is_locked: bool = False

    def __repr__(self) -> str:
        return f"d{self.sides}{'[L]' if self.is_locked else ''}"


# ---------------------------------------------------------------------------
# Pool composition
# ---------------------------------------------------------------------------

def compose_pool(hero: HeroEntity) -> List[Die]:
    """
    Build the hero's full dice pool for one combat turn.

    Locked dice (is_locked=True) come first; normal dice follow.
    """
    locked_count = hero.locked_dice_count()
    normal_count = max(0, hero.base_dice_count - locked_count)

    pool: List[Die] = []
    for _ in range(locked_count):
        pool.append(Die(sides=hero.locked_dice_sides, is_locked=True))
    for _ in range(normal_count):
        pool.append(Die(sides=hero.base_dice_sides, is_locked=False))
    return pool


def apply_status_modifiers(
    pool: List[Die],
    status_effects: List,
    rng: random.Random,
) -> List[Die]:
    """
    Apply Upgrade / Downgrade tier changes and Bleed die-discard to the pool.

    Call this BEFORE rolling.  Returns a (possibly shorter or re-tiered) pool.
    """
    from combat.status_effects import StatusType, upgrade_die, downgrade_die, has_status

    result = list(pool)

    # Upgrade / Downgrade (mutually exclusive — cancellation is handled at application)
    if has_status(status_effects, StatusType.UPGRADE):
        result = [Die(sides=upgrade_die(d.sides), is_locked=d.is_locked) for d in result]
    elif has_status(status_effects, StatusType.DOWNGRADE):
        result = [Die(sides=downgrade_die(d.sides), is_locked=d.is_locked) for d in result]

    # Bleed: discard 1 random die; always keep at least 1
    if has_status(status_effects, StatusType.BLEED):
        if len(result) > 1:
            idx = rng.randrange(len(result))
            result = [d for i, d in enumerate(result) if i != idx]

    return result


# ---------------------------------------------------------------------------
# Rolling
# ---------------------------------------------------------------------------

def roll_pool(
    pool: List[Die],
    status_effects: List,
    rng: random.Random,
    has_lucky_roll: bool = False,
) -> List[int]:
    """
    Roll every die in the pool and return the results as a list of ints.

    Applies in order:
      1. Advantage (keep best of 2 rolls per die) or Disadvantage (keep worst).
         Advantage resolves before Lucky Roll per the turn-order spec.
      2. Lucky Roll passive — reroll the single lowest result (keep new value).
      3. Paralyze — set N dice to 1 after rolling (stacks determine N).

    Parameters
    ----------
    pool            : Dice to roll (after apply_status_modifiers).
    status_effects  : Active effects on the rolling hero / enemy.
    rng             : Random source.
    has_lucky_roll  : True when the hero has the Lucky Roll passive (Rogue).
    """
    from combat.status_effects import StatusType, has_status, get_status

    has_adv = has_status(status_effects, StatusType.ADVANTAGE)
    has_dis = has_status(status_effects, StatusType.DISADVANTAGE)

    # Step 1 — roll with Advantage / Disadvantage
    results: List[int] = []
    for die in pool:
        r1 = rng.randint(1, die.sides)
        if has_adv:
            r2 = rng.randint(1, die.sides)
            results.append(max(r1, r2))
        elif has_dis:
            r2 = rng.randint(1, die.sides)
            results.append(min(r1, r2))
        else:
            results.append(r1)

    # Step 2 — Lucky Roll: reroll the single lowest kept result
    if has_lucky_roll and results:
        min_val = min(results)
        min_idx = results.index(min_val)
        results[min_idx] = rng.randint(1, pool[min_idx].sides)

    # Step 3 — Paralyze: set N dice to 1 (first N in the list)
    paralyze = get_status(status_effects, StatusType.PARALYZE)
    if paralyze:
        count = min(paralyze.stacks, len(results))
        for i in range(count):
            results[i] = 1

    return results
