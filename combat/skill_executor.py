"""
skill_executor.py — Converts dice assignments into concrete skill outcomes.

Takes the SkillAssignment objects produced by the dice assignment engine and
computes the final SkillResult that the combat engine will act on.

Standard skills:  effectiveness = sum(dice) + stat_modifier
Eviscerate:       hit_count = sum(dice); per_hit_damage = 2 + DEX_mod
Quick Jab:        effectiveness = len(assigned_dice) * DEX_mod
Charged spells:   no effectiveness here — combat engine handles charge firing
"""

from dataclasses import dataclass, field
from typing import List, Optional

from hero.hero_entity import HeroEntity, Skill, Stat
from combat.dice_assignment_engine import SkillAssignment


@dataclass
class SkillResult:
    """Resolved outcome of one skill use in a combat round."""
    skill: Skill
    effectiveness: int   # primary power value (damage, heal amount, hit count for Eviscerate)
    effect_type: str     # passed through from skill.effect_type
    hits_all: bool       # True when the effect hits all enemies / all allies

    special: Optional[str] = None

    # Multi-hit fields (Eviscerate only)
    hit_count: int = 1          # number of individual hits
    per_hit_damage: int = 0     # base damage per hit (0 = not multi-hit; use effectiveness directly)

    # Extra context for Blade Dance (set by combat engine after all assignments resolved)
    dice_spent_elsewhere: int = 0


def execute_skill(hero: HeroEntity, assignment: SkillAssignment) -> Optional["SkillResult"]:
    """
    Compute the result of one skill assignment for a hero.

    Returns None when:
      - The assignment has no dice (skill was not activated this turn).
      - The skill is charge-based (charge_cost > 0); the combat engine handles
        charge accumulation and firing separately.
    """
    if not assignment.is_active:
        return None

    skill = assignment.skill
    special = skill.special
    effect_type = skill.effect_type

    # Charge-based skills are handled entirely in the combat engine
    if skill.charge_cost > 0:
        return None

    dice_sum = sum(assignment.assigned_dice)
    dice_count = len(assignment.assigned_dice)

    # --- Eviscerate: multi-hit (hit count = sum of 2 dice, flat 1 dmg per hit) ---
    if special == "eviscerate":
        hit_count = dice_sum
        return SkillResult(
            skill=skill,
            effectiveness=hit_count,
            effect_type=effect_type,
            hits_all=False,
            special=special,
            hit_count=hit_count,
            per_hit_damage=1,
        )

    # --- Quick Jab: damage = dice_count * DEX_modifier ---
    if special == "quick_jab":
        dex_mod = hero.effective_modifier(Stat.DEX)
        effectiveness = max(0, dice_count * dex_mod)
        return SkillResult(
            skill=skill,
            effectiveness=effectiveness,
            effect_type=effect_type,
            hits_all=False,
            special=special,
        )

    # --- Blade Dance: effectiveness resolved later in combat engine ---
    # We emit the result with 0 effectiveness as a placeholder; the combat
    # engine sets dice_spent_elsewhere and computes final damage.
    if special == "blade_dance":
        dex_mod = hero.effective_modifier(Stat.DEX)
        return SkillResult(
            skill=skill,
            effectiveness=0,       # filled in by combat engine
            effect_type=effect_type,
            hits_all=False,
            special=special,
            dice_spent_elsewhere=0,  # filled in by combat engine
        )

    # --- Standard effectiveness = sum + stat modifier ---
    effectiveness = dice_sum + hero.effective_modifier(skill.associated_stat)

    # Blood Cleave bonus flat damage
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
