"""
quest_executor.py — Wires player assignment commands to the tick-based quest lifecycle.

Quest execution is split into three scheduled phases so time actually passes:

  Phase 1 — Travel there  (travel_time ticks)
    Heroes depart immediately; quest shows ASSIGNED, heroes TRAVELING.
    When they arrive, travel events are resolved.

  Phase 2 — Resolution  (resolution_time ticks)
    Heroes are ON_QUEST; combat or stat-check runs instantly in game logic
    but the result is held until resolution_time ticks have elapsed.

  Phase 3 — Travel back  (travel_time ticks)
    Quest shows RESOLVING, heroes TRAVELING.  When they return home the
    rewards are credited, heroes reset to IDLE, and the quest is removed
    from the map.

Phases are driven by TimeEngine.schedule() so they fire at the right tick
without polling.  In-progress quest state is stored in _active_quests keyed
by quest_id until the heroes arrive back.
"""

import json
import os
import random
from typing import Dict, List, Optional

from game_runtime.event_bus import EventBus
from game_runtime.time_engine import TimeEngine
from hero.hero_entity import HeroEntity, HeroStatus
from enemy.enemy import Enemy
from enemy.enemy_loader import load_enemy
from economy.gold_ledger import GoldLedger
from economy.roster_manager import RosterManager
from overworld.map_state import MapState
from overworld.hero_assignment import HeroAssignment, AssignmentError
from quest.quest_model import Quest, QuestStatus, QuestType
from quest.travel_phase import roll_travel_events, apply_travel_outcomes
from quest.stat_check_resolver import resolve_stat_check
from quest.reward_distributor import distribute_rewards
from combat.combat_engine import CombatEngine

_ENCOUNTER_PATH = os.path.join(
    os.path.dirname(__file__), "..", "data", "encounters.json"
)


