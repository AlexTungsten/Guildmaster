"""
quest_pool.py — Quest pool definitions for each act of a Guildmaster run.

Defines:
  - ActPool: a container of easy/hard/elite quest lists for one act, with a
    weighted random draw method.
  - build_default_pools(): constructs the full set of Act 1–3 quest pools
    with pre-authored quest templates.

Draw weights: easy 60%, hard 30%, elite 10%.  Each draw returns a deep copy
of the chosen template so the pool is never mutated by the game.
"""

import copy
import random
from dataclasses import dataclass, field
from typing import List, Dict

from quest.quest_model import Quest, QuestDifficulty, QuestType, Reward


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
    """Build placeholder quest pools for acts 1, 2, and 3."""
    # Act 1 quests — lower exhaustion, modest rewards, mostly single-hero
    act1_easy = [
        Quest(
            quest_id="a1_e1",
            title="Goblin Ambush",
            description="A group of goblins has been spotted near the trade road.",
            quest_type=QuestType.COMBAT,
            difficulty=QuestDifficulty.EASY,
            travel_time=20,
            resolution_time=40,
            base_exhaustion=8.0,
            reward=Reward(gold=20, xp=30),
        ),
        Quest(
            quest_id="a1_e2",
            title="Missing Shipment",
            description="A merchant's goods have gone missing. Investigate.",
            quest_type=QuestType.STAT_CHECK,
            difficulty=QuestDifficulty.EASY,
            travel_time=15,
            resolution_time=30,
            base_exhaustion=6.0,
            reward=Reward(gold=15, xp=25),
            stat_checks=[{"stat": "intelligence", "dc": 10}],
        ),
        Quest(
            quest_id="a1_e3",
            title="Rat Infestation",
            description="The cellar beneath the inn is crawling with giant rats.",
            quest_type=QuestType.COMBAT,
            difficulty=QuestDifficulty.EASY,
            travel_time=10,
            resolution_time=30,
            base_exhaustion=5.0,
            reward=Reward(gold=10, xp=20),
        ),
    ]
    act1_hard = [
        Quest(
            quest_id="a1_h1",
            title="Bandit Leader",
            description="A notorious bandit leader has taken control of a village.",
            quest_type=QuestType.COMBAT,
            difficulty=QuestDifficulty.HARD,
            required_heroes=2,
            travel_time=30,
            resolution_time=60,
            base_exhaustion=15.0,
            reward=Reward(gold=50, xp=75),
        ),
        Quest(
            quest_id="a1_h2",
            title="Ancient Riddle",
            description="A sealed vault requires solving an ancient puzzle.",
            quest_type=QuestType.STAT_CHECK,
            difficulty=QuestDifficulty.HARD,
            travel_time=25,
            resolution_time=50,
            base_exhaustion=12.0,
            reward=Reward(gold=40, xp=60),
            stat_checks=[{"stat": "intelligence", "dc": 14}, {"stat": "dexterity", "dc": 12}],
        ),
    ]
    act1_elite = [
        Quest(
            quest_id="a1_el1",
            title="Troll Bridge",
            description="A massive troll has claimed the only bridge into town.",
            quest_type=QuestType.COMBAT,
            difficulty=QuestDifficulty.ELITE,
            required_heroes=3,
            travel_time=40,
            resolution_time=80,
            base_exhaustion=25.0,
            reward=Reward(gold=120, xp=180),
        ),
    ]

    # Act 2 quests — higher exhaustion, better rewards
    act2_easy = [
        Quest(
            quest_id="a2_e1",
            title="Shadow Cultists",
            description="Cultists have been performing rituals in the old chapel.",
            quest_type=QuestType.COMBAT,
            difficulty=QuestDifficulty.EASY,
            travel_time=25,
            resolution_time=45,
            base_exhaustion=12.0,
            reward=Reward(gold=35, xp=50),
        ),
        Quest(
            quest_id="a2_e2",
            title="Cursed Artifact",
            description="A strange artifact is causing the townsfolk to act strangely.",
            quest_type=QuestType.STAT_CHECK,
            difficulty=QuestDifficulty.EASY,
            travel_time=20,
            resolution_time=35,
            base_exhaustion=10.0,
            reward=Reward(gold=30, xp=45),
            stat_checks=[{"stat": "intelligence", "dc": 12}],
        ),
        Quest(
            quest_id="a2_e3",
            title="Undead Patrol",
            description="Undead creatures have been spotted patrolling the graveyard.",
            quest_type=QuestType.COMBAT,
            difficulty=QuestDifficulty.EASY,
            travel_time=20,
            resolution_time=40,
            base_exhaustion=11.0,
            reward=Reward(gold=32, xp=48),
        ),
    ]
    act2_hard = [
        Quest(
            quest_id="a2_h1",
            title="Necromancer's Lair",
            description="A necromancer is raising an army of undead from the old catacombs.",
            quest_type=QuestType.COMBAT,
            difficulty=QuestDifficulty.HARD,
            required_heroes=2,
            travel_time=35,
            resolution_time=70,
            base_exhaustion=20.0,
            reward=Reward(gold=80, xp=120),
        ),
        Quest(
            quest_id="a2_h2",
            title="Corruption Investigation",
            description="The local guard captain may be working for dark forces.",
            quest_type=QuestType.STAT_CHECK,
            difficulty=QuestDifficulty.HARD,
            travel_time=30,
            resolution_time=55,
            base_exhaustion=18.0,
            reward=Reward(gold=70, xp=100),
            stat_checks=[{"stat": "charisma", "dc": 15}, {"stat": "intelligence", "dc": 13}],
        ),
    ]
    act2_elite = [
        Quest(
            quest_id="a2_el1",
            title="Vampire Lord",
            description="An ancient vampire lord has awakened in the ruined castle.",
            quest_type=QuestType.COMBAT,
            difficulty=QuestDifficulty.ELITE,
            required_heroes=3,
            travel_time=50,
            resolution_time=100,
            base_exhaustion=35.0,
            reward=Reward(gold=200, xp=300),
        ),
    ]

    # Act 3 quests — highest exhaustion and rewards, demonic theme
    act3_easy = [
        Quest(
            quest_id="a3_e1",
            title="Demonic Scouts",
            description="Demonic scouts are probing the city's defenses.",
            quest_type=QuestType.COMBAT,
            difficulty=QuestDifficulty.EASY,
            travel_time=30,
            resolution_time=50,
            base_exhaustion=16.0,
            reward=Reward(gold=55, xp=80),
        ),
        Quest(
            quest_id="a3_e2",
            title="Infernal Ritual",
            description="A demonic ritual must be disrupted before it completes.",
            quest_type=QuestType.STAT_CHECK,
            difficulty=QuestDifficulty.EASY,
            travel_time=25,
            resolution_time=40,
            base_exhaustion=14.0,
            reward=Reward(gold=50, xp=70),
            stat_checks=[{"stat": "intelligence", "dc": 14}],
        ),
        Quest(
            quest_id="a3_e3",
            title="Hellfire Patrol",
            description="Imps and lesser demons patrol the outer district.",
            quest_type=QuestType.COMBAT,
            difficulty=QuestDifficulty.EASY,
            travel_time=25,
            resolution_time=45,
            base_exhaustion=15.0,
            reward=Reward(gold=52, xp=75),
        ),
    ]
    act3_hard = [
        Quest(
            quest_id="a3_h1",
            title="Demon General",
            description="A demon general commands the invading forces at the city gates.",
            quest_type=QuestType.COMBAT,
            difficulty=QuestDifficulty.HARD,
            required_heroes=2,
            travel_time=40,
            resolution_time=80,
            base_exhaustion=28.0,
            reward=Reward(gold=130, xp=190),
        ),
        Quest(
            quest_id="a3_h2",
            title="Planar Breach",
            description="A rift between worlds must be sealed before more demons pour through.",
            quest_type=QuestType.STAT_CHECK,
            difficulty=QuestDifficulty.HARD,
            travel_time=35,
            resolution_time=65,
            base_exhaustion=25.0,
            reward=Reward(gold=110, xp=165),
            stat_checks=[{"stat": "intelligence", "dc": 17}, {"stat": "constitution", "dc": 15}],
        ),
    ]
    act3_elite = [
        Quest(
            quest_id="a3_el1",
            title="Arch-Demon",
            description="The arch-demon commanding the invasion has revealed itself.",
            quest_type=QuestType.COMBAT,
            difficulty=QuestDifficulty.ELITE,
            required_heroes=3,
            travel_time=60,
            resolution_time=120,
            base_exhaustion=50.0,
            reward=Reward(gold=350, xp=500),
        ),
    ]

    return {
        1: ActPool(act=1, easy=act1_easy, hard=act1_hard, elite=act1_elite),
        2: ActPool(act=2, easy=act2_easy, hard=act2_hard, elite=act2_elite),
        3: ActPool(act=3, easy=act3_easy, hard=act3_hard, elite=act3_elite),
    }
