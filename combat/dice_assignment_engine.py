"""
dice_assignment_engine.py — Distributes rolled dice across a hero's skills.

After the dice pool is rolled, this engine decides which die values go to
which skill slot.  The assignment strategy is driven by the hero's
behavior_profile:

  focus    — Fill skill 0 completely before moving on to later skills.
  balanced — Round-robin across all skills with remaining capacity.
  greedy   — Sort dice descending; always fill the skill with the most
             remaining capacity first.
  dump     — Sort dice ascending (weakest first); fill from the last skill
             backward (sacrifice later skills to protect the primary).

Locked dice (d4s from exhaustion) are always consumed first, in skill order
(0, 1, 2), before any normal dice are distributed.
"""

from dataclasses import dataclass, field
from typing import List, Optional

from hero.hero_entity import HeroEntity, Skill


@dataclass
class SkillAssignment:
    """Records which die values were assigned to a particular skill."""
    skill: Skill
    assigned_dice: List[int] = field(default_factory=list)

    @property
    def is_active(self) -> bool:
        """True when at least one die has been assigned to this skill."""
        return len(self.assigned_dice) > 0

    @property
    def effectiveness(self) -> int:
        """Raw effectiveness before the stat modifier is added: sum of all assigned dice."""
        return sum(self.assigned_dice)


def assign_dice(
    hero: HeroEntity,
    rolled_locked: List[int],
    rolled_normal: List[int],
) -> List[SkillAssignment]:
    """
    Assign rolled die values to the hero's skill slots and return the results.

    Parameters
    ----------
    hero           : The hero whose skills and behavior_profile govern assignment.
    rolled_locked  : Results of the locked (d4) dice in pool order.
    rolled_normal  : Results of the normal (d10) dice in pool order.

    Returns a list containing one SkillAssignment per non-None skill slot.
    """
    # Build one SkillAssignment per non-None skill; None slots produce a None placeholder
    assignments: List[Optional[SkillAssignment]] = []
    for skill in hero.skills:
        if skill is not None:
            assignments.append(SkillAssignment(skill=skill))
        else:
            assignments.append(None)

    # Track remaining capacity (dice_slots) for each skill index
    remaining_slots = []
    for i, skill in enumerate(hero.skills):
        if skill is not None:
            remaining_slots.append(skill.dice_slots)
        else:
            remaining_slots.append(0)

    # --- Phase 1: Assign locked dice in skill order (skill 0, 1, 2) ---
    # Locked dice are distributed sequentially so the primary skill bears the exhaustion burden first
    locked_pool = list(rolled_locked)
    for i, assignment in enumerate(assignments):
        if assignment is None:
            continue
        while locked_pool and remaining_slots[i] > 0:
            die_val = locked_pool.pop(0)
            assignment.assigned_dice.append(die_val)
            remaining_slots[i] -= 1

    # --- Phase 2: Assign normal dice per behavior profile ---
    normal_pool = list(rolled_normal)
    profile = hero.behavior_profile

    def active_indices():
        """Return indices of non-None skills that still have capacity."""
        return [i for i, a in enumerate(assignments) if a is not None and remaining_slots[i] > 0]

    if profile == "focus":
        # Fill each skill completely before moving to the next, prioritizing skill 0
        for i in range(len(assignments)):
            if assignments[i] is None:
                continue
            while normal_pool and remaining_slots[i] > 0:
                die_val = normal_pool.pop(0)
                assignments[i].assigned_dice.append(die_val)
                remaining_slots[i] -= 1
            if not normal_pool:
                break

    elif profile in ("balanced", "all_around"):
        # Distribute one die at a time to each skill in round-robin fashion
        while normal_pool:
            indices = active_indices()
            if not indices:
                break
            for i in indices:
                if not normal_pool:
                    break
                die_val = normal_pool.pop(0)
                assignments[i].assigned_dice.append(die_val)
                remaining_slots[i] -= 1

    elif profile == "greedy":
        # Best die values go to the skill that has the most remaining slots
        normal_pool.sort(reverse=True)   # Highest dice first
        while normal_pool:
            indices = active_indices()
            if not indices:
                break
            # Choose the skill with the most remaining capacity; ties broken by lowest index
            best_i = max(indices, key=lambda i: remaining_slots[i])
            die_val = normal_pool.pop(0)
            assignments[best_i].assigned_dice.append(die_val)
            remaining_slots[best_i] -= 1

    elif profile == "dump":
        # Weakest dice go to the last skill first; primary skill keeps the best dice
        normal_pool.sort(reverse=False)   # Lowest dice first
        while normal_pool:
            # Fill from the last skill backward
            indices = list(reversed(active_indices()))
            if not indices:
                break
            for i in indices:
                if not normal_pool:
                    break
                die_val = normal_pool.pop(0)
                assignments[i].assigned_dice.append(die_val)
                remaining_slots[i] -= 1

    # Return only the non-None assignments (skip empty skill slots)
    return [a for a in assignments if a is not None]
