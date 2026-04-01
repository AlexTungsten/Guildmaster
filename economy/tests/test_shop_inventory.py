import unittest
from economy.shop_inventory import ShopInventory, ItemListing, HeroListing, TrainingListing


def make_shop():
    shop = ShopInventory(shop_id="test_shop")
    shop.items = [
        ItemListing(item_id="sword_01", name="Iron Sword", category="weapon", cost=30),
        ItemListing(item_id="shield_01", name="Wooden Shield", category="armor", cost=20),
    ]
    shop.heroes = [
        HeroListing(hero_id="hero_01", name="Alice", archetype="warrior", cost=100),
    ]
    shop.training = [
        TrainingListing(skill_id="skill_slash", name="Slash", associated_stat="STR", cost=50),
    ]
    return shop


class TestShopInventory(unittest.TestCase):
    def setUp(self):
        self.shop = make_shop()

    def test_get_item_returns_correct_listing(self):
        item = self.shop.get_item("sword_01")
        self.assertIsNotNone(item)
        self.assertEqual(item.name, "Iron Sword")

    def test_get_item_returns_none_for_unknown(self):
        item = self.shop.get_item("nonexistent")
        self.assertIsNone(item)

    def test_get_hero_returns_correct_listing(self):
        hero = self.shop.get_hero("hero_01")
        self.assertIsNotNone(hero)
        self.assertEqual(hero.name, "Alice")

    def test_get_hero_returns_none_for_unknown(self):
        hero = self.shop.get_hero("nonexistent")
        self.assertIsNone(hero)

    def test_get_training_returns_correct_listing(self):
        training = self.shop.get_training("skill_slash")
        self.assertIsNotNone(training)
        self.assertEqual(training.name, "Slash")

    def test_get_training_returns_none_for_unknown(self):
        training = self.shop.get_training("nonexistent")
        self.assertIsNone(training)

    def test_mark_sold_sets_sold_true_for_item(self):
        result = self.shop.mark_sold("sword_01")
        self.assertTrue(result)
        self.assertTrue(self.shop.get_item("sword_01").sold)

    def test_mark_sold_sets_sold_true_for_hero(self):
        result = self.shop.mark_sold("hero_01")
        self.assertTrue(result)
        self.assertTrue(self.shop.get_hero("hero_01").sold)

    def test_mark_sold_sets_sold_true_for_training(self):
        result = self.shop.mark_sold("skill_slash")
        self.assertTrue(result)
        self.assertTrue(self.shop.get_training("skill_slash").sold)

    def test_mark_sold_returns_false_for_unknown(self):
        result = self.shop.mark_sold("nonexistent_id")
        self.assertFalse(result)

    def test_to_dict_from_dict_round_trip(self):
        self.shop.mark_sold("sword_01")
        data = self.shop.to_dict()
        restored = ShopInventory.from_dict(data)
        self.assertEqual(restored.shop_id, "test_shop")
        self.assertEqual(len(restored.items), 2)
        self.assertEqual(len(restored.heroes), 1)
        self.assertEqual(len(restored.training), 1)
        sword = restored.get_item("sword_01")
        self.assertIsNotNone(sword)
        self.assertTrue(sword.sold)
        shield = restored.get_item("shield_01")
        self.assertIsNotNone(shield)
        self.assertFalse(shield.sold)
        hero = restored.get_hero("hero_01")
        self.assertIsNotNone(hero)
        self.assertEqual(hero.archetype, "warrior")
        self.assertEqual(hero.cost, 100)


if __name__ == "__main__":
    unittest.main()
