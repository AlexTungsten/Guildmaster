import unittest
from game_runtime.event_bus import EventBus
from hero.hero_entity import HeroEntity, HeroStatus
from economy.gold_ledger import GoldLedger
from economy.roster_manager import RosterManager
from economy.shop_inventory import ShopInventory, ItemListing, HeroListing, TrainingListing
from economy.shop_actions import ShopActions, ShopError


def make_bus_and_components(starting_gold=200, roster_cap=5):
    bus = EventBus()
    ledger = GoldLedger(bus, starting_gold=starting_gold)
    roster = RosterManager(bus, cap=roster_cap)
    actions = ShopActions(bus, ledger, roster)
    return bus, ledger, roster, actions


def make_shop():
    shop = ShopInventory(shop_id="shop_1")
    shop.heroes = [
        HeroListing(hero_id="h1", name="Bran", archetype="rogue", cost=80),
    ]
    shop.items = [
        ItemListing(item_id="item_sword", name="Iron Sword", category="weapon", cost=30),
    ]
    shop.training = [
        TrainingListing(skill_id="skill_fire", name="Fireball", associated_stat="INT", cost=60),
    ]
    return shop


class TestShopActions(unittest.TestCase):
    def setUp(self):
        self.bus, self.ledger, self.roster, self.actions = make_bus_and_components()
        self.shop = make_shop()
        self.hired_events = []
        self.bought_events = []
        self.trained_events = []
        self.bus.subscribe("shop.hero_hired", lambda d: self.hired_events.append(d))
        self.bus.subscribe("shop.item_bought", lambda d: self.bought_events.append(d))
        self.bus.subscribe("shop.skill_trained", lambda d: self.trained_events.append(d))

    def test_hire_hero_deducts_gold_adds_to_roster_marks_sold(self):
        result = self.actions.hire_hero(self.shop, "h1")
        self.assertEqual(result.hero_id, "h1")
        self.assertEqual(result.cost, 80)
        self.assertEqual(self.ledger.balance, 120)
        self.assertEqual(self.roster.count, 1)
        self.assertIsNotNone(self.roster.get_hero("h1"))
        self.assertTrue(self.shop.get_hero("h1").sold)
        self.assertEqual(len(self.hired_events), 1)
        self.assertEqual(self.hired_events[0]["hero_id"], "h1")

    def test_hire_hero_raises_shop_error_insufficient_gold(self):
        _, ledger, roster, actions = make_bus_and_components(starting_gold=10)
        shop = make_shop()
        with self.assertRaises(ShopError):
            actions.hire_hero(shop, "h1")
        self.assertEqual(roster.count, 0)

    def test_hire_hero_raises_shop_error_roster_full(self):
        _, ledger, roster, actions = make_bus_and_components(starting_gold=500, roster_cap=0)
        shop = make_shop()
        with self.assertRaises(ShopError):
            actions.hire_hero(shop, "h1")

    def test_buy_item_deducts_gold_marks_sold_publishes_event(self):
        result = self.actions.buy_item(self.shop, "item_sword")
        self.assertEqual(result.item_id, "item_sword")
        self.assertEqual(result.cost, 30)
        self.assertEqual(self.ledger.balance, 170)
        self.assertTrue(self.shop.get_item("item_sword").sold)
        self.assertEqual(len(self.bought_events), 1)
        self.assertEqual(self.bought_events[0]["item_id"], "item_sword")

    def test_buy_item_raises_shop_error_insufficient_gold(self):
        _, ledger, roster, actions = make_bus_and_components(starting_gold=5)
        shop = make_shop()
        with self.assertRaises(ShopError):
            actions.buy_item(shop, "item_sword")
        self.assertFalse(shop.get_item("item_sword").sold)

    def test_train_skill_deducts_gold_replaces_hero_skill(self):
        hero = HeroEntity(hero_id="hero_x", name="Test Hero", archetype="mage")
        result = self.actions.train_skill(self.shop, "skill_fire", hero, replace_slot=1)
        self.assertEqual(result.skill_id, "skill_fire")
        self.assertEqual(result.hero_id, "hero_x")
        self.assertEqual(result.replaced_slot, 1)
        self.assertEqual(result.cost, 60)
        self.assertEqual(self.ledger.balance, 140)
        self.assertIsNotNone(hero.skills[1])
        self.assertEqual(hero.skills[1].name, "Fireball")
        self.assertTrue(self.shop.get_training("skill_fire").sold)
        self.assertEqual(len(self.trained_events), 1)
        self.assertEqual(self.trained_events[0]["slot"], 1)

    def test_train_skill_raises_shop_error_insufficient_gold(self):
        _, ledger, roster, actions = make_bus_and_components(starting_gold=10)
        shop = make_shop()
        hero = HeroEntity(hero_id="hero_y", name="Poor Hero", archetype="warrior")
        with self.assertRaises(ShopError):
            actions.train_skill(shop, "skill_fire", hero, replace_slot=0)

    def test_train_skill_raises_shop_error_invalid_slot(self):
        hero = HeroEntity(hero_id="hero_z", name="Test Hero", archetype="warrior")
        with self.assertRaises(ShopError):
            self.actions.train_skill(self.shop, "skill_fire", hero, replace_slot=3)


if __name__ == "__main__":
    unittest.main()
