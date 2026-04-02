"""
item_applicator.py — Applies, removes, and triggers item effects on heroes.

Three public entry points:

  apply_passive_items(hero)   — Called at quest start.  Stat-boost passives
                                raise the hero's base stat directly.

  remove_passive_items(hero)  — Called at quest end.  Reverses any stat boosts
                                and wipes all equipped slots (items are consumed).

  apply_ready_glasses(heroes) — Called once before combat round 1.  Grants
                                ADVANTAGE status (duration=1) to heroes wearing
                                Ready Glasses.

  apply_heal_potions(heroes)  — Called at the end of each combat round's hero
                                phase.  Heals +5 HP for each living hero wearing
                                a Heal Potion.

  check_greater_heal(hero)    — Called after each damage event in combat.
                                Triggers if HP ≤ 50% and the item is equipped.
                                Heals 30% of max HP and consumes the item.
                                Returns True if the item fired.
"""

from typing import List

from hero.hero_entity import HeroEntity
from item.item_catalog import get_item


# ---------------------------------------------------------------------------
# Quest-level: apply and remove passive effects
# ---------------------------------------------------------------------------

def apply_passive_items(hero: HeroEntity) -> None:
    """
    Apply passive item effects to a hero at quest start.

    Only 'stat_boost' passives need up-front application; combat-only
    passives (heal_per_turn, advantage_first_round) are handled in the
    combat engine.
    """
    for item_id in hero.equipped_items:
        if item_id is None:
            continue
        item = get_item(item_id)
        if item is None or item["category"] != "passive":
            continue
        if item["effect"] == "stat_boost":
            _apply_stat_delta(hero, item["stat"], item["value"])


def remove_passive_items(hero: HeroEntity) -> None:
    """
    Reverse passive stat boosts and consume all equipped items at quest end.

    Stat boosts are removed first so the hero's base stats return to their
    pre-quest values.  All equipped slots are then cleared — items are
    permanently destroyed regardless of whether they were used.
    """
    for item_id in hero.equipped_items:
        if item_id is None:
            continue
        item = get_item(item_id)
        if item is None or item["category"] != "passive":
            continue
        if item["effect"] == "stat_boost":
            _apply_stat_delta(hero, item["stat"], -item["value"])

    # Destroy all equipped items (passive and conditional alike)
    hero.equipped_items = [None] * hero.item_slots


# ---------------------------------------------------------------------------
# Combat-level: round-by-round hooks
# ---------------------------------------------------------------------------

def apply_ready_glasses(heroes: List[HeroEntity]) -> None:
    """
    Grant ADVANTAGE (duration=1) to heroes wearing Ready Glasses.

    Must be called once before round 1.  Because ADVANTAGE has duration=1
    it expires automatically after the first round's roll.
    """
    from combat.status_effects import StatusEffect, StatusType
    for hero in heroes:
        if _has_item(hero, "ready_glasses"):
            hero.apply_status(StatusEffect(status_type=StatusType.ADVANTAGE, duration=1))


def apply_heal_potions(heroes: List[HeroEntity]) -> None:
    """
    Heal each living hero wearing a Heal Potion by +5 HP.

    Call this once at the end of each combat round's hero phase.
    """
    for hero in heroes:
        if hero.current_health > 0 and _has_item(hero, "heal_potion"):
            hero.current_health = min(hero.max_health, hero.current_health + 5)


def check_greater_heal(hero: HeroEntity) -> bool:
    """
    Trigger Greater Heal if the hero is at or below 50% HP.

    Heals 30% of max_health, then removes the item from the equipped slot.
    Returns True if the item fired, False if the condition was not met or
    the item was not equipped.
    """
    if not _has_item(hero, "greater_heal"):
        return False
    if hero.current_health > hero.max_health * 0.5:
        return False
    # Fire: heal 30% of max HP
    heal = int(hero.max_health * 0.30)
    hero.current_health = min(hero.max_health, hero.current_health + heal)
    # Consume the item
    for i, item_id in enumerate(hero.equipped_items):
        if item_id == "greater_heal":
            hero.equipped_items[i] = None
            break
    return True


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _has_item(hero: HeroEntity, item_id: str) -> bool:
    """Return True if item_id occupies any equipped slot on hero."""
    return item_id in hero.equipped_items


def _apply_stat_delta(hero: HeroEntity, stat_name: str, delta: int) -> None:
    """Add delta to the named base stat (delta may be negative to reverse a boost)."""
    if stat_name == "strength":
        hero.strength += delta
    elif stat_name == "dexterity":
        hero.dexterity += delta
    elif stat_name == "intelligence":
        hero.intelligence += delta
    elif stat_name == "charisma":
        hero.charisma += delta
    elif stat_name == "constitution":
        hero.constitution += delta
