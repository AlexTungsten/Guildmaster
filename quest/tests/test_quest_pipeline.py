import unittest
from unittest.mock import MagicMock, patch
from typing import List, Optional

from hero.hero_entity import HeroEntity, Stat
from hero.hero_entity import Skill
from enemy.enemy import Enemy
from combat.combat_engine import CombatResult, CombatRound
from game_runtime.event_bus import EventBus
from quest.quest_model import Quest, QuestType, QuestDifficulty, QuestStatus, Reward
from quest.quest_pipeline import QuestPipeline, QuestPipelineResult
from quest.reward_distributor import DistributionResult


def make_hero(hero_id: str = "h1") -> HeroEntity:
    h = HeroEntity(
        hero_id=hero_id,
        name="Test Hero",
        archetype="warrior",
        intelligence=12,
        strength=14,
    )
    return h


def make_enemy() -> Enemy:
    skill = Skill(
        name="Slash",
        description="A slash attack.",
        associated_stat=Stat.STR,
        dice_slots=1,
        effect_type="damage",
    )
    return Enemy(
        enemy_id="e1",
        name="Goblin",
        archetype="melee",
        act=1,
        max_health=10,
        current_health=10,
        skills=[skill],
        base_dice_count=2,
    )


def make_combat_quest() -> Quest:
    return Quest(
        quest_id="combat_q",
        title="Combat Test Quest",
        description="Fight!",
        quest_type=QuestType.COMBAT,
        difficulty=QuestDifficulty.EASY,
        travel_time=10,
        resolution_time=30,
        base_exhaustion=5.0,
        reward=Reward(gold=20, xp=30),
    )


def make_stat_check_quest() -> Quest:
    return Quest(
        quest_id="stat_q",
        title="Stat Check Test Quest",
        description="Think!",
        quest_type=QuestType.STAT_CHECK,
        difficulty=QuestDifficulty.EASY,
        travel_time=10,
        resolution_time=30,
        base_exhaustion=5.0,
        reward=Reward(gold=15, xp=20),
        stat_checks=[{"stat": Stat.INT, "dc": 5}],  # Very low DC so it usually passes
    )


def make_mock_combat_engine(victory: bool = True) -> MagicMock:
    mock_engine = MagicMock()
    combat_result = CombatResult(
        victory=victory,
        rounds=[],
        heroes_survived=["h1"] if victory else [],
        total_hero_damage_taken=10,
    )
    mock_engine.pre_simulate.return_value = combat_result
    mock_engine.simulate.return_value = combat_result
    return mock_engine


class TestQuestPipelineCombat(unittest.TestCase):
    def setUp(self):
        self.event_bus = EventBus()
        self.published_events = {}
        self.event_bus.subscribe("quest.complete", lambda d: self.published_events.update({"quest.complete": d}))
        self.event_bus.subscribe("quest.pre_simulation_ready", lambda d: self.published_events.update({"quest.pre_simulation_ready": d}))

    def test_combat_quest_returns_pipeline_result(self):
        mock_engine = make_mock_combat_engine(victory=True)
        pipeline = QuestPipeline(event_bus=self.event_bus, combat_engine=mock_engine)
        heroes = [make_hero()]
        quest = make_combat_quest()
        result = pipeline.run(quest, heroes, enemies=[make_enemy()])
        self.assertIsInstance(result, QuestPipelineResult)

    def test_combat_quest_victory_true_when_won(self):
        mock_engine = make_mock_combat_engine(victory=True)
        pipeline = QuestPipeline(event_bus=self.event_bus, combat_engine=mock_engine)
        heroes = [make_hero()]
        quest = make_combat_quest()
        result = pipeline.run(quest, heroes, enemies=[make_enemy()])
        self.assertTrue(result.victory)

    def test_combat_quest_victory_false_when_lost(self):
        mock_engine = make_mock_combat_engine(victory=False)
        pipeline = QuestPipeline(event_bus=self.event_bus, combat_engine=mock_engine)
        heroes = [make_hero()]
        quest = make_combat_quest()
        result = pipeline.run(quest, heroes, enemies=[make_enemy()])
        self.assertFalse(result.victory)

    def test_quest_complete_event_published(self):
        mock_engine = make_mock_combat_engine(victory=True)
        pipeline = QuestPipeline(event_bus=self.event_bus, combat_engine=mock_engine)
        heroes = [make_hero()]
        quest = make_combat_quest()
        pipeline.run(quest, heroes, enemies=[make_enemy()])
        self.assertIn("quest.complete", self.published_events)

    def test_pre_simulation_ready_event_published_for_combat(self):
        mock_engine = make_mock_combat_engine(victory=True)
        pipeline = QuestPipeline(event_bus=self.event_bus, combat_engine=mock_engine)
        heroes = [make_hero()]
        quest = make_combat_quest()
        pipeline.run(quest, heroes, enemies=[make_enemy()])
        self.assertIn("quest.pre_simulation_ready", self.published_events)

    def test_quest_status_complete_at_end(self):
        mock_engine = make_mock_combat_engine(victory=True)
        pipeline = QuestPipeline(event_bus=self.event_bus, combat_engine=mock_engine)
        heroes = [make_hero()]
        quest = make_combat_quest()
        pipeline.run(quest, heroes, enemies=[make_enemy()])
        self.assertEqual(quest.status, QuestStatus.COMPLETE)

    def test_distribution_present_on_victory(self):
        mock_engine = make_mock_combat_engine(victory=True)
        pipeline = QuestPipeline(event_bus=self.event_bus, combat_engine=mock_engine)
        heroes = [make_hero()]
        quest = make_combat_quest()
        result = pipeline.run(quest, heroes, enemies=[make_enemy()])
        self.assertIsNotNone(result.distribution)

    def test_distribution_none_on_defeat(self):
        mock_engine = make_mock_combat_engine(victory=False)
        pipeline = QuestPipeline(event_bus=self.event_bus, combat_engine=mock_engine)
        heroes = [make_hero()]
        quest = make_combat_quest()
        result = pipeline.run(quest, heroes, enemies=[make_enemy()])
        self.assertIsNone(result.distribution)

    def test_combat_result_in_pipeline_result(self):
        mock_engine = make_mock_combat_engine(victory=True)
        pipeline = QuestPipeline(event_bus=self.event_bus, combat_engine=mock_engine)
        heroes = [make_hero()]
        quest = make_combat_quest()
        result = pipeline.run(quest, heroes, enemies=[make_enemy()])
        self.assertIsNotNone(result.combat_result)

    def test_quest_id_preserved_in_result(self):
        mock_engine = make_mock_combat_engine(victory=True)
        pipeline = QuestPipeline(event_bus=self.event_bus, combat_engine=mock_engine)
        heroes = [make_hero()]
        quest = make_combat_quest()
        result = pipeline.run(quest, heroes, enemies=[make_enemy()])
        self.assertEqual(result.quest_id, quest.quest_id)


