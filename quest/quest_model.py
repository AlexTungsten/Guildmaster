"""
quest_model.py — Core data model for a Guildmaster quest.

Defines:
  - QuestType: COMBAT or STAT_CHECK — governs which resolution path is used.
  - QuestDifficulty: EASY / HARD / ELITE — drives pool weights and rewards.
  - QuestStatus: lifecycle state from spawn through completion or expiration.
  - Consequence: a typed outcome applied when a critical quest expires.
  - Reward: gold and XP (plus optional skill/item) granted on success.
  - Quest: the full quest record including timing, assignment, and stat checks.
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import List, Optional, Any


class QuestType(Enum):
    """Determines how the quest is resolved once the heroes arrive."""
    COMBAT = "combat"
    STAT_CHECK = "stat_check"


class QuestDifficulty(Enum):
    """Narrative and mechanical tier; affects draw weights and reward magnitude."""
    EASY = "easy"
    HARD = "hard"
    ELITE = "elite"


class QuestStatus(Enum):
    """
    Lifecycle state of one quest instance.

    AVAILABLE  -> ASSIGNED -> TRAVELING -> RESOLVING -> COMPLETE
                                                     -> EXPIRED (if untouched too long)
    """
    AVAILABLE = "available"
    ASSIGNED = "assigned"
    TRAVELING = "traveling"
    RESOLVING = "resolving"
    COMPLETE = "complete"
    EXPIRED = "expired"


@dataclass
class Consequence:
    """
    A negative outcome applied when a critical quest is left to expire.

    type: string key identifying the consequence handler (e.g. "boss_buff").
    data: arbitrary dict payload forwarded to the handler.
    """
    type: str
    data: dict = field(default_factory=dict)


@dataclass
class Reward:
    """Resources granted to the guild and its heroes on quest success."""
    gold: int = 0
    xp: int = 0
    skill: Optional[Any] = None   # Optional skill object granted to an assigned hero
    item: Optional[Any] = None    # Optional item object placed in the guild inventory


@dataclass
class Quest:
    """
    Complete quest record — spawned on the map, assigned to heroes, and resolved.

    Timing fields (in ticks):
      travel_time     — How long heroes spend traveling before resolution begins.
      resolution_time — How long the resolution phase takes.
      expiration_time — How long the quest stays on the map before auto-expiring.
      spawned_at_tick — The tick at which this quest was added to the map.

    stat_checks is a list of dicts with keys {"stat": str, "dc": int}, only
    used when quest_type == QuestType.STAT_CHECK.
    """
    quest_id: str
    title: str
    description: str
    quest_type: QuestType
    difficulty: QuestDifficulty
    is_critical: bool = False           # Critical quests trigger Consequences when expired
    required_heroes: int = 1            # Minimum heroes that must be assigned
    max_heroes: int = 3                 # Upper bound on assigned heroes
    travel_time: int = 30
    resolution_time: int = 60
    expiration_time: int = 120
    base_exhaustion: float = 10.0       # Exhaustion applied to each hero on completion
    reward: Reward = field(default_factory=Reward)
    consequence: Optional[Consequence] = None
    status: QuestStatus = field(default=QuestStatus.AVAILABLE)
    assigned_hero_ids: List[str] = field(default_factory=list)
    spawned_at_tick: int = 0
    stat_checks: List[dict] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "quest_id": self.quest_id,
            "title": self.title,
            "description": self.description,
            "quest_type": self.quest_type.value,
            "difficulty": self.difficulty.value,
            "is_critical": self.is_critical,
            "required_heroes": self.required_heroes,
            "max_heroes": self.max_heroes,
            "travel_time": self.travel_time,
            "resolution_time": self.resolution_time,
            "expiration_time": self.expiration_time,
            "base_exhaustion": self.base_exhaustion,
            "reward": {
                "gold": self.reward.gold,
                "xp": self.reward.xp,
                "skill": self.reward.skill,
                "item": self.reward.item,
            },
            # Consequence serialized to dict; None when not set
            "consequence": {
                "type": self.consequence.type,
                "data": self.consequence.data,
            } if self.consequence is not None else None,
            "status": self.status.value,
            "assigned_hero_ids": list(self.assigned_hero_ids),
            "spawned_at_tick": self.spawned_at_tick,
            "stat_checks": list(self.stat_checks),
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Quest":
        """Reconstruct a Quest from a previously serialized dict."""
        reward_data = data.get("reward", {})
        reward = Reward(
            gold=reward_data.get("gold", 0),
            xp=reward_data.get("xp", 0),
            skill=reward_data.get("skill"),
            item=reward_data.get("item"),
        )
        consequence = None
        if data.get("consequence") is not None:
            c = data["consequence"]
            consequence = Consequence(type=c["type"], data=c.get("data", {}))
        return cls(
            quest_id=data["quest_id"],
            title=data["title"],
            description=data["description"],
            quest_type=QuestType(data["quest_type"]),
            difficulty=QuestDifficulty(data["difficulty"]),
            is_critical=data.get("is_critical", False),
            required_heroes=data.get("required_heroes", 1),
            max_heroes=data.get("max_heroes", 3),
            travel_time=data.get("travel_time", 30),
            resolution_time=data.get("resolution_time", 60),
            expiration_time=data.get("expiration_time", 120),
            base_exhaustion=data.get("base_exhaustion", 10.0),
            reward=reward,
            consequence=consequence,
            status=QuestStatus(data.get("status", "available")),
            assigned_hero_ids=data.get("assigned_hero_ids", []),
            spawned_at_tick=data.get("spawned_at_tick", 0),
            stat_checks=data.get("stat_checks", []),
        )
