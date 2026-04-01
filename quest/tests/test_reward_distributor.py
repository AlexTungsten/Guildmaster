import unittest

from hero.hero_entity import HeroEntity
from quest.quest_model import Quest, QuestType, QuestDifficulty, Reward
from quest.reward_distributor import distribute_rewards, DistributionResult


def make_hero(hero_id: str = "h1", xp: int = 0, xp_to_next: int = 100) -> HeroEntity:
    h = HeroEntity(hero_id=hero_id, name="Test Hero", archetype="warrior")
    h.xp = xp
    h.xp_to_next = xp_to_next
    return h


def make_quest(xp: int = 50, gold: int = 30, base_exhaustion: float = 10.0) -> Quest:
    return Quest(
        quest_id="q1",
        title="Test Quest",
        description="desc",
        quest_type=QuestType.COMBAT,
        difficulty=QuestDifficulty.EASY,
        base_exhaustion=base_exhaustion,
        reward=Reward(gold=gold, xp=xp),
    )


class TestDistributeRewardsXP(unittest.TestCase):
    def test_heroes_gain_xp_equal_to_quest_xp(self):
        hero = make_hero()
        quest = make_quest(xp=50)
        distribute_rewards(quest, [hero], damage_taken={})
        self.assertEqual(hero.xp, 50)

    def test_multiple_heroes_all_gain_xp(self):
        heroes = [make_hero("h1"), make_hero("h2"), make_hero("h3")]
        quest = make_quest(xp=40)
        distribute_rewards(quest, heroes, damage_taken={})
        for h in heroes:
            self.assertEqual(h.xp, 40)

    def test_zero_xp_quest_no_xp_gained(self):
        hero = make_hero()
        quest = make_quest(xp=0)
        distribute_rewards(quest, [hero], damage_taken={})
        self.assertEqual(hero.xp, 0)


class TestDistributeRewardsLevelUp(unittest.TestCase):
    def test_heroes_that_level_up_recorded(self):
        hero = make_hero(xp=90, xp_to_next=100)
        quest = make_quest(xp=20)  # 90 + 20 = 110 >= 100 -> level up
        result = distribute_rewards(quest, [hero], damage_taken={})
        self.assertIn(hero.hero_id, result.heroes_leveled_up)

    def test_heroes_that_do_not_level_up_not_recorded(self):
        hero = make_hero(xp=0, xp_to_next=100)
        quest = make_quest(xp=50)  # 50 < 100 -> no level up
        result = distribute_rewards(quest, [hero], damage_taken={})
        self.assertNotIn(hero.hero_id, result.heroes_leveled_up)

    def test_heroes_leveled_up_empty_when_none_level(self):
        heroes = [make_hero("h1"), make_hero("h2")]
        quest = make_quest(xp=10)
        result = distribute_rewards(quest, heroes, damage_taken={})
        self.assertEqual(result.heroes_leveled_up, [])


class TestDistributeRewardsExhaustion(unittest.TestCase):
    def test_base_exhaustion_applied_to_all_heroes(self):
        heroes = [make_hero("h1"), make_hero("h2")]
        quest = make_quest(base_exhaustion=15.0)
        distribute_rewards(quest, heroes, damage_taken={})
        for h in heroes:
            self.assertGreaterEqual(h.exhaustion, 15.0)

    def test_damage_based_exhaustion_scaled_correctly(self):
        hero = make_hero()
        hero.exhaustion = 0.0
        quest = make_quest(base_exhaustion=10.0)
        damage_taken = {hero.hero_id: 50}
        distribute_rewards(quest, [hero], damage_taken=damage_taken, exhaustion_damage_scale=0.1)
        # Expected: 10.0 + 50 * 0.1 = 15.0
        self.assertAlmostEqual(hero.exhaustion, 15.0)

    def test_custom_exhaustion_damage_scale(self):
        hero = make_hero()
        hero.exhaustion = 0.0
        quest = make_quest(base_exhaustion=5.0)
        damage_taken = {hero.hero_id: 100}
        distribute_rewards(quest, [hero], damage_taken=damage_taken, exhaustion_damage_scale=0.2)
        # Expected: 5.0 + 100 * 0.2 = 25.0
        self.assertAlmostEqual(hero.exhaustion, 25.0)

    def test_exhaustion_applied_recorded_in_result(self):
        hero = make_hero()
        quest = make_quest(base_exhaustion=10.0)
        damage_taken = {hero.hero_id: 20}
        result = distribute_rewards(quest, [hero], damage_taken=damage_taken, exhaustion_damage_scale=0.1)
        self.assertIn(hero.hero_id, result.exhaustion_applied)
        self.assertAlmostEqual(result.exhaustion_applied[hero.hero_id], 12.0)

    def test_no_damage_taken_just_base_exhaustion(self):
        hero = make_hero()
        hero.exhaustion = 0.0
        quest = make_quest(base_exhaustion=8.0)
        result = distribute_rewards(quest, [hero], damage_taken={})
        self.assertAlmostEqual(result.exhaustion_applied[hero.hero_id], 8.0)


class TestDistributeRewardsGold(unittest.TestCase):
    def test_gold_earned_matches_quest_reward_gold(self):
        hero = make_hero()
        quest = make_quest(gold=75)
        result = distribute_rewards(quest, [hero], damage_taken={})
        self.assertEqual(result.gold_earned, 75)

    def test_gold_earned_zero(self):
        hero = make_hero()
        quest = make_quest(gold=0)
        result = distribute_rewards(quest, [hero], damage_taken={})
        self.assertEqual(result.gold_earned, 0)


if __name__ == "__main__":
    unittest.main()
