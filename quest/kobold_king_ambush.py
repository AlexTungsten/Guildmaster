"""
kobold_king_ambush.py — Pre-fight stat check gauntlet for the Kobold King encounter.

When the Kobold King is the act boss, heroes traveling to the hideout face a
series of ambushes based on how many Kobold King critical quests were completed.
Each check that fails applies a penalty to heroes who don't pass it.  Only one
hero needs to succeed per check to avoid the penalty.

Ambush count by critical quests completed:
  0 → 5 ambushes   (full table)
  1 → 3 ambushes
  2 → 1 ambush
  3+ → 1 ambush    (floor — always at least 1)

Ambush table (one per stat):
  Spike Trap         — DEX — Take X damage
  Tripwire Alarm     — INT — Gain X exhaustion
  Guard Patrol       — CHR — Take X damage + 2 Bleed
  Collapsing Tunnel  — CON — Take X damage + 1 Paralyze (carries into first turn)
  Heavy Debris       — STR — Take X damage + gain X exhaustion

Penalty magnitudes are defined in AMBUSH_CONFIG and can be adjusted for balance.
"""

from __future__ import annotations

import random
from dataclasses import dataclass
from typing import List, Optional

from hero.hero_entity import HeroEntity, Stat


# ---------------------------------------------------------------------------
# Tunable penalty constants — adjust during balancing
# ---------------------------------------------------------------------------

AMBUSH_CONFIG = {
    "spike_trap":        {"damage": 8,  "exhaustion": 0},
    "tripwire_alarm":    {"damage": 0,  "exhaustion": 15},
    "guard_patrol":      {"damage": 6,  "exhaustion": 0,  "bleed": 2},
    "collapsing_tunnel": {"damage": 5,  "exhaustion": 0,  "paralyze": 1},
    "heavy_debris":      {"damage": 6,  "exhaustion": 10},
}

# DC for each ambush stat check
AMBUSH_DC = 12


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------

@dataclass
class AmbushEvent:
    """One ambush check in the pre-fight gauntlet."""
    key: str          # matches AMBUSH_CONFIG key
    stat: Stat
    description: str


# The full ambush table — draw from this in order or randomly based on count
_FULL_TABLE: List[AmbushEvent] = [
    AmbushEvent("spike_trap",        Stat.DEX, "Spike Trap — dodge or take damage"),
    AmbushEvent("tripwire_alarm",    Stat.INT, "Tripwire Alarm — spot it or gain exhaustion"),
    AmbushEvent("guard_patrol",      Stat.CHA, "Guard Patrol — bluff past or take damage + Bleed"),
    AmbushEvent("collapsing_tunnel", Stat.CON, "Collapsing Tunnel — brace or take damage + Paralyze"),
    AmbushEvent("heavy_debris",      Stat.STR, "Heavy Debris — push through or take damage + exhaustion"),
]

_COUNT_BY_CQ = {0: 5, 1: 3, 2: 1}   # 3+ → 1


def ambush_count(critical_quests_completed: int) -> int:
    """Number of ambushes to draw for the given critical quest count."""
    return _COUNT_BY_CQ.get(min(critical_quests_completed, 2), 1)


# ---------------------------------------------------------------------------
# Resolution
# ---------------------------------------------------------------------------

@dataclass
class AmbushOutcome:
    """Result of one ambush event for one hero party."""
    event: AmbushEvent
    passed: bool         # True if at least one hero succeeded the DC check
    damage_dealt: int    # Total raw damage applied (before hero block/temp HP)
    exhaustion_dealt: float
    bleed_stacks: int
    paralyze_stacks: int


def resolve_ambush(
    event: AmbushEvent,
    heroes: List[HeroEntity],
    rng: random.Random,
    dc: int = AMBUSH_DC,
) -> AmbushOutcome:
    """
    Roll the stat check for each hero; if any pass, no penalty is applied.
    If all fail, apply the configured penalty to ALL heroes.
    """
    stat_map = {
        Stat.STR: "strength",
        Stat.DEX: "dexterity",
        Stat.INT: "intelligence",
        Stat.CHA: "charisma",
        Stat.CON: "constitution",
    }
    living = [h for h in heroes if h.current_health > 0]
    passed = False
    for hero in living:
        stat_val = getattr(hero, stat_map[event.stat], 10)
        modifier = (stat_val // 2) - 5
        roll = rng.randint(1, 20) + modifier
        if roll >= dc:
            passed = True
            break

    cfg = AMBUSH_CONFIG[event.key]
    damage_dealt = 0
    exhaustion_dealt = 0.0
    bleed_stacks = 0
    paralyze_stacks = 0

    if not passed:
        from combat.status_effects import StatusEffect, StatusType

        dmg = cfg.get("damage", 0)
        exh = cfg.get("exhaustion", 0)
        bleed = cfg.get("bleed", 0)
        paralyze = cfg.get("paralyze", 0)

        for hero in living:
            if dmg > 0:
                actual = min(dmg, hero.current_health - 1)   # never kill
                if actual > 0:
                    hero.current_health -= actual
                    damage_dealt += actual
            if exh > 0:
                hero.exhaustion = getattr(hero, "exhaustion", 0) + exh
                exhaustion_dealt += exh
            if bleed > 0:
                for _ in range(bleed):
                    hero.apply_status(StatusEffect(status_type=StatusType.BLEED, duration=1))
                bleed_stacks += bleed
            if paralyze > 0:
                hero.apply_status(StatusEffect(
                    status_type=StatusType.PARALYZE, duration=1, stacks=paralyze,
                ))
                paralyze_stacks += paralyze

    return AmbushOutcome(
        event=event,
        passed=passed,
        damage_dealt=damage_dealt,
        exhaustion_dealt=exhaustion_dealt,
        bleed_stacks=bleed_stacks,
        paralyze_stacks=paralyze_stacks,
    )


def run_kobold_king_ambushes(
    heroes: List[HeroEntity],
    critical_quests_completed: int,
    rng: random.Random,
) -> List[AmbushOutcome]:
    """
    Run the full Kobold King pre-fight ambush gauntlet.

    Draws `ambush_count` events from the table (without replacement) and
    resolves each one against the hero party.  Returns outcomes in order.
    """
    count = ambush_count(critical_quests_completed)
    events = rng.sample(_FULL_TABLE, k=min(count, len(_FULL_TABLE)))
    return [resolve_ambush(e, heroes, rng) for e in events]
