"""
quest_spawner.py — Periodically draws new quests from the act pool onto the map.

The QuestSpawner fires once per spawn_interval ticks when the map has fewer
than max_active_quests live quests.  Each spawn draws a new quest from the
appropriate act's weighted pool, stamps it with the current tick as its
spawn time, and publishes "quest.spawned".

The spawn interval and cap can be tuned when creating the spawner; defaults
(60 ticks interval, 5 max quests) are appropriate for the default game speed.
"""

import random
from dataclasses import dataclass
from typing import Dict, Optional

from quest.quest_model import Quest
from quest.quest_pool import ActPool, build_default_pools
from overworld.map_state import MapState
from game_runtime.event_bus import EventBus


class QuestSpawner:
    def __init__(
        self,
        event_bus: EventBus,
        spawn_interval: int = 60,       # Ticks between potential spawns
        max_active_quests: int = 5,     # Cap on simultaneous available quests
        rng: random.Random = None,
    ):
        self._event_bus = event_bus
        self._spawn_interval = spawn_interval
        self._max_active_quests = max_active_quests
        self._rng = rng if rng is not None else random.Random()
        # Pre-build all act pools so draws are fast at runtime
        self._pools: Dict[int, ActPool] = build_default_pools()
        self._last_spawn_tick: int = 0   # Tick of the most recent successful spawn

    def tick(self, map_state: MapState, current_tick: int) -> Optional[Quest]:
        """
        Attempt to spawn a quest for the current tick.

        Returns the newly spawned Quest if a spawn occurred, or None if the
        conditions (interval or cap) were not met.
        """
        if (
            current_tick - self._last_spawn_tick >= self._spawn_interval
            and len(map_state.active_quests) < self._max_active_quests
        ):
            pool = self._pools.get(map_state.current_act)
            if pool is None:
                return None   # No pool defined for this act; skip
            # Draw a deep-copy from the act pool (see ActPool.draw)
            quest = pool.draw(rng=self._rng)
            # Stamp the quest with a unique ID and its spawn tick for expiry calculation
            quest.quest_id = f"q_{current_tick}"
            quest.spawned_at_tick = current_tick
            map_state.add_quest(quest)
            self._last_spawn_tick = current_tick
            self._event_bus.publish(
                "quest.spawned",
                {
                    "quest_id": quest.quest_id,
                    "difficulty": quest.difficulty.value,
                    "act": map_state.current_act,
                },
            )
            return quest
        return None
