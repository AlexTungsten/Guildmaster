import unittest

from quest.quest_model import Quest, QuestType, QuestDifficulty, QuestStatus, Reward
from overworld.map_state import MapState, ShopSlot, BossSlot


def _make_quest(quest_id: str = "q1") -> Quest:
    return Quest(
        quest_id=quest_id,
        title="Test Quest",
        description="A test quest.",
        quest_type=QuestType.COMBAT,
        difficulty=QuestDifficulty.EASY,
        reward=Reward(gold=10, xp=10),
    )


def _make_shop(shop_id: str = "shop_0") -> ShopSlot:
    return ShopSlot(
        shop_id=shop_id,
        spawned_at_tick=0,
        expiration_tick=100,
        inventory=[],
    )


class TestMapStateQuests(unittest.TestCase):
    def test_add_quest(self):
        ms = MapState()
        q = _make_quest("q1")
        ms.add_quest(q)
        self.assertIn("q1", ms.active_quests)
        self.assertIs(ms.active_quests["q1"], q)

    def test_remove_quest(self):
        ms = MapState()
        q = _make_quest("q1")
        ms.add_quest(q)
        ms.remove_quest("q1")
        self.assertNotIn("q1", ms.active_quests)

    def test_remove_nonexistent_quest_does_not_raise(self):
        ms = MapState()
        ms.remove_quest("nonexistent")  # should not raise


class TestMapStateShops(unittest.TestCase):
    def test_add_shop(self):
        ms = MapState()
        s = _make_shop("shop_0")
        ms.add_shop(s)
        self.assertIn("shop_0", ms.active_shops)

    def test_expire_shop_removes_from_active(self):
        ms = MapState()
        s = _make_shop("shop_0")
        ms.add_shop(s)
        ms.expire_shop("shop_0")
        self.assertNotIn("shop_0", ms.active_shops)

    def test_expire_shop_marks_expired(self):
        ms = MapState()
        s = _make_shop("shop_0")
        ms.add_shop(s)
        ms.expire_shop("shop_0")
        self.assertTrue(s.expired)

    def test_expire_nonexistent_shop_does_not_raise(self):
        ms = MapState()
        ms.expire_shop("nonexistent")  # should not raise


class TestMapStateBoss(unittest.TestCase):
    def test_apply_boss_buff_appends(self):
        ms = MapState(boss=BossSlot(boss_id="boss_1", act=1))
        ms.apply_boss_buff("enraged")
        ms.apply_boss_buff("shielded")
        self.assertEqual(ms.boss.buffs, ["enraged", "shielded"])

    def test_apply_boss_buff_no_boss_does_not_raise(self):
        ms = MapState(boss=None)
        ms.apply_boss_buff("enraged")  # should not raise


class TestMapStateSerialisation(unittest.TestCase):
    def test_to_dict_from_dict_round_trip_without_boss(self):
        ms = MapState(current_act=2, act_start_tick=50, boss_timer_duration=300)
        q = _make_quest("q1")
        ms.add_quest(q)
        s = _make_shop("shop_0")
        ms.add_shop(s)

        data = ms.to_dict()
        restored = MapState.from_dict(data)

        self.assertEqual(restored.current_act, 2)
        self.assertEqual(restored.act_start_tick, 50)
        self.assertEqual(restored.boss_timer_duration, 300)
        self.assertIn("q1", restored.active_quests)
        self.assertIn("shop_0", restored.active_shops)
        self.assertIsNone(restored.boss)

    def test_to_dict_from_dict_round_trip_with_boss(self):
        boss = BossSlot(boss_id="boss_1", act=1, revealed=True, buffs=["enraged"])
        ms = MapState(boss=boss)

        data = ms.to_dict()
        restored = MapState.from_dict(data)

        self.assertIsNotNone(restored.boss)
        self.assertEqual(restored.boss.boss_id, "boss_1")
        self.assertEqual(restored.boss.act, 1)
        self.assertTrue(restored.boss.revealed)
        self.assertEqual(restored.boss.buffs, ["enraged"])

    def test_round_trip_preserves_quest_fields(self):
        ms = MapState()
        q = _make_quest("q42")
        q.spawned_at_tick = 77
        ms.add_quest(q)

        restored = MapState.from_dict(ms.to_dict())
        rq = restored.active_quests["q42"]
        self.assertEqual(rq.spawned_at_tick, 77)
        self.assertEqual(rq.difficulty, QuestDifficulty.EASY)


if __name__ == "__main__":
    unittest.main()
