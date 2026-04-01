import random
import unittest
from unittest.mock import MagicMock, patch, call

from quest.quest_model import Quest, QuestType, QuestDifficulty, QuestStatus, Reward, Consequence
from overworld.map_state import MapState, BossSlot
from overworld.quest_spawner import QuestSpawner
from overworld.shop_spawner import ShopSpawner
from overworld.boss_timer import BossTimer
from overworld.expiration_tracker import ExpirationTracker
from overworld.overworld_controller import OverworldController
from quest.critical_injector import CriticalInjector, CriticalWindow
from game_runtime.event_bus import EventBus


def _make_controller_with_mocks():
    bus = EventBus()
    map_state = MapState(
        current_act=1,
        boss=BossSlot(boss_id="boss_1", act=1),
    )
    quest_spawner = MagicMock(spec=QuestSpawner)
    quest_spawner.tick.return_value = None
    shop_spawner = MagicMock(spec=ShopSpawner)
    shop_spawner.tick.return_value = None
    boss_timer = MagicMock(spec=BossTimer)
    boss_timer.tick.return_value = False
    critical_injector = MagicMock(spec=CriticalInjector)
    critical_injector.get_due.return_value = []

    controller = OverworldController(
        event_bus=bus,
        map_state=map_state,
        quest_spawner=quest_spawner,
        shop_spawner=shop_spawner,
        boss_timer=boss_timer,
        critical_injector=critical_injector,
    )
    return controller, bus, map_state, quest_spawner, shop_spawner, boss_timer, critical_injector


class TestOverworldControllerTick(unittest.TestCase):
    def test_tick_calls_quest_spawner(self):
        controller, *_, quest_spawner, _, boss_timer, critical_injector = _make_controller_with_mocks()
        controller.tick(current_tick=100)
        quest_spawner.tick.assert_called_once()

    def test_tick_calls_shop_spawner(self):
        controller, *_, quest_spawner, shop_spawner, boss_timer, critical_injector = _make_controller_with_mocks()
        controller.tick(current_tick=100)
        shop_spawner.tick.assert_called_once()

    def test_tick_calls_boss_timer(self):
        controller, *_, quest_spawner, shop_spawner, boss_timer, critical_injector = _make_controller_with_mocks()
        controller.tick(current_tick=100)
        boss_timer.tick.assert_called_once()

    def test_tick_calls_critical_injector(self):
        controller, *_, quest_spawner, shop_spawner, boss_timer, critical_injector = _make_controller_with_mocks()
        controller.tick(current_tick=100)
        critical_injector.get_due.assert_called_once_with(100)

    def test_critical_quest_injected_into_map_state(self):
        controller, bus, map_state, quest_spawner, shop_spawner, boss_timer, critical_injector = _make_controller_with_mocks()
        critical_quest = Quest(
            quest_id="crit_q",
            title="Critical",
            description="desc",
            quest_type=QuestType.COMBAT,
            difficulty=QuestDifficulty.ELITE,
            reward=Reward(),
        )
        critical_injector.get_due.return_value = [critical_quest]

        controller.tick(current_tick=200)
        self.assertIn("crit_q", map_state.active_quests)

    def test_critical_quest_boss_buff_consequence_propagates(self):
        bus = EventBus()
        map_state = MapState(
            current_act=1,
            boss=BossSlot(boss_id="boss_1", act=1),
        )
        quest_spawner = MagicMock(spec=QuestSpawner)
        quest_spawner.tick.return_value = None
        shop_spawner = MagicMock(spec=ShopSpawner)
        shop_spawner.tick.return_value = None
        boss_timer = MagicMock(spec=BossTimer)
        boss_timer.tick.return_value = False
        critical_injector = MagicMock(spec=CriticalInjector)
        critical_injector.get_due.return_value = []

        controller = OverworldController(
            event_bus=bus,
            map_state=map_state,
            quest_spawner=quest_spawner,
            shop_spawner=shop_spawner,
            boss_timer=boss_timer,
            critical_injector=critical_injector,
        )

        # Manually publish a critical_expired event with a boss_buff consequence
        consequence = Consequence(type="boss_buff", data={"buff": "enraged"})
        bus.publish("quest.critical_expired", {"quest_id": "q1", "consequence": consequence})

        self.assertIn("enraged", map_state.boss.buffs)

    def test_non_boss_buff_consequence_does_not_add_buff(self):
        bus = EventBus()
        map_state = MapState(
            current_act=1,
            boss=BossSlot(boss_id="boss_1", act=1),
        )
        quest_spawner = MagicMock(spec=QuestSpawner)
        quest_spawner.tick.return_value = None
        shop_spawner = MagicMock(spec=ShopSpawner)
        shop_spawner.tick.return_value = None
        boss_timer = MagicMock(spec=BossTimer)
        boss_timer.tick.return_value = False
        critical_injector = MagicMock(spec=CriticalInjector)
        critical_injector.get_due.return_value = []

        controller = OverworldController(
            event_bus=bus,
            map_state=map_state,
            quest_spawner=quest_spawner,
            shop_spawner=shop_spawner,
            boss_timer=boss_timer,
            critical_injector=critical_injector,
        )

        consequence = Consequence(type="other_type", data={"buff": "enraged"})
        bus.publish("quest.critical_expired", {"quest_id": "q1", "consequence": consequence})
        self.assertEqual(map_state.boss.buffs, [])


