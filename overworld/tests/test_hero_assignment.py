import unittest

from hero.hero_entity import HeroEntity, HeroStatus
from quest.quest_model import Quest, QuestType, QuestDifficulty, QuestStatus, Reward
from overworld.hero_assignment import HeroAssignment, AssignmentError
from game_runtime.event_bus import EventBus


def _make_hero(hero_id: str = "h1", name: str = "Alice", status: HeroStatus = HeroStatus.IDLE) -> HeroEntity:
    h = HeroEntity(hero_id=hero_id, name=name, archetype="warrior")
    h.status = status
    return h


def _make_quest(
    quest_id: str = "q1",
    required_heroes: int = 1,
    max_heroes: int = 3,
    status: QuestStatus = QuestStatus.AVAILABLE,
) -> Quest:
    return Quest(
        quest_id=quest_id,
        title="Test",
        description="desc",
        quest_type=QuestType.COMBAT,
        difficulty=QuestDifficulty.EASY,
        reward=Reward(),
        required_heroes=required_heroes,
        max_heroes=max_heroes,
        status=status,
    )


class TestHeroAssignment(unittest.TestCase):
    def setUp(self):
        self.bus = EventBus()
        self.assignment = HeroAssignment(self.bus)

    def test_valid_assignment_sets_hero_status_traveling(self):
        quest = _make_quest()
        hero = _make_hero()
        self.assignment.assign(quest, [hero])
        self.assertEqual(hero.status, HeroStatus.TRAVELING)

    def test_valid_assignment_sets_quest_status_assigned(self):
        quest = _make_quest()
        hero = _make_hero()
        self.assignment.assign(quest, [hero])
        self.assertEqual(quest.status, QuestStatus.ASSIGNED)

    def test_valid_assignment_sets_assigned_hero_ids(self):
        quest = _make_quest()
        hero = _make_hero("h1")
        self.assignment.assign(quest, [hero])
        self.assertEqual(quest.assigned_hero_ids, ["h1"])

    def test_non_idle_hero_raises_assignment_error(self):
        quest = _make_quest()
        hero = _make_hero(status=HeroStatus.ON_QUEST)
        with self.assertRaises(AssignmentError):
            self.assignment.assign(quest, [hero])

    def test_too_few_heroes_raises_assignment_error(self):
        quest = _make_quest(required_heroes=2)
        hero = _make_hero()
        with self.assertRaises(AssignmentError):
            self.assignment.assign(quest, [hero])

    def test_too_many_heroes_raises_assignment_error(self):
        quest = _make_quest(max_heroes=1)
        heroes = [_make_hero("h1"), _make_hero("h2")]
        with self.assertRaises(AssignmentError):
            self.assignment.assign(quest, heroes)

    def test_non_available_quest_raises_assignment_error(self):
        quest = _make_quest(status=QuestStatus.ASSIGNED)
        hero = _make_hero()
        with self.assertRaises(AssignmentError):
            self.assignment.assign(quest, [hero])

    def test_quest_assigned_event_published_on_success(self):
        quest = _make_quest("q1")
        hero = _make_hero("h1")

        received = []
        self.bus.subscribe("quest.assigned", lambda d: received.append(d))

        self.assignment.assign(quest, [hero])
        self.assertEqual(len(received), 1)
        self.assertEqual(received[0]["quest_id"], "q1")
        self.assertEqual(received[0]["hero_ids"], ["h1"])

    def test_validate_returns_false_with_reason_for_non_idle_hero(self):
        quest = _make_quest()
        hero = _make_hero(status=HeroStatus.TRAVELING)
        valid, reason = self.assignment.validate(quest, [hero])
        self.assertFalse(valid)
        self.assertIn("not idle", reason)

    def test_validate_returns_false_with_reason_for_too_few(self):
        quest = _make_quest(required_heroes=2)
        hero = _make_hero()
        valid, reason = self.assignment.validate(quest, [hero])
        self.assertFalse(valid)
        self.assertIn("Not enough", reason)

    def test_validate_returns_false_with_reason_for_too_many(self):
        quest = _make_quest(max_heroes=1)
        heroes = [_make_hero("h1"), _make_hero("h2")]
        valid, reason = self.assignment.validate(quest, heroes)
        self.assertFalse(valid)
        self.assertIn("Too many", reason)

    def test_validate_returns_false_with_reason_for_non_available_quest(self):
        quest = _make_quest(status=QuestStatus.COMPLETE)
        hero = _make_hero()
        valid, reason = self.assignment.validate(quest, [hero])
        self.assertFalse(valid)
        self.assertIn("not available", reason)

    def test_validate_returns_true_empty_reason_on_success(self):
        quest = _make_quest()
        hero = _make_hero()
        valid, reason = self.assignment.validate(quest, [hero])
        self.assertTrue(valid)
        self.assertEqual(reason, "")


if __name__ == "__main__":
    unittest.main()
