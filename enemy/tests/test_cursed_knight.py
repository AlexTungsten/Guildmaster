"""Tests for the CursedKnightEnemy — critical quest variant mechanics."""

import random
import unittest

from hero.hero_entity import Skill, Stat
from enemy.special_enemies import CursedKnightEnemy
from enemy.enemy_loader import load_enemy


def _rng(seed: int = 0) -> random.Random:
    return random.Random(seed)


def _make_knight(
    hp: int = 250,
    bloodlust: int = 125,
    max_turns: int = 2,
) -> CursedKnightEnemy:
    """Build a CursedKnightEnemy directly without the JSON loader."""
    slash = Skill(
        name="Slash", description="",
        associated_stat=Stat.STR, dice_slots=1,
        effect_type="damage", special="bleed",
    )
    shield = Skill(
        name="Worn Down Shield", description="",
        associated_stat=Stat.CON, dice_slots=1,
        effect_type="defend",
    )
    cleave = Skill(
        name="Blood Cleave", description="",
        associated_stat=Stat.STR, dice_slots=2,
        effect_type="aoe", special="bleed",
    )
    knight = CursedKnightEnemy(
        enemy_id="cursed_knight",
        name="Cursed Knight",
        archetype="cursed_knight",
        act=1,
        max_health=hp,
        current_health=hp,
        skills=[slash, shield, cleave],
        base_dice_count=3,
        base_dice_sides=4,
        bloodlust_current=bloodlust,
        max_combat_turns=max_turns,
    )
    return knight


class TestCursedKnightBloodlust(unittest.TestCase):

    def test_bloodlust_decreases_on_damage_taken(self):
        knight = _make_knight(hp=250, bloodlust=125)
        knight.take_damage(30)
        self.assertEqual(knight.bloodlust_current, 95)

    def test_bloodlust_cannot_go_below_zero(self):
        knight = _make_knight(hp=250, bloodlust=10)
        knight.take_damage(50)
        self.assertEqual(knight.bloodlust_current, 0)

    def test_gain_bloodlust_increases_value(self):
        knight = _make_knight(hp=250, bloodlust=50)
        knight.gain_bloodlust(30)
        self.assertEqual(knight.bloodlust_current, 80)

    def test_gain_bloodlust_capped_at_max(self):
        knight = _make_knight(hp=100, bloodlust=0)
        # bloodlust_max = floor(100 * 0.75) = 75
        knight.gain_bloodlust(999)
        self.assertEqual(knight.bloodlust_current, knight.bloodlust_max)

    def test_bloodlust_max_based_on_current_hp(self):
        knight = _make_knight(hp=200, bloodlust=0)
        self.assertEqual(knight.bloodlust_max, 150)  # floor(200 * 0.75)

    def test_bloodlust_max_recalculates_after_damage(self):
        knight = _make_knight(hp=200, bloodlust=100)
        knight.take_damage(100)  # hp drops to 100
        self.assertEqual(knight.bloodlust_max, 75)   # floor(100 * 0.75)


class TestCursedKnightFlee(unittest.TestCase):

    def test_flees_after_max_turns(self):
        knight = _make_knight(hp=250, max_turns=2)
        rng = _rng(0)
        knight.take_turn(rng)   # turn 1
        self.assertFalse(knight.fled)
        knight.take_turn(rng)   # turn 2 — should flee
        self.assertTrue(knight.fled)
        self.assertEqual(knight.current_health, 0)

    def test_not_dead_before_turn_limit(self):
        knight = _make_knight(hp=250, max_turns=2)
        rng = _rng(0)
        knight.take_turn(rng)   # turn 1
        self.assertTrue(knight.current_health > 0)
        self.assertFalse(knight.fled)

    def test_damage_taken_accumulates(self):
        knight = _make_knight(hp=250, max_turns=999)
        knight.take_damage(40)
        knight.take_damage(30)
        self.assertEqual(knight.damage_taken_this_encounter, 70)

    def test_damage_taken_not_incremented_by_block_absorption(self):
        knight = _make_knight(hp=250, max_turns=999)
        knight.block = 20
        knight.take_damage(15)  # fully absorbed by block
        self.assertEqual(knight.damage_taken_this_encounter, 0)

    def test_damage_taken_only_counts_real_hp_lost(self):
        knight = _make_knight(hp=250, max_turns=999)
        knight.block = 10
        knight.take_damage(25)  # 10 absorbed, 15 real HP
        self.assertEqual(knight.damage_taken_this_encounter, 15)

    def test_single_turn_flee(self):
        knight = _make_knight(hp=250, max_turns=1)
        rng = _rng(0)
        knight.take_turn(rng)
        self.assertTrue(knight.fled)

    def test_zero_flee_turns_never_flees(self):
        knight = _make_knight(hp=250, max_turns=0)
        rng = _rng(0)
        for _ in range(10):
            knight.take_turn(rng)
        self.assertFalse(knight.fled)
        self.assertTrue(knight.current_health > 0)


class TestCursedKnightLoader(unittest.TestCase):
    """Verify the JSON file loads correctly as a CursedKnightEnemy."""

    def test_loads_as_correct_type(self):
        knight = load_enemy("cursed_knight", act=1)
        self.assertIsInstance(knight, CursedKnightEnemy)

    def test_loaded_hp(self):
        knight = load_enemy("cursed_knight", act=1)
        self.assertEqual(knight.max_health, 250)

    def test_loaded_has_three_skills(self):
        knight = load_enemy("cursed_knight", act=1)
        self.assertEqual(len(knight.skills), 3)

    def test_loaded_bloodlust_default(self):
        knight = load_enemy("cursed_knight", act=1)
        self.assertEqual(knight.bloodlust_current, 125)


if __name__ == "__main__":
    unittest.main()
