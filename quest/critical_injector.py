"""
critical_injector.py — Scheduled injection of critical story quests.

Critical quests are pre-authored, time-gated quests that must appear at
specific tick milestones (e.g., "Boss approaches" warning at tick 200 of an
act).  Unlike normal quests, they are injected deterministically rather than
drawn from the random pool.

If a critical quest expires without being completed its Consequence is applied
(e.g., boss gains a buff), raising the stakes for the final encounter.
"""

from dataclasses import dataclass, field
from typing import List, Optional, Set

from quest.quest_model import Quest, Consequence, QuestType, QuestDifficulty, Reward
from typing import Optional


@dataclass
class CriticalWindow:
    """A single scheduled injection: fire quest at inject_at_tick."""
    inject_at_tick: int
    quest: Quest


class CriticalInjector:
    def __init__(self, windows: List[CriticalWindow]):
        # Sort windows by tick so get_due() can iterate in chronological order
        self._windows: List[CriticalWindow] = sorted(windows, key=lambda w: w.inject_at_tick)
        # Track which window indices have already been injected to prevent double-firing
        self._injected: Set[int] = set()

    def get_due(self, current_tick: int) -> List[Quest]:
        """Return all quests whose inject_at_tick <= current_tick that haven't been injected yet."""
        due: List[Quest] = []
        for i, window in enumerate(self._windows):
            if window.inject_at_tick <= current_tick and i not in self._injected:
                self._injected.add(i)   # Mark as injected so it won't fire again
                due.append(window.quest)
        return due

    def reset(self) -> None:
        """Clear injected tracking so quests can fire again (for new act)."""
        self._injected.clear()


def build_critical_injector(boss_id: str, act_start_tick: int) -> "CriticalInjector":
    """
    Build a CriticalInjector with boss-specific critical quest windows.

    Each boss injects 2 windows during the act.  The quests in each window
    carry the enemy composition and boss_context so QuestExecutor can resolve
    them correctly and write results back to ActRunState.

    Baron Midas   — 2x Bandit Captain + 1x Bandit Leader; gold steal feeds Midas HP.
    Cursed Knight — Cursed Knight flee-timer encounter; damage reduces boss HP.
    Kobold King   — 1x Kobold + 2x Kobold Tinkerer; completions reduce guard quality.
    """
    _COMPOSITIONS = {
        "baron_midas":   ["bandit_captain", "bandit_captain", "bandit_leader"],
        "cursed_knight": ["cursed_knight"],
        "kobold_king":   ["kobold", "kobold_tinkerer", "kobold_tinkerer"],
    }
    _TITLES = {
        "baron_midas":   ("Bandit Gold Shipment", "Final Bandit Push"),
        "cursed_knight": ("Cursed Knight Patrol", "Cursed Knight Resurgence"),
        "kobold_king":   ("Kobold Advance Party", "Kobold Tinkerer Ambush"),
    }
    _DESCRIPTIONS = {
        "baron_midas":   (
            "A heavily guarded bandit convoy is moving through the region. Stop them before the gold reaches Midas.",
            "The bandits are making one last push to deliver their haul. Intercept them now.",
        ),
        "cursed_knight": (
            "Reports of a cursed knight terrorizing nearby settlements. He never stays long — act fast.",
            "The cursed knight has been spotted again. Engage before he retreats.",
        ),
        "kobold_king":   (
            "A kobold scouting party is casing the roads ahead. Drive them off.",
            "Kobold tinkerers are setting traps near the king's hideout. Dismantle them.",
        ),
    }
    _CONSEQUENCES = {
        "baron_midas":   ("baron_midas_unchecked", "Midas accumulates extra gold — boss gains +50 HP"),
        "cursed_knight": ("cursed_knight_healed",  "The knight recovers — boss starts at full HP"),
        "kobold_king":   ("kobold_reinforced",      "Guards are reinforced — boss starts with stronger guards"),
    }

    composition = _COMPOSITIONS.get(boss_id, [])
    titles = _TITLES.get(boss_id, ("Critical Quest", "Critical Quest"))
    descs = _DESCRIPTIONS.get(boss_id, ("", ""))
    cons_types = _CONSEQUENCES.get(boss_id, ("boss_buff", "boss_buff"))

    windows = []
    for i, (title, desc, cons_type) in enumerate(zip(titles, descs, cons_types)):
        quest_id = f"critical_{boss_id}_{act_start_tick}_{i}"
        windows.append(CriticalWindow(
            inject_at_tick=act_start_tick + 200 * (i + 1),
            quest=Quest(
                quest_id=quest_id,
                title=title,
                description=desc,
                quest_type=QuestType.COMBAT,
                difficulty=QuestDifficulty.ELITE,
                is_critical=True,
                required_heroes=2,
                travel_time=40,
                resolution_time=80,
                base_exhaustion=20.0,
                reward=Reward(gold=150, xp=200),
                consequence=Consequence(type=cons_type, data={"boss_id": boss_id}),
                enemy_composition=list(composition),
                boss_context=boss_id,
            ),
        ))

    return CriticalInjector(windows=windows)


def build_default_injector(act_start_tick: int) -> "CriticalInjector":
    """Return a CriticalInjector with 2 example critical windows per act."""
    # Window 1: early warning at act_start + 200 ticks
    window1 = CriticalWindow(
        inject_at_tick=act_start_tick + 200,
        quest=Quest(
            quest_id=f"critical_boss_warning_{act_start_tick}",
            title="Boss Approaches",
            description="A powerful enemy is gathering strength. Defeat it before it becomes unstoppable.",
            quest_type=QuestType.COMBAT,
            difficulty=QuestDifficulty.ELITE,
            is_critical=True,
            required_heroes=2,
            travel_time=40,
            resolution_time=80,
            base_exhaustion=20.0,
            reward=Reward(gold=100, xp=150),
            # If this quest expires, the boss gains a buff worth +10 power
            consequence=Consequence(type="boss_buff", data={"buff_amount": 10}),
        ),
    )
    # Window 2: final stand at act_start + 400 ticks — last chance to weaken the boss
    window2 = CriticalWindow(
        inject_at_tick=act_start_tick + 400,
        quest=Quest(
            quest_id=f"critical_final_stand_{act_start_tick}",
            title="Final Stand",
            description="The boss is making its final move. Stop it now or face dire consequences.",
            quest_type=QuestType.COMBAT,
            difficulty=QuestDifficulty.ELITE,
            is_critical=True,
            required_heroes=3,
            travel_time=50,
            resolution_time=100,
            base_exhaustion=30.0,
            reward=Reward(gold=200, xp=300),
            # If this quest expires, the boss gains a larger buff worth +25 power
            consequence=Consequence(type="boss_buff", data={"buff_amount": 25}),
        ),
    )
    return CriticalInjector(windows=[window1, window2])
