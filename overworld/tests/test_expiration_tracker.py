import unittest

from quest.quest_model import Quest, QuestType, QuestDifficulty, QuestStatus, Reward, Consequence
from overworld.map_state import MapState, ShopSlot, BossSlot
from overworld.expiration_tracker import ExpirationTracker
from game_runtime.event_bus import EventBus


def _make_quest(
    quest_id: str = "q1",
    spawned_at_tick: int = 0,
    expiration_time: int = 100,
    is_critical: bool = False,
    consequence: Consequence = None,
    status: QuestStatus = QuestStatus.AVAILABLE,
) -> Quest:
    return Quest(
        quest_id=quest_id,
        title="Test",
        description="desc",
        quest_type=QuestType.COMBAT,
        difficulty=QuestDifficulty.EASY,
        reward=Reward(),
        spawned_at_tick=spawned_at_tick,
        expiration_time=expiration_time,
        is_critical=is_critical,
        consequence=consequence,
        status=status,
    )


def _make_shop(shop_id: str = "shop_0", expiration_tick: int = 100) -> ShopSlot:
    return ShopSlot(
        shop_id=shop_id,
        spawned_at_tick=0,
        expiration_tick=expiration_tick,
    )


class TestExpirationTrackerQuests(unittest.TestCase):
    def setUp(self):
        self.bus = EventBus()
        self.tracker = ExpirationTracker(self.bus)

    def test_quest_expires_when_tick_reaches_threshold(self):
        ms = MapState()
        q = _make_quest(spawned_at_tick=0, expiration_time=100)
        ms.add_quest(q)
        expired_quests, _ = self.tracker.tick(ms, current_tick=100)
        self.assertIn("q1", expired_quests)
        self.assertNotIn("q1", ms.active_quests)

    def test_quest_does_not_expire_before_threshold(self):
        ms = MapState()
        q = _make_quest(spawned_at_tick=0, expiration_time=100)
        ms.add_quest(q)
        expired_quests, _ = self.tracker.tick(ms, current_tick=99)
        self.assertEqual(expired_quests, [])
        self.assertIn("q1", ms.active_quests)

    def test_critical_quest_expiry_publishes_critical_expired(self):
        ms = MapState()
        consequence = Consequence(type="boss_buff", data={"buff": "enraged"})
        q = _make_quest(is_critical=True, consequence=consequence)
        ms.add_quest(q)

        received = []
        self.bus.subscribe("quest.critical_expired", lambda d: received.append(d))

        self.tracker.tick(ms, current_tick=100)
        self.assertEqual(len(received), 1)
        self.assertEqual(received[0]["quest_id"], "q1")
        self.assertIs(received[0]["consequence"], consequence)

    def test_critical_quest_expiry_does_not_publish_quest_expired(self):
        ms = MapState()
        consequence = Consequence(type="boss_buff", data={"buff": "enraged"})
        q = _make_quest(is_critical=True, consequence=consequence)
        ms.add_quest(q)

        plain_expired = []
        self.bus.subscribe("quest.expired", lambda d: plain_expired.append(d))

        self.tracker.tick(ms, current_tick=100)
        self.assertEqual(plain_expired, [])

    def test_non_critical_quest_expiry_publishes_quest_expired(self):
        ms = MapState()
        q = _make_quest(is_critical=False)
        ms.add_quest(q)

        received = []
        self.bus.subscribe("quest.expired", lambda d: received.append(d))

        self.tracker.tick(ms, current_tick=100)
        self.assertEqual(len(received), 1)
        self.assertEqual(received[0]["quest_id"], "q1")

    def test_assigned_quest_does_not_expire(self):
        ms = MapState()
        q = _make_quest(status=QuestStatus.ASSIGNED)
        ms.add_quest(q)

        expired_quests, _ = self.tracker.tick(ms, current_tick=100)
        self.assertEqual(expired_quests, [])
        self.assertIn("q1", ms.active_quests)


class TestExpirationTrackerShops(unittest.TestCase):
    def setUp(self):
        self.bus = EventBus()
        self.tracker = ExpirationTracker(self.bus)

    def test_shop_expires_when_tick_reaches_expiration(self):
        ms = MapState()
        s = _make_shop(expiration_tick=50)
        ms.add_shop(s)

        _, expired_shops = self.tracker.tick(ms, current_tick=50)
        self.assertIn("shop_0", expired_shops)
        self.assertNotIn("shop_0", ms.active_shops)

    def test_shop_does_not_expire_before_expiration(self):
        ms = MapState()
        s = _make_shop(expiration_tick=50)
        ms.add_shop(s)

        _, expired_shops = self.tracker.tick(ms, current_tick=49)
        self.assertEqual(expired_shops, [])
        self.assertIn("shop_0", ms.active_shops)

    def test_shop_expired_event_published(self):
        ms = MapState()
        s = _make_shop(expiration_tick=50)
        ms.add_shop(s)

        received = []
        self.bus.subscribe("shop.expired", lambda d: received.append(d))

        self.tracker.tick(ms, current_tick=50)
        self.assertEqual(len(received), 1)
        self.assertEqual(received[0]["shop_id"], "shop_0")


if __name__ == "__main__":
    unittest.main()
