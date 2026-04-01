import unittest
from unittest.mock import patch

from hero.hero_entity import HeroEntity, HeroStatus, Skill, Stat


def make_hero(**kwargs) -> HeroEntity:
    defaults = {
        "hero_id": "h1",
        "name": "Aldric",
        "archetype": "fighter",
    }
    defaults.update(kwargs)
    return HeroEntity(**defaults)


class TestStatModifier(unittest.TestCase):
    def test_stat_10_gives_modifier_0(self):
        hero = make_hero(strength=10)
        self.assertEqual(hero.stat_modifier(Stat.STR), 0)

    def test_stat_8_gives_modifier_minus_1(self):
        hero = make_hero(dexterity=8)
        self.assertEqual(hero.stat_modifier(Stat.DEX), -1)

    def test_stat_14_gives_modifier_2(self):
        hero = make_hero(intelligence=14)
        self.assertEqual(hero.stat_modifier(Stat.INT), 2)

    def test_stat_20_gives_modifier_5(self):
        hero = make_hero(charisma=20)
        self.assertEqual(hero.stat_modifier(Stat.CHA), 5)

    def test_effective_stat_applies_loss(self):
        hero = make_hero(strength=10, strength_loss=3)
        self.assertEqual(hero.effective_stat(Stat.STR), 7)

    def test_effective_stat_min_zero(self):
        hero = make_hero(constitution=5, constitution_loss=10)
        self.assertEqual(hero.effective_stat(Stat.CON), 0)


class TestExhaustionLevel(unittest.TestCase):
    def _check(self, exhaustion, expected_level):
        hero = make_hero(exhaustion=exhaustion)
        self.assertEqual(hero.exhaustion_level(), expected_level)

    def test_level_1_at_0(self):
        self._check(0, 1)

    def test_level_1_at_19(self):
        self._check(19, 1)

    def test_level_2_at_20(self):
        self._check(20, 2)

    def test_level_2_at_39(self):
        self._check(39, 2)

    def test_level_3_at_40(self):
        self._check(40, 3)

    def test_level_3_at_59(self):
        self._check(59, 3)

    def test_level_4_at_60(self):
        self._check(60, 4)

    def test_level_4_at_99(self):
        self._check(99, 4)

    def test_level_5_at_100(self):
        self._check(100, 5)


class TestLockedDiceCount(unittest.TestCase):
    def test_level_1_zero_locked(self):
        hero = make_hero(exhaustion=0)
        self.assertEqual(hero.locked_dice_count(), 0)

    def test_level_2_one_locked(self):
        hero = make_hero(exhaustion=25)
        self.assertEqual(hero.locked_dice_count(), 1)

    def test_level_3_two_locked(self):
        hero = make_hero(exhaustion=45)
        self.assertEqual(hero.locked_dice_count(), 2)

    def test_level_4_three_locked(self):
        hero = make_hero(exhaustion=70)
        self.assertEqual(hero.locked_dice_count(), 3)

    def test_level_5_four_locked(self):
        hero = make_hero(exhaustion=110)
        self.assertEqual(hero.locked_dice_count(), 4)


class TestEffectiveModifier(unittest.TestCase):
    def test_no_penalty_at_exhaustion_level_1(self):
        hero = make_hero(strength=14, exhaustion=10)
        # No affected stats at level 1
        self.assertEqual(hero.effective_modifier(Stat.STR), hero.stat_modifier(Stat.STR))

    def test_penalty_applies_to_highest_stat_at_level_2(self):
        hero = make_hero(strength=16, dexterity=10, exhaustion=25)
        # STR is highest, should have penalty
        affected = hero._exhaustion_affected_stats()
        self.assertIn(Stat.STR, affected)
        self.assertNotIn(Stat.DEX, affected)
        effective = hero.effective_modifier(Stat.STR)
        normal = hero.stat_modifier(Stat.STR)
        self.assertLess(effective, normal)

    def test_unaffected_stat_unchanged(self):
        hero = make_hero(strength=16, dexterity=10, exhaustion=25)
        self.assertEqual(hero.effective_modifier(Stat.DEX), hero.stat_modifier(Stat.DEX))


class TestRecoverExhaustion(unittest.TestCase):
    def test_recovery_when_idle(self):
        hero = make_hero(exhaustion=10.0, status=HeroStatus.IDLE)
        hero.recover_exhaustion(3.0)
        self.assertEqual(hero.exhaustion, 7.0)

    def test_no_recovery_when_not_idle(self):
        hero = make_hero(exhaustion=10.0, status=HeroStatus.ON_QUEST)
        hero.recover_exhaustion(3.0)
        self.assertEqual(hero.exhaustion, 10.0)

    def test_exhaustion_does_not_go_below_zero(self):
        hero = make_hero(exhaustion=1.0, status=HeroStatus.IDLE)
        hero.recover_exhaustion(5.0)
        self.assertEqual(hero.exhaustion, 0.0)


