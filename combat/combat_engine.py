"""
combat_engine.py — Turn-based combat simulator for Guildmaster.

Runs round-by-round combat between a party of heroes and a group of enemies.
Each round:
  1. Hero phase: every living hero rolls their dice pool, assigns dice to
     skills, executes skills, and deals damage to enemies.
  2. Enemy phase: every living enemy uses its next attack pattern skill to
     deal damage to a random living hero.

The engine supports two execution modes:
  - simulate()      — Full run with event publication (used in real gameplay).
  - pre_simulate()  — Deterministic dry-run with seed=42 and no events
                      (used to show the player a projected outcome).

No game state is mutated outside of the hero/enemy HP values; callers are
responsible for resetting HP if they pre-simulate before the real combat.
"""

from dataclasses import dataclass, field
from typing import List, Optional, Tuple
import random

from hero.hero_entity import HeroEntity, HeroStatus, Stat
from enemy.enemy import Enemy
from combat.dice_pool_compositor import compose_pool, roll_pool, Die
from combat.dice_assignment_engine import assign_dice, SkillAssignment
from combat.skill_executor import execute_all_skills, SkillResult
from game_runtime.event_bus import EventBus


def _split_pool(pool: List[Die]) -> Tuple[List[Die], List[Die]]:
    """
    Partition a dice pool into locked dice (d4) and normal dice (d10).

    Used internally to feed separate locked/normal lists into assign_dice().
    """
    locked = [d for d in pool if d.is_locked]
    normal = [d for d in pool if not d.is_locked]
    return locked, normal


@dataclass
class CombatRound:
    """Snapshot of one round of combat."""
    round_number: int
    hero_results: List[SkillResult]    # All skill results fired by heroes this round
    enemy_results: List[SkillResult]   # All skill results fired by enemies this round
    hero_damage_taken: int             # Total HP lost by heroes in this round
    enemy_damage_dealt: int            # Total HP removed from enemies this round


@dataclass
class CombatResult:
    """Aggregate result of a full combat encounter."""
    victory: bool                      # True when all enemies died before all heroes
    rounds: List[CombatRound]
    heroes_survived: List[str]         # hero_id of each hero still alive at the end
    total_hero_damage_taken: int       # Cumulative HP lost across all rounds


