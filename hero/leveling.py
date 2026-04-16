"""
leveling.py — Hero level-up reward system for Guildmaster.

Handles all level-specific rewards:
  Level 2 — +1 die to pool, +2 stat points
  Level 3 — Choose level-3 passive, change behavior profile, +2 stat points
  Level 4 — All base pool dice upgrade 1 tier (or +1 die if already at d12), +2 stat points
  Level 5 — Upgrade chosen passive OR upgrade starting passive, +2 stat points

Stat allocation (pending_stat_points) is separate — callers distribute them via
hero.allocate_stat_point(stat).

Die tier progression: d4 < d6 < d8 < d10 < d12
Barbarian exception at level 4: d12 is already the tier cap, so +1 die instead.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from hero.hero_entity import HeroEntity, Skill

# Die tier upgrade table (floored at d4, capped at d12)
_TIER_UP = {4: 6, 6: 8, 8: 10, 10: 12, 12: 12}
_TIER_CAP = 12

# ---------------------------------------------------------------------------
# Level-3 passive definitions per archetype
# ---------------------------------------------------------------------------

# Each entry: passive_id -> full passive dict (same format as archetype JSON)
_LEVEL3_PASSIVES: dict[str, dict] = {
    # Barbarian
    "blood_rage": {
        "passive_id": "blood_rage",
        "name": "Blood Rage",
        "description": (
            "End of each turn: spend 5% current HP (temp HP first, floors at 1). "
            "Gain 1 permanent damage stack for this combat. "
            "Each stack adds +1 flat bonus to all outgoing damage."
        ),
        "effect_type": "blood_rage",
    },
    "iron_will": {
        "passive_id": "iron_will",
        "name": "Iron Will",
        "description": (
            "Start of each turn: convert half of current temp HP (rounded down) "
            "into real HP."
        ),
        "effect_type": "iron_will",
    },
    # Rogue
    "venomous": {
        "passive_id": "venomous",
        "name": "Venomous",
        "description": "All debuffs applied by this Rogue last 1 additional turn.",
        "effect_type": "venomous",
    },
    "thousand_cuts": {
        "passive_id": "thousand_cuts",
        "name": "Thousand Cuts",
        "description": (
            "Reroll the 2 lowest dice after rolling, keeping the better result for each. "
            "Additionally the dice pool gains +1 permanent die."
        ),
        "effect_type": "thousand_cuts",
    },
    # Mage
    "arcane_flow": {
        "passive_id": "arcane_flow",
        "name": "Arcane Flow",
        "description": (
            "All spell charge costs halved (rounded up). "
            "Once per turn when a spell fires, gain a bonus d12 for this turn."
        ),
        "effect_type": "arcane_flow",
    },
    "spellweave": {
        "passive_id": "spellweave",
        "name": "Spellweave",
        "description": (
            "After 3 unique spell elements are cast in combat, a convergence spell "
            "fires automatically. Arcane Bolt adds +5 bonus damage to convergence if "
            "cast this combat."
        ),
        "effect_type": "spellweave",
    },
    # Cleric
    "divine_overflow": {
        "passive_id": "divine_overflow",
        "name": "Divine Overflow",
        "description": (
            "When Hildegard heals any unit, half the healing (rounded down) also "
            "applies to the unit with the lowest current HP on the field."
        ),
        "effect_type": "divine_overflow",
    },
    "prayer": {
        "passive_id": "prayer",
        "name": "Prayer",
        "description": (
            "Each non-attack skill cast adds 1 Prayer stack. "
            "All outgoing damage gains +1 per stack. "
            "At 10 stacks all offensive skills become AOE for the rest of combat."
        ),
        "effect_type": "prayer",
    },
}

# Valid level-3 passive choices per archetype
_ARCHETYPE_L3_OPTIONS: dict[str, list[str]] = {
    "Barbarian": ["blood_rage", "iron_will"],
    "Rogue":     ["venomous", "thousand_cuts"],
    "Mage":      ["arcane_flow", "spellweave"],
    "Cleric":    ["divine_overflow", "prayer"],
}

# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def apply_level_up(hero: "HeroEntity") -> None:
    """
    Apply the automatic (non-choice) rewards for the hero's current level.

    Called immediately after hero.level is incremented by gain_xp().
    The +2 stat points are already credited by gain_xp() via
    hero.pending_stat_points += 2.

    Level 2: +1 die to pool
    Level 3: nothing automatic (player must call apply_passive_choice)
    Level 4: upgrade all base pool dice 1 tier (Barbarian: +1 die instead)
    Level 5: nothing automatic (player must call apply_level5_upgrade)
    """
    if hero.level == 2:
        hero.base_dice_count += 1

    elif hero.level == 4:
        if hero.base_dice_sides >= _TIER_CAP:
            # Already at tier cap (Barbarian d12) — grant extra die instead
            hero.base_dice_count += 1
        else:
            hero.base_dice_sides = _TIER_UP.get(hero.base_dice_sides, hero.base_dice_sides)


def apply_passive_choice(hero: "HeroEntity", passive_id: str) -> bool:
    """
    Record and apply the hero's level-3 passive choice.

    Returns True on success, False if the passive_id is invalid for this
    archetype or the hero is not level 3.

    Also applies the +1 die bonus granted by Thousand Cuts immediately.
    """
    valid = _ARCHETYPE_L3_OPTIONS.get(hero.archetype, [])
    if passive_id not in valid:
        return False

    passive = _LEVEL3_PASSIVES[passive_id]
    hero.level3_passive_id = passive_id
    hero.add_passive(passive)

    # Thousand Cuts also grants an extra die immediately
    if passive_id == "thousand_cuts":
        hero.base_dice_count += 1

    return True


def apply_level5_upgrade(hero: "HeroEntity", upgrade_id: str) -> bool:
    """
    Apply the chosen level-5 upgrade.

    upgrade_id must be one of:
      "<passive_id>_upgrade"  — upgrades the level-3 passive
      "<starting_passive>_upgrade" — upgrades the starting passive

    Valid upgrade IDs per archetype:
      Barbarian : "blood_rage_upgrade" | "iron_will_upgrade" | "ironhide_upgrade"
      Rogue     : "venomous_upgrade"   | "thousand_cuts_upgrade" | "lucky_roll_upgrade"
      Mage      : "arcane_flow_upgrade"| "spellweave_upgrade"    | "prepared_upgrade"
      Cleric    : "divine_overflow_upgrade" | "prayer_upgrade"   | "field_synthesis_upgrade"

    The upgrade flag is stored on hero.level5_upgrade and checked by the
    combat engine at runtime.
    """
    _VALID_UPGRADES: dict[str, list[str]] = {
        "Barbarian": ["blood_rage_upgrade", "iron_will_upgrade", "ironhide_upgrade"],
        "Rogue":     ["venomous_upgrade", "thousand_cuts_upgrade", "lucky_roll_upgrade"],
        "Mage":      ["arcane_flow_upgrade", "spellweave_upgrade", "prepared_upgrade"],
        "Cleric":    ["divine_overflow_upgrade", "prayer_upgrade", "field_synthesis_upgrade"],
    }
    valid = _VALID_UPGRADES.get(hero.archetype, [])
    if upgrade_id not in valid:
        return False

    hero.level5_upgrade = upgrade_id

    # ironhide_upgrade: locked dice become d8 (Barbarian only)
    if upgrade_id == "ironhide_upgrade":
        hero.locked_dice_sides = 8

    return True


def get_level3_options(hero: "HeroEntity") -> list[dict]:
    """Return the two level-3 passive dicts available to this hero's archetype."""
    options = _ARCHETYPE_L3_OPTIONS.get(hero.archetype, [])
    return [_LEVEL3_PASSIVES[pid] for pid in options if pid in _LEVEL3_PASSIVES]


def change_behavior_profile(hero: "HeroEntity", profile: str) -> bool:
    """
    Set the hero's behavior profile.  Only available at level 3+.

    Valid profiles: focus, balanced, greedy, dump
    Returns True on success.
    """
    valid_profiles = {"focus", "balanced", "greedy", "dump"}
    if profile not in valid_profiles:
        return False
    if hero.level < 3:
        return False
    hero.behavior_profile = profile
    return True
