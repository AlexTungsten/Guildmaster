import unittest

from game_runtime.event_bus import EventBus
from game_runtime.state_manager import StateManager


class TestStateManager(unittest.TestCase):
    def setUp(self):
        self.bus = EventBus()
        self.manager = StateManager(self.bus)

    def test_get_and_set_nested_keys(self):
        self.manager.set(42, "heroes", "hero_1", "level")
        result = self.manager.get("heroes", "hero_1", "level")
        self.assertEqual(result, 42)

    def test_get_missing_key_returns_none(self):
        result = self.manager.get("nonexistent", "key")
        self.assertIsNone(result)

    def test_snapshot_is_deep_copy(self):
        self.manager.set({"hp": 30}, "heroes", "hero_1")
        snap = self.manager.snapshot()
        snap["heroes"]["hero_1"]["hp"] = 999
        # Original state should be unchanged
        original = self.manager.get("heroes", "hero_1", "hp")
        self.assertEqual(original, 30)

    def test_serialize_deserialize_round_trip(self):
        self.manager.set("warrior", "party", "leader", "class")
        self.manager.set(100, "party", "gold")
        json_str = self.manager.serialize()

        new_bus = EventBus()
        new_manager = StateManager(new_bus)
        new_manager.deserialize(json_str)

        self.assertEqual(new_manager.get("party", "leader", "class"), "warrior")
        self.assertEqual(new_manager.get("party", "gold"), 100)

    def test_state_changed_event_published_on_set(self):
        events = []
        self.bus.subscribe("state.changed", lambda data: events.append(data))
        self.manager.set(5, "level")
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["keys"], ["level"])
        self.assertEqual(events[0]["value"], 5)

    def test_state_loaded_event_published_on_deserialize(self):
        events = []
        self.bus.subscribe("state.loaded", lambda data: events.append(data))
        self.manager.set(1, "x")
        json_str = self.manager.serialize()
        self.manager.deserialize(json_str)
        self.assertEqual(len(events), 1)
        self.assertIn("state", events[0])


if __name__ == "__main__":
    unittest.main()
