import unittest

from hero.hero_entity import HeroEntity, Skill, Stat
from combat.dice_assignment_engine import SkillAssignment
from combat.skill_executor import execute_skill, execute_all_skills, SkillResult


def _make_hero(**kwargs) -> HeroEntity:
    defaults = dict(
        hero_id="h1",
        name="Test Hero",
        archetype="warrior",
        strength=10,
        dexterity=10,
        intelligence=10,
        charisma=10,
        constitution=10,
    )
    defaults.update(kwargs)
    return HeroEntity(**defaults)


def _make_skill(effect_type: str = "damage", stat: Stat = Stat.STR) -> Skill:
    return Skill(
        name="Test Skill",
        description="A test skill",
        associated_stat=stat,
        dice_slots=2,
        effect_type=effect_type,
    )


class TestExecuteSkill(unittest.TestCase):

    def test_returns_none_when_no_dice_assigned(self):
        hero = _make_hero()
        skill = _make_skill()
        assignment = SkillAssignment(skill=skill, assigned_dice=[])
        result = execute_skill(hero, assignment)
        self.assertIsNone(result)

    def test_correct_effectiveness(self):
        # strength=10 -> modifier = floor(10/2) - 5 = 0
        hero = _make_hero(strength=10)
        skill = _make_skill(stat=Stat.STR)
        assignment = SkillAssignment(skill=skill, assigned_dice=[4, 6])
        result = execute_skill(hero, assignment)
        self.assertIsNotNone(result)
        self.assertEqual(result.effectiveness, 10)  # 4 + 6 + 0

    def test_effectiveness_with_nonzero_modifier(self):
        # strength=14 -> modifier = floor(14/2) - 5 = 2
        hero = _make_hero(strength=14)
        skill = _make_skill(stat=Stat.STR)
        assignment = SkillAssignment(skill=skill, assigned_dice=[3, 5])
        result = execute_skill(hero, assignment)
        self.assertIsNotNone(result)
        self.assertEqual(result.effectiveness, 10)  # 3 + 5 + 2

    def test_aoe_skill_hits_all_true(self):
        hero = _make_hero()
        skill = _make_skill(effect_type="aoe")
        assignment = SkillAssignment(skill=skill, assigned_dice=[5])
        result = execute_skill(hero, assignment)
        self.assertIsNotNone(result)
        self.assertTrue(result.hits_all)

    def test_non_aoe_skill_hits_all_false(self):
        hero = _make_hero()
        skill = _make_skill(effect_type="damage")
        assignment = SkillAssignment(skill=skill, assigned_dice=[5])
        result = execute_skill(hero, assignment)
        self.assertIsNotNone(result)
        self.assertFalse(result.hits_all)

    def test_effect_type_stored_correctly(self):
        hero = _make_hero()
        skill = _make_skill(effect_type="heal")
        assignment = SkillAssignment(skill=skill, assigned_dice=[3])
        result = execute_skill(hero, assignment)
        self.assertIsNotNone(result)
        self.assertEqual(result.effect_type, "heal")


class TestExecuteAllSkills(unittest.TestCase):

    def test_filters_out_inactive_assignments(self):
        hero = _make_hero()
        skill_active = _make_skill(effect_type="damage")
        skill_inactive = _make_skill(effect_type="aoe")
        assignments = [
            SkillAssignment(skill=skill_active, assigned_dice=[4]),
            SkillAssignment(skill=skill_inactive, assigned_dice=[]),
        ]
        results = execute_all_skills(hero, assignments)
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].effect_type, "damage")

    def test_returns_all_active_results(self):
        hero = _make_hero()
        skills = [_make_skill() for _ in range(3)]
        assignments = [
            SkillAssignment(skill=skills[0], assigned_dice=[2]),
            SkillAssignment(skill=skills[1], assigned_dice=[3]),
            SkillAssignment(skill=skills[2], assigned_dice=[1]),
        ]
        results = execute_all_skills(hero, assignments)
        self.assertEqual(len(results), 3)

    def test_empty_assignments_returns_empty(self):
        hero = _make_hero()
        results = execute_all_skills(hero, [])
        self.assertEqual(results, [])

    def test_all_inactive_returns_empty(self):
        hero = _make_hero()
        skill = _make_skill()
        assignments = [SkillAssignment(skill=skill, assigned_dice=[])]
        results = execute_all_skills(hero, assignments)
        self.assertEqual(results, [])


if __name__ == "__main__":
    unittest.main()
