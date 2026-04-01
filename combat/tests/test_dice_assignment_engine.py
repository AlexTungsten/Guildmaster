import unittest

from combat.dice_assignment_engine import SkillAssignment, assign_dice
from hero.hero_entity import HeroEntity, Skill, Stat


def make_hero(**kwargs) -> HeroEntity:
    defaults = {
        "hero_id": "h1",
        "name": "Tester",
        "archetype": "fighter",
    }
    defaults.update(kwargs)
    return HeroEntity(**defaults)


def make_skill(name="Attack", dice_slots=2, stat=Stat.STR) -> Skill:
    return Skill(name=name, description="desc", associated_stat=stat, dice_slots=dice_slots, effect_type="damage")


class TestFocusProfile(unittest.TestCase):
    def setUp(self):
        skill0 = make_skill("Skill0", dice_slots=3)
        skill1 = make_skill("Skill1", dice_slots=2)
        skill2 = make_skill("Skill2", dice_slots=2)
        self.hero = make_hero(behavior_profile="focus")
        self.hero.skills = [skill0, skill1, skill2]

    def test_focus_fills_skill_0_first(self):
        # 4 normal dice; skill0 has 3 slots
        results = assign_dice(self.hero, [], [8, 7, 6, 5])
        assignments = {a.skill.name: a for a in results}
        self.assertEqual(len(assignments["Skill0"].assigned_dice), 3)
        self.assertEqual(len(assignments["Skill1"].assigned_dice), 1)
        self.assertEqual(len(assignments["Skill2"].assigned_dice), 0)

    def test_focus_overflow_to_next_when_skill_0_full(self):
        # 6 normal dice; skill0 has 3, skill1 has 2, overflow rest to skill2
        results = assign_dice(self.hero, [], [9, 8, 7, 6, 5, 4])
        assignments = {a.skill.name: a for a in results}
        self.assertEqual(len(assignments["Skill0"].assigned_dice), 3)
        self.assertEqual(len(assignments["Skill1"].assigned_dice), 2)
        self.assertEqual(len(assignments["Skill2"].assigned_dice), 1)


class TestBalancedProfile(unittest.TestCase):
    def setUp(self):
        skill0 = make_skill("Skill0", dice_slots=2)
        skill1 = make_skill("Skill1", dice_slots=2)
        skill2 = make_skill("Skill2", dice_slots=2)
        self.hero = make_hero(behavior_profile="balanced")
        self.hero.skills = [skill0, skill1, skill2]

    def test_balanced_distributes_evenly(self):
        # 6 dice, 3 skills with 2 slots each
        results = assign_dice(self.hero, [], [5, 5, 5, 5, 5, 5])
        for assignment in results:
            self.assertEqual(len(assignment.assigned_dice), 2)

    def test_balanced_round_robin_partial(self):
        # 4 dice, 3 skills with 2 slots each
        results = assign_dice(self.hero, [], [1, 2, 3, 4])
        assignments = {a.skill.name: a for a in results}
        # First pass: skill0, skill1, skill2 each get 1
        # Second pass: skill0 gets 1 more
        self.assertEqual(len(assignments["Skill0"].assigned_dice), 2)
        self.assertEqual(len(assignments["Skill1"].assigned_dice), 1)
        self.assertEqual(len(assignments["Skill2"].assigned_dice), 1)


class TestGreedyProfile(unittest.TestCase):
    def setUp(self):
        skill0 = make_skill("Skill0", dice_slots=2)
        skill1 = make_skill("Skill1", dice_slots=3)
        skill2 = make_skill("Skill2", dice_slots=1)
        self.hero = make_hero(behavior_profile="greedy")
        self.hero.skills = [skill0, skill1, skill2]

    def test_greedy_assigns_best_dice_to_skill_with_most_slots(self):
        # skill1 has 3 slots (most), should get top dice first
        # dice = [10, 8, 6, 4, 2, 1], skill1 has 3 slots
        results = assign_dice(self.hero, [], [10, 8, 6, 4, 2, 1])
        assignments = {a.skill.name: a for a in results}
        # After sorting descending: [10, 8, 6, 4, 2, 1]
        # skill1 (3 slots) gets 10 first
        self.assertIn(10, assignments["Skill1"].assigned_dice)


