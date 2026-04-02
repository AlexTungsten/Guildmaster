"""
quest_executor.py — Wires player assignment commands to the quest pipeline.

QuestExecutor subscribes to "player.assign_quest" and orchestrates the full
quest lifecycle:
  1. Look up quest from MapState and heroes from RosterManager.
  2. Validate and commit via HeroAssignment.
  3. Spawn enemies from the encounter table (data/encounters.json).
  4. Run QuestPipeline (travel -> resolution -> rewards).
  5. Credit gold to the GoldLedger on victory.
  6. Heal heroes and reset them to IDLE.

Encounter tables are data-driven: data/encounters.json maps
act + difficulty to lists of possible enemy compositions.
"""

import json
import os
import random
from typing import Dict, List, Optional

from game_runtime.event_bus import EventBus
from hero.hero_entity import HeroEntity, HeroStatus
from enemy.enemy import Enemy
from enemy.enemy_loader import load_enemy
from economy.gold_ledger import GoldLedger
from economy.roster_manager import RosterManager
from overworld.map_state import MapState
from overworld.hero_assignment import HeroAssignment, AssignmentError
from quest.quest_model import Quest, QuestType
from quest.quest_pipeline import QuestPipeline, QuestPipelineResult
from combat.combat_engine import CombatEngine

_ENCOUNTER_PATH = os.path.join(
    os.path.dirname(__file__), "..", "data", "encounters.json"
)


def _load_encounter_table() -> dict:
    """Load the encounter table from JSON."""
    with open(_ENCOUNTER_PATH, "r") as f:
        return json.load(f)


class QuestExecutor:
    def __init__(
        self,
        event_bus: EventBus,
        map_state: MapState,
        roster: RosterManager,
        ledger: GoldLedger,
        combat_engine: CombatEngine,
        heal_percent: float = 1.0,
    ):
        self._event_bus = event_bus
        self._map_state = map_state
        self._roster = roster
        self._ledger = ledger
        self._pipeline = QuestPipeline(event_bus, combat_engine)
        self._assignment = HeroAssignment(event_bus)
        self._heal_percent = heal_percent
        self._encounter_table = _load_encounter_table()
        self._rng = random.Random()

        # Subscribe to player assignment commands
        self._event_bus.subscribe("player.assign_quest", self._on_assign_quest)

    def _on_assign_quest(self, data: dict) -> None:
        """
        Handle a player.assign_quest event.

        data: {"quest_id": str, "hero_ids": List[str]}
        """
        quest_id = data["quest_id"]
        hero_ids = data["hero_ids"]

        # Look up quest
        quest = self._map_state.active_quests.get(quest_id)
        if quest is None:
            self._event_bus.publish("quest.error", {
                "quest_id": quest_id,
                "reason": f"Quest '{quest_id}' not found",
            })
            return

        # Look up heroes
        heroes: List[HeroEntity] = []
        for hid in hero_ids:
            hero = self._roster.get_hero(hid)
            if hero is None:
                self._event_bus.publish("quest.error", {
                    "quest_id": quest_id,
                    "reason": f"Hero '{hid}' not found in roster",
                })
                return
            heroes.append(hero)

        # Validate and commit assignment
        try:
            self._assignment.assign(quest, heroes)
        except AssignmentError as e:
            self._event_bus.publish("quest.error", {
                "quest_id": quest_id,
                "reason": str(e),
            })
            return

        # Spawn enemies for combat quests
        enemies: Optional[List[Enemy]] = None
        if quest.quest_type == QuestType.COMBAT:
            enemies = self._spawn_enemies(quest)

        # Run the full pipeline
        result = self._pipeline.run(quest, heroes, enemies)

        # Post-pipeline: credit gold, heal, reset heroes
        self._finalize(result, heroes)

    def _spawn_enemies(self, quest: Quest) -> List[Enemy]:
        """Pick a random encounter from the table and load enemy instances."""
        act_key = f"act_{self._map_state.current_act}"
        difficulty = quest.difficulty.value

        act_table = self._encounter_table.get(act_key, {})
        compositions = act_table.get(difficulty, [])

        if not compositions:
            return []

        chosen = self._rng.choice(compositions)
        enemy_ids = chosen.get("enemies", [])

        enemies = []
        for eid in enemy_ids:
            try:
                enemies.append(load_enemy(eid, self._map_state.current_act))
            except FileNotFoundError:
                pass

        return enemies

    def _finalize(self, result: QuestPipelineResult, heroes: List[HeroEntity]) -> None:
        """Credit gold on victory, heal heroes, and reset to IDLE."""
        # Credit gold
        if result.victory and result.distribution:
            self._ledger.earn(result.distribution.gold_earned, reason="quest_reward")

        # Heal and reset all participating heroes
        for hero in heroes:
            if hero.current_health > 0:
                self._heal_hero(hero)
                hero.status = HeroStatus.IDLE
                # Clear combat status effects and temp HP
                hero.status_effects.clear()
                hero.temp_hp = 0

        # Publish result for UI / logging
        self._event_bus.publish("quest.executed", {
            "quest_id": result.quest_id,
            "victory": result.victory,
            "gold_earned": result.distribution.gold_earned if result.distribution else 0,
        })

    def _heal_hero(self, hero: HeroEntity) -> None:
        """Heal a hero by heal_percent of their max HP."""
        heal_amount = int(hero.max_health * self._heal_percent)
        hero.current_health = min(hero.max_health, hero.current_health + heal_amount)

    @property
    def heal_percent(self) -> float:
        return self._heal_percent

    @heal_percent.setter
    def heal_percent(self, value: float) -> None:
        self._heal_percent = max(0.0, min(1.0, value))
