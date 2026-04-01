import unittest

from combat.dice_pool_compositor import Die, compose_pool, roll_pool
from hero.hero_entity import HeroEntity, HeroStatus


def make_hero(**kwargs) -> HeroEntity:
    defaults = {
        "hero_id": "h1",
        "name": "Tester",
        "archetype": "rogue",
    }
    defaults.update(kwargs)
    return HeroEntity(**defaults)


class TestDie(unittest.TestCase):
    def test_roll_in_range(self):
        die = Die(sides=10)
        for _ in range(100):
            result = die.roll()
            self.assertGreaterEqual(result, 1)
            self.assertLessEqual(result, 10)

    def test_repr_normal(self):
        die = Die(sides=6)
        self.assertEqual(repr(die), "d6")

    def test_repr_locked(self):
        die = Die(sides=4, is_locked=True)
        self.assertEqual(repr(die), "d4[LOCKED]")


class TestComposePool(unittest.TestCase):
    def test_exhaustion_level_1_no_locked_dice(self):
        # exhaustion=0 => level 1, no locked dice
        hero = make_hero(exhaustion=0, base_dice_count=4)
        pool = compose_pool(hero)
        self.assertEqual(len(pool), 4)
        locked = [d for d in pool if d.is_locked]
        self.assertEqual(len(locked), 0)

    def test_exhaustion_level_3_two_locked_dice(self):
        # exhaustion=45 => level 3, 2 locked dice
        hero = make_hero(exhaustion=45, base_dice_count=4)
        pool = compose_pool(hero)
        self.assertEqual(len(pool), 4)
        locked = [d for d in pool if d.is_locked]
        normal = [d for d in pool if not d.is_locked]
        self.assertEqual(len(locked), 2)
        self.assertEqual(len(normal), 2)

    def test_locked_dice_are_first_in_list(self):
        hero = make_hero(exhaustion=45, base_dice_count=4)
        pool = compose_pool(hero)
        # First 2 should be locked
        self.assertTrue(pool[0].is_locked)
        self.assertTrue(pool[1].is_locked)
        self.assertFalse(pool[2].is_locked)
        self.assertFalse(pool[3].is_locked)

    def test_locked_dice_are_d4(self):
        hero = make_hero(exhaustion=45, base_dice_count=4)
        pool = compose_pool(hero)
        for die in pool:
            if die.is_locked:
                self.assertEqual(die.sides, 4)
            else:
                self.assertEqual(die.sides, 10)

    def test_roll_pool_returns_correct_count(self):
        hero = make_hero(exhaustion=0, base_dice_count=4)
        pool = compose_pool(hero)
        results = roll_pool(pool)
        self.assertEqual(len(results), 4)

    def test_roll_pool_values_in_range(self):
        hero = make_hero(exhaustion=45, base_dice_count=4)
        pool = compose_pool(hero)
        results = roll_pool(pool)
        for i, val in enumerate(results):
            die = pool[i]
            self.assertGreaterEqual(val, 1)
            self.assertLessEqual(val, die.sides)


class TestComposePoolCustomDiceSides(unittest.TestCase):

    def test_base_dice_sides_12_produces_d12_normal_dice(self):
        # A hero with base_dice_sides=12 (Barbarian) should have d12 normal dice
        hero = make_hero(exhaustion=0, base_dice_count=4, base_dice_sides=12)
        pool = compose_pool(hero)
        normal_dice = [d for d in pool if not d.is_locked]
        self.assertTrue(len(normal_dice) > 0)
        for die in normal_dice:
            self.assertEqual(die.sides, 12)

    def test_locked_dice_sides_6_ironhide_produces_d6_locked_dice(self):
        # A hero with locked_dice_sides=6 (Ironhide) and exhaustion level 2+ should have d6 locked dice
        hero = make_hero(exhaustion=25, base_dice_count=4, locked_dice_sides=6)
        pool = compose_pool(hero)
        locked_dice = [d for d in pool if d.is_locked]
        self.assertTrue(len(locked_dice) > 0)
        for die in locked_dice:
            self.assertEqual(die.sides, 6)

    def test_locked_dice_sides_6_does_not_affect_normal_dice(self):
        # With Ironhide, only locked dice change; normal dice still use base_dice_sides
        hero = make_hero(exhaustion=25, base_dice_count=4, locked_dice_sides=6, base_dice_sides=12)
        pool = compose_pool(hero)
        normal_dice = [d for d in pool if not d.is_locked]
        for die in normal_dice:
            self.assertEqual(die.sides, 12)


if __name__ == "__main__":
    unittest.main()