class TestDumpProfile(unittest.TestCase):
    def setUp(self):
        skill0 = make_skill("Skill0", dice_slots=2)
        skill1 = make_skill("Skill1", dice_slots=2)
        skill2 = make_skill("Skill2", dice_slots=2)
        self.hero = make_hero(behavior_profile="dump")
        self.hero.skills = [skill0, skill1, skill2]

    def test_dump_assigns_worst_dice_to_last_skills(self):
        # sorted ascending: [1, 2, 3, 4, 5, 6]
        # round-robin over reversed order each pass: skill2, skill1, skill0
        # pass 1: skill2 gets 1, skill1 gets 2, skill0 gets 3
        # pass 2: skill2 gets 4, skill1 gets 5, skill0 gets 6
        results = assign_dice(self.hero, [], [6, 5, 4, 3, 2, 1])
        assignments = {a.skill.name: a for a in results}
        # skill2 should receive the worst die (1) and skill0 should receive the best (6)
        self.assertIn(1, assignments["Skill2"].assigned_dice)
        self.assertIn(6, assignments["Skill0"].assigned_dice)
        # Overall: skill0 has highest values, skill2 has lowest values
        self.assertGreater(
            sum(assignments["Skill0"].assigned_dice),
            sum(assignments["Skill2"].assigned_dice),
        )


class TestLockedDicePriority(unittest.TestCase):
    def setUp(self):
        skill0 = make_skill("Skill0", dice_slots=2)
        skill1 = make_skill("Skill1", dice_slots=2)
        self.hero = make_hero(behavior_profile="balanced")
        self.hero.skills = [skill0, skill1, None]

    def test_locked_dice_fill_slots_before_normal(self):
        # 2 locked dice, 2 normal dice; skills have 2 slots each
        results = assign_dice(self.hero, [3, 2], [8, 7])
        assignments = {a.skill.name: a for a in results}
        # skill0 should have locked dice first
        self.assertIn(3, assignments["Skill0"].assigned_dice)
        self.assertIn(2, assignments["Skill0"].assigned_dice)
        # Normal dice go to skill1
        self.assertIn(8, assignments["Skill1"].assigned_dice)
        self.assertIn(7, assignments["Skill1"].assigned_dice)

    def test_locked_dice_fill_all_slots_no_normal_dice_added(self):
        # skill0 has 2 slots; 2 locked dice fill it completely; no normal dice
        results = assign_dice(self.hero, [4, 3], [9])
        assignments = {a.skill.name: a for a in results}
        self.assertEqual(len(assignments["Skill0"].assigned_dice), 2)
        # All locked in slot 0; normal die goes to skill1
        self.assertNotIn(9, assignments["Skill0"].assigned_dice)
        self.assertIn(9, assignments["Skill1"].assigned_dice)


class TestSkillAssignmentProperties(unittest.TestCase):
    def test_skill_with_no_dice_is_not_active(self):
        skill = make_skill()
        assignment = SkillAssignment(skill=skill)
        self.assertFalse(assignment.is_active)

    def test_skill_with_dice_is_active(self):
        skill = make_skill()
        assignment = SkillAssignment(skill=skill, assigned_dice=[5, 3])
        self.assertTrue(assignment.is_active)

    def test_effectiveness_is_sum_of_assigned_dice(self):
        skill = make_skill()
        assignment = SkillAssignment(skill=skill, assigned_dice=[5, 3, 7])
        self.assertEqual(assignment.effectiveness, 15)

    def test_effectiveness_zero_when_no_dice(self):
        skill = make_skill()
        assignment = SkillAssignment(skill=skill)
        self.assertEqual(assignment.effectiveness, 0)

    def test_none_skills_not_in_results(self):
        hero = make_hero(behavior_profile="balanced")
        hero.skills = [make_skill("S0"), None, make_skill("S2")]
        results = assign_dice(hero, [], [5, 5])
        self.assertEqual(len(results), 2)
        names = [a.skill.name for a in results]
        self.assertIn("S0", names)
        self.assertIn("S2", names)


if __name__ == "__main__":
    unittest.main()