class TestGainXP(unittest.TestCase):
    def test_no_level_up_when_xp_below_threshold(self):
        hero = make_hero()
        leveled = hero.gain_xp(50)
        self.assertFalse(leveled)
        self.assertEqual(hero.level, 1)
        self.assertEqual(hero.xp, 50)

    def test_level_up_when_xp_meets_threshold(self):
        hero = make_hero()
        leveled = hero.gain_xp(100)
        self.assertTrue(leveled)
        self.assertEqual(hero.level, 2)
        self.assertEqual(hero.xp, 0)
        self.assertEqual(hero.xp_to_next, 150)

    def test_level_up_with_overflow_xp(self):
        hero = make_hero()
        leveled = hero.gain_xp(120)
        self.assertTrue(leveled)
        self.assertEqual(hero.xp, 20)

    def test_xp_to_next_scales_on_level_up(self):
        hero = make_hero()
        hero.gain_xp(100)
        self.assertEqual(hero.xp_to_next, 150)
        hero.gain_xp(150)
        self.assertEqual(hero.xp_to_next, 225)


class TestApplyPermanentStatLoss(unittest.TestCase):
    def test_increases_a_loss_field(self):
        hero = make_hero()
        stat = hero.apply_permanent_stat_loss()
        loss_val = hero._stat_loss_value(stat)
        self.assertEqual(loss_val, 1)

    def test_returns_a_stat(self):
        hero = make_hero()
        stat = hero.apply_permanent_stat_loss()
        self.assertIsInstance(stat, Stat)


class TestDeathRoll(unittest.TestCase):
    def test_death_roll_true_when_roll_below_exhaustion(self):
        hero = make_hero(exhaustion=500)
        with patch("hero.hero_entity.random.randint", return_value=499):
            self.assertTrue(hero.death_roll())

    def test_death_roll_false_when_roll_above_exhaustion(self):
        hero = make_hero(exhaustion=100)
        with patch("hero.hero_entity.random.randint", return_value=200):
            self.assertFalse(hero.death_roll())

    def test_death_roll_false_at_zero_exhaustion(self):
        hero = make_hero(exhaustion=0)
        with patch("hero.hero_entity.random.randint", return_value=1):
            # roll=1, exhaustion=0; 1 < 0 is False
            self.assertFalse(hero.death_roll())


class TestReplaceSkill(unittest.TestCase):
    def setUp(self):
        self.hero = make_hero()
        self.skill_a = Skill("Slash", "A slash", Stat.STR, 2, "damage")
        self.skill_b = Skill("Block", "A block", Stat.CON, 1, "defense")

    def test_replace_skill_returns_old_and_sets_new(self):
        self.hero.skills[0] = self.skill_a
        old = self.hero.replace_skill(0, self.skill_b)
        self.assertEqual(old, self.skill_a)
        self.assertEqual(self.hero.skills[0], self.skill_b)

    def test_replace_skill_returns_none_when_slot_empty(self):
        old = self.hero.replace_skill(1, self.skill_a)
        self.assertIsNone(old)
        self.assertEqual(self.hero.skills[1], self.skill_a)


class TestHeroEntitySerialization(unittest.TestCase):
    def test_to_dict_from_dict_round_trip(self):
        hero = make_hero(
            strength=14,
            dexterity=12,
            exhaustion=35.5,
            level=3,
            xp=50,
            xp_to_next=225,
            status=HeroStatus.ON_QUEST,
        )
        skill = Skill("Fireball", "Fire damage", Stat.INT, 3, "aoe_damage")
        hero.skills[0] = skill

        data = hero.to_dict()
        restored = HeroEntity.from_dict(data)

        self.assertEqual(restored.hero_id, hero.hero_id)
        self.assertEqual(restored.name, hero.name)
        self.assertEqual(restored.strength, hero.strength)
        self.assertEqual(restored.exhaustion, hero.exhaustion)
        self.assertEqual(restored.level, hero.level)
        self.assertEqual(restored.status, hero.status)
        self.assertIsNotNone(restored.skills[0])
        self.assertEqual(restored.skills[0].name, "Fireball")
        self.assertIsNone(restored.skills[1])
        self.assertIsNone(restored.skills[2])


if __name__ == "__main__":
    unittest.main()
