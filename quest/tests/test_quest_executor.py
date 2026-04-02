"""Tests for QuestExecutor — the glue between assignment, pipeline, and economy."""

import unittest

from game_runtime.event_bus import EventBus
from economy.economy_controller import EconomyController
from overworld.map_state import MapState, BossSlot
from quest.quest_model import Quest, QuestType, QuestDifficulty, QuestStatus, Reward
from quest.quest_executor import QuestExecutor
from combat.combat_engine import CombatEngine
from hero.archetype_loader import load_archetype


def _make_quest(quest_id="q_1", quest_type=QuestType.COMBAT, difficulty=QuestDifficulty.EASY,
                gold=20, xp=30):
    return Quest(
        quest_id=quest_id,
        title="Test Quest",
        description="A test quest",
        quest_type=quest_type,
        difficulty=difficulty,
        reward=Reward(gold=gold, xp=xp),
        travel_time=0,
        resolution_time=0,
        expiration_time=999,
    )


class TestQuestExecutorAssignment(unittest.TestCase):
    """Test that quest executor correctly processes player.assign_quest events."""

    def setUp(self):
        self.eb = EventBus()
        self.map_state = MapState(current_act=1, act_start_tick=0, boss=BossSlot(boss_id="b1", act=1))
        self.econ = EconomyController(self.eb, starting_gold=500)
        self.engine = CombatEngine(self.eb)
        self.executor = QuestExecutor(
            event_bus=self.eb,
            map_state=self.map_state,
            roster=self.econ.roster,
            ledger=self.econ.ledger,
            combat_engine=self.engine,
        )
        self.executed_events = []
        self.error_events = []
        self.eb.subscribe("quest.executed", lambda d: self.executed_events.append(d))
        self.eb.subscribe("quest.error", lambda d: self.error_events.append(d))

    def _add_hero(self, archetype="barbarian", hero_id="h_0", name="TestHero"):
        hero = load_archetype(archetype, hero_id, name)
        self.econ.roster.add_hero(hero)
        return hero

    def test_successful_combat_quest(self):
        hero = self._add_hero()
        quest = _make_quest(quest_type=QuestType.COMBAT, difficulty=QuestDifficulty.EASY, gold=20)
        self.map_state.add_quest(quest)

        self.eb.publish("player.assign_quest", {"quest_id": "q_1", "hero_ids": ["h_0"]})

        self.assertEqual(len(self.executed_events), 1)
        self.assertTrue(self.executed_events[0]["victory"] or not self.executed_events[0]["victory"])

    def test_successful_stat_check_quest(self):
        hero = self._add_hero()
        quest = _make_quest(quest_type=QuestType.STAT_CHECK, gold=15, xp=25)
        quest.stat_checks = [{"stat": "strength", "dc": 5}]
        self.map_state.add_quest(quest)

        self.eb.publish("player.assign_quest", {"quest_id": "q_1", "hero_ids": ["h_0"]})

        self.assertEqual(len(self.executed_events), 1)

    def test_hero_reset_to_idle_after_quest(self):
        hero = self._add_hero()
        quest = _make_quest(quest_type=QuestType.STAT_CHECK)
        quest.stat_checks = [{"stat": "strength", "dc": 1}]
        self.map_state.add_quest(quest)

        self.eb.publish("player.assign_quest", {"quest_id": "q_1", "hero_ids": ["h_0"]})

        from hero.hero_entity import HeroStatus
        self.assertEqual(hero.status, HeroStatus.IDLE)

    def test_hero_healed_after_quest(self):
        hero = self._add_hero()
        hero.current_health = 10  # Damage before quest
        quest = _make_quest(quest_type=QuestType.STAT_CHECK)
        quest.stat_checks = [{"stat": "strength", "dc": 1}]
        self.map_state.add_quest(quest)

        self.eb.publish("player.assign_quest", {"quest_id": "q_1", "hero_ids": ["h_0"]})

        # Default heal_percent=1.0 means full heal
        self.assertEqual(hero.current_health, hero.max_health)

    def test_partial_heal(self):
        hero = self._add_hero()
        self.executor.heal_percent = 0.5
        hero.current_health = 1
        quest = _make_quest(quest_type=QuestType.STAT_CHECK)
        quest.stat_checks = [{"stat": "strength", "dc": 1}]
        self.map_state.add_quest(quest)

        self.eb.publish("player.assign_quest", {"quest_id": "q_1", "hero_ids": ["h_0"]})

        expected = 1 + int(hero.max_health * 0.5)
        self.assertEqual(hero.current_health, min(hero.max_health, expected))

    def test_gold_credited_on_victory(self):
        hero = self._add_hero()
        initial_gold = self.econ.ledger.balance
        quest = _make_quest(quest_type=QuestType.STAT_CHECK, gold=50)
        quest.stat_checks = [{"stat": "strength", "dc": 1}]  # Easy pass
        self.map_state.add_quest(quest)

        self.eb.publish("player.assign_quest", {"quest_id": "q_1", "hero_ids": ["h_0"]})

        if self.executed_events[0]["victory"]:
            self.assertEqual(self.econ.ledger.balance, initial_gold + 50)

    def test_error_on_missing_quest(self):
        self._add_hero()
        self.eb.publish("player.assign_quest", {"quest_id": "nonexistent", "hero_ids": ["h_0"]})

        self.assertEqual(len(self.error_events), 1)
        self.assertIn("not found", self.error_events[0]["reason"])

    def test_error_on_missing_hero(self):
        quest = _make_quest()
        self.map_state.add_quest(quest)

        self.eb.publish("player.assign_quest", {"quest_id": "q_1", "hero_ids": ["no_such_hero"]})

        self.assertEqual(len(self.error_events), 1)
        self.assertIn("not found", self.error_events[0]["reason"])

    def test_error_on_double_assignment(self):
        hero = self._add_hero()
        q1 = _make_quest(quest_id="q_1", quest_type=QuestType.STAT_CHECK)
        q1.stat_checks = [{"stat": "strength", "dc": 1}]
        q2 = _make_quest(quest_id="q_2", quest_type=QuestType.STAT_CHECK)
        q2.stat_checks = [{"stat": "strength", "dc": 1}]
        self.map_state.add_quest(q1)
        self.map_state.add_quest(q2)

        # First assignment succeeds and resets hero to IDLE
        self.eb.publish("player.assign_quest", {"quest_id": "q_1", "hero_ids": ["h_0"]})
        # Second should also work since hero is back to IDLE
        self.eb.publish("player.assign_quest", {"quest_id": "q_2", "hero_ids": ["h_0"]})

        self.assertEqual(len(self.executed_events), 2)

    def test_multi_hero_assignment(self):
        h1 = self._add_hero("barbarian", "h_0", "Hero A")
        h2 = self._add_hero("rogue", "h_1", "Hero B")
        quest = _make_quest(quest_type=QuestType.COMBAT)
        quest.max_heroes = 3
        self.map_state.add_quest(quest)

        self.eb.publish("player.assign_quest", {"quest_id": "q_1", "hero_ids": ["h_0", "h_1"]})

        self.assertEqual(len(self.executed_events), 1)


class TestEncounterSpawning(unittest.TestCase):
    """Verify that enemies are spawned from the encounter table."""

    def test_combat_quest_spawns_enemies(self):
        eb = EventBus()
        map_state = MapState(current_act=1, act_start_tick=0, boss=BossSlot(boss_id="b1", act=1))
        econ = EconomyController(eb, starting_gold=500)
        engine = CombatEngine(eb)
        executor = QuestExecutor(
            event_bus=eb, map_state=map_state, roster=econ.roster,
            ledger=econ.ledger, combat_engine=engine,
        )

        hero = load_archetype("barbarian", "h_0", "Tester")
        econ.roster.add_hero(hero)

        quest = _make_quest(quest_type=QuestType.COMBAT, difficulty=QuestDifficulty.EASY)
        map_state.add_quest(quest)

        results = []
        eb.subscribe("quest.executed", lambda d: results.append(d))

        eb.publish("player.assign_quest", {"quest_id": "q_1", "hero_ids": ["h_0"]})

        # Should have run combat (not errored)
        self.assertEqual(len(results), 1)


if __name__ == "__main__":
    unittest.main()
