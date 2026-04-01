"""
stat_check_resolver.py — Resolves skill/ability checks for non-combat quests.

Stat-check quests present one or more difficulty checks (DC = Difficulty
Class) against specific ability scores.  For each check, every hero in the
party rolls a d20 and adds their effective modifier for that stat.  The check
passes as long as at least one hero in the party beats the DC — simulating the
"any party member can attempt it" rule.

StatCheckOutcome.all_passed is True when every individual check was passed by
at least one hero.  any_passed is True when at least one check was passed
(used by the quest pipeline to determine quest success).
"""

import random
from dataclasses import dataclass, field
from typing import List, Dict

from hero.hero_entity import HeroEntity, Stat


@dataclass
class CheckResult:
    """Result of one hero's attempt at a single stat check."""
    stat: str       # Canonical stat value string (e.g. "intelligence")
    dc: int         # The target number needed to pass
    hero_id: str
    roll: int       # Raw d20 result (1–20)
    modifier: int   # Hero's effective_modifier for this stat
    total: int      # roll + modifier
    passed: bool    # True when total >= dc


@dataclass
class StatCheckOutcome:
    """Aggregate result across all checks and all heroes."""
    checks: List[CheckResult]   # Every individual roll for audit/display
    all_passed: bool            # True when every check was passed by at least one hero
    any_passed: bool            # True when at least one check was passed


def resolve_stat_check(
    heroes: List[HeroEntity],
    checks: List[dict],
    rng: random.Random = None,
) -> StatCheckOutcome:
    """Resolve stat checks for each check dict. Only ONE hero needs to pass per check."""
    _rng = rng if rng is not None else random
    all_results: List[CheckResult] = []
    checks_passed: List[bool] = []

    for check in checks:
        stat_raw = check["stat"]
        dc = check["dc"]

        # Normalize the stat to a Stat enum regardless of whether it was passed
        # as a Stat enum instance, a value string, or a name string (e.g. "STR")
        if isinstance(stat_raw, Stat):
            stat_enum = stat_raw
            stat_str = stat_raw.value
        else:
            stat_str = str(stat_raw)
            try:
                # First attempt: match by value (e.g. "intelligence")
                stat_enum = Stat(stat_str)
            except ValueError:
                # Fallback: match by name (e.g. "INT" or "INTELLIGENCE")
                stat_enum = Stat[stat_str.upper()]
                stat_str = stat_enum.value

        check_passed = False
        for hero in heroes:
            roll = _rng.randint(1, 20)       # d20 roll
            modifier = hero.effective_modifier(stat_enum)  # Includes exhaustion penalty
            total = roll + modifier
            passed = total >= dc
            if passed:
                check_passed = True   # At least one hero beat this check

            all_results.append(CheckResult(
                stat=stat_str,
                dc=dc,
                hero_id=hero.hero_id,
                roll=roll,
                modifier=modifier,
                total=total,
                passed=passed,
            ))

        checks_passed.append(check_passed)

    # all_passed: every check was beaten; any_passed: at least one check succeeded
    all_passed = all(checks_passed) if checks_passed else True
    any_passed = any(checks_passed) if checks_passed else False

    return StatCheckOutcome(
        checks=all_results,
        all_passed=all_passed,
        any_passed=any_passed,
    )
