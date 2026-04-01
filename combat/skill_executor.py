"""
skill_executor.py — Converts dice assignments into concrete skill outcomes.

Takes the SkillAssignment objects produced by the dice assignment engine and
computes the final SkillResult that the combat engine will act on.

Normal skills:  effectiveness = sum(dice) + stat_modifier
Eviscerate:     hit_count = sum(dice); per_hit_damage = 2 + DEX_mod
                (base — combat engine upgrades to 4 + DEX_mod when target has a debuff)
Heal:           effectiveness = sum(dice) + CHA_mod  (applied to lowest-HP ally)
"""

from dataclasses import dataclass, field
from typing import List, Optional

from hero.hero_entity import HeroEntity, Skill, Stat
from combat.dice_assignment_engine import SkillAssignment


@dataclass
class SkillResult:
    """Resolved outcome of one skill use in a combat round."""
    skill: Skill
    effectiveness: int   # primary power value (damage, heal amount, or hit count for Eviscerate)
    effect_type: str     # passed through from skill.effect_type
    hits_all: bool       # True when effect_type == "aoe"
    special: Optional[str] = None

    # Multi-hit fields (Eviscerate only)
    hit_count: int = 1          # number of individual hits
    per_hit_damage: int = 0     # base damage per hit (0 = not multi-hit; use effectiveness directly)


def execute_skill(hero: HeroEntity, assignment: SkillAssignment) -> Optional[SkillResult]:
    """
    Compute the result of one skill assignment for a hero.

    Returns None when the assignment has no dice (skill was not activated).
    """
    if not assignment.is_active:
        return None

    skill = assignment.skill
    dice_sum = sum(assignment.assigned_dice)
    special = skill.special
    effect_type = skill.effect_type

    # --- Eviscerate: multi-hit ---
    if special == "eviscerate":
        hit_count = dice_sum                                     # sum of 2 dice = number of hits
        per_hit = 2 + hero.effective_modifier(Stat.DEX)         # base damage per hit
        return SkillResult(
            skill=skill,
            effectiveness=hit_count,                            # used by engine to know hit count
            effect_type=effect_type,
            hits_all=False,
            special=special,
            hit_count=hit_count,
            per_hit_damage=max(1, per_hit),                     # floor at 1
        )

    # --- Standard effectiveness = sum + stat modifier ---
    effectiveness = dice_sum + hero.effective_modifier(skill.associated_stat)

    # Blood Cleave bonus
    if special == "blood_cleave":
        effectiveness += 5

    return SkillResult(
        skill=skill,
        effectiveness=effectiveness,
        effect_type=effect_type,
        hits_all=(effect_type == "aoe"),
        special=special,
        hit_count=1,
        per_hit_damage=0,
    )


def execute_all_skills(
    hero: HeroEntity, assignments: List[SkillAssignment]
) -> List[SkillResult]:
    """Execute every active skill assignment and return the non-None results."""
    results = []
    for assignment in assignments:
        result = execute_skill(hero, assignment)
        if result is not None:
            results.append(result)
    return results
