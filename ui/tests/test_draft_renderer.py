import unittest
from ui.renderers.draft_renderer import render_draft_screen, render_run_start_screen


class TestRenderDraftScreen(unittest.TestCase):
    def setUp(self):
        self.archetypes = [
            {"name": "Warrior", "description": "Tough melee fighter"},
            {"name": "Mage", "description": "Powerful spellcaster"},
            {"name": "Rogue"},
        ]
        self.roster = [
            {"name": "Alice", "archetype": "Warrior"},
            {"name": "Bob", "archetype": "Mage"},
        ]

    def test_contains_hero_draft_header(self):
        result = render_draft_screen(self.archetypes, 3, [])
        self.assertIn("HERO DRAFT", result)

    def test_lists_all_archetypes(self):
        result = render_draft_screen(self.archetypes, 3, [])
        self.assertIn("Warrior", result)
        self.assertIn("Mage", result)
        self.assertIn("Rogue", result)

    def test_shows_picks_remaining(self):
        result = render_draft_screen(self.archetypes, 5, [])
        self.assertIn("5", result)

    def test_shows_current_roster_heroes(self):
        result = render_draft_screen(self.archetypes, 1, self.roster)
        self.assertIn("Alice", result)
        self.assertIn("Bob", result)

    def test_shows_empty_roster_when_none(self):
        result = render_draft_screen(self.archetypes, 3, [])
        self.assertIn("Empty", result)

    def test_archetype_description_shown_when_present(self):
        result = render_draft_screen(self.archetypes, 3, [])
        self.assertIn("Tough melee fighter", result)

    def test_archetype_without_description_still_shown(self):
        result = render_draft_screen(self.archetypes, 3, [])
        self.assertIn("Rogue", result)

    def test_contains_done_instruction(self):
        result = render_draft_screen(self.archetypes, 3, [])
        self.assertIn("done", result)


class TestRenderRunStartScreen(unittest.TestCase):
    def setUp(self):
        self.roster = [
            {"name": "Alice", "archetype": "Warrior"},
            {"name": "Bob", "archetype": "Mage"},
        ]
        self.boss = {"name": "The Dragon", "act": 1}

    def test_contains_boss_name(self):
        result = render_run_start_screen(self.roster, self.boss)
        self.assertIn("The Dragon", result)

    def test_contains_all_hero_names(self):
        result = render_run_start_screen(self.roster, self.boss)
        self.assertIn("Alice", result)
        self.assertIn("Bob", result)

    def test_contains_run_begins_header(self):
        result = render_run_start_screen(self.roster, self.boss)
        self.assertIn("RUN BEGINS", result)

    def test_contains_act_number(self):
        result = render_run_start_screen(self.roster, self.boss)
        self.assertIn("Act 1", result)

    def test_contains_press_enter(self):
        result = render_run_start_screen(self.roster, self.boss)
        self.assertIn("ENTER", result)

    def test_boss_fallback_to_boss_id(self):
        boss = {"boss_id": "boss_dragon", "act": 2}
        result = render_run_start_screen(self.roster, boss)
        self.assertIn("boss_dragon", result)


if __name__ == "__main__":
    unittest.main()
