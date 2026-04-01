import unittest

from quest.quest_model import Quest, QuestType, QuestDifficulty, Consequence, Reward
from quest.critical_injector import CriticalWindow, CriticalInjector, build_default_injector


def make_critical_quest(qid: str = "crit_q") -> Quest:
    return Quest(
        quest_id=qid,
        title="Critical Quest",
        description="A critical quest.",
        quest_type=QuestType.COMBAT,
        difficulty=QuestDifficulty.ELITE,
        is_critical=True,
        consequence=Consequence(type="boss_buff"),
    )


class TestCriticalInjectorGetDue(unittest.TestCase):
    def setUp(self):
        self.q1 = make_critical_quest("cq1")
        self.q2 = make_critical_quest("cq2")
        self.injector = CriticalInjector(windows=[
            CriticalWindow(inject_at_tick=100, quest=self.q1),
            CriticalWindow(inject_at_tick=300, quest=self.q2),
        ])

    def test_returns_quests_at_or_after_tick(self):
        due = self.injector.get_due(100)
        self.assertEqual(len(due), 1)
        self.assertEqual(due[0].quest_id, "cq1")

    def test_returns_nothing_before_window_tick(self):
        due = self.injector.get_due(50)
        self.assertEqual(due, [])

    def test_does_not_return_same_quest_twice(self):
        self.injector.get_due(100)
        due_again = self.injector.get_due(150)
        ids = [q.quest_id for q in due_again]
        self.assertNotIn("cq1", ids)

    def test_returns_multiple_when_several_due(self):
        due = self.injector.get_due(300)
        self.assertEqual(len(due), 2)

    def test_windows_sorted_by_tick(self):
        # Create injector with out-of-order windows
        q_a = make_critical_quest("qa")
        q_b = make_critical_quest("qb")
        injector = CriticalInjector(windows=[
            CriticalWindow(inject_at_tick=500, quest=q_a),
            CriticalWindow(inject_at_tick=200, quest=q_b),
        ])
        due = injector.get_due(200)
        self.assertEqual(len(due), 1)
        self.assertEqual(due[0].quest_id, "qb")


class TestCriticalInjectorReset(unittest.TestCase):
    def test_reset_clears_injected_tracking(self):
        q = make_critical_quest("cq_reset")
        injector = CriticalInjector(windows=[
            CriticalWindow(inject_at_tick=50, quest=q),
        ])
        # First injection
        due = injector.get_due(50)
        self.assertEqual(len(due), 1)
        # After reset, should fire again
        injector.reset()
        due_again = injector.get_due(50)
        self.assertEqual(len(due_again), 1)
        self.assertEqual(due_again[0].quest_id, "cq_reset")


class TestBuildDefaultInjector(unittest.TestCase):
    def test_returns_critical_injector(self):
        injector = build_default_injector(act_start_tick=0)
        self.assertIsInstance(injector, CriticalInjector)

    def test_has_two_windows(self):
        injector = build_default_injector(act_start_tick=0)
        self.assertEqual(len(injector._windows), 2)

    def test_windows_use_act_start_tick(self):
        injector = build_default_injector(act_start_tick=1000)
        ticks = [w.inject_at_tick for w in injector._windows]
        self.assertIn(1200, ticks)
        self.assertIn(1400, ticks)

    def test_windows_have_boss_buff_consequence(self):
        injector = build_default_injector(act_start_tick=0)
        for window in injector._windows:
            self.assertIsNotNone(window.quest.consequence)
            self.assertEqual(window.quest.consequence.type, "boss_buff")

    def test_quests_are_critical(self):
        injector = build_default_injector(act_start_tick=0)
        for window in injector._windows:
            self.assertTrue(window.quest.is_critical)

    def test_get_due_fires_at_correct_ticks(self):
        injector = build_default_injector(act_start_tick=0)
        # Nothing before tick 200
        due = injector.get_due(199)
        self.assertEqual(due, [])
        # First window at 200
        due = injector.get_due(200)
        self.assertEqual(len(due), 1)
        # Second window at 400
        due = injector.get_due(400)
        self.assertEqual(len(due), 1)


if __name__ == "__main__":
    unittest.main()
