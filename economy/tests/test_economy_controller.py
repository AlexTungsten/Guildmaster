import unittest
from game_runtime.event_bus import EventBus
from hero.hero_entity import HeroEntity, HeroStatus
from economy.economy_controller import EconomyController
from economy.shop_inventory import ShopInventory, HeroListing, ItemListing
from economy.shop_actions import ShopError


class TestEconomyController(unittest.TestCase):
    def setUp(self):
        self.bus = EventBus()
        self.controller = EconomyController(
            event_bus=self.bus,
            starting_gold=200,
            roster_cap=10,
            inventory_max=20,
        )

    def test_earn_gold_delegates_to_ledger(self):
        new_balance = self.controller.earn_gold(50, reason="quest")
        self.assertEqual(new_balance, 250)
        self.assertEqual(self.controller.ledger.balance, 250)

    def test_tick_reduces_exhaustion_of_idle_heroes(self):
        hero = HeroEntity(hero_id="h1", name="Alice", archetype="warrior")
        hero.exhaustion = 20.0
        hero.status = HeroStatus.IDLE
        self.controller.roster.add_hero(hero)
        self.controller.tick(seconds=3.0)
        self.assertAlmostEqual(hero.exhaustion, 17.0)

    def test_tick_does_not_affect_non_idle_heroes(self):
        hero = HeroEntity(hero_id="h2", name="Bob", archetype="rogue")
        hero.exhaustion = 20.0
        hero.status = HeroStatus.ON_QUEST
        self.controller.roster.add_hero(hero)
        self.controller.tick(seconds=3.0)
        self.assertAlmostEqual(hero.exhaustion, 20.0)

    def test_shop_actions_wired_to_ledger_and_roster(self):
        shop = ShopInventory(shop_id="test_shop")
        shop.heroes = [
            HeroListing(hero_id="h_new", name="Charlie", archetype="mage", cost=80),
        ]
        result = self.controller.shop_actions.hire_hero(shop, "h_new")
        self.assertEqual(result.hero_id, "h_new")
        self.assertEqual(self.controller.ledger.balance, 120)
        self.assertEqual(self.controller.roster.count, 1)
        self.assertIsNotNone(self.controller.roster.get_hero("h_new"))

    def test_shop_actions_raises_when_insufficient_gold(self):
        controller = EconomyController(event_bus=self.bus, starting_gold=10)
        shop = ShopInventory(shop_id="shop_x")
        shop.heroes = [
            HeroListing(hero_id="h_exp", name="Expensive Hero", archetype="paladin", cost=500),
        ]
        with self.assertRaises(ShopError):
            controller.shop_actions.hire_hero(shop, "h_exp")

    def test_to_dict_from_dict_round_trip_restores_balance(self):
        self.controller.earn_gold(100, reason="bonus")
        data = self.controller.to_dict()
        new_bus = EventBus()
        restored = EconomyController.from_dict(data, new_bus)
        self.assertEqual(restored.ledger.balance, 300)

    def test_to_dict_from_dict_round_trip_restores_roster(self):
        hero = HeroEntity(hero_id="h1", name="Alice", archetype="warrior")
        self.controller.roster.add_hero(hero)
        data = self.controller.to_dict()
        new_bus = EventBus()
        restored = EconomyController.from_dict(data, new_bus)
        self.assertEqual(restored.roster.count, 1)
        self.assertIsNotNone(restored.roster.get_hero("h1"))

    def test_properties_accessible(self):
        self.assertIsNotNone(self.controller.ledger)
        self.assertIsNotNone(self.controller.roster)
        self.assertIsNotNone(self.controller.inventory)
        self.assertIsNotNone(self.controller.shop_actions)


if __name__ == "__main__":
    unittest.main()
