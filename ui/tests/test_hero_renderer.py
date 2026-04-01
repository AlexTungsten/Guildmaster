import unittest
from ui.renderers.hero_renderer import render_hero_panel, render_hero_detail, exhaustion_label


def make_hero(name="Alice", archetype="Warrior", exhaustion=0.0, skills=None):
    return {
        "hero_id": "hero_1",
        "name": name,
        "archetype": archetype,
        "level": 1,
        "xp": 0,
        "xp_to_next": 100,
        "current_health": 25,
        "max_health": 30,
        "exhaustion": exhaustion,
        "strength": 12,
        "dexterity": 10,
        "intelligence": 8,
        "charisma": 11,
        "constitution": 10,
        "strength_loss": 0,
        "dexterity_loss": 0,
        "intelligence_loss": 0,
        "charisma_loss": 0,
        "constitution_loss": 0,
        "skills": skills if skills is not None else [None, None, None],
        "behavior_profile": "balanced",
        "item_slots": 1,
        "equipped_items": [None],
        "status": "idle",
    }


class TestRenderHeroPanel(unittest.TestCase):
    def setUp(self):
        self.heroes = [
            make_hero("Alice", "Warrior"),
            make_hero("Bob", "Mage"),
        ]

    def test_contains_each_hero_name(self):
        result = render_hero_panel(self.heroes)
        self.assertIn("Alice", result)
        self.assertIn("Bob", result)

    def test_shows_stats(self):
        result = render_hero_panel(self.heroes)
        self.assertIn("STR:", result)
        self.assertIn("DEX:", result)
        self.assertIn("INT:", result)
        self.assertIn("CHA:", result)
        self.assertIn("CON:", result)

    def test_shows_skills_line(self):
        result = render_hero_panel(self.heroes)
        self.assertIn("Skills:", result)

    def test_shows_skill_names_when_present(self):
        skills = [
            {"name": "Slash", "dice_slots": 2, "description": "", "associated_stat": "strength", "effect_type": "damage"},
            None,
            None,
        ]
        heroes = [make_hero("Alice", "Warrior", skills=skills)]
        result = render_hero_panel(heroes)
        self.assertIn("Slash", result)

    def test_shows_none_when_no_skills(self):
        result = render_hero_panel([make_hero()])
        self.assertIn("None", result)

    def test_shows_archetype(self):
        result = render_hero_panel(self.heroes)
        self.assertIn("Warrior", result)

    def test_shows_exhaustion_label(self):
        hero = make_hero(exhaustion=25.0)
        result = render_hero_panel([hero])
        self.assertIn("Tired", result)


class TestRenderHeroDetail(unittest.TestCase):
    def setUp(self):
        self.hero = make_hero("Charlie", "Rogue")

    def test_shows_all_stat_fields(self):
        result = render_hero_detail(self.hero)
        self.assertIn("STR", result)
        self.assertIn("DEX", result)
        self.assertIn("INT", result)
        self.assertIn("CHA", result)
        self.assertIn("CON", result)

    def test_shows_exhaustion_value_and_level(self):
        result = render_hero_detail(self.hero)
        self.assertIn("Exhaustion", result)
        self.assertIn("Rested", result)

    def test_shows_all_three_skill_slots(self):
        result = render_hero_detail(self.hero)
        self.assertIn("Slot 0", result)
        self.assertIn("Slot 1", result)
        self.assertIn("Slot 2", result)

    def test_shows_item_slots(self):
        result = render_hero_detail(self.hero)
        self.assertIn("Items", result)

    def test_shows_behavior_profile(self):
        result = render_hero_detail(self.hero)
        self.assertIn("balanced", result)

    def test_shows_status(self):
        result = render_hero_detail(self.hero)
        self.assertIn("idle", result)


class TestExhaustionLabel(unittest.TestCase):
    def test_rested_at_0(self):
        self.assertEqual(exhaustion_label(0), "Rested")

    def test_tired_at_25(self):
        self.assertEqual(exhaustion_label(25), "Tired")

    def test_weary_at_50(self):
        self.assertEqual(exhaustion_label(50), "Weary")

    def test_drained_at_75(self):
        self.assertEqual(exhaustion_label(75), "Drained")

    def test_critical_at_100(self):
        self.assertEqual(exhaustion_label(100), "Critical")

    def test_rested_boundary(self):
        self.assertEqual(exhaustion_label(19), "Rested")
        self.assertEqual(exhaustion_label(20), "Tired")

    def test_tired_boundary(self):
        self.assertEqual(exhaustion_label(39), "Tired")
        self.assertEqual(exhaustion_label(40), "Weary")

    def test_weary_boundary(self):
        self.assertEqual(exhaustion_label(59), "Weary")
        self.assertEqual(exhaustion_label(60), "Drained")

    def test_drained_boundary(self):
        self.assertEqual(exhaustion_label(99), "Drained")
        self.assertEqual(exhaustion_label(100), "Critical")


if __name__ == "__main__":
    unittest.main()
