"""
enemy_loader.py — Loads enemy templates from JSON data files.

Each enemy JSON file in data/enemies/ defines the full template for one enemy
type: stats, dice configuration, and skill list.  load_enemy() reads the file,
selects the appropriate Enemy subclass for enemies with special mechanics, and
applies act scaling.
"""

import json
import os
from typing import List

from enemy.enemy import Enemy, make_enemy

_DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "data", "enemies")

# Maps enemy_id -> subclass for enemies that need special combat behaviour
def _get_special_classes():
    from enemy.special_enemies import (
        WerewolfEnemy,
        KoboldTinkererEnemy,
        BanditLeaderEnemy,
        CursedKnightEnemy,
    )
    return {
        "werewolf":       WerewolfEnemy,
        "kobold_tinkerer": KoboldTinkererEnemy,
        "bandit_leader":  BanditLeaderEnemy,
        "cursed_knight":  CursedKnightEnemy,
    }


def load_enemy(enemy_id: str, act: int) -> Enemy:
    """
    Load an enemy template from JSON and return a scaled Enemy instance.

    Special enemies (werewolf, kobold_tinkerer, bandit_leader, cursed_knight)
    are instantiated as their specific subclasses.

    Parameters
    ----------
    enemy_id : str  — matches the JSON filename (e.g. "bandit" -> bandit.json)
    act      : int  — act number used for HP scaling (1, 2, or 3)
    """
    path = os.path.join(_DATA_DIR, f"{enemy_id}.json")
    if not os.path.exists(path):
        raise FileNotFoundError(f"Enemy template not found: {path}")

    with open(path, "r") as f:
        template = json.load(f)

    special = _get_special_classes()
    klass = special.get(enemy_id, Enemy)
    return make_enemy(template, act, klass=klass)


def list_enemies() -> List[str]:
    """Return a list of available enemy_ids from the data/enemies/ folder."""
    if not os.path.exists(_DATA_DIR):
        return []
    return [f[:-5] for f in os.listdir(_DATA_DIR) if f.endswith(".json")]
