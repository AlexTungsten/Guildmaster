"""
quest_pipeline.py — End-to-end quest execution pipeline for Guildmaster.

Orchestrates all phases of a single quest run in order:
  1. Travel phase   — random encounter rolls affect heroes en route.
  2. Resolution     — either a stat check or a two-phase combat simulation.
  3. Reward         — XP and exhaustion distributed; gold amount recorded.
  4. Completion     — quest status set to COMPLETE, event published.

For combat quests the engine first runs a deterministic pre-simulation and
publishes its projected result (for UI display), then runs the actual seeded
live combat.

All phases mutate the passed hero objects directly; the caller is responsible
for using the correct hero instances tied to the roster.
"""

from dataclasses import dataclass, field
from typing import List, Optional, Dict, Callable

from hero.hero_entity import HeroEntity
from quest.quest_model import Quest, QuestStatus, QuestType
from quest.travel_phase import roll_travel_events, apply_travel_outcomes
from quest.stat_check_resolver import resolve_stat_check
from quest.reward_distributor import distribute_rewards, DistributionResult
from enemy.enemy import Enemy
from combat.combat_engine import CombatEngine, CombatResult
from game_runtime.event_bus import EventBus


@dataclass
class QuestPipelineResult:
    """Top-level result returned after the full quest pipeline completes."""
    quest_id: str
    victory: bool                           # True if the heroes succeeded
    distribution: Optional[DistributionResult]  # None on defeat
    combat_result: Optional[CombatResult]       # None for stat-check quests


class QuestPipeline:
    def __init__(self, event_bus: EventBus, combat_engine: CombatEngine):
        self._event_bus = event_bus
        self._combat_engine = combat_engine

    def run(
        self,
        quest: Quest,
        heroes: List[HeroEntity],
        enemies: List[Enemy] = None,
    ) -> QuestPipelineResult:
        """
        Execute all phases of one quest for the given party and enemies.

        Parameters
        ----------
        quest   : The quest being run (status is mutated by this method).
        heroes  : Heroes assigned to the quest (their stats are mutated).
        enemies : Required for COMBAT quests; ignored for STAT_CHECK quests.
        """
        # Step 1: Travel phase — may add XP, damage, or exhaustion to heroes
        quest.status = QuestStatus.TRAVELING
        travel_result = roll_travel_events(heroes, quest.travel_time)
        apply_travel_outcomes(heroes, travel_result)

        # Step 2: Resolution phase — branch on quest type
        quest.status = QuestStatus.RESOLVING

        combat_result: Optional[CombatResult] = None
        victory = False

        if quest.quest_type == QuestType.STAT_CHECK:
            # Pure skill resolution — pass if any hero beats any check
            outcome = resolve_stat_check(heroes, quest.stat_checks)
            victory = outcome.any_passed

        elif quest.quest_type == QuestType.COMBAT and enemies:
            # Pre-simulate with a fixed seed so the UI can show a projection
            pre_result = self._combat_engine.pre_simulate(heroes, enemies)
            self._event_bus.publish("quest.pre_simulation_ready", pre_result)

            quest.status = QuestStatus.RESOLVING

            # Run the real combat simulation (unseeded for genuine randomness)
            combat_result = self._combat_engine.simulate(heroes, enemies)
            victory = combat_result.victory

        # Step 3: Calculate per-hero damage taken from the combat result
        damage_taken: Dict[str, int] = {}
        if combat_result is not None:
            if len(heroes) > 0:
                # Distribute total damage evenly across all heroes (approximation)
                per_hero_damage = combat_result.total_hero_damage_taken // len(heroes)
                for hero in heroes:
                    damage_taken[hero.hero_id] = per_hero_damage

        # Step 4: Distribute rewards on victory; skip on defeat
        distribution: Optional[DistributionResult] = None
        if victory:
            distribution = distribute_rewards(quest, heroes, damage_taken)

        # Step 5: Mark complete and notify listeners
        quest.status = QuestStatus.COMPLETE

        result = QuestPipelineResult(
            quest_id=quest.quest_id,
            victory=victory,
            distribution=distribution,
            combat_result=combat_result,
        )

        # Publish "quest.complete" so the economy controller can credit gold
        self._event_bus.publish("quest.complete", result)

        return result
