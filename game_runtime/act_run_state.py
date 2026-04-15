"""
act_run_state.py — Per-act runtime state shared across quests and the boss fight.

ActRunState is the single place where boss-specific progression data is
accumulated across an act.  It is created when the act starts (boss_id is
randomly selected at that point) and consumed when the boss fight loads.

Fields
------
act            : int — act number (1, 2, 3)
boss_id        : str — randomly selected boss for this act
                       ("baron_midas", "cursed_knight", "kobold_king")

midas_gold     : int — total gold stolen by bandits during the act;
                       each hit by a gold_steal enemy adds 5 gold.
                       Fed to load_boss("baron_midas", gold_stolen=midas_gold).

cursed_knight_damage_dealt : int — cumulative HP damage dealt to the Cursed
                       Knight in critical quest encounters.
                       Fed to load_boss("cursed_knight", damage_dealt=N)
                       to reduce starting HP and bloodlust.

critical_quests_completed  : int — number of Kobold King critical quests
                       completed successfully.
                       Fed to load_kobold_king_encounter(critical_quests_completed=N)
                       to determine guard composition and ambush count.
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from typing import List


# The three Act 1 boss options
ACT1_BOSS_IDS: List[str] = ["baron_midas", "cursed_knight", "kobold_king"]


@dataclass
class ActRunState:
    """Per-act accumulator for boss-fight initialization data."""

    act: int = 1
    boss_id: str = "baron_midas"

    # Baron Midas: gold stolen by bandits during the act
    midas_gold: int = 0

    # Cursed Knight: HP damage dealt during critical quest encounters
    cursed_knight_damage_dealt: int = 0

    # Kobold King: number of critical quests completed
    critical_quests_completed: int = 0

    def record_gold_stolen(self, amount: int) -> None:
        """Accumulate gold stolen — called per-hit from QuestExecutor."""
        self.midas_gold += amount

    def record_cursed_knight_damage(self, amount: int) -> None:
        """Add HP damage dealt to the Cursed Knight encounter."""
        self.cursed_knight_damage_dealt += amount

    def record_critical_quest_completed(self) -> None:
        """Increment the Kobold King critical quest counter."""
        self.critical_quests_completed += 1

    def to_dict(self) -> dict:
        return {
            "act": self.act,
            "boss_id": self.boss_id,
            "midas_gold": self.midas_gold,
            "cursed_knight_damage_dealt": self.cursed_knight_damage_dealt,
            "critical_quests_completed": self.critical_quests_completed,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "ActRunState":
        return cls(
            act=data.get("act", 1),
            boss_id=data.get("boss_id", "baron_midas"),
            midas_gold=data.get("midas_gold", 0),
            cursed_knight_damage_dealt=data.get("cursed_knight_damage_dealt", 0),
            critical_quests_completed=data.get("critical_quests_completed", 0),
        )


def select_act_boss(act: int, rng: random.Random = None) -> str:
    """Randomly select a boss ID for the given act."""
    _rng = rng if rng is not None else random.Random()
    if act == 1:
        return _rng.choice(ACT1_BOSS_IDS)
    # Future acts extend here
    return "baron_midas"


def new_act_run_state(act: int, rng: random.Random = None) -> ActRunState:
    """Create a fresh ActRunState with a randomly selected boss."""
    boss_id = select_act_boss(act, rng)
    return ActRunState(act=act, boss_id=boss_id)
