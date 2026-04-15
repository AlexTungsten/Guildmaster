"""
boss_loader.py — Loads boss definitions from JSON data files.

Each boss JSON file in data/bosses/ defines one boss or encounter.
load_boss()              — generic loader; returns BossEnemy (or CursedKnightBossEnemy).
load_kobold_king_encounter() — special encounter loader; returns full entity list.
"""

import json
import os
from typing import List

from hero.hero_entity import Skill, Stat
from enemy.boss_enemy import BossEnemy, PhaseDefinition
from enemy.enemy import Enemy

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


# ---------------------------------------------------------------------------
# Cursed Knight boss (non-phase, transformation-based)
# ---------------------------------------------------------------------------

def _load_cursed_knight_boss(damage_dealt: int = 0) -> "CursedKnightBossEnemy":
    """
    Load the Cursed Knight boss variant.

    Parameters
    ----------
    damage_dealt : int — damage already dealt to the Knight during the act;
                         reduces starting HP and bloodlust proportionally.
    """
    from enemy.special_enemies import CursedKnightBossEnemy

    path = os.path.join(_DATA_DIR, "cursed_knight.json")
    if not os.path.exists(path):
        raise FileNotFoundError(f"Boss template not found: {path}")
    with open(path, "r") as f:
        template = json.load(f)

    skills = [_build_skill(s) for s in template.get("skills", [])]
    hp = max(1, template.get("base_health", 250) - damage_dealt)
    bloodlust = max(0, 125 - damage_dealt)

    return CursedKnightBossEnemy(
        enemy_id=template["boss_id"],
        name=template["name"],
        archetype=template.get("archetype", "cursed_knight_boss"),
        act=1,
        max_health=hp,
        current_health=hp,
        skills=skills,
        base_dice_count=template.get("base_dice_count", 3),
        base_dice_sides=template.get("base_dice_sides", 4),
        skill_buffers=[[] for _ in skills],
        block=0,
        status_effects=[],
        bloodlust_current=bloodlust,
    )


# ---------------------------------------------------------------------------
# Kobold King encounter (multi-entity, two-phase)
# ---------------------------------------------------------------------------

def load_kobold_king_encounter(critical_quests_completed: int = 0) -> List[Enemy]:
    """
    Load the full Kobold King encounter.

    Returns a list in append order:
      [KoboldKingEnemy, MechEnemy, guard0, guard1, guard2, guard3]

    Guard composition is determined by critical_quests_completed:
      0  -> 4x Kobold Tinkerer
      1  -> 2x Kobold Tinkerer + 2x Kobold
      2  -> 1x Kobold Tinkerer + 3x Kobold
      3+ -> 4x Kobold
    """
    from enemy.special_enemies import KoboldKingEnemy, MechEnemy
    from enemy.enemy_loader import load_enemy

    path = os.path.join(_DATA_DIR, "kobold_king.json")
    if not os.path.exists(path):
        raise FileNotFoundError(f"Boss template not found: {path}")
    with open(path, "r") as f:
        template = json.load(f)

    # Build Mech (starts hidden)
    mech_data = template["mech"]
    mech_skills = [_build_skill(s) for s in mech_data["skills"]]
    mech = MechEnemy(
        enemy_id="mech",
        name="The Mech",
        archetype="mech",
        act=1,
        max_health=mech_data.get("base_health", 150),
        current_health=mech_data.get("base_health", 150),
        skills=mech_skills,
        base_dice_count=mech_data.get("base_dice_count", 3),
        base_dice_sides=mech_data.get("base_dice_sides", 8),
        skill_buffers=[[] for _ in mech_skills],
        block=0,
        status_effects=[],
    )

    # Guard composition table
    if critical_quests_completed <= 0:
        guard_ids = ["kobold_tinkerer"] * 4
    elif critical_quests_completed == 1:
        guard_ids = ["kobold_tinkerer", "kobold_tinkerer", "kobold", "kobold"]
    elif critical_quests_completed == 2:
        guard_ids = ["kobold_tinkerer", "kobold", "kobold", "kobold"]
    else:
        guard_ids = ["kobold"] * 4

    guards = [load_enemy(gid, act=1) for gid in guard_ids]

    # Build King (absolute untargetable, links to Mech and guards)
    king = KoboldKingEnemy(
        enemy_id="kobold_king",
        name="Kobold King",
        archetype="kobold_king",
        act=1,
        max_health=9999,   # Functionally unkillable — removed via phase transition
        current_health=9999,
        skills=[],
        base_dice_count=0,
        base_dice_sides=6,
        skill_buffers=[],
        block=0,
        status_effects=[],
        mech_ref=mech,
        guards=guards,
    )

    return [king, mech] + guards


# ---------------------------------------------------------------------------
# Generic boss loader (Baron Midas and future multi-phase bosses)
# ---------------------------------------------------------------------------

def load_boss(boss_id: str, gold_stolen: int = 0, damage_dealt: int = 0) -> Enemy:
    """
    Load a boss and return the appropriate entity.

    Special cases:
      cursed_knight -> CursedKnightBossEnemy (non-phase, transformation-based)
      All others    -> BossEnemy (phase-accumulation system)

    Parameters
    ----------
    boss_id      : str — matches the JSON filename
    gold_stolen  : int — Baron Midas HP bonus (1 HP per gold)
    damage_dealt : int — Cursed Knight HP/bloodlust reduction from prior fight
    """
    if boss_id == "cursed_knight":
        return _load_cursed_knight_boss(damage_dealt)

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
        accum_cost = 0
        for s in phase_data["skills"]:
            if s.get("accumulation_cost"):
                accum_cost = s["accumulation_cost"]
        phase_defs.append(PhaseDefinition(
            phase=phase_data["phase"],
            skills=skills,
            accumulation_cost=accum_cost,
        ))

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
