"""
exhaustion.py — Tick-level exhaustion recovery helper for Guildmaster.

Provides a single convenience function that drives per-tick exhaustion
recovery for one hero.  The actual recovery logic lives on HeroEntity
(which checks idle status and clamps to zero); this module's job is to
measure the delta so callers can log or display how much was recovered.
"""

from hero.hero_entity import HeroEntity


def tick_exhaustion_recovery(hero: HeroEntity, seconds: float = 1.0) -> float:
    """
    Attempt to recover exhaustion for one hero over the given time slice.

    Delegates to hero.recover_exhaustion(), which does nothing when the hero
    is not idle.  Returns the actual amount of exhaustion that was removed
    (0.0 when the hero is busy or already fully rested).
    """
    before = hero.exhaustion
    hero.recover_exhaustion(seconds)
    after = hero.exhaustion
    # Delta is positive when exhaustion decreased, zero when no recovery occurred
    return before - after
