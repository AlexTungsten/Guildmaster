"""
archetype_loader.py — Loads hero archetype definitions from JSON data files.

Each archetype JSON file in data/archetypes/ defines the full template for
one hero class: base stats, dice configuration, starting skills, learnable
skills, and passives.
load_archetype() reads the file and returns a fully constructed HeroEntity.
"""

import json
import os
from typing import Optional
from hero.hero_entity import HeroEntity, Skill, Stat

# Path to the data/archetypes/ folder relative to the project root
_DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "data", "archetypes")

# Stat name → Stat enum lookup (accepts full names and abbreviations)
_STAT_MAP = {
    "STRENGTH": Stat.STR,  "DEXTERITY": Stat.DEX,
    "INTELLIGENCE": Stat.INT, "CHARISMA": Stat.CHA,
    "CONSTITUTION": Stat.CON,
    "STR": Stat.STR, "DEX": Stat.DEX, "INT": Stat.INT,
    "CHA": Stat.CHA, "CON": Stat.CON,
}


def _build_skill(s: dict) -> Skill:
    """Convert one skill dict from JSON into a Skill object."""
    stat_str = s["associated_stat"].upper()
    associated_stat = _STAT_MAP.get(stat_str, Stat.STR)
    # Accept both old "refresh_cost" key and new "charge_cost"
    charge_cost = s.get("charge_cost", s.get("refresh_cost", 0))
    return Skill(
        name=s["name"],
        description=s.get("description", ""),
        associated_stat=associated_stat,
        dice_slots=s["dice_slots"],
        effect_type=s["effect_type"],
        special=s.get("special"),
        charge_cost=charge_cost,
        current_charge=0,
        element=s.get("element"),
    )


def load_archetype(archetype_id: str, hero_id: str, name: str) -> HeroEntity:
    """
    Load an archetype JSON file and return a HeroEntity with correct stats/skills/passives.

    Parameters
    ----------
    archetype_id : str  — matches the JSON filename (e.g. "barbarian" -> barbarian.json)
    hero_id      : str  — unique ID to assign to this hero instance
    name         : str  — display name for this hero instance
    """
    path = os.path.join(_DATA_DIR, f"{archetype_id}.json")
    if not os.path.exists(path):
        raise FileNotFoundError(f"Archetype file not found: {path}")

    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)

    stats = data.get("stats", {})
    passives = data.get("passives", [])

    # Determine locked_dice_sides from passives (Ironhide overrides d4 -> d6)
    locked_dice_sides = 4
    for passive in passives:
        if passive.get("effect_type") == "locked_dice_override":
            locked_dice_sides = int(passive.get("value", 4))

    # Build starting Skill objects
    skills = [_build_skill(s) for s in data.get("skills", [])]
    # Pad to 3 skill slots with None
    while len(skills) < 3:
        skills.append(None)

    # Build learnable Skill objects
    learnable_skills = [_build_skill(s) for s in data.get("learnable_skills", [])]

    item_slots = data.get("item_slots", 1)
    max_hp = data.get("max_health", 30)

    hero = HeroEntity(
        hero_id=hero_id,
        name=name,
        archetype=data.get("name", archetype_id),
        strength=stats.get("strength", 10),
        dexterity=stats.get("dexterity", 10),
        intelligence=stats.get("intelligence", 10),
        charisma=stats.get("charisma", 10),
        constitution=stats.get("constitution", 10),
        max_health=max_hp,
        current_health=max_hp,
        base_dice_count=data.get("base_dice_count", 4),
        base_dice_sides=data.get("base_dice_sides", 10),
        locked_dice_sides=locked_dice_sides,
        item_slots=item_slots,
        equipped_items=[None] * item_slots,
        skills=skills,
        learnable_skills=learnable_skills,
        passives=passives,
    )
    return hero


def list_archetypes() -> list:
    """Return a list of available archetype_ids from the data/archetypes/ folder."""
    if not os.path.exists(_DATA_DIR):
        return []
    return [
        f[:-5] for f in os.listdir(_DATA_DIR)
        if f.endswith(".json")
    ]
