import random
import unittest
from unittest.mock import patch, MagicMock

from hero.hero_entity import HeroEntity, Stat
from quest.stat_check_resolver import resolve_stat_check, StatCheckOutcome, CheckResult


def make_hero(hero_id: str = "h1", intelligence: int = 10) -> HeroEntity:
    return HeroEntity(hero_id=hero_id, name="Test Hero", archetype="wizard",
                      intelligence=intelligence)


class FixedRNG:
    """RNG that always returns a fixed d20 value."""
    def __init__(self, fixed_value: int):
        self._value = fixed_value

    def randint(self, a: int, b: int) -> int:
        return self._value

    def random(self):
        return 0.5

    def choice(self, seq):
        return seq[0]


class TestResolveStatCheckPassing(unittest.TestCase):
    def test_passing_roll_marks_passed(self):
        hero = make_hero()  # intelligence=10, modifier=0
        rng = FixedRNG(20)  # roll 20 + 0 = 20 >= dc 10 -> pass
        checks = [{"stat": Stat.INT, "dc": 10}]
        outcome = resolve_stat_check([hero], checks, rng=rng)
        self.assertTrue(outcome.checks[0].passed)

    def test_any_passed_true_when_hero_passes(self):
        hero = make_hero()
        rng = FixedRNG(20)
        checks = [{"stat": Stat.INT, "dc": 10}]
        outcome = resolve_stat_check([hero], checks, rng=rng)
        self.assertTrue(outcome.any_passed)

    def test_all_passed_true_when_single_check_passes(self):
        hero = make_hero()
        rng = FixedRNG(20)
        checks = [{"stat": Stat.INT, "dc": 10}]
        outcome = resolve_stat_check([hero], checks, rng=rng)
        self.assertTrue(outcome.all_passed)


class TestResolveStatCheckFailing(unittest.TestCase):
    def test_failing_roll_marks_not_passed(self):
        hero = make_hero()  # intelligence=10, modifier=0
        rng = FixedRNG(1)  # roll 1 + 0 = 1 < dc 15 -> fail
        checks = [{"stat": Stat.INT, "dc": 15}]
        outcome = resolve_stat_check([hero], checks, rng=rng)
        self.assertFalse(outcome.checks[0].passed)

    def test_any_passed_false_when_all_fail(self):
        heroes = [make_hero("h1"), make_hero("h2")]
        rng = FixedRNG(1)
        checks = [{"stat": Stat.INT, "dc": 20}]
        outcome = resolve_stat_check(heroes, checks, rng=rng)
        self.assertFalse(outcome.any_passed)

    def test_all_passed_false_when_any_check_fails(self):
        hero = make_hero()
        rng = FixedRNG(1)
        checks = [
            {"stat": Stat.INT, "dc": 10},
            {"stat": Stat.STR, "dc": 20},
        ]

        class AlternatingRNG:
            def __init__(self):
                self._calls = 0
            def randint(self, a, b):
                self._calls += 1
                # First check gets 15 (pass dc=10), second gets 1 (fail dc=20)
                if self._calls <= 1:
                    return 15
                return 1
            def random(self):
                return 0.5

        outcome = resolve_stat_check([hero], checks, rng=AlternatingRNG())
        self.assertFalse(outcome.all_passed)


class TestAnyPassedMultipleHeroes(unittest.TestCase):
    def test_any_passed_true_if_one_hero_passes(self):
        # hero1 has low int, hero2 has high int
        h1 = make_hero("h1", intelligence=4)   # modifier = floor(4/2)-5 = -3
        h2 = make_hero("h2", intelligence=20)  # modifier = floor(20/2)-5 = 5

        class HeroSpecificRNG:
            def __init__(self):
                self._calls = 0
            def randint(self, a, b):
                self._calls += 1
                if self._calls == 1:
                    return 1   # h1 fails (1 + -3 = -2 < dc 12)
                return 20      # h2 passes (20 + 5 = 25 >= dc 12)
            def random(self):
                return 0.5

        checks = [{"stat": Stat.INT, "dc": 12}]
        outcome = resolve_stat_check([h1, h2], checks, rng=HeroSpecificRNG())
        self.assertTrue(outcome.any_passed)

    def test_all_passed_true_only_when_every_check_has_pass(self):
        hero = make_hero()
        rng = FixedRNG(20)  # always 20, passes everything
        checks = [
            {"stat": Stat.INT, "dc": 10},
            {"stat": Stat.STR, "dc": 10},
        ]
        outcome = resolve_stat_check([hero], checks, rng=rng)
        self.assertTrue(outcome.all_passed)


class TestStatCheckAcceptsRng(unittest.TestCase):
    def test_accepts_rng_parameter(self):
        hero = make_hero()
        rng = random.Random(42)
        checks = [{"stat": Stat.INT, "dc": 10}]
        outcome = resolve_stat_check([hero], checks, rng=rng)
        self.assertIsInstance(outcome, StatCheckOutcome)

    def test_no_rng_still_works(self):
        hero = make_hero()
        checks = [{"stat": Stat.INT, "dc": 10}]
        outcome = resolve_stat_check([hero], checks)
        self.assertIsInstance(outcome, StatCheckOutcome)

    def test_check_result_fields_populated(self):
        hero = make_hero()
        rng = FixedRNG(15)
        checks = [{"stat": Stat.INT, "dc": 10}]
        outcome = resolve_stat_check([hero], checks, rng=rng)
        cr = outcome.checks[0]
        self.assertEqual(cr.roll, 15)
        self.assertEqual(cr.dc, 10)
        self.assertEqual(cr.hero_id, hero.hero_id)
        self.assertEqual(cr.stat, Stat.INT.value)

    def test_string_stat_accepted(self):
        hero = make_hero()
        rng = FixedRNG(15)
        checks = [{"stat": "intelligence", "dc": 10}]
        outcome = resolve_stat_check([hero], checks, rng=rng)
        self.assertIsInstance(outcome, StatCheckOutcome)


if __name__ == "__main__":
    unittest.main()
