import unittest
from game_runtime.event_bus import EventBus
from ui.action_dispatcher import ActionDispatcher


class TestActionDispatcher(unittest.TestCase):
    def setUp(self):
        self.event_bus = EventBus()
        self.dispatcher = ActionDispatcher(self.event_bus)
        self.received = {}

    def _subscribe(self, event_type):
        def handler(data):
            self.received[event_type] = data
        self.event_bus.subscribe(event_type, handler)

    def test_assign_quest_publishes_event(self):
        self._subscribe("player.assign_quest")
        success, msg = self.dispatcher.dispatch("assign q_1 hero_1 hero_2")
        self.assertTrue(success)
        self.assertIn("player.assign_quest", self.received)
        data = self.received["player.assign_quest"]
        self.assertEqual(data["quest_id"], "q_1")
        self.assertEqual(data["hero_ids"], ["hero_1", "hero_2"])

    def test_open_shop_publishes_event(self):
        self._subscribe("player.open_shop")
        success, msg = self.dispatcher.dispatch("shop shop_1")
        self.assertTrue(success)
        self.assertIn("player.open_shop", self.received)
        self.assertEqual(self.received["player.open_shop"]["shop_id"], "shop_1")

    def test_hire_hero_publishes_event(self):
        self._subscribe("player.hire_hero")
        success, msg = self.dispatcher.dispatch("hire hero_1")
        self.assertTrue(success)
        self.assertIn("player.hire_hero", self.received)
        self.assertEqual(self.received["player.hire_hero"]["hero_id"], "hero_1")

    def test_buy_item_publishes_event(self):
        self._subscribe("player.buy_item")
        success, msg = self.dispatcher.dispatch("buy item_1")
        self.assertTrue(success)
        self.assertIn("player.buy_item", self.received)
        self.assertEqual(self.received["player.buy_item"]["item_id"], "item_1")

    def test_train_skill_publishes_event_with_int_slot(self):
        self._subscribe("player.train_skill")
        success, msg = self.dispatcher.dispatch("train skill_1 hero_1 0")
        self.assertTrue(success)
        self.assertIn("player.train_skill", self.received)
        data = self.received["player.train_skill"]
        self.assertEqual(data["skill_id"], "skill_1")
        self.assertEqual(data["hero_id"], "hero_1")
        self.assertEqual(data["slot"], 0)
        self.assertIsInstance(data["slot"], int)

    def test_leave_publishes_event(self):
        self._subscribe("player.leave_shop")
        success, msg = self.dispatcher.dispatch("leave")
        self.assertTrue(success)
        self.assertIn("player.leave_shop", self.received)

    def test_pause_publishes_event(self):
        self._subscribe("player.toggle_pause")
        success, msg = self.dispatcher.dispatch("pause")
        self.assertTrue(success)
        self.assertIn("player.toggle_pause", self.received)

    def test_manual_publishes_event(self):
        self._subscribe("player.manual_combat")
        success, msg = self.dispatcher.dispatch("manual")
        self.assertTrue(success)
        self.assertIn("player.manual_combat", self.received)

    def test_draft_uppercase_publishes_event_with_int_index(self):
        self._subscribe("player.draft_hero")
        success, msg = self.dispatcher.dispatch("DRAFT 2")
        self.assertTrue(success)
        self.assertIn("player.draft_hero", self.received)
        data = self.received["player.draft_hero"]
        self.assertEqual(data["index"], 2)
        self.assertIsInstance(data["index"], int)

    def test_quit_publishes_event(self):
        self._subscribe("player.quit")
        success, msg = self.dispatcher.dispatch("quit")
        self.assertTrue(success)
        self.assertIn("player.quit", self.received)

    def test_unknown_command_returns_false_and_no_publish(self):
        events_seen = []
        for event in [
            "player.assign_quest", "player.open_shop", "player.hire_hero",
            "player.buy_item", "player.train_skill", "player.leave_shop",
            "player.toggle_pause", "player.manual_combat", "player.draft_hero",
            "player.quit", "player.view_heroes", "player.view_items",
        ]:
            self.event_bus.subscribe(event, lambda d, e=event: events_seen.append(e))

        success, msg = self.dispatcher.dispatch("xyz")
        self.assertFalse(success)
        self.assertIn("xyz", msg)
        self.assertEqual(events_seen, [])

    def test_dispatch_returns_true_for_all_valid_commands(self):
        valid_commands = [
            "assign q_1 hero_1",
            "shop shop_1",
            "hire hero_1",
            "buy item_1",
            "train skill_1 hero_1 0",
            "leave",
            "heroes",
            "items",
            "pause",
            "manual",
            "draft 1",
            "quit",
        ]
        for cmd in valid_commands:
            success, msg = self.dispatcher.dispatch(cmd)
            self.assertTrue(success, f"Expected True for command: {cmd!r}, got msg={msg!r}")

    def test_heroes_publishes_event(self):
        self._subscribe("player.view_heroes")
        success, msg = self.dispatcher.dispatch("heroes")
        self.assertTrue(success)
        self.assertIn("player.view_heroes", self.received)

    def test_items_publishes_event(self):
        self._subscribe("player.view_items")
        success, msg = self.dispatcher.dispatch("items")
        self.assertTrue(success)
        self.assertIn("player.view_items", self.received)


if __name__ == "__main__":
    unittest.main()
