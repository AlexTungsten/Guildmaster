import random
import unittest

from quest.quest_model import Quest, QuestDifficulty
from quest.quest_pool import ActPool, build_default_pools


def _make_pool(act: int = 1) -> ActPool:
    from quest.quest_model import Quest, QuestType, QuestDifficulty, Reward

    def q(qid, diff):
        return Quest(
            quest_id=qid,
            title=qid,
            description="desc",
            quest_type=QuestType.COMBAT,
            difficulty=diff,
        )

    easy = [q("e1", QuestDifficulty.EASY), q("e2", QuestDifficulty.EASY), q("e3", QuestDifficulty.EASY)]
    hard = [q("h1", QuestDifficulty.HARD), q("h2", QuestDifficulty.HARD)]
    elite = [q("el1", QuestDifficulty.ELITE)]
    return ActPool(act=act, easy=easy, hard=hard, elite=elite)


class TestActPoolDraw(unittest.TestCase):
    def setUp(self):
        self.pool = _make_pool()

    def test_draw_returns_quest(self):
        result = self.pool.draw()
        self.assertIsInstance(result, Quest)

    def test_draw_with_rng(self):
        rng = random.Random(42)
        result = self.pool.draw(rng=rng)
        self.assertIsInstance(result, Quest)

    def test_draw_returns_copy(self):
        rng = random.Random(0)
        result = self.pool.draw(rng=rng)
        result.title = "MUTATED"
        # Original easy quests should be unchanged
        for q in self.pool.easy + self.pool.hard + self.pool.elite:
            self.assertNotEqual(q.title, "MUTATED")

    def test_draw_copy_independence(self):
        rng1 = random.Random(0)
        rng2 = random.Random(0)
        r1 = self.pool.draw(rng=rng1)
        r2 = self.pool.draw(rng=rng2)
        # Both should have equal content (same seed)
        self.assertEqual(r1.quest_id, r2.quest_id)
        # Mutating one should not affect the other
        r1.title = "CHANGED"
        self.assertNotEqual(r1.title, r2.title)

    def test_draw_weighted_distribution(self):
        rng = random.Random(12345)
        easy_count = 0
        hard_count = 0
        elite_count = 0
        for _ in range(200):
            result = self.pool.draw(rng=rng)
            if result.difficulty == QuestDifficulty.EASY:
                easy_count += 1
            elif result.difficulty == QuestDifficulty.HARD:
                hard_count += 1
            elif result.difficulty == QuestDifficulty.ELITE:
                elite_count += 1
        # Easy should be the most common (~60%), hard second (~30%), elite least (~10%)
        self.assertGreater(easy_count, hard_count)
        self.assertGreater(hard_count, elite_count)
        # Rough sanity checks
        self.assertGreater(easy_count, 80)
        self.assertLess(elite_count, 50)


class TestBuildDefaultPools(unittest.TestCase):
    def test_returns_dict_with_acts(self):
        pools = build_default_pools()
        self.assertIn(1, pools)
        self.assertIn(2, pools)
        self.assertIn(3, pools)

    def test_each_act_is_act_pool(self):
        pools = build_default_pools()
        for act_num, pool in pools.items():
            self.assertIsInstance(pool, ActPool)

    def test_each_pool_has_easy_hard_elite(self):
        pools = build_default_pools()
        for act_num, pool in pools.items():
            self.assertTrue(len(pool.easy) > 0, f"Act {act_num} missing easy quests")
            self.assertTrue(len(pool.hard) > 0, f"Act {act_num} missing hard quests")
            self.assertTrue(len(pool.elite) > 0, f"Act {act_num} missing elite quests")

    def test_draw_from_default_pool(self):
        pools = build_default_pools()
        rng = random.Random(99)
        for act_num, pool in pools.items():
            result = pool.draw(rng=rng)
            self.assertIsInstance(result, Quest)

    def test_act_numbers_match(self):
        pools = build_default_pools()
        for act_num, pool in pools.items():
            self.assertEqual(pool.act, act_num)


if __name__ == "__main__":
    unittest.main()
