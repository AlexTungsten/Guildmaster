import unittest
from game_runtime.event_bus import EventBus
from hero.hero_entity import HeroEntity, HeroStatus
from economy.gold_ledger import GoldLedger
from economy.roster_manager import RosterManager


def make_hero(hero_id="h1", name="Alice", archetype="warrior", status=HeroStatus.IDLE, exhaustion=0.0):
    hero = HeroEntity(hero_id=hero_id, name=name, archetype=archetype)
    hero.status = status
    hero.exhaustion = exhaustion
    return hero


class TestRosterManager(unittest.TestCase):
    def setUp(self):
        self.bus = EventBus()
        self.added_events = []
        self.removed_events = []
        self.bus.subscribe("roster.hero_added", lambda d: self.added_events.append(d))
        self.bus.subscribe("roster.hero_removed", lambda d: self.removed_events.append(d))

    def test_add_hero_increases_count(self):
        roster = RosterManager(self.bus, cap=5)
        hero = make_hero()
        roster.add_hero(hero)
        self.assertEqual(roster.count, 1)

    def test_add_hero_raises_value_error_when_full(self):
        roster = RosterManager(self.bus, cap=1)
        roster.add_hero(make_hero("h1", "Alice"))
        with self.assertRaises(ValueError):
            roster.add_hero(make_hero("h2", "Bob"))

    def test_remove_hero_decreases_count_and_returns_hero(self):
        roster = RosterManager(self.bus, cap=5)
        hero = make_hero("h1", "Alice")
        roster.add_hero(hero)
        removed = roster.remove_hero("h1")
        self.assertEqual(roster.count, 0)
        self.assertIsNotNone(removed)
        self.assertEqual(removed.hero_id, "h1")

    def test_remove_hero_returns_none_for_unknown(self):
        roster = RosterManager(self.bus, cap=5)
        result = roster.remove_hero("nonexistent")
        self.assertIsNone(result)

    def test_idle_heroes_returns_only_idle(self):
        roster = RosterManager(self.bus, cap=5)
        idle = make_hero("h1", "Alice", status=HeroStatus.IDLE)
        traveling = make_hero("h2", "Bob", status=HeroStatus.TRAVELING)
        roster.add_hero(idle)
        roster.add_hero(traveling)
        idle_list = roster.idle_heroes()
        self.assertEqual(len(idle_list), 1)
        self.assertEqual(idle_list[0].hero_id, "h1")

    def test_increase_cap_spends_gold_and_increases_cap(self):
        roster = RosterManager(self.bus, cap=5)
        ledger = GoldLedger(self.bus, starting_gold=100)
        cap_events = []
        self.bus.subscribe("roster.cap_increased", lambda d: cap_events.append(d))
        result = roster.increase_cap(ledger, cost=50, amount=5)
        self.assertTrue(result)
        self.assertEqual(roster.cap, 10)
        self.assertEqual(ledger.balance, 50)
        self.assertEqual(len(cap_events), 1)
        self.assertEqual(cap_events[0]["new_cap"], 10)

    def test_increase_cap_returns_false_when_insufficient_gold(self):
        roster = RosterManager(self.bus, cap=5)
        ledger = GoldLedger(self.bus, starting_gold=10)
        result = roster.increase_cap(ledger, cost=50, amount=5)
        self.assertFalse(result)
        self.assertEqual(roster.cap, 5)

    def test_tick_exhaustion_recovery_reduces_idle_exhaustion(self):
        roster = RosterManager(self.bus, cap=5)
        hero = make_hero("h1", "Alice", exhaustion=10.0)
        roster.add_hero(hero)
        roster.tick_exhaustion_recovery(seconds=2.0)
        self.assertAlmostEqual(hero.exhaustion, 8.0)

    def test_tick_exhaustion_no_effect_on_non_idle_heroes(self):
        roster = RosterManager(self.bus, cap=5)
        hero = make_hero("h1", "Alice", status=HeroStatus.TRAVELING, exhaustion=10.0)
        roster.add_hero(hero)
        roster.tick_exhaustion_recovery(seconds=2.0)
        self.assertAlmostEqual(hero.exhaustion, 10.0)

    def test_hero_added_event_published(self):
        roster = RosterManager(self.bus, cap=5)
        hero = make_hero("h1", "Alice")
        roster.add_hero(hero)
        self.assertEqual(len(self.added_events), 1)
        self.assertEqual(self.added_events[0]["hero_id"], "h1")
        self.assertEqual(self.added_events[0]["name"], "Alice")

    def test_hero_removed_event_published(self):
        roster = RosterManager(self.bus, cap=5)
        hero = make_hero("h1", "Alice")
        roster.add_hero(hero)
        roster.remove_hero("h1")
        self.assertEqual(len(self.removed_events), 1)
        self.assertEqual(self.removed_events[0]["hero_id"], "h1")

    def test_to_dict_from_dict_round_trip(self):
        roster = RosterManager(self.bus, cap=10)
        hero = make_hero("h1", "Alice", exhaustion=5.0)
        roster.add_hero(hero)
        data = roster.to_dict()
        new_bus = EventBus()
        restored = RosterManager.from_dict(data, new_bus)
        self.assertEqual(restored.cap, 10)
        self.assertEqual(restored.count, 1)
        self.assertIsNotNone(restored.get_hero("h1"))
        self.assertAlmostEqual(restored.get_hero("h1").exhaustion, 5.0)


if __name__ == "__main__":
    unittest.main()
