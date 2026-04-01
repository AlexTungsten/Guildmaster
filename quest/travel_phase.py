"""
travel_phase.py — Random travel events during a hero party's journey to a quest.

While heroes travel to a quest location they may encounter random events that
affect their health, exhaustion, and XP.  The probability of an event
occurring scales with travel time (longer journeys = more likely encounters),
capped at 60%.

In autoplay mode the first choice of each event is automatically selected.
gold_delta outcomes are returned in the result dict but not applied here —
the calling system (economy controller) is responsible for adjusting the
guild's gold.
"""

import random
from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any

from hero.hero_entity import HeroEntity


@dataclass
class EventChoice:
    """One possible player response to a travel event."""
    label: str
    outcome: dict  # Keys: "gold_delta", "xp_delta", "health_delta", "exhaustion_delta"


@dataclass
class RandomEvent:
    """A narrative travel event with one or more selectable choices."""
    event_id: str
    title: str
    description: str
    choices: List[EventChoice]


@dataclass
class TravelResult:
    """The outcome of the travel phase for a single quest leg."""
    events_fired: List[RandomEvent]    # Events that occurred (0 or 1 currently)
    chosen_outcomes: List[dict]        # The outcome dict for each fired event


# Static pool of possible travel encounters
TRAVEL_EVENT_POOL: List[RandomEvent] = [
    RandomEvent(
        event_id="te_ambush",
        title="Roadside Ambush",
        description="A small group of bandits leaps from the bushes, demanding toll.",
        choices=[
            EventChoice(
                label="Fight them off",
                # Combat costs health and exhaustion but earns a small XP reward
                outcome={"health_delta": -5, "xp_delta": 10, "exhaustion_delta": 2.0},
            ),
            EventChoice(
                label="Pay the toll",
                # Paying avoids combat but costs guild gold (handled by the caller)
                outcome={"gold_delta": -10, "xp_delta": 0},
            ),
        ],
    ),
    RandomEvent(
        event_id="te_shrine",
        title="Ancient Shrine",
        description="The party discovers a forgotten shrine glowing with faint magic.",
        choices=[
            EventChoice(
                label="Pray at the shrine",
                # Shrine restores health and reduces exhaustion slightly
                outcome={"health_delta": 5, "exhaustion_delta": -3.0, "xp_delta": 5},
            ),
            EventChoice(
                label="Ignore it and press on",
                outcome={},  # No change; the party pushes on without benefit
            ),
        ],
    ),
    RandomEvent(
        event_id="te_storm",
        title="Sudden Storm",
        description="A fierce storm rolls in, battering the travelers with rain and wind.",
        choices=[
            EventChoice(
                label="Push through the storm",
                # Fighting through the storm is exhausting and damages health
                outcome={"exhaustion_delta": 5.0, "health_delta": -3, "xp_delta": 8},
            ),
            EventChoice(
                label="Seek shelter and wait",
                # Sheltering costs a little exhaustion from the delay but avoids damage
                outcome={"exhaustion_delta": 1.0},
            ),
        ],
    ),
]


def roll_travel_events(
    heroes: List[HeroEntity],
    travel_time: int,
    rng: random.Random = None,
) -> TravelResult:
    """
    Roll for random events during travel.

    Probability of an event firing = min(0.6, travel_time / 100).
    A travel_time of 60+ ticks guarantees at most a 60% chance; shorter trips
    are proportionally less likely to trigger events.

    Autoplay: the first choice is automatically selected for each event.
    """
    _rng = rng if rng is not None else random
    # Longer travel = higher chance of an encounter, capped at 60%
    probability = min(0.6, travel_time / 100)
    events_fired: List[RandomEvent] = []
    chosen_outcomes: List[dict] = []

    if _rng.random() < probability:
        event = _rng.choice(TRAVEL_EVENT_POOL)
        events_fired.append(event)
        # Auto-select first choice (autoplay default)
        chosen_outcomes.append(event.choices[0].outcome)

    return TravelResult(events_fired=events_fired, chosen_outcomes=chosen_outcomes)


def apply_travel_outcomes(heroes: List[HeroEntity], result: TravelResult) -> None:
    """
    Apply travel event outcomes to all heroes in the party.

    Each outcome is applied uniformly to every hero.  gold_delta is a
    guild-level effect and is intentionally ignored here — the economy
    controller must handle it separately using the TravelResult.
    """
    for outcome in result.chosen_outcomes:
        xp_delta = outcome.get("xp_delta", 0)
        health_delta = outcome.get("health_delta", 0)
        exhaustion_delta = outcome.get("exhaustion_delta", 0)
        # gold_delta is guild-level, ignored here

        for hero in heroes:
            if xp_delta:
                hero.gain_xp(xp_delta)
            if health_delta:
                # Clamp to valid HP range [0, max_health]
                hero.current_health = min(
                    hero.max_health,
                    max(0, hero.current_health + health_delta),
                )
            if exhaustion_delta:
                hero.add_exhaustion(exhaustion_delta)
