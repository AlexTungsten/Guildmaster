"""
expiration_tracker.py — Detects and processes expired quests and shops each tick.

Each game tick the ExpirationTracker inspects the MapState for:
  - Quests that are still AVAILABLE but have exceeded their expiration_time.
  - Shops whose expiration_tick has been reached.

Critical quest expiry fires a special "quest.critical_expired" event so
OverworldController can propagate any boss buffs.  Normal quest expiry fires
"quest.expired".  Shop expiry fires "shop.expired".

The tracker returns lists of expired IDs so callers can log or react further.
"""

from typing import List, Tuple

from quest.quest_model import Quest, QuestStatus
from overworld.map_state import MapState, ShopSlot
from game_runtime.event_bus import EventBus


class ExpirationTracker:
    def __init__(self, event_bus: EventBus):
        self._event_bus = event_bus

    def tick(
        self, map_state: MapState, current_tick: int
    ) -> Tuple[List[str], List[str]]:
        """
        Scan map_state for expired entries and clean them up.

        Returns (expired_quest_ids, expired_shop_ids) so callers can track
        what was removed without needing to compare map state before and after.
        """
        expired_quest_ids: List[str] = []
        expired_shop_ids: List[str] = []

        # --- Quest expiration ---
        # Collect IDs first to avoid mutating the dict while iterating it
        quests_to_expire = []
        for quest_id, quest in list(map_state.active_quests.items()):
            if (
                current_tick >= quest.spawned_at_tick + quest.expiration_time
                and quest.status == QuestStatus.AVAILABLE   # Only expire unassigned quests
            ):
                quests_to_expire.append(quest_id)

        for quest_id in quests_to_expire:
            quest = map_state.active_quests.get(quest_id)
            if quest is None:
                continue  # Already removed by a concurrent operation
            if quest.is_critical and quest.consequence is not None:
                # Critical expiry fires a richer event so boss buffs can be applied
                self._event_bus.publish(
                    "quest.critical_expired",
                    {"quest_id": quest_id, "consequence": quest.consequence},
                )
            else:
                self._event_bus.publish("quest.expired", {"quest_id": quest_id})
            map_state.remove_quest(quest_id)
            expired_quest_ids.append(quest_id)

        # --- Shop expiration ---
        shops_to_expire = []
        for shop_id, shop in list(map_state.active_shops.items()):
            if current_tick >= shop.expiration_tick:
                shops_to_expire.append(shop_id)

        for shop_id in shops_to_expire:
            map_state.expire_shop(shop_id)  # Marks expired=True and removes from dict
            self._event_bus.publish("shop.expired", {"shop_id": shop_id})
            expired_shop_ids.append(shop_id)

        return expired_quest_ids, expired_shop_ids
