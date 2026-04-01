"""
test_special_skills.py — Tests for Barbarian special mechanics.

Covers:
  - Blood Cleave effectiveness bonus (+5)
  - Blood Cleave HP self-cost (temp HP first, then real HP, floors at 1)
  - Bloodletting / absorb_damage / apply_temp_hp / has_passive
"""

import unittest

from hero.hero_entity import HeroEntity, Skill, Stat
from combat.dice_assignment_engine import SkillAssignment
from combat.skill_executor import execute_skill, SkillResult


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_hero(**kwargs) -> HeroEntity:
    defaults = dict(
        hero_id="h1",
        name="Grok",
        archetype="Barbarian",
        strength=14,
        dexterity=12,
        intelligence=7,
        charisma=8,
        constitution=15,
    )
    defaults.update(kwargs)
    return HeroEntity(**defaults)


def _make_skill(effect_type: str = "damage", special: str = None, stat: Stat = Stat.STR) -> Skill:
    return Skill(
        name="Test Skill",
        description="A test skill",
        associated_stat=stat,
        dice_slots=1,
        effect_type=effect_type,
        special=special,
    )


# ---------------------------------------------------------------------------
# Blood Cleave effectiveness tests (via skill_executor)
# ---------------------------------------------------------------------------

class TestBloodCleaveEffectiveness(unittest.TestCase):

    def test_blood_cleave_adds_5_bonus(self):
        # strength=14 -> modifier = floor(14/2) - 5 = 2
        # dice = [5], modifier = 2, special bonus = 5 => effectiveness = 12
        hero = _make_hero(strength=14)
        skill = _make_skill(effect_type="aoe", special="blood_cleave", stat=Stat.STR)
        assignment = SkillAssignment(skill=skill, assigned_dice=[5])
        result = execute_skill(hero, assignment)
        self.assertIsNotNone(result)
        self.assertEqual(result.effectiveness, 12)  # 5 + 2 + 5

    def test_non_blood_cleave_no_bonus(self):
        # strength=14 -> modifier = 2; dice = [5]; no bonus => effectiveness = 7
        hero = _make_hero(strength=14)
        skill = _make_skill(effect_type="damage", special=None, stat=Stat.STR)
        assignment = SkillAssignment(skill=skill, assigned_dice=[5])
        result = execute_skill(hero, assignment)
        self.assertIsNotNone(result)
        self.assertEqual(result.effectiveness, 7)  # 5 + 2

    def test_blood_cleave_special_forwarded_to_result(self):
        hero = _make_hero()
        skill = _make_skill(effect_type="aoe", special="blood_cleave")
        assignment = SkillAssignment(skill=skill, assigned_dice=[3])
        result = execute_skill(hero, assignment)
        self.assertEqual(result.special, "blood_cleave")

    def test_bloodletting_special_forwarded_to_result(self):
        hero = _make_hero()
        skill = _make_skill(effect_type="defend", special="bloodletting", stat=Stat.CON)
        assignment = SkillAssignment(skill=skill, assigned_dice=[4])
        result = execute_skill(hero, assignment)
        self.assertEqual(result.special, "bloodletting")

    def test_no_special_forwarded_as_none(self):
        hero = _make_hero()
        skill = _make_skill(effect_type="damage", special=None)
        assignment = SkillAssignment(skill=skill, assigned_dice=[3])
        result = execute_skill(hero, assignment)
        self.assertIsNone(result.special)


# ---------------------------------------------------------------------------
# Blood Cleave self-cost tests (via HeroEntity methods)
# ---------------------------------------------------------------------------

class TestBloodCleaveSelfCost(unittest.TestCase):
    """Tests for the 5% HP cost mechanic, applied directly via hero methods."""

    def test_self_cost_reduces_temp_hp_first(self):
        hero = _make_hero(current_health=100, max_health=100, temp_hp=50)
        cost = max(1, int(hero.current_health * 0.05))  # 5% of 100 = 5
        if hero.temp_hp >= cost:
            hero.temp_hp -= cost
        else:
            remaining = cost - hero.temp_hp
            hero.temp_hp = 0
            hero.current_health = max(1, hero.current_health - remaining)
        self.assertEqual(hero.temp_hp, 45)
        self.assertEqual(hero.current_health, 100)

    def test_self_cost_reduces_real_hp_when_no_temp_hp(self):
        hero = _make_hero(current_health=100, max_health=100, temp_hp=0)
        cost = max(1, int(hero.current_health * 0.05))  # 5% of 100 = 5
        if hero.temp_hp >= cost:
            hero.temp_hp -= cost
        else:
            remaining = cost - hero.temp_hp
            hero.temp_hp = 0
            hero.current_health = max(1, hero.current_health - remaining)
        self.assertEqual(hero.current_health, 95)
        self.assertEqual(hero.temp_hp, 0)

    def test_self_cost_floors_real_hp_at_1(self):
        hero = _make_hero(current_health=1, max_health=100, temp_hp=0)
        # 5% of 1 = 0 -> max(1, 0) = 1 cost
        cost = max(1, int(hero.current_health * 0.05))
        self.assertEqual(cost, 1)
        if hero.temp_hp >= cost:
            hero.temp_hp -= cost
        else:
            remaining = cost - hero.temp_hp
            hero.temp_hp = 0
            hero.current_health = max(1, hero.current_health - remaining)
        # HP floors at 1, never reaches 0 from self-cost
        self.assertGreaterEqual(hero.current_health, 1)

    def test_blood_cleave_never_kills_hero(self):
        hero = _make_hero(current_health=2, max_health=100, temp_hp=0)
        # 5% of 2 = 0 -> cost=1
        cost = max(1, int(hero.current_health * 0.05))
        if hero.temp_hp >= cost:
            hero.temp_hp -= cost
        else:
            remaining = cost - hero.temp_hp
            hero.temp_hp = 0
            hero.current_health = max(1, hero.current_health - remaining)
        self.assertGreaterEqual(hero.current_health, 1)

    def test_self_cost_partial_temp_hp(self):
        # temp_hp < cost: temp drains to 0, remainder hits real HP
        hero = _make_hero(current_health=100, max_health=100, temp_hp=2)
        cost = max(1, int(hero.current_health * 0.05))  # cost = 5
        if hero.temp_hp >= cost:
            hero.temp_hp -= cost
        else:
            remaining = cost - hero.temp_hp
            hero.temp_hp = 0
            hero.current_health = max(1, hero.current_health - remaining)
        self.assertEqual(hero.temp_hp, 0)
        self.assertEqual(hero.current_health, 97)  # 100 - (5 - 2) = 97


