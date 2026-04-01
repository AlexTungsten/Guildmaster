import unittest

from quest.quest_model import (
    Quest, QuestType, QuestDifficulty, QuestStatus,
    Reward, Consequence,
)


def make_quest(**kwargs) -> Quest:
    defaults = dict(
        quest_id="q1",
        title="Test Quest",
        description="A test quest.",
        quest_type=QuestType.COMBAT,
        difficulty=QuestDifficulty.EASY,
    )
    defaults.update(kwargs)
    return Quest(**defaults)


class TestQuestDefaults(unittest.TestCase):
    def setUp(self):
        self.quest = make_quest()

    def test_is_critical_default(self):
        self.assertFalse(self.quest.is_critical)

    def test_required_heroes_default(self):
        self.assertEqual(self.quest.required_heroes, 1)

    def test_max_heroes_default(self):
        self.assertEqual(self.quest.max_heroes, 3)

    def test_travel_time_default(self):
        self.assertEqual(self.quest.travel_time, 30)

    def test_resolution_time_default(self):
        self.assertEqual(self.quest.resolution_time, 60)

    def test_expiration_time_default(self):
        self.assertEqual(self.quest.expiration_time, 120)

    def test_base_exhaustion_default(self):
        self.assertEqual(self.quest.base_exhaustion, 10.0)

    def test_status_default(self):
        self.assertEqual(self.quest.status, QuestStatus.AVAILABLE)

    def test_assigned_hero_ids_default(self):
        self.assertEqual(self.quest.assigned_hero_ids, [])

    def test_spawned_at_tick_default(self):
        self.assertEqual(self.quest.spawned_at_tick, 0)

    def test_stat_checks_default(self):
        self.assertEqual(self.quest.stat_checks, [])

    def test_consequence_default_none(self):
        self.assertIsNone(self.quest.consequence)


class TestRewardDefaults(unittest.TestCase):
    def test_gold_default_zero(self):
        r = Reward()
        self.assertEqual(r.gold, 0)

    def test_xp_default_zero(self):
        r = Reward()
        self.assertEqual(r.xp, 0)

    def test_skill_default_none(self):
        r = Reward()
        self.assertIsNone(r.skill)

    def test_item_default_none(self):
        r = Reward()
        self.assertIsNone(r.item)


class TestConsequence(unittest.TestCase):
    def test_stores_type(self):
        c = Consequence(type="boss_buff")
        self.assertEqual(c.type, "boss_buff")

    def test_stores_data(self):
        c = Consequence(type="debuff_quest", data={"amount": 5})
        self.assertEqual(c.data["amount"], 5)

    def test_data_default_empty_dict(self):
        c = Consequence(type="boss_buff")
        self.assertEqual(c.data, {})


class TestQuestToDict(unittest.TestCase):
    def test_to_dict_round_trip(self):
        reward = Reward(gold=50, xp=100)
        quest = make_quest(reward=reward, spawned_at_tick=10)
        d = quest.to_dict()
        restored = Quest.from_dict(d)
        self.assertEqual(restored.quest_id, quest.quest_id)
        self.assertEqual(restored.title, quest.title)
        self.assertEqual(restored.description, quest.description)
        self.assertEqual(restored.quest_type, quest.quest_type)
        self.assertEqual(restored.difficulty, quest.difficulty)
        self.assertEqual(restored.reward.gold, quest.reward.gold)
        self.assertEqual(restored.reward.xp, quest.reward.xp)
        self.assertEqual(restored.status, quest.status)
        self.assertEqual(restored.spawned_at_tick, quest.spawned_at_tick)

    def test_to_dict_with_consequence(self):
        c = Consequence(type="boss_buff", data={"x": 1})
        quest = make_quest(is_critical=True, consequence=c)
        d = quest.to_dict()
        restored = Quest.from_dict(d)
        self.assertIsNotNone(restored.consequence)
        self.assertEqual(restored.consequence.type, "boss_buff")
        self.assertEqual(restored.consequence.data["x"], 1)

    def test_to_dict_without_consequence(self):
        quest = make_quest()
        d = quest.to_dict()
        self.assertIsNone(d["consequence"])
        restored = Quest.from_dict(d)
        self.assertIsNone(restored.consequence)

    def test_from_dict_preserves_status(self):
        quest = make_quest(status=QuestStatus.TRAVELING)
        d = quest.to_dict()
        restored = Quest.from_dict(d)
        self.assertEqual(restored.status, QuestStatus.TRAVELING)


if __name__ == "__main__":
    unittest.main()
