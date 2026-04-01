import unittest
from ui.renderers.map_renderer import render_map_screen, render_boss_timer_bar


class TestRenderMapScreen(unittest.TestCase):
    def setUp(self):
        self.quests = [
            {
                "quest_id": "q_1",
                "title": "Goblin Raid",
                "difficulty": "easy",
                "expiry": 120,
                "status": "available",
                "assigned_hero_ids": [],
            }
        ]
        self.shops = [
            {"shop_id": "shop_1", "expiry": 60}
        ]
        self.boss = {"boss_id": "boss_1", "act": 1, "revealed": False, "buffs": []}
        self.heroes = [
            {"name": "Alice", "status": "idle", "exhaustion": 0.0},
            {"name": "Bob", "status": "on_quest", "exhaustion": 25.0},
        ]

    def test_contains_act_number(self):
        result = render_map_screen(
            self.quests, self.shops, self.boss,
            current_tick=10, act=2, boss_ticks_remaining=500,
            hero_statuses=self.heroes
        )
        self.assertIn("ACT 2", result)

    def test_contains_tick(self):
        result = render_map_screen(
            self.quests, self.shops, self.boss,
            current_tick=42, act=1, boss_ticks_remaining=500,
            hero_statuses=self.heroes
        )
        self.assertIn("42", result)

    def test_shows_quest_titles(self):
        result = render_map_screen(
            self.quests, self.shops, self.boss,
            current_tick=0, act=1, boss_ticks_remaining=600,
            hero_statuses=self.heroes
        )
        self.assertIn("Goblin Raid", result)

    def test_shows_boss_ticks_remaining(self):
        result = render_map_screen(
            self.quests, self.shops, self.boss,
            current_tick=0, act=1, boss_ticks_remaining=350,
            hero_statuses=self.heroes
        )
        self.assertIn("350", result)

    def test_shows_hero_statuses(self):
        result = render_map_screen(
            self.quests, self.shops, self.boss,
            current_tick=0, act=1, boss_ticks_remaining=600,
            hero_statuses=self.heroes
        )
        self.assertIn("Alice", result)
        self.assertIn("Bob", result)

    def test_boss_not_yet_revealed(self):
        result = render_map_screen(
            self.quests, self.shops, self.boss,
            current_tick=0, act=1, boss_ticks_remaining=600,
            hero_statuses=self.heroes
        )
        self.assertIn("Not yet revealed", result)

    def test_boss_revealed(self):
        boss = {"boss_id": "boss_1", "act": 1, "revealed": True, "buffs": ["enraged"]}
        result = render_map_screen(
            self.quests, self.shops, boss,
            current_tick=0, act=1, boss_ticks_remaining=100,
            hero_statuses=self.heroes
        )
        self.assertIn("boss_1", result)
        self.assertIn("enraged", result)

    def test_no_boss(self):
        result = render_map_screen(
            self.quests, self.shops, None,
            current_tick=0, act=1, boss_ticks_remaining=600,
            hero_statuses=self.heroes
        )
        self.assertIn("Not yet revealed", result)

    def test_shop_shown(self):
        result = render_map_screen(
            self.quests, self.shops, self.boss,
            current_tick=0, act=1, boss_ticks_remaining=600,
            hero_statuses=self.heroes
        )
        self.assertIn("shop_1", result)


class TestRenderBossTimerBar(unittest.TestCase):
    def test_output_has_correct_length_markers(self):
        result = render_boss_timer_bar(300, 600, width=40)
        self.assertIn("[", result)
        self.assertIn("]", result)
        self.assertIn("300/600", result)

    def test_zero_remaining_at_end(self):
        result = render_boss_timer_bar(0, 600, width=40)
        self.assertIn("0/600", result)
        # All filled
        self.assertIn("#" * 40, result)

    def test_full_remaining_empty_bar(self):
        result = render_boss_timer_bar(600, 600, width=10)
        self.assertIn("." * 10, result)
        self.assertIn("600/600", result)

    def test_half_remaining(self):
        result = render_boss_timer_bar(300, 600, width=10)
        self.assertIn("#####", result)
        self.assertIn("300/600", result)

    def test_bar_width_correct(self):
        width = 20
        result = render_boss_timer_bar(200, 600, width=width)
        # Extract bar content between [ and ]
        start = result.index("[") + 1
        end = result.index("]")
        bar_content = result[start:end]
        self.assertEqual(len(bar_content), width)


if __name__ == "__main__":
    unittest.main()
