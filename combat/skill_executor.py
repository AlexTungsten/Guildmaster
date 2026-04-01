"""
skill_executor.py — Converts dice assignments into concrete skill outcomes.

Takes the SkillAssignment objects produced by the dice assignment engine and
computes final effectiveness (dice sum + stat modifier) and the effect type
that the combat engine will apply to targets.

Keeping this as a separate, pure-function module makes it straightforward to
test skill resolution without running a full combat simulation.
"""

from dataclasses import dataclass, field
from typing import List, Optional

from hero.hero_entity import HeroEntity, Skill, Stat
from combat.dice_assignment_engine import SkillAssignment


@dataclass
class SkillResult:
    """Resolved outcome of one skill use in a combat round."""
    skill: Skill
    effectiveness: int   # Final power value: dice sum + stat modifier
    effect_type: str     # Passed through from skill.effect_type (e.g. "damage", "heal", "aoe")
    hits_all: bool       # True when effect_type == "aoe" (hits every living enemy)


def execute_skill(hero: HeroEntity, assignment: SkillAssignment) -> Optional[SkillResult]:
    """
    Compute the result of one skill assignment for a hero.

    Returns None when the assignment has no dice (skill was not activated this
    round, e.g., locked dice filled all slots with low values and no normal
    dice remained).

    Effectiveness = sum(assigned_dice) + hero.effective_modifier(associated_stat)
    The stat modifier accounts for both the hero's base stat and any
    exhaustion penalties on that stat.
    """
    if not assignment.is_active:
        return None  # No dice were assigned; skill does not fire

    effectiveness = sum(assignment.assigned_dice) + hero.effective_modifier(
        assignment.skill.associated_stat
    )
    effect_type = assignment.skill.effect_type
    # AOE skills hit all living enemies simultaneously
    hits_all = effect_type == "aoe"

    return SkillResult(
        skill=assignment.skill,
        effectiveness=effectiveness,
        effect_type=effect_type,
        hits_all=hits_all,
    )


def execute_all_skills(
    hero: HeroEntity, assignments: List[SkillAssignment]
) -> List[SkillResult]:
    """
    Execute every skill assignment for a hero and return the non-None results.

    Skills that produced no assignment (inactive) are silently skipped.
    """
    results = []
    for assignment in assignments:
        result = execute_skill(hero, assignment)
        if result is not None:
            results.append(result)
    return results