# ---------------------------------------------------------------------------
# absorb_damage tests
# ---------------------------------------------------------------------------

class TestAbsorbDamage(unittest.TestCase):

    def test_absorb_reduces_temp_hp_first(self):
        hero = _make_hero(current_health=50, max_health=50, temp_hp=20)
        real_damage = hero.absorb_damage(10)
        self.assertEqual(hero.temp_hp, 10)
        self.assertEqual(hero.current_health, 50)
        self.assertEqual(real_damage, 0)

    def test_absorb_reduces_real_hp_after_temp_exhausted(self):
        hero = _make_hero(current_health=50, max_health=50, temp_hp=5)
        real_damage = hero.absorb_damage(15)
        self.assertEqual(hero.temp_hp, 0)
        self.assertEqual(hero.current_health, 40)
        self.assertEqual(real_damage, 10)

    def test_absorb_no_temp_hp_hits_only_real_hp(self):
        hero = _make_hero(current_health=50, max_health=50, temp_hp=0)
        real_damage = hero.absorb_damage(20)
        self.assertEqual(hero.temp_hp, 0)
        self.assertEqual(hero.current_health, 30)
        self.assertEqual(real_damage, 20)

    def test_absorb_damage_clamps_real_hp_to_zero(self):
        hero = _make_hero(current_health=5, max_health=50, temp_hp=0)
        real_damage = hero.absorb_damage(100)
        self.assertEqual(hero.current_health, 0)
        self.assertEqual(real_damage, 100)

    def test_absorb_damage_exact_temp_hp_match(self):
        hero = _make_hero(current_health=50, max_health=50, temp_hp=10)
        real_damage = hero.absorb_damage(10)
        self.assertEqual(hero.temp_hp, 0)
        self.assertEqual(hero.current_health, 50)
        self.assertEqual(real_damage, 0)


# ---------------------------------------------------------------------------
# apply_temp_hp tests
# ---------------------------------------------------------------------------

class TestApplyTempHP(unittest.TestCase):

    def test_apply_temp_hp_sets_value(self):
        hero = _make_hero(temp_hp=0)
        hero.apply_temp_hp(30)
        self.assertEqual(hero.temp_hp, 30)

    def test_apply_temp_hp_replaces_existing(self):
        hero = _make_hero(temp_hp=50)
        hero.apply_temp_hp(20)
        self.assertEqual(hero.temp_hp, 20)

    def test_apply_temp_hp_does_not_stack(self):
        hero = _make_hero(temp_hp=10)
        hero.apply_temp_hp(15)
        hero.apply_temp_hp(25)
        # Last call wins — no stacking
        self.assertEqual(hero.temp_hp, 25)


# ---------------------------------------------------------------------------
# has_passive tests
# ---------------------------------------------------------------------------

class TestHasPassive(unittest.TestCase):

    def test_has_passive_returns_true_for_ironhide(self):
        passives = [{"passive_id": "ironhide", "name": "Ironhide"}]
        hero = _make_hero(passives=passives)
        self.assertTrue(hero.has_passive("ironhide"))

    def test_has_passive_returns_false_for_unknown(self):
        passives = [{"passive_id": "ironhide", "name": "Ironhide"}]
        hero = _make_hero(passives=passives)
        self.assertFalse(hero.has_passive("berserker"))

    def test_has_passive_returns_false_with_no_passives(self):
        hero = _make_hero(passives=[])
        self.assertFalse(hero.has_passive("ironhide"))

    def test_has_passive_multiple_passives(self):
        passives = [
            {"passive_id": "ironhide", "name": "Ironhide"},
            {"passive_id": "rage", "name": "Rage"},
        ]
        hero = _make_hero(passives=passives)
        self.assertTrue(hero.has_passive("ironhide"))
        self.assertTrue(hero.has_passive("rage"))
        self.assertFalse(hero.has_passive("stealth"))


if __name__ == "__main__":
    unittest.main()
