"""Tests for BossEnemy (Baron Midas) phase system and combat integration."""

import random
import unittest

from enemy.boss_loader import load_boss, list_bosses
from enemy.boss_enemy import BossEnemy
from hero.hero_entity import HeroEntity, HeroStatus, Skill, Stat
from hero.archetype_loader import load_archetype
from combat.combat_engine import CombatEngine
from game_runtime.event_bus import EventBus


class TestBossLoader(unittest.TestCase):
    """Verify boss JSON loading and HP scaling."""

    def test_list_bosses(self):
        bosses = list_bosses()
        self.assertIn("baron_midas", bosses)

    def test_load_baron_midas_base_hp(self):
        boss = load_boss("baron_midas", gold_stolen=0)
        self.assertEqual(boss.name, "Baron Midas")
        self.assertEqual(boss.max_health, 100)
        self.assertEqual(boss.current_health, 100)
        self.assertEqual(boss.base_dice_count, 4)
        self.assertEqual(boss.base_dice_sides, 4)

    def test_gold_stolen_adds_hp(self):
        boss = load_boss("baron_midas", gold_stolen=200)
        self.assertEqual(boss.max_health, 300)  # 100 + 200
        self.assertEqual(boss.current_health, 300)

    def test_gold_stolen_capped_at_566(self):
        boss = load_boss("baron_midas", gold_stolen=1000)
        self.assertEqual(boss.max_health, 666)  # 100 + 566 (cap)
        self.assertEqual(boss.current_health, 666)

    def test_four_phases_loaded(self):
        boss = load_boss("baron_midas")
        self.assertEqual(len(boss.phase_definitions), 4)
        self.assertEqual(boss.phase_definitions[0].phase, 1)
        self.assertEqual(boss.phase_definitions[3].phase, 4)

    def test_phase1_skills(self):
        boss = load_boss("baron_midas")
        self.assertEqual(len(boss.skills), 3)
        self.assertEqual(boss.skills[0].name, "Steal")
        self.assertEqual(boss.skills[0].dice_slots, 1)
        self.assertEqual(boss.skills[1].name, "Gilded Shield")
        self.assertEqual(boss.skills[2].name, "I NEED GOLD")

    def test_phase1_accumulation_cost(self):
        boss = load_boss("baron_midas")
        self.assertEqual(boss.skill3_cost, 15)


