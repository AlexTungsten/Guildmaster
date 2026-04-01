import unittest

from game_runtime.event_bus import EventBus
from game_runtime.time_engine import TimeEngine


class TestTimeEngine(unittest.TestCase):
    def setUp(self):
        self.bus = EventBus()
        self.engine = TimeEngine(self.bus)

    def test_advance_increments_tick(self):
        self.engine.advance(3)
        self.assertEqual(self.engine.tick, 3)

    def test_paused_engine_does_not_advance(self):
        self.engine.pause("combat")
        self.engine.advance(5)
        self.assertEqual(self.engine.tick, 0)

    def test_multiple_pause_reasons_all_must_clear(self):
        self.engine.pause("combat")
        self.engine.pause("dialogue")
        self.engine.resume("combat")
        self.engine.advance(1)
        # Still paused due to "dialogue"
        self.assertEqual(self.engine.tick, 0)
        self.engine.resume("dialogue")
        self.engine.advance(1)
        self.assertEqual(self.engine.tick, 1)

    def test_resume_one_reason_while_another_active_stays_paused(self):
        self.engine.pause("reason_a")
        self.engine.pause("reason_b")
        self.engine.resume("reason_a")
        self.assertTrue(self.engine.is_paused)
        self.engine.advance(1)
        self.assertEqual(self.engine.tick, 0)

    def test_scheduled_event_fires_at_correct_tick(self):
        fired = []
        self.bus.subscribe("my.event", lambda data: fired.append(data))
        self.engine.schedule(3, "my.event", {"info": "test"})
        self.engine.advance(2)
        self.assertEqual(fired, [])
        self.engine.advance(1)
        self.assertEqual(len(fired), 1)
        self.assertEqual(fired[0]["info"], "test")

    def test_scheduled_event_does_not_fire_early(self):
        fired = []
        self.bus.subscribe("early.event", lambda data: fired.append(data))
        self.engine.schedule(5, "early.event", None)
        self.engine.advance(4)
        self.assertEqual(fired, [])

    def test_speed_multiplier_affects_tick_advancement(self):
        self.engine.set_speed(2.0)
        self.engine.advance(1)
        self.assertEqual(self.engine.tick, 2)

    def test_time_tick_event_published_each_tick(self):
        ticks_received = []
        self.bus.subscribe("time.tick", lambda data: ticks_received.append(data["tick"]))
        self.engine.advance(3)
        self.assertEqual(ticks_received, [1, 2, 3])

    def test_to_dict_from_dict_round_trip(self):
        self.engine.pause("saving")
        self.engine.set_speed(1.5)
        self.engine.advance(0)  # tick stays 0 (paused)
        self.engine.resume("saving")
        self.engine.advance(2)
        self.engine.schedule(5, "future.event", {"key": "value"})

        data = self.engine.to_dict()
        new_bus = EventBus()
        restored = TimeEngine.from_dict(data, new_bus)

        self.assertEqual(restored.tick, self.engine.tick)
        self.assertEqual(restored._speed, self.engine._speed)
        self.assertEqual(restored._pause_reasons, self.engine._pause_reasons)
        self.assertEqual(len(restored._scheduled), len(self.engine._scheduled))


if __name__ == "__main__":
    unittest.main()
