import unittest

from overworld.map_state import MapState, BossSlot
from overworld.boss_timer import BossTimer
from game_runtime.event_bus import EventBus


def _make_map_state(act_start_tick: int = 0, boss_timer_duration: int = 600) -> MapState:
    return MapState(
        current_act=1,
        act_start_tick=act_start_tick,
        boss_timer_duration=boss_timer_duration,
        boss=BossSlot(boss_id="boss_1", act=1),
    )


class TestBossTimer(unittest.TestCase):
    def setUp(self):
        self.bus = EventBus()
        self.timer = BossTimer(self.bus)

    def test_ticks_remaining_counts_down_correctly(self):
        ms = _make_map_state(act_start_tick=0, boss_timer_duration=600)
        self.assertEqual(self.timer.ticks_remaining(ms, current_tick=0), 600)
        self.assertEqual(self.timer.ticks_remaining(ms, current_tick=300), 300)
        self.assertEqual(self.timer.ticks_remaining(ms, current_tick=600), 0)

    def test_ticks_remaining_does_not_go_below_zero(self):
        ms = _make_map_state(act_start_tick=0, boss_timer_duration=600)
        self.assertEqual(self.timer.ticks_remaining(ms, current_tick=700), 0)

    def test_boss_appeared_event_published_when_timer_reaches_zero(self):
        ms = _make_map_state(act_start_tick=0, boss_timer_duration=600)
        received = []
        self.bus.subscribe("boss.appeared", lambda d: received.append(d))

        self.timer.tick(ms, current_tick=600)
        self.assertEqual(len(received), 1)
        self.assertEqual(received[0]["act"], 1)
        self.assertEqual(received[0]["boss_id"], "boss_1")

    def test_tick_returns_true_when_boss_first_appears(self):
        ms = _make_map_state(act_start_tick=0, boss_timer_duration=600)
        result = self.timer.tick(ms, current_tick=600)
        self.assertTrue(result)

    def test_tick_returns_false_before_timer_expires(self):
        ms = _make_map_state(act_start_tick=0, boss_timer_duration=600)
        result = self.timer.tick(ms, current_tick=599)
        self.assertFalse(result)

    def test_tick_returns_false_after_boss_already_appeared(self):
        ms = _make_map_state(act_start_tick=0, boss_timer_duration=600)
        self.timer.tick(ms, current_tick=600)
        result = self.timer.tick(ms, current_tick=601)
        self.assertFalse(result)

    def test_boss_appeared_only_published_once(self):
        ms = _make_map_state(act_start_tick=0, boss_timer_duration=600)
        received = []
        self.bus.subscribe("boss.appeared", lambda d: received.append(d))

        self.timer.tick(ms, current_tick=600)
        self.timer.tick(ms, current_tick=700)
        self.assertEqual(len(received), 1)

    def test_tick_reveals_boss_on_map_state(self):
        ms = _make_map_state(act_start_tick=0, boss_timer_duration=600)
        self.timer.tick(ms, current_tick=600)
        self.assertTrue(ms.boss.revealed)

    def test_on_boss_defeated_sets_defeated_true(self):
        ms = _make_map_state()
        self.timer.on_boss_defeated(ms)
        self.assertTrue(ms.boss.defeated)

    def test_on_boss_defeated_publishes_event(self):
        ms = _make_map_state()
        received = []
        self.bus.subscribe("boss.defeated", lambda d: received.append(d))

        self.timer.on_boss_defeated(ms)
        self.assertEqual(len(received), 1)
        self.assertEqual(received[0]["act"], 1)

    def test_reset_for_act_resets_trigger(self):
        ms = _make_map_state(act_start_tick=0, boss_timer_duration=600)
        self.timer.tick(ms, current_tick=600)
        self.assertTrue(self.timer._triggered)

        self.timer.reset_for_act(ms, new_act=2, current_tick=601)
        self.assertFalse(self.timer._triggered)

    def test_reset_for_act_updates_map_state(self):
        ms = _make_map_state(act_start_tick=0, boss_timer_duration=600)
        self.timer.reset_for_act(ms, new_act=2, current_tick=601)
        self.assertEqual(ms.current_act, 2)
        self.assertEqual(ms.act_start_tick, 601)

    def test_reset_for_act_publishes_act_started(self):
        ms = _make_map_state()
        received = []
        self.bus.subscribe("act.started", lambda d: received.append(d))

        self.timer.reset_for_act(ms, new_act=2, current_tick=0)
        self.assertEqual(len(received), 1)
        self.assertEqual(received[0]["act"], 2)

    def test_boss_appears_with_accumulated_buffs(self):
        ms = _make_map_state(boss_timer_duration=600)
        ms.boss.buffs = ["enraged", "shielded"]
        received = []
        self.bus.subscribe("boss.appeared", lambda d: received.append(d))

        self.timer.tick(ms, current_tick=600)
        self.assertEqual(received[0]["buffs"], ["enraged", "shielded"])


if __name__ == "__main__":
    unittest.main()
