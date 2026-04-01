import unittest
from ui.game_loop import GameLoop


class TestGameLoopCreate(unittest.TestCase):
    def test_create_returns_game_loop_instance(self):
        loop = GameLoop.create(starting_gold=100)
        self.assertIsInstance(loop, GameLoop)

    def test_last_output_empty_before_any_tick(self):
        loop = GameLoop.create(starting_gold=100)
        self.assertEqual(loop.last_output, "")

    def test_tick_appends_to_output_lines(self):
        loop = GameLoop.create(starting_gold=100)
        self.assertEqual(len(loop._output_lines), 0)
        loop.tick()
        self.assertEqual(len(loop._output_lines), 1)

    def test_last_output_nonempty_after_one_tick(self):
        loop = GameLoop.create(starting_gold=100)
        loop.tick()
        self.assertNotEqual(loop.last_output, "")

    def test_handle_input_heroes_changes_screen_to_heroes(self):
        loop = GameLoop.create(starting_gold=100)
        loop.handle_input("heroes")
        self.assertEqual(loop._screen, "heroes")

    def test_handle_input_leave_changes_screen_to_map(self):
        loop = GameLoop.create(starting_gold=100)
        loop.handle_input("heroes")
        self.assertEqual(loop._screen, "heroes")
        loop.handle_input("leave")
        self.assertEqual(loop._screen, "map")

    def test_render_current_screen_map_contains_MAP(self):
        loop = GameLoop.create(starting_gold=100)
        loop._screen = "map"
        result = loop._render_current_screen()
        self.assertIn("MAP", result)

    def test_render_current_screen_heroes_contains_HEROES(self):
        loop = GameLoop.create(starting_gold=100)
        loop._screen = "heroes"
        result = loop._render_current_screen()
        self.assertIn("HEROES", result)

    def test_ten_ticks_produce_ten_output_lines(self):
        loop = GameLoop.create(starting_gold=100)
        for _ in range(10):
            loop.tick()
        self.assertEqual(len(loop._output_lines), 10)

    def test_handle_input_returns_string(self):
        loop = GameLoop.create(starting_gold=100)
        result = loop.handle_input("pause")
        self.assertIsInstance(result, str)

    def test_handle_input_unknown_command_returns_false_message(self):
        loop = GameLoop.create(starting_gold=100)
        result = loop.handle_input("xyzzy")
        self.assertIn("xyzzy", result)

    def test_screen_starts_as_map(self):
        loop = GameLoop.create(starting_gold=100)
        self.assertEqual(loop._screen, "map")

    def test_running_starts_false(self):
        loop = GameLoop.create(starting_gold=100)
        self.assertFalse(loop._running)


if __name__ == "__main__":
    unittest.main()