class CombatEngine:
    def __init__(self, event_bus: EventBus):
        self._event_bus = event_bus

    def simulate(
        self,
        heroes: List[HeroEntity],
        enemies: List[Enemy],
        max_rounds: int = 50,
    ) -> CombatResult:
        """
        Run a live combat encounter and publish events.

        Uses an unseeded (random) RNG for genuine randomness.  Publishes
        "combat.round_complete", "combat.victory", or "combat.defeat" events
        on the bus so the UI and other systems can react in real time.
        """
        return self._run(heroes, enemies, max_rounds, publish_events=True, seed=None)

    def pre_simulate(
        self,
        heroes: List[HeroEntity],
        enemies: List[Enemy],
    ) -> CombatResult:
        """
        Run a deterministic dry-run to project the combat outcome.

        Uses seed=42 so the result is reproducible and does not affect the
        actual RNG state.  No events are published.  Note: this mutates hero
        and enemy HP — the caller should work on copies if the originals
        must be preserved.
        """
        return self._run(heroes, enemies, max_rounds=50, publish_events=False, seed=42)

    def _run(
        self,
        heroes: List[HeroEntity],
        enemies: List[Enemy],
        max_rounds: int,
        publish_events: bool,
        seed: Optional[int],
    ) -> CombatResult:
        """
        Internal combat loop shared by simulate() and pre_simulate().

        Parameters
        ----------
        heroes         : Party of heroes; their HP is mutated in place.
        enemies        : List of enemies; their HP is mutated in place.
        max_rounds     : Safety cap to prevent infinite loops.
        publish_events : Whether to fire events on the bus each round.
        seed           : RNG seed for deterministic runs; None = random.
        """
        if seed is not None:
            rng = random.Random(seed)   # Isolated seeded RNG for pre-simulation
        else:
            rng = random.Random()       # Fresh unseeded RNG for live combat

        rounds: List[CombatRound] = []
        total_hero_damage_taken = 0

        for round_number in range(1, max_rounds + 1):
            living_heroes = [h for h in heroes if h.current_health > 0]
            living_enemies = [e for e in enemies if e.is_alive]

            # End early if one side is already wiped out
            if not living_heroes or not living_enemies:
                break

            all_hero_results: List[SkillResult] = []
            enemy_damage_dealt = 0

            # --- Hero phase ---
            for hero in living_heroes:
                # Build and split the dice pool based on hero's exhaustion state
                pool = compose_pool(hero)
                locked_dice, normal_dice = _split_pool(pool)

                # Roll each category separately so assign_dice can handle them differently
                rolled_locked = [rng.randint(1, d.sides) for d in locked_dice]
                rolled_normal = [rng.randint(1, d.sides) for d in normal_dice]

                # Assign dice to skills according to the hero's behavior profile
                assignments = assign_dice(hero, rolled_locked, rolled_normal)
                # Resolve each assignment into a SkillResult (dice sum + stat modifier)
                results = execute_all_skills(hero, assignments)
                all_hero_results.extend(results)

                # Apply damage from each skill result to the enemy targets
                for result in results:
                    if result.effectiveness <= 0:
                        continue   # Negative effectiveness deals no damage
                    living_now = [e for e in enemies if e.is_alive]
                    if not living_now:
                        break
                    if result.hits_all:
                        # AOE: damage every living enemy equally
                        for enemy in living_now:
                            enemy.take_damage(result.effectiveness)
                            enemy_damage_dealt += result.effectiveness
                    else:
                        # Single-target: choose a random living enemy
                        target = rng.choice(living_now)
                        target.take_damage(result.effectiveness)
                        enemy_damage_dealt += result.effectiveness

            # --- Enemy phase ---
            all_enemy_results: List[SkillResult] = []
            hero_damage_taken = 0

            for enemy in living_enemies:
                if not enemy.is_alive:
                    continue   # Skip enemies killed during the hero phase
                living_now = [h for h in heroes if h.current_health > 0]
                if not living_now:
                    break

                # Advance the enemy's attack pattern to get the next skill index
                skill_index = enemy.pattern.next_skill_index()
                if not enemy.skills:
                    continue   # Enemy has no skills defined; skip its turn
                skill = enemy.skills[skill_index % len(enemy.skills)]

                # Enemies always roll d10s (no exhaustion or locked dice mechanic)
                rolled = [rng.randint(1, 10) for _ in range(enemy.base_dice_count)]
                effectiveness = sum(rolled) + enemy.stat_modifier(skill.associated_stat)

                # Import here to avoid circular name collision with the local SkillResult
                from combat.skill_executor import SkillResult as SR
                enemy_result = SR(
                    skill=skill,
                    effectiveness=effectiveness,
                    effect_type=skill.effect_type,
                    hits_all=(skill.effect_type == "aoe"),
                )
                all_enemy_results.append(enemy_result)

                # Deal damage to a random living hero (enemies always single-target here)
                if effectiveness > 0:
                    target_hero = rng.choice(living_now)
                    target_hero.current_health = max(
                        0, target_hero.current_health - effectiveness
                    )
                    hero_damage_taken += effectiveness

            total_hero_damage_taken += hero_damage_taken

            combat_round = CombatRound(
                round_number=round_number,
                hero_results=all_hero_results,
                enemy_results=all_enemy_results,
                hero_damage_taken=hero_damage_taken,
                enemy_damage_dealt=enemy_damage_dealt,
            )
            rounds.append(combat_round)

            if publish_events:
                self._event_bus.publish("combat.round_complete", round_number)

            # Re-check survivors after both phases before starting the next round
            living_heroes = [h for h in heroes if h.current_health > 0]
            living_enemies = [e for e in enemies if e.is_alive]

            if not living_enemies or not living_heroes:
                break

        # --- Determine final outcome ---
        living_heroes = [h for h in heroes if h.current_health > 0]
        living_enemies = [e for e in enemies if e.is_alive]
        # Victory requires all enemies dead AND at least one hero alive
        victory = len(living_enemies) == 0 and len(living_heroes) > 0
        heroes_survived = [h.hero_id for h in living_heroes]

        if publish_events:
            if victory:
                self._event_bus.publish("combat.victory", None)
            else:
                self._event_bus.publish("combat.defeat", None)

        return CombatResult(
            victory=victory,
            rounds=rounds,
            heroes_survived=heroes_survived,
            total_hero_damage_taken=total_hero_damage_taken,
        )
