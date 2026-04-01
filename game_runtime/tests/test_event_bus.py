import unittest

from game_runtime.event_bus import EventBus


class TestEventBus(unittest.TestCase):
    def setUp(self):
        self.bus = EventBus()

    def test_subscribe_and_publish_fires_handler(self):
        received = []
        self.bus.subscribe("test.event", lambda data: received.append(data))
        self.bus.publish("test.event", "hello")
        self.assertEqual(received, ["hello"])

    def test_unsubscribe_stops_handler(self):
        received = []

        def handler(data):
            received.append(data)

        self.bus.subscribe("test.event", handler)
        self.bus.unsubscribe("test.event", handler)
        self.bus.publish("test.event", "hello")
        self.assertEqual(received, [])

    def test_multiple_handlers_all_fire(self):
        results_a = []
        results_b = []
        self.bus.subscribe("test.event", lambda data: results_a.append(data))
        self.bus.subscribe("test.event", lambda data: results_b.append(data))
        self.bus.publish("test.event", 42)
        self.assertEqual(results_a, [42])
        self.assertEqual(results_b, [42])

    def test_publish_with_no_subscribers_is_safe(self):
        # Should not raise
        self.bus.publish("nonexistent.event", "data")

    def test_subscribe_during_publish_not_called_in_same_cycle(self):
        called_count = []

        def first_handler(data):
            called_count.append("first")
            # subscribe a second handler during publish
            self.bus.subscribe("test.event", second_handler)

        def second_handler(data):
            called_count.append("second")

        self.bus.subscribe("test.event", first_handler)
        self.bus.publish("test.event", None)
        # second_handler should NOT have been called in this publish cycle
        self.assertNotIn("second", called_count)
        self.assertIn("first", called_count)

        # But it should fire on the next publish
        called_count.clear()
        self.bus.publish("test.event", None)
        self.assertIn("second", called_count)


if __name__ == "__main__":
    unittest.main()
