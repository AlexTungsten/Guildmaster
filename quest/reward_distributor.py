"""
reward_distributor.py — Applies quest rewards and exhaustion to the hero party.

After a quest is completed successfully, every participating hero receives:
  - Full quest XP (each hero gets the complete amount, not a split share).
  - Exhaustion equal to base_exhaustion + (damage_taken * exhaustion_damage_scale).

Gold is not distributed here — the caller (quest pipeline / economy controller)
handles gold via the GoldLedger.  Only the gold amount is returned so the
caller knows how much to credit.
"""

from dataclasses import dataclass, field
from typing import List, Dict

from hero.hero_entity import HeroEntity
from quest.quest_model import Quest, Reward


@dataclass
class DistributionResult:
    """Summary of what was awarded and applied to heroes after a successful quest."""
    gold_earned: int                        # Amount the guild's ledger should be credited
    heroes_leveled_up: List[str]            # hero_ids that gained a level
    exhaustion_applied: Dict[str, float]    # hero_id -> total exhaustion added


def distribute_rewards(
    quest: Quest,
    heroes: List[HeroEntity],
    damage_taken: Dict[str, int],
    exhaustion_damage_scale: float = 0.1,
) -> DistributionResult:
    """
    Distribute XP, apply exhaustion, and return DistributionResult.

    Parameters
    ----------
    quest                   : The completed quest (provides XP, gold, base_exhaustion).
    heroes                  : Heroes to receive rewards.
    damage_taken            : hero_id -> HP lost during combat (used to scale exhaustion).
    exhaustion_damage_scale : Multiplier converting damage taken into extra exhaustion.
    """
    heroes_leveled_up: List[str] = []
    exhaustion_applied: Dict[str, float] = {}

    for hero in heroes:
        # Every hero gets full quest XP — there is no party-split mechanic
        leveled_up = hero.gain_xp(quest.reward.xp)
        if leveled_up:
            heroes_leveled_up.append(hero.hero_id)

        # Base exhaustion is inherent to the quest difficulty/length
        total_exhaustion = quest.base_exhaustion

        # Heroes who took more damage accumulate extra exhaustion (injury fatigue)
        hero_damage = damage_taken.get(hero.hero_id, 0)
        total_exhaustion += hero_damage * exhaustion_damage_scale

        hero.add_exhaustion(total_exhaustion)
        exhaustion_applied[hero.hero_id] = total_exhaustion

    return DistributionResult(
        gold_earned=quest.reward.gold,    # Caller must credit this to the ledger
        heroes_leveled_up=heroes_leveled_up,
        exhaustion_applied=exhaustion_applied,
    )
