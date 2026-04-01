import unittest
from ui.renderers.shop_renderer import render_shop_screen, render_gold_bar


def make_shop():
    return {
        "shop_id": "shop_42",
        "heroes_for_hire": [
            {"name": "Kira", "archetype": "Ranger", "cost": 80, "sold": False},
            {"name": "Drok", "archetype": "Barbarian", "cost": 60, "sold": True},
        ],
        "items": [
            {"name": "Iron Sword", "category": "weapon", "cost": 30, "sold": False},
            {"name": "Health Potion", "category": "consumable", "cost": 10, "sold": True},
        ],
        "training": [
            {"skill_name": "Power Strike", "stat": "strength", "cost": 50, "sold": False},
            {"skill_name": "Evasion", "stat": "dexterity", "cost": 40, "sold": True},
        ],
    }


class TestRenderShopScreen(unittest.TestCase):
    def setUp(self):
        self.shop = make_shop()
        self.gold = 200

    def test_shows_shop_id(self):
        result = render_shop_screen(self.shop, self.gold)
        self.assertIn("shop_42", result)

    def test_shows_gold(self):
        result = render_shop_screen(self.shop, self.gold)
        self.assertIn("200g", result)

    def test_shows_heroes_for_hire_section(self):
        result = render_shop_screen(self.shop, self.gold)
        self.assertIn("HEROES FOR HIRE", result)
        self.assertIn("Kira", result)
        self.assertIn("Drok", result)

    def test_shows_items_section(self):
        result = render_shop_screen(self.shop, self.gold)
        self.assertIn("ITEMS", result)
        self.assertIn("Iron Sword", result)
        self.assertIn("Health Potion", result)

    def test_shows_training_section(self):
        result = render_shop_screen(self.shop, self.gold)
        self.assertIn("TRAINING", result)
        self.assertIn("Power Strike", result)
        self.assertIn("Evasion", result)

    def test_shows_sold_marker_for_sold_hero(self):
        result = render_shop_screen(self.shop, self.gold)
        self.assertIn("[SOLD]", result)

    def test_sold_marker_on_sold_item(self):
        result = render_shop_screen(self.shop, self.gold)
        # Health Potion is sold
        lines = result.split("\n")
        potion_lines = [l for l in lines if "Health Potion" in l]
        self.assertTrue(any("[SOLD]" in l for l in potion_lines))

    def test_sold_marker_on_sold_training(self):
        result = render_shop_screen(self.shop, self.gold)
        lines = result.split("\n")
        evasion_lines = [l for l in lines if "Evasion" in l]
        self.assertTrue(any("[SOLD]" in l for l in evasion_lines))

    def test_not_sold_has_no_sold_marker(self):
        result = render_shop_screen(self.shop, self.gold)
        lines = result.split("\n")
        kira_lines = [l for l in lines if "Kira" in l]
        self.assertTrue(all("[SOLD]" not in l for l in kira_lines))

    def test_contains_leave_command(self):
        result = render_shop_screen(self.shop, self.gold)
        self.assertIn("leave", result)

    def test_empty_sections(self):
        shop = {"shop_id": "shop_0", "heroes_for_hire": [], "items": [], "training": []}
        result = render_shop_screen(shop, 50)
        self.assertIn("HEROES FOR HIRE", result)
        self.assertIn("ITEMS", result)
        self.assertIn("TRAINING", result)


class TestRenderGoldBar(unittest.TestCase):
    def test_formats_correctly(self):
        result = render_gold_bar(150)
        self.assertEqual(result, "Gold: 150g")

    def test_zero_gold(self):
        result = render_gold_bar(0)
        self.assertEqual(result, "Gold: 0g")

    def test_large_gold(self):
        result = render_gold_bar(99999)
        self.assertEqual(result, "Gold: 99999g")


if __name__ == "__main__":
    unittest.main()
