import random
import unittest

from overworld.map_state import MapState, ShopSlot
from overworld.shop_spawner import ShopSpawner, ITEM_POOL, HERO_POOL, TRAINING_POOL
from game_runtime.event_bus import EventBus


class TestShopSpawner(unittest.TestCase):
    def setUp(self):
        self.bus = EventBus()
        self.rng = random.Random(99)
        self.spawner = ShopSpawner(
            event_bus=self.bus,
            spawn_interval=180,
            shop_duration=120,
            rng=self.rng,
        )

    def test_spawns_shop_after_spawn_interval(self):
        ms = MapState()
        shop = self.spawner.tick(ms, current_tick=180)
        self.assertIsNotNone(shop)
        self.assertEqual(len(ms.active_shops), 1)

    def test_does_not_spawn_before_interval(self):
        ms = MapState()
        shop = self.spawner.tick(ms, current_tick=179)
        self.assertIsNone(shop)
        self.assertEqual(len(ms.active_shops), 0)

    def test_does_not_spawn_when_two_shops_active(self):
        ms = MapState()
        self.spawner.tick(ms, current_tick=180)
        self.spawner.tick(ms, current_tick=360)
        # 2 shops now active
        self.assertEqual(len(ms.active_shops), 2)
        shop = self.spawner.tick(ms, current_tick=540)
        self.assertIsNone(shop)

    def test_shop_inventory_contains_items_from_pools(self):
        ms = MapState()
        shop = self.spawner.tick(ms, current_tick=180)
        item_ids = {it["item_id"] for it in ITEM_POOL}
        hero_ids = {h["hero_id"] for h in HERO_POOL}
        training_ids = {t["skill_id"] for t in TRAINING_POOL}

        inv = shop.inventory
        self.assertEqual(len(inv), 4)
        # first 2 should be items
        for item in inv[:2]:
            self.assertIn(item["item_id"], item_ids)
        # 3rd is a hero
        self.assertIn(inv[2]["hero_id"], hero_ids)
        # 4th is training
        self.assertIn(inv[3]["skill_id"], training_ids)

    def test_shop_spawned_event_published(self):
        ms = MapState()
        received = []
        self.bus.subscribe("shop.spawned", lambda d: received.append(d))

        self.spawner.tick(ms, current_tick=180)
        self.assertEqual(len(received), 1)
        self.assertIn("shop_id", received[0])

    def test_shop_id_increments_with_each_spawn(self):
        ms = MapState()
        shop1 = self.spawner.tick(ms, current_tick=180)
        self.assertEqual(shop1.shop_id, "shop_0")

        # Remove first shop so a second can spawn
        ms.active_shops.clear()
        shop2 = self.spawner.tick(ms, current_tick=360)
        self.assertEqual(shop2.shop_id, "shop_1")

    def test_shop_expiration_tick_is_set_correctly(self):
        ms = MapState()
        shop = self.spawner.tick(ms, current_tick=180)
        self.assertEqual(shop.expiration_tick, 180 + 120)


if __name__ == "__main__":
    unittest.main()
