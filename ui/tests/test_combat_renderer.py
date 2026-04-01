import unittest
from ui.renderers.combat_renderer import (
    render_combat_view,
    render_hp_bar,
    render_dice_pool,
    render_skill_assignments,
)


def make_hero(name="Alice", current_health=20, max_health=30, exhaustion=0.0):
    return {
        "name": name,
        "current_health": current_health,
        "max_health": max_health,
        "exhaustion": exhaustion,
    }


def make_enemy(name="Goblin", current_health=15, max_health=15):
    return {
        "name": name,
        "current_health": current_health,
        "max_health": max_health,
    }


class TestRenderCombatView(unittest.TestCase):
    def setUp(self):
        self.heroes = [make_hero("Alice"), make_hero("Bob", 10, 30)]
        self.enemies = [make_enemy("Goblin"), make_enemy("Orc", 20, 25)]

    def test_contains_round_number(self):
        result = render_combat_view(self.heroes, self.enemies, round_number=5)
        self.assertIn("Round 5", result)

    def test_shows_all_hero_names(self):
        result = render_combat_view(self.heroes, self.enemies, round_number=1)
        self.assertIn("Alice", result)
        self.assertIn("Bob", result)

    def test_shows_all_enemy_names(self):
        result = render_combat_view(self.heroes, self.enemies, round_number=1)
        self.assertIn("Goblin", result)
        self.assertIn("Orc", result)

    def test_shows_pre_sim_result_victory(self):
        pre_sim = {"victory": True, "rounds": [1, 2, 3]}
        result = render_combat_view(self.heroes, self.enemies, round_number=1, pre_sim_result=pre_sim)
        self.assertIn("PRE-SIMULATION", result)
        self.assertIn("VICTORY", result)
        self.assertIn("3 rounds", result)

    def test_shows_pre_sim_result_defeat(self):
        pre_sim = {"victory": False, "rounds": [1, 2]}
        result = render_combat_view(self.heroes, self.enemies, round_number=1, pre_sim_result=pre_sim)
        self.assertIn("DEFEAT", result)

    def test_shows_intervention_timer(self):
        result = render_combat_view(
            self.heroes, self.enemies, round_number=1,
            intervention_seconds_remaining=10
        )
        self.assertIn("10s remaining", result)
        self.assertIn("Intervene", result)

    def test_no_pre_sim_by_default(self):
        result = render_combat_view(self.heroes, self.enemies, round_number=1)
        self.assertNotIn("PRE-SIMULATION", result)

    def test_no_intervention_by_default(self):
        result = render_combat_view(self.heroes, self.enemies, round_number=1)
        self.assertNotIn("Intervene", result)

    def test_autoplay_footer_when_no_intervention(self):
        result = render_combat_view(self.heroes, self.enemies, round_number=1)
        self.assertIn("auto", result)

    def test_manual_footer_when_intervention(self):
        result = render_combat_view(
            self.heroes, self.enemies, round_number=1,
            intervention_seconds_remaining=5
        )
        self.assertIn("manual", result)


class TestRenderHpBar(unittest.TestCase):
    def test_fills_correctly_at_full_health(self):
        result = render_hp_bar(30, 30, width=10)
        self.assertIn("#" * 10, result)
        self.assertIn("30/30", result)

    def test_shows_zero_filled_at_zero_health(self):
        result = render_hp_bar(0, 30, width=10)
        self.assertIn("." * 10, result)
        self.assertIn("0/30", result)

    def test_partial_fill(self):
        result = render_hp_bar(15, 30, width=10)
        self.assertIn("#####", result)
        self.assertIn("15/30", result)

    def test_bar_format(self):
        result = render_hp_bar(10, 20)
        self.assertTrue(result.startswith("["))
        self.assertIn("]", result)
        self.assertIn("10/20", result)

    def test_zero_max_health(self):
        result = render_hp_bar(0, 0)
        self.assertIn("0/0", result)


class TestRenderDicePool(unittest.TestCase):
    def test_shows_locked_and_normal_dice(self):
        result = render_dice_pool([3, 5], [1, 4, 6])
        self.assertIn("LOCKED", result)
        self.assertIn("Normal", result)
        self.assertIn("3", result)
        self.assertIn("5", result)
        self.assertIn("1", result)
        self.assertIn("4", result)
        self.assertIn("6", result)

    def test_empty_dice_pools(self):
        result = render_dice_pool([], [])
        self.assertIn("LOCKED", result)
        self.assertIn("Normal", result)

    def test_format(self):
        result = render_dice_pool([2], [4])
        self.assertIn("Dice Pool:", result)


class TestRenderSkillAssignments(unittest.TestCase):
    def test_shows_skill_name_and_dice(self):
        assignments = [
            {"skill_name": "Slash", "dice_slots": 2, "assigned_dice": [3, 5], "effectiveness": 8},
        ]
        result = render_skill_assignments(assignments)
        self.assertIn("Slash", result)
        self.assertIn("2 slots", result)
        self.assertIn("Effectiveness=8", result)

    def test_multiple_assignments(self):
        assignments = [
            {"skill_name": "Slash", "dice_slots": 2, "assigned_dice": [3], "effectiveness": 4},
            {"skill_name": "Heal", "dice_slots": 1, "assigned_dice": [6], "effectiveness": 6},
        ]
        result = render_skill_assignments(assignments)
        self.assertIn("Slash", result)
        self.assertIn("Heal", result)

    def test_empty_assignments(self):
        result = render_skill_assignments([])
        self.assertEqual(result, "")


if __name__ == "__main__":
    unittest.main()
