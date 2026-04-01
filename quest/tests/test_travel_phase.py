import random
import unittest

from hero.hero_entity import HeroEntity
from quest.travel_phase import (
    roll_travel_events, apply_travel_outcomes,
    TravelResult, RandomEvent, TRAVEL_EVENT_POOL,
)


def make_hero(hero_id: str = "h1") -> HeroEntity:
    return HeroEntity(hero_id=hero_id, name="Test Hero", archetype="warrior")


class TestRollTravelEvents(unittest.TestCase):
    def test_returns_travel_result(self):
        heroes = [make_hero()]
        result = roll_travel_events(heroes, travel_time=50)
        self.assertIsInstance(result, TravelResult)

    def test_zero_travel_time_no_events(self):
        heroes = [make_hero()]
        # P = min(0.6, 0/100) = 0, so no event should fire
        rng = random.Random(42)
        result = roll_travel_events(heroes, travel_time=0, rng=rng)
        self.assertEqual(len(result.events_fired), 0)
        self.assertEqual(len(result.chosen_outcomes), 0)

    def test_high_travel_time_can_fire_event(self):
        heroes = [make_hero()]
        # With a seeded RNG that gives a low roll, event should fire at travel_time=100
        # P=0.6, we need rng.random() < 0.6
        fired_count = 0
        for seed in range(50):
            rng = random.Random(seed)
            result = roll_travel_events(heroes, travel_time=100, rng=rng)
            fired_count += len(result.events_fired)
        self.assertGreater(fired_count, 0)

    def test_uses_provided_rng(self):
        heroes = [make_hero()]
        rng1 = random.Random(999)
        rng2 = random.Random(999)
        result1 = roll_travel_events(heroes, travel_time=60, rng=rng1)
        result2 = roll_travel_events(heroes, travel_time=60, rng=rng2)
        self.assertEqual(len(result1.events_fired), len(result2.events_fired))

    def test_event_pool_has_three_events(self):
        self.assertEqual(len(TRAVEL_EVENT_POOL), 3)

    def test_each_event_has_two_choices(self):
        for event in TRAVEL_EVENT_POOL:
            self.assertEqual(len(event.choices), 2)


class TestApplyTravelOutcomes(unittest.TestCase):
    def test_apply_xp_delta(self):
        hero = make_hero()
        initial_xp = hero.xp
        result = TravelResult(
            events_fired=[],
            chosen_outcomes=[{"xp_delta": 20}],
        )
        apply_travel_outcomes([hero], result)
        self.assertEqual(hero.xp, initial_xp + 20)

    def test_apply_health_delta_positive(self):
        hero = make_hero()
        hero.current_health = 20
        result = TravelResult(
            events_fired=[],
            chosen_outcomes=[{"health_delta": 5}],
        )
        apply_travel_outcomes([hero], result)
        self.assertEqual(hero.current_health, 25)

    def test_clamps_health_to_max_health(self):
        hero = make_hero()
        hero.current_health = 28
        hero.max_health = 30
        result = TravelResult(
            events_fired=[],
            chosen_outcomes=[{"health_delta": 10}],
        )
        apply_travel_outcomes([hero], result)
        self.assertEqual(hero.current_health, 30)

    def test_clamps_health_above_zero(self):
        hero = make_hero()
        hero.current_health = 3
        result = TravelResult(
            events_fired=[],
            chosen_outcomes=[{"health_delta": -10}],
        )
        apply_travel_outcomes([hero], result)
        self.assertEqual(hero.current_health, 0)

    def test_apply_exhaustion_delta(self):
        hero = make_hero()
        initial_exhaustion = hero.exhaustion
        result = TravelResult(
            events_fired=[],
            chosen_outcomes=[{"exhaustion_delta": 5.0}],
        )
        apply_travel_outcomes([hero], result)
        self.assertAlmostEqual(hero.exhaustion, initial_exhaustion + 5.0)

    def test_apply_exhaustion_increases_exhaustion(self):
        hero = make_hero()
        hero.exhaustion = 0.0
        result = TravelResult(
            events_fired=[],
            chosen_outcomes=[{"exhaustion_delta": 3.5}],
        )
        apply_travel_outcomes([hero], result)
        self.assertGreater(hero.exhaustion, 0.0)

    def test_no_outcomes_no_changes(self):
        hero = make_hero()
        initial_health = hero.current_health
        initial_xp = hero.xp
        initial_exhaustion = hero.exhaustion
        result = TravelResult(events_fired=[], chosen_outcomes=[])
        apply_travel_outcomes([hero], result)
        self.assertEqual(hero.current_health, initial_health)
        self.assertEqual(hero.xp, initial_xp)
        self.assertEqual(hero.exhaustion, initial_exhaustion)

    def test_applies_to_all_heroes(self):
        heroes = [make_hero("h1"), make_hero("h2"), make_hero("h3")]
        for h in heroes:
            h.exhaustion = 0.0
        result = TravelResult(
            events_fired=[],
            chosen_outcomes=[{"exhaustion_delta": 2.0}],
        )
        apply_travel_outcomes(heroes, result)
        for h in heroes:
            self.assertAlmostEqual(h.exhaustion, 2.0)


if __name__ == "__main__":
    unittest.main()
