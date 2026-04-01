"""
shop_spawner.py — Periodically generates travelling merchant shops on the map.

Each shop contains a randomly sampled mix of items, a hero for hire, and a
training option.  At most 2 shops are active simultaneously; a new shop only
spawns if the map has fewer than that and the spawn_interval has elapsed.

ITEM_POOL, HERO_POOL, and TRAINING_POOL are static lists of available
merchandise.  In a more complete game these would be loaded from data files
or generated procedurally based on the current act.
"""

import random
from dataclasses import dataclass
from typing import List, Optional

from overworld.map_state import MapState, ShopSlot
from game_runtime.event_bus import EventBus


# --- Static merchandise pools ---

ITEM_POOL: List[dict] = [
    {"item_id": "item_001", "name": "Health Potion", "category": "consumable", "cost": 25},
    {"item_id": "item_002", "name": "Iron Shield", "category": "armor", "cost": 80},
    {"item_id": "item_003", "name": "Silver Dagger", "category": "weapon", "cost": 60},
    {"item_id": "item_004", "name": "Mana Crystal", "category": "consumable", "cost": 40},
    {"item_id": "item_005", "name": "Leather Boots", "category": "armor", "cost": 35},
]

HERO_POOL: List[dict] = [
    {"hero_id": "hire_001", "name": "Gareth the Bold", "archetype": "warrior", "cost": 150},
    {"hero_id": "hire_002", "name": "Lyra Swiftarrow", "archetype": "ranger", "cost": 140},
    {"hero_id": "hire_003", "name": "Aldric Spellweave", "archetype": "mage", "cost": 160},
]

TRAINING_POOL: List[dict] = [
    {"skill_id": "train_001", "name": "Combat Drills", "cost": 50},
    {"skill_id": "train_002", "name": "Arcane Studies", "cost": 60},
    {"skill_id": "train_003", "name": "Wilderness Survival", "cost": 45},
]


class ShopSpawner:
    def __init__(
        self,
        event_bus: EventBus,
        spawn_interval: int = 180,    # Ticks between potential shop spawns
        shop_duration: int = 120,     # Ticks a shop stays open after spawning
        rng: random.Random = None,
    ):
        self._event_bus = event_bus
        self._spawn_interval = spawn_interval
        self._shop_duration = shop_duration
        self._rng = rng if rng is not None else random.Random()
        self._last_spawn_tick: int = 0
        self._shop_counter: int = 0   # Monotonically increasing for unique shop IDs

    def tick(self, map_state: MapState, current_tick: int) -> Optional[ShopSlot]:
        """
        Attempt to spawn a shop for the current tick.

        Spawns only when fewer than 2 shops are active and the interval has
        elapsed.  Returns the new ShopSlot or None if no spawn occurred.
        """
        if (
            current_tick - self._last_spawn_tick >= self._spawn_interval
            and len(map_state.active_shops) < 2  # Hard cap of 2 simultaneous shops
        ):
            # Sample 2 random items and 1 hero/training offering for the shop inventory
            items = self._rng.sample(ITEM_POOL, 2)
            hero = self._rng.choice(HERO_POOL)
            training = self._rng.choice(TRAINING_POOL)
            inventory = list(items) + [hero, training]

            shop = ShopSlot(
                shop_id=f"shop_{self._shop_counter}",
                spawned_at_tick=current_tick,
                expiration_tick=current_tick + self._shop_duration,  # Shop closes after duration
                inventory=inventory,
            )
            self._shop_counter += 1
            self._last_spawn_tick = current_tick
            map_state.add_shop(shop)
            self._event_bus.publish("shop.spawned", {"shop_id": shop.shop_id})
            return shop
        return None
