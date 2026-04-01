import random
import unittest

from overworld.map_state import MapState
from overworld.quest_spawner import QuestSpawner
from game_runtime.event_bus import EventBus


class TestQuestSpawner(unittest.TestCase):
    def setUp(self):
        self.bus = EventBus()
        self.rng = random.Random(42)
        self.spawner = QuestSpawner(
            event_bus=self.bus,
            spawn_interval=60,
            max_active_quests=5,
            rng=self.rng,
        )

    def test_spawns_quest_after_spawn_interval(self):
        ms = MapState(current_act=1)
        quest = self.spawner.tick(ms, current_tick=60)
        self.assertIsNotNone(quest)
        self.assertEqual(len(ms.active_quests), 1)

    def test_does_not_spawn_before_interval_elapses(self):
        ms = MapState(current_act=1)
        quest = self.spawner.tick(ms, current_tick=59)
        self.assertIsNone(quest)
        self.assertEqual(len(ms.active_quests), 0)

    def test_does_not_spawn_when_at_max_active_quests(self):
        ms = MapState(current_act=1)
        # fill up to max
        self.spawner.tick(ms, current_tick=60)
        # advance time to allow next spawn
        for i in range(1, 5):
            self.spawner.tick(ms, current_tick=60 + i * 60)
        # now at max (5)
        self.assertEqual(len(ms.active_quests), 5)
        quest = self.spawner.tick(ms, current_tick=60 + 5 * 60)
        self.assertIsNone(quest)

    def test_spawned_quest_has_correct_spawned_at_tick(self):
        ms = MapState(current_act=1)
        quest = self.spawner.tick(ms, current_tick=60)
        self.assertEqual(quest.spawned_at_tick, 60)

    def test_spawned_quest_id_includes_tick(self):
        ms = MapState(current_act=1)
        quest = self.spawner.tick(ms, current_tick=120)
        self.assertEqual(quest.quest_id, "q_120")

    def test_quest_spawned_event_published(self):
        ms = MapState(current_act=1)

        received = []
        self.bus.subscribe("quest.spawned", lambda d: received.append(d))

        self.spawner.tick(ms, current_tick=60)
        self.assertEqual(len(received), 1)
        self.assertIn("quest_id", received[0])
        self.assertIn("difficulty", received[0])
        self.assertEqual(received[0]["act"], 1)

    def test_does_not_spawn_on_second_tick_without_interval(self):
        ms = MapState(current_act=1)
        self.spawner.tick(ms, current_tick=60)
        quest2 = self.spawner.tick(ms, current_tick=61)
        self.assertIsNone(quest2)


if __name__ == "__main__":
    unittest.main()
