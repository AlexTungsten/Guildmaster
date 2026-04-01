import unittest

from hero.archetype_loader import load_archetype, list_archetypes
from hero.hero_entity import HeroEntity


class TestLoadBarbarianArchetype(unittest.TestCase):

    def setUp(self):
        self.hero = load_archetype("barbarian", "h1", "Grok")

    def test_returns_hero_entity(self):
        self.assertIsInstance(self.hero, HeroEntity)

    def test_strength(self):
        self.assertEqual(self.hero.strength, 14)

    def test_constitution(self):
        self.assertEqual(self.hero.constitution, 15)

    def test_dexterity(self):
        self.assertEqual(self.hero.dexterity, 12)

    def test_intelligence(self):
        self.assertEqual(self.hero.intelligence, 7)

    def test_charisma(self):
        self.assertEqual(self.hero.charisma, 8)

    def test_base_dice_sides_12(self):
        self.assertEqual(self.hero.base_dice_sides, 12)

    def test_locked_dice_sides_6_from_ironhide(self):
        self.assertEqual(self.hero.locked_dice_sides, 6)

    def test_has_three_skills(self):
        # All three skill slots filled (none padded with None since barbarian has 3)
        non_none = [s for s in self.hero.skills if s is not None]
        self.assertEqual(len(non_none), 3)

    def test_skill_names(self):
        names = [s.name for s in self.hero.skills if s is not None]
        self.assertIn("Bash", names)
        self.assertIn("Blood Cleave", names)
        self.assertIn("Bloodletting", names)

    def test_bloodletting_has_correct_special(self):
        skill = next(s for s in self.hero.skills if s and s.name == "Bloodletting")
        self.assertEqual(skill.special, "bloodletting")

    def test_blood_cleave_has_correct_special(self):
        skill = next(s for s in self.hero.skills if s and s.name == "Blood Cleave")
        self.assertEqual(skill.special, "blood_cleave")

    def test_bash_special_is_none(self):
        skill = next(s for s in self.hero.skills if s and s.name == "Bash")
        self.assertIsNone(skill.special)

    def test_has_passive_ironhide(self):
        self.assertTrue(self.hero.has_passive("ironhide"))

    def test_has_passive_unknown_returns_false(self):
        self.assertFalse(self.hero.has_passive("berserker"))


class TestListArchetypes(unittest.TestCase):

    def test_barbarian_in_list(self):
        archetypes = list_archetypes()
        self.assertIn("barbarian", archetypes)

    def test_returns_list(self):
        self.assertIsInstance(list_archetypes(), list)


class TestLoadUnknownArchetype(unittest.TestCase):

    def test_raises_file_not_found(self):
        with self.assertRaises(FileNotFoundError):
            load_archetype("paladin", "h2", "Sir Nothere")


if __name__ == "__main__":
    unittest.main()