def _load_encounter_table() -> dict:
    with open(_ENCOUNTER_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


class QuestExecutor:
    def __init__(
        self,
        event_bus: EventBus,
        time_engine: TimeEngine,
        map_state: MapState,
        roster: RosterManager,
        ledger: GoldLedger,
        combat_engine: CombatEngine,
        heal_percent: float = 1.0,
    ):
        self._event_bus = event_bus
        self._time_engine = time_engine
        self._map_state = map_state
        self._roster = roster
        self._ledger = ledger
        self._combat_engine = combat_engine
        self._assignment = HeroAssignment(event_bus)
        self._heal_percent = heal_percent
        self._encounter_table = _load_encounter_table()
        self._rng = random.Random()

        # In-flight quest state keyed by quest_id
        # Each entry: {quest, heroes, enemies, victory, combat_result, distribution}
        self._active_quests: Dict[str, dict] = {}

        self._event_bus.subscribe("player.assign_quest", self._on_assign_quest)
        self._event_bus.subscribe("quest.phase.arrive", self._on_quest_arrive)
        self._event_bus.subscribe("quest.phase.return", self._on_quest_return)
        self._event_bus.subscribe("quest.phase.heroes_back", self._on_heroes_back)

    # ------------------------------------------------------------------
    # Phase 0 — Assignment
    # ------------------------------------------------------------------

    def _on_assign_quest(self, data: dict) -> None:
        quest_id = data["quest_id"]
        hero_ids = data["hero_ids"]

        quest = self._map_state.active_quests.get(quest_id)
        if quest is None:
            self._event_bus.publish("quest.error", {
                "quest_id": quest_id,
                "reason": f"Quest '{quest_id}' not found",
            })
            return

        heroes: List[HeroEntity] = []
        for name in hero_ids:
            hero = self._roster.get_hero_by_name(name)
            if hero is None:
                self._event_bus.publish("quest.error", {
                    "quest_id": quest_id,
                    "reason": f"Hero '{name}' not found in roster",
                })
                return
            heroes.append(hero)

        try:
            # Sets heroes to TRAVELING and quest to ASSIGNED
            self._assignment.assign(quest, heroes)
        except AssignmentError as e:
            self._event_bus.publish("quest.error", {
                "quest_id": quest_id,
                "reason": str(e),
            })
            return

        enemies: Optional[List[Enemy]] = None
        if quest.quest_type == QuestType.COMBAT:
            enemies = self._spawn_enemies(quest)

        self._active_quests[quest_id] = {
            "quest": quest,
            "heroes": heroes,
            "enemies": enemies,
            "victory": False,
            "combat_result": None,
            "distribution": None,
        }

        # Schedule arrival after travel_time ticks
        self._time_engine.schedule(
            quest.travel_time, "quest.phase.arrive", {"quest_id": quest_id}
        )
        self._event_bus.publish("quest.started", {
            "quest_id": quest_id,
            "travel_time": quest.travel_time,
            "resolution_time": quest.resolution_time,
        })

    # ------------------------------------------------------------------
    # Phase 1 — Heroes arrive; resolve travel events + quest content
    # ------------------------------------------------------------------

    def _on_quest_arrive(self, data: dict) -> None:
        quest_id = data["quest_id"]
        state = self._active_quests.get(quest_id)
        if state is None:
            return

        quest: Quest = state["quest"]
        heroes: List[HeroEntity] = state["heroes"]
        enemies: Optional[List[Enemy]] = state["enemies"]

        # Apply travel events accumulated during the journey
        travel_result = roll_travel_events(heroes, quest.travel_time, self._rng)
        apply_travel_outcomes(heroes, travel_result)

        # Transition to resolution phase
        quest.status = QuestStatus.RESOLVING
        for hero in heroes:
            hero.status = HeroStatus.ON_QUEST

        # Run quest resolution (instantaneous in game logic, time passes via schedule)
        victory = False
        combat_result = None

        if quest.quest_type == QuestType.STAT_CHECK:
            outcome = resolve_stat_check(heroes, quest.stat_checks)
            victory = outcome.any_passed

        elif quest.quest_type == QuestType.COMBAT and enemies:
            pre_result = self._combat_engine.pre_simulate(heroes, enemies)
            self._event_bus.publish("quest.pre_simulation_ready", pre_result)
            combat_result = self._combat_engine.simulate(heroes, enemies)
            victory = combat_result.victory

        state["victory"] = victory
        state["combat_result"] = combat_result

        # Schedule end of resolution after resolution_time ticks
        self._time_engine.schedule(
            quest.resolution_time, "quest.phase.return", {"quest_id": quest_id}
        )

    # ------------------------------------------------------------------
    # Phase 2 — Resolution done; heroes begin the journey home
    # ------------------------------------------------------------------

    def _on_quest_return(self, data: dict) -> None:
        quest_id = data["quest_id"]
        state = self._active_quests.get(quest_id)
        if state is None:
            return

        quest: Quest = state["quest"]
        heroes: List[HeroEntity] = state["heroes"]
        victory: bool = state["victory"]
        combat_result = state["combat_result"]

        # Calculate damage taken and distribute rewards now (outcome is fixed)
        damage_taken: Dict[str, int] = {}
        if combat_result is not None and heroes:
            per_hero = combat_result.total_hero_damage_taken // len(heroes)
            for hero in heroes:
                damage_taken[hero.hero_id] = per_hero

        distribution = None
        if victory:
            distribution = distribute_rewards(quest, heroes, damage_taken)

        state["distribution"] = distribution

        # Heroes travel back — quest stays RESOLVING so it shows in ACTIVE QUESTS
        for hero in heroes:
            hero.status = HeroStatus.TRAVELING

        # Schedule heroes arriving home after another travel_time ticks
        self._time_engine.schedule(
            quest.travel_time, "quest.phase.heroes_back", {"quest_id": quest_id}
        )

    # ------------------------------------------------------------------
    # Phase 3 — Heroes arrive home; finalize and reset
    # ------------------------------------------------------------------

    def _on_heroes_back(self, data: dict) -> None:
        quest_id = data["quest_id"]
        state = self._active_quests.pop(quest_id, None)
        if state is None:
            return

        quest: Quest = state["quest"]
        heroes: List[HeroEntity] = state["heroes"]
        victory: bool = state["victory"]
        distribution = state["distribution"]

        # Credit gold to the guild ledger
        if victory and distribution:
            self._ledger.earn(distribution.gold_earned, reason="quest_reward")

        # Heal and reset heroes
        for hero in heroes:
            if hero.current_health > 0:
                heal = int(hero.max_health * self._heal_percent)
                hero.current_health = min(hero.max_health, hero.current_health + heal)
                hero.status = HeroStatus.IDLE
                hero.status_effects.clear()
                hero.temp_hp = 0

        quest.status = QuestStatus.COMPLETE
        self._map_state.remove_quest(quest_id)

        self._event_bus.publish("quest.executed", {
            "quest_id": quest_id,
            "victory": victory,
            "gold_earned": distribution.gold_earned if distribution else 0,
        })

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _spawn_enemies(self, quest: Quest) -> List[Enemy]:
        act_key = f"act_{self._map_state.current_act}"
        difficulty = quest.difficulty.value
        compositions = self._encounter_table.get(act_key, {}).get(difficulty, [])
        if not compositions:
            return []
        chosen = self._rng.choice(compositions)
        enemies = []
        for eid in chosen.get("enemies", []):
            try:
                enemies.append(load_enemy(eid, self._map_state.current_act))
            except FileNotFoundError:
                pass
        return enemies

    @property
    def heal_percent(self) -> float:
        return self._heal_percent

    @heal_percent.setter
    def heal_percent(self, value: float) -> None:
        self._heal_percent = max(0.0, min(1.0, value))
