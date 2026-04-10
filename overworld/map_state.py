"""
map_state.py — Live snapshot of everything visible on the overworld map.

MapState is the single authoritative record of:
  - Which quests are currently spawned and available.
  - Which travelling shops are open.
  - The current act's boss slot (identity, buffs, revealed/defeated status).
  - Timing information for the current act and the boss countdown timer.

This is a pure data container — it has no event bus dependency and performs
no side effects.  All mutation is done through the small mutator methods
(add_quest, remove_quest, etc.) rather than direct field access so that
OverworldController and the ExpirationTracker remain the single callers
responsible for map changes.
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional

from quest.quest_model import Quest, QuestStatus


@dataclass
class ShopSlot:
    """Tracks one instance of a travelling shop on the map."""
    shop_id: str
    spawned_at_tick: int
    expiration_tick: int           # Tick at which this shop automatically closes
    inventory: List[dict] = field(default_factory=list)  # Raw item/hero/training dicts
    expired: bool = False          # Set to True after the shop has been closed


@dataclass
class BossSlot:
    """
    Tracks the act boss.

    The boss starts hidden (revealed=False) until the boss timer fires, at
    which point revealed=True and the UI shows the boss encounter.  Buffs are
    accumulated strings added when critical quests expire.
    """
    boss_id: str
    act: int
    revealed: bool = False
    defeated: bool = False
    buffs: List[str] = field(default_factory=list)


@dataclass
class MapState:
    """Full overworld map snapshot for one act."""
    active_quests: Dict[str, Quest] = field(default_factory=dict)       # quest_id -> Quest
    active_shops: Dict[str, ShopSlot] = field(default_factory=dict)    # shop_id -> ShopSlot
    boss: Optional[BossSlot] = None
    current_act: int = 1
    act_start_tick: int = 0
    boss_timer_duration: int = 10000  # Ticks from act_start until the boss is revealed

    def add_quest(self, quest: Quest) -> None:
        """Register a newly spawned quest on the map."""
        self.active_quests[quest.quest_id] = quest

    def remove_quest(self, quest_id: str) -> None:
        """Remove a quest (completed, expired, or assigned away); no-op if not present."""
        self.active_quests.pop(quest_id, None)

    def add_shop(self, shop: ShopSlot) -> None:
        """Register a newly spawned shop on the map."""
        self.active_shops[shop.shop_id] = shop

    def expire_shop(self, shop_id: str) -> None:
        """
        Mark a shop as expired and remove it from the active map.

        Sets expired=True on the ShopSlot before deletion so any external
        reference to the slot can detect it was closed.
        """
        shop = self.active_shops.get(shop_id)
        if shop is not None:
            shop.expired = True
            del self.active_shops[shop_id]

    def apply_boss_buff(self, buff: str) -> None:
        """Append a buff string to the boss's buff list (consequence of a critical expiry)."""
        if self.boss is not None:
            self.boss.buffs.append(buff)

    def to_dict(self) -> dict:
        boss_dict = None
        if self.boss is not None:
            boss_dict = {
                "boss_id": self.boss.boss_id,
                "act": self.boss.act,
                "revealed": self.boss.revealed,
                "defeated": self.boss.defeated,
                "buffs": list(self.boss.buffs),
            }
        return {
            "active_quests": {qid: q.to_dict() for qid, q in self.active_quests.items()},
            "active_shops": {
                sid: {
                    "shop_id": s.shop_id,
                    "spawned_at_tick": s.spawned_at_tick,
                    "expiration_tick": s.expiration_tick,
                    "inventory": list(s.inventory),
                    "expired": s.expired,
                }
                for sid, s in self.active_shops.items()
            },
            "boss": boss_dict,
            "current_act": self.current_act,
            "act_start_tick": self.act_start_tick,
            "boss_timer_duration": self.boss_timer_duration,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "MapState":
        """Reconstruct a MapState from a previously serialized dict."""
        active_quests = {
            qid: Quest.from_dict(qdata)
            for qid, qdata in data.get("active_quests", {}).items()
        }
        active_shops = {}
        for sid, sdata in data.get("active_shops", {}).items():
            active_shops[sid] = ShopSlot(
                shop_id=sdata["shop_id"],
                spawned_at_tick=sdata["spawned_at_tick"],
                expiration_tick=sdata["expiration_tick"],
                inventory=sdata.get("inventory", []),
                expired=sdata.get("expired", False),
            )
        boss = None
        if data.get("boss") is not None:
            b = data["boss"]
            boss = BossSlot(
                boss_id=b["boss_id"],
                act=b["act"],
                revealed=b.get("revealed", False),
                defeated=b.get("defeated", False),
                buffs=b.get("buffs", []),
            )
        return cls(
            active_quests=active_quests,
            active_shops=active_shops,
            boss=boss,
            current_act=data.get("current_act", 1),
            act_start_tick=data.get("act_start_tick", 0),
            boss_timer_duration=data.get("boss_timer_duration", 600),
        )