class TestOverworldControllerCreate(unittest.TestCase):
    def test_create_returns_overworld_controller(self):
        bus = EventBus()
        controller = OverworldController.create(bus, act=1, current_tick=0)
        self.assertIsInstance(controller, OverworldController)

    def test_create_sets_correct_act(self):
        bus = EventBus()
        controller = OverworldController.create(bus, act=2, current_tick=0)
        self.assertEqual(controller.map_state.current_act, 2)

    def test_create_sets_boss(self):
        bus = EventBus()
        controller = OverworldController.create(bus, act=1, current_tick=0)
        self.assertIsNotNone(controller.map_state.boss)
        self.assertEqual(controller.map_state.boss.boss_id, "boss_1")

    def test_create_has_all_subsystems(self):
        bus = EventBus()
        controller = OverworldController.create(bus, act=1, current_tick=0)
        self.assertIsNotNone(controller._quest_spawner)
        self.assertIsNotNone(controller._shop_spawner)
        self.assertIsNotNone(controller._boss_timer)
        self.assertIsNotNone(controller._critical_injector)
        self.assertIsNotNone(controller._expiration_tracker)


class TestOverworldControllerIntegration(unittest.TestCase):
    def test_multiple_ticks_eventually_spawns_quest(self):
        bus = EventBus()
        controller = OverworldController.create(bus, act=1, current_tick=0)
        # QuestSpawner default interval is 60; tick at 60 should spawn
        controller.tick(current_tick=60)
        self.assertGreater(len(controller.map_state.active_quests), 0)

    def test_many_ticks_trigger_boss_timer(self):
        bus = EventBus()
        controller = OverworldController.create(bus, act=1, current_tick=0)
        appeared_events = []
        bus.subscribe("boss.appeared", lambda d: appeared_events.append(d))

        # boss_timer_duration default is 600
        for tick in range(1, 605):
            controller.tick(current_tick=tick)

        self.assertEqual(len(appeared_events), 1)

    def test_ticks_spawn_shop_after_interval(self):
        bus = EventBus()
        controller = OverworldController.create(bus, act=1, current_tick=0)
        spawned = []
        bus.subscribe("shop.spawned", lambda d: spawned.append(d))

        # ShopSpawner default interval is 180
        controller.tick(current_tick=180)
        self.assertEqual(len(spawned), 1)


if __name__ == "__main__":
    unittest.main()
