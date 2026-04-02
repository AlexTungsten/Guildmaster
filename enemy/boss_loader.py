"""
boss_loader.py — Loads boss definitions from JSON data files.

Each boss JSON file in data/bosses/ defines a multi-phase boss encounter.
load_boss() reads the file, builds phase definitions with Skill objects,
and returns a BossEnemy instance with gold-stolen HP scaling applied.
"""

import json
import os
from typing import List

from hero.hero_entity import Skill, Stat
from enemy.boss_enemy import BossEnemy, PhaseDefinition

_DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "data", "bosses")

# Map stat name strings to Stat enum
_STAT_MAP = {
    "STRENGTH": Stat.STR, "STR": Stat.STR,
    "DEXTERITY": Stat.DEX, "DEX": Stat.DEX,
    "INTELLIGENCE": Stat.INT, "INT": Stat.INT,
    "CHARISMA": Stat.CHA, "CHA": Stat.CHA,
    "CONSTITUTION": Stat.CON, "CON": Stat.CON,
}


def _build_skill(data: dict) -> Skill:
    """Build a Skill from a JSON skill entry."""
    stat_str = data["associated_stat"].upper()
    return Skill(
        name=data["name"],
        description=data.get("description", ""),
        associated_stat=_STAT_MAP.get(stat_str, Stat.STR),
        dice_slots=data["dice_slots"],
        effect_type=data["effect_type"],
        special=data.get("special"),
        refresh_cost=data.get("refresh_cost", 0),
    )


def load_boss(boss_id: str, gold_stolen: int = 0) -> BossEnemy:
    """
    Load a boss from JSON and return a BossEnemy with gold-stolen HP applied.

    Parameters
    ----------
    boss_id     : str — matches the JSON filename (e.g. "baron_midas")
    gold_stolen : int — gold accumulated during the act; adds 1 HP per gold
                        (capped by the boss's gold_stolen_hp_cap)
    """
    path = os.path.join(_DATA_DIR, f"{boss_id}.json")
    if not os.path.exists(path):
        raise FileNotFoundError(f"Boss template not found: {path}")

    with open(path, "r") as f:
        template = json.load(f)

    # Cap gold stolen
    hp_cap = template.get("gold_stolen_hp_cap", 566)
    capped_gold = min(gold_stolen, hp_cap)

    # Build phase definitions
    phase_defs: List[PhaseDefinition] = []
    for phase_data in template.get("phases", []):
        skills = [_build_skill(s) for s in phase_data["skills"]]
        # Accumulation cost lives on the last skill (Skill 3)
        accum_cost = 0
        for s in phase_data["skills"]:
            if s.get("accumulation_cost"):
                accum_cost = s["accumulation_cost"]
        phase_defs.append(PhaseDefinition(
            phase=phase_data["phase"],
            skills=skills,
            accumulation_cost=accum_cost,
        ))

    # Start with Phase 1 skills
    phase1 = phase_defs[0] if phase_defs else None
    starting_skills = list(phase1.skills) if phase1 else []
    starting_cost = phase1.accumulation_cost if phase1 else 15

    base_hp = template.get("base_health", 100)

    boss = BossEnemy(
        enemy_id=template["boss_id"],
        name=template["name"],
        archetype=template.get("archetype", "boss"),
        act=1,
        strength=template.get("strength", 10),
        dexterity=template.get("dexterity", 10),
        intelligence=template.get("intelligence", 10),
        charisma=template.get("charisma", 10),
        constitution=template.get("constitution", 10),
        max_health=base_hp,
        current_health=base_hp,
        skills=starting_skills,
        base_dice_count=template.get("starting_dice_count", 4),
        base_dice_sides=template.get("starting_dice_sides", 4),
        skill_buffers=[],
        block=0,
        status_effects=[],
        phase_definitions=phase_defs,
        current_phase=1,
        skill3_progress=0,
        skill3_cost=starting_cost,
        bonus_dice=0,
        dice_sides_override=0,
        has_permanent_advantage=False,
        gold_stolen=capped_gold,
    )

    return boss


def list_bosses() -> List[str]:
    """Return a list of available boss_ids from the data/bosses/ folder."""
    if not os.path.exists(_DATA_DIR):
        return []
    return [f[:-5] for f in os.listdir(_DATA_DIR) if f.endswith(".json")]
