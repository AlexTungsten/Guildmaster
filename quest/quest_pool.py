"""
quest_pool.py — Quest pool definitions for each act of a Guildmaster run.

Defines:
  - ActPool: a container of easy/hard/elite quest lists for one act, with a
    weighted random draw method.
  - build_default_pools(): loads quests from data/quests/act{N}/*.json and
    builds the full set of Act 1–3 quest pools.

Draw weights: easy 60%, hard 30%, elite 10%.  Each draw returns a deep copy
of the chosen template so the pool is never mutated by the game.

To add a new quest, drop a JSON file into the appropriate data/quests/act{N}/
directory. It will be picked up automatically on next load.
"""

import copy
import json
import pathlib
import random
from dataclasses import dataclass
from typing import List, Dict

from quest.quest_model import Quest, QuestDifficulty

_QUESTS_DIR = pathlib.Path(__file__).parent.parent / "data" / "quests"


@dataclass
class ActPool:
    """Quest pool for one act, partitioned by difficulty tier."""
    act: int
    easy: List[Quest]
    hard: List[Quest]
    elite: List[Quest]

    def draw(self, rng: random.Random = None) -> Quest:
        """Weighted random draw: easy 60%, hard 30%, elite 10%."""
        _rng = rng if rng is not None else random
        roll = _rng.random()
        # Threshold-based selection mirrors a weighted choice without reweighting
        if roll < 0.60:
            pool = self.easy
        elif roll < 0.90:
            pool = self.hard
        else:
            pool = self.elite
        chosen = _rng.choice(pool)
        # Return a deep copy so callers can mutate quest fields (e.g., quest_id, spawned_at_tick)
        return copy.deepcopy(chosen)


def build_default_pools() -> Dict[int, "ActPool"]:
    """
    Load quest pools from data/quests/act{N}/*.json for acts 1–3.

    Each JSON file is deserialized via Quest.from_dict().  Files are sorted
    alphabetically within each act directory so load order is deterministic.
    Quests are routed to easy/hard/elite lists by their "difficulty" field.
    """
    pools: Dict[int, ActPool] = {}
    for act_num in (1, 2, 3):
        act_dir = _QUESTS_DIR / f"act{act_num}"
        easy: List[Quest] = []
        hard: List[Quest] = []
        elite: List[Quest] = []
        for json_file in sorted(act_dir.glob("*.json")):
            with open(json_file, encoding="utf-8") as f:
                data = json.load(f)
            quest = Quest.from_dict(data)
            if quest.difficulty == QuestDifficulty.EASY:
                easy.append(quest)
            elif quest.difficulty == QuestDifficulty.HARD:
                hard.append(quest)
            elif quest.difficulty == QuestDifficulty.ELITE:
                elite.append(quest)
        pools[act_num] = ActPool(act=act_num, easy=easy, hard=hard, elite=elite)
    return pools