class TestQuestPipelineStatCheck(unittest.TestCase):
    def setUp(self):
        self.event_bus = EventBus()
        self.published_events = {}
        self.event_bus.subscribe("quest.complete", lambda d: self.published_events.update({"quest.complete": d}))
        self.event_bus.subscribe("quest.pre_simulation_ready", lambda d: self.published_events.update({"quest.pre_simulation_ready": d}))

    def test_stat_check_quest_resolves_without_combat(self):
        mock_engine = MagicMock()
        pipeline = QuestPipeline(event_bus=self.event_bus, combat_engine=mock_engine)
        heroes = [make_hero()]
        quest = make_stat_check_quest()
        result = pipeline.run(quest, heroes, enemies=None)
        mock_engine.simulate.assert_not_called()
        mock_engine.pre_simulate.assert_not_called()

    def test_stat_check_combat_result_none(self):
        mock_engine = MagicMock()
        pipeline = QuestPipeline(event_bus=self.event_bus, combat_engine=mock_engine)
        heroes = [make_hero()]
        quest = make_stat_check_quest()
        result = pipeline.run(quest, heroes, enemies=None)
        self.assertIsNone(result.combat_result)

    def test_stat_check_pre_sim_event_not_published(self):
        mock_engine = MagicMock()
        pipeline = QuestPipeline(event_bus=self.event_bus, combat_engine=mock_engine)
        heroes = [make_hero()]
        quest = make_stat_check_quest()
        pipeline.run(quest, heroes, enemies=None)
        self.assertNotIn("quest.pre_simulation_ready", self.published_events)

    def test_stat_check_quest_complete_event_published(self):
        mock_engine = MagicMock()
        pipeline = QuestPipeline(event_bus=self.event_bus, combat_engine=mock_engine)
        heroes = [make_hero()]
        quest = make_stat_check_quest()
        pipeline.run(quest, heroes, enemies=None)
        self.assertIn("quest.complete", self.published_events)

    def test_stat_check_quest_status_complete_at_end(self):
        mock_engine = MagicMock()
        pipeline = QuestPipeline(event_bus=self.event_bus, combat_engine=mock_engine)
        heroes = [make_hero()]
        quest = make_stat_check_quest()
        pipeline.run(quest, heroes, enemies=None)
        self.assertEqual(quest.status, QuestStatus.COMPLETE)

    def test_stat_check_returns_pipeline_result(self):
        mock_engine = MagicMock()
        pipeline = QuestPipeline(event_bus=self.event_bus, combat_engine=mock_engine)
        heroes = [make_hero()]
        quest = make_stat_check_quest()
        result = pipeline.run(quest, heroes, enemies=None)
        self.assertIsInstance(result, QuestPipelineResult)


if __name__ == "__main__":
    unittest.main()