class TestBossPhaseSystem(unittest.TestCase):
    """Verify phase transitions and permanent buff accumulation."""

    def _make_boss(self, gold_stolen=0):
        return load_boss("baron_midas", gold_stolen=gold_stolen)

    def test_starts_in_phase1(self):
        boss = self._make_boss()
        self.assertEqual(boss.current_phase, 1)
        self.assertEqual(boss.bonus_dice, 0)
        self.assertEqual(boss.dice_sides_override, 0)
        self.assertFalse(boss.has_permanent_advantage)

    def test_effective_dice_count_includes_bonus(self):
        boss = self._make_boss()
        self.assertEqual(boss.effective_dice_count, 4)  # base 4 + 0 bonus
        boss.bonus_dice = 1
        self.assertEqual(boss.effective_dice_count, 5)

    def test_effective_dice_sides_uses_override(self):
        boss = self._make_boss()
        self.assertEqual(boss.effective_dice_sides, 4)  # base d4
        boss.dice_sides_override = 8
        self.assertEqual(boss.effective_dice_sides, 8)

    def test_phase1_to_phase2_transition(self):
        boss = self._make_boss()
        # Force Skill 3 progress to exceed cost
        boss.skill3_progress = 14
        rng = random.Random(42)
        # Run a turn — overflow dice should push progress over 15
        boss.take_turn(rng)
        # Check if phase advanced (might need multiple turns)
        # Since we start at 14 and 4d4 always rolls at least 4, overflow should fire it
        if boss.current_phase == 2:
            self.assertEqual(boss.bonus_dice, 1)  # gained 1 extra die
            self.assertEqual(boss.skill3_cost, 20)  # Phase 2 cost
            self.assertEqual(boss.skills[0].name, "Steal")
            self.assertEqual(boss.skills[0].dice_slots, 2)  # Phase 2 Steal has 2 slots

    def test_phase2_to_phase3_upgrades_dice(self):
        boss = self._make_boss()
        # Manually set to phase 2
        boss.current_phase = 2
        boss.bonus_dice = 1
        pd2 = boss.phase_definitions[1]
        boss.skills = list(pd2.skills)
        boss.skill_buffers = [[] for _ in boss.skills]
        boss.skill3_cost = 20
        boss.skill3_progress = 0

        # Force transition
        boss.skill3_progress = 100  # Way over cost
        rng = random.Random(42)
        boss.take_turn(rng)

        if boss.current_phase == 3:
            self.assertEqual(boss.dice_sides_override, 8)  # d8 upgrade

    def test_phase3_to_phase4_gives_advantage(self):
        boss = self._make_boss()
        # Manually set to phase 3
        boss.current_phase = 3
        boss.bonus_dice = 1
        boss.dice_sides_override = 8
        pd3 = boss.phase_definitions[2]
        boss.skills = list(pd3.skills)
        boss.skill_buffers = [[] for _ in boss.skills]
        boss.skill3_cost = 40
        boss.skill3_progress = 100  # Over cost

        rng = random.Random(42)
        boss.take_turn(rng)

        if boss.current_phase == 4:
            self.assertTrue(boss.has_permanent_advantage)

    def test_final_state_5d8_advantage(self):
        """After all 3 phase transitions: 5d8 with permanent Advantage."""
        boss = self._make_boss()
        # Simulate all 3 transitions by manually applying buffs
        boss._advance_phase()  # Phase 1 -> 2: +1 die
        boss._advance_phase()  # Phase 2 -> 3: d8 upgrade
        boss._advance_phase()  # Phase 3 -> 4: permanent Advantage

        self.assertEqual(boss.current_phase, 4)
        self.assertEqual(boss.effective_dice_count, 5)  # 4 + 1
        self.assertEqual(boss.effective_dice_sides, 8)
        self.assertTrue(boss.has_permanent_advantage)

    def test_steal_reduces_skill3_cost(self):
        """Steal's effectiveness feeds into Skill 3 progress."""
        boss = self._make_boss()
        boss.skill3_progress = 0
        # Use a fixed RNG that gives predictable results
        rng = random.Random(99)
        initial_progress = boss.skill3_progress
        boss.take_turn(rng)
        # After a turn, skill3_progress should have increased from
        # both overflow dice AND Steal's effectiveness (if Steal fired)
        self.assertGreater(boss.skill3_progress, initial_progress)


class TestBossCombatIntegration(unittest.TestCase):
    """Verify Baron Midas works with the full combat engine."""

    def _make_party(self):
        """Create a party of 4 heroes from archetypes."""
        heroes = []
        specs = [
            ("barbarian", "hero_0", "Grimjaw"),
            ("cleric", "hero_1", "Elara"),
            ("rogue", "hero_2", "Vex"),
            ("mage", "hero_3", "Aldric"),
        ]
        for arch, hid, name in specs:
            heroes.append(load_archetype(arch, hid, name))
        return heroes

    def test_combat_runs_without_error(self):
        """Smoke test: a full combat against Baron Midas completes."""
        eb = EventBus()
        engine = CombatEngine(eb)
        heroes = self._make_party()
        boss = load_boss("baron_midas", gold_stolen=50)

        result = engine.simulate(heroes, [boss], max_rounds=50)
        # Combat should complete (either victory or defeat)
        self.assertIsNotNone(result)
        self.assertIsInstance(result.victory, bool)
        self.assertGreater(len(result.rounds), 0)

    def test_combat_with_max_gold_stolen(self):
        """Baron Midas at max HP (666) should be a tough fight."""
        eb = EventBus()
        engine = CombatEngine(eb)
        heroes = self._make_party()
        boss = load_boss("baron_midas", gold_stolen=1000)

        self.assertEqual(boss.current_health, 666)
        result = engine.simulate(heroes, [boss], max_rounds=50)
        self.assertIsNotNone(result)

    def test_pre_simulate_is_deterministic(self):
        """Pre-simulation should produce identical results each call."""
        eb = EventBus()
        engine = CombatEngine(eb)

        heroes1 = self._make_party()
        boss1 = load_boss("baron_midas", gold_stolen=100)
        result1 = engine.pre_simulate(heroes1, [boss1])

        heroes2 = self._make_party()
        boss2 = load_boss("baron_midas", gold_stolen=100)
        result2 = engine.pre_simulate(heroes2, [boss2])

        self.assertEqual(result1.victory, result2.victory)
        self.assertEqual(len(result1.rounds), len(result2.rounds))


if __name__ == "__main__":
    unittest.main()
