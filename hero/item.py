"""
item.py — Item data model for Guildmaster heroes.

Items occupy hero item slots and can trigger automatically (threshold-based)
or be activated manually (on_use).  Effects include HP restoration, exhaustion
reduction, temporary stat boosts, and temp HP grants.

Triggers
--------
on_use          — Player activates manually; single use per combat/quest.
at_hp_threshold — Auto-triggers when hero current_hp <= threshold × max_hp.
on_quest_start  — Auto-applies at the beginning of a quest.
on_quest_complete — Auto-triggers after quest resolution.
on_combat_start — Auto-applies at the beginning of each combat.

Effects
-------
heal_hp           — Restore value HP (capped at max_hp).
reduce_exhaustion — Reduce exhaustion by value (floor 0).
temp_stat         — Add value to stat for duration ("quest" or "combat").
add_temp_hp       — Grant value temp HP.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from typing import Optional


_ITEMS_DIR = os.path.join(os.path.dirname(__file__), "..", "data", "items")


@dataclass
class Item:
    """One item held in a hero's item slot."""

    item_id: str
    name: str
    description: str

    # When this item activates
    trigger: str          # "on_use" | "at_hp_threshold" | "on_quest_start" |
                          # "on_quest_complete" | "on_combat_start"
    # What it does
    effect: str           # "heal_hp" | "reduce_exhaustion" | "temp_stat" | "add_temp_hp"
    value: int            # Magnitude of the effect

    # Optional fields
    threshold: float = 0.0          # HP fraction for at_hp_threshold (e.g. 0.5 = 50% HP)
    stat: Optional[str] = None      # Stat name for temp_stat effect ("strength", etc.)
    duration: str = "instant"       # "instant" | "quest" | "combat"
    auto_trigger: bool = False      # True for threshold / start triggers; False = on_use
    charges: int = 1                # How many times this item can activate (1 = single use)
    charges_used: int = 0           # Tracks consumption

    @property
    def is_exhausted(self) -> bool:
        """True when all charges have been consumed."""
        return self.charges_used >= self.charges

    def consume_charge(self) -> bool:
        """
        Consume one charge.  Returns True if the item activated, False if already
        exhausted.
        """
        if self.is_exhausted:
            return False
        self.charges_used += 1
        return True

    def to_dict(self) -> dict:
        return {
            "item_id": self.item_id,
            "name": self.name,
            "description": self.description,
            "trigger": self.trigger,
            "effect": self.effect,
            "value": self.value,
            "threshold": self.threshold,
            "stat": self.stat,
            "duration": self.duration,
            "auto_trigger": self.auto_trigger,
            "charges": self.charges,
            "charges_used": self.charges_used,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Item":
        return cls(
            item_id=data["item_id"],
            name=data["name"],
            description=data["description"],
            trigger=data["trigger"],
            effect=data["effect"],
            value=data["value"],
            threshold=data.get("threshold", 0.0),
            stat=data.get("stat"),
            duration=data.get("duration", "instant"),
            auto_trigger=data.get("auto_trigger", False),
            charges=data.get("charges", 1),
            charges_used=data.get("charges_used", 0),
        )


def load_item(item_id: str) -> Item:
    """Load an item from data/items/<item_id>.json."""
    path = os.path.join(_ITEMS_DIR, f"{item_id}.json")
    if not os.path.exists(path):
        raise FileNotFoundError(f"Item file not found: {path}")
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    return Item.from_dict(data)


def list_items() -> list[str]:
    """Return all available item IDs from data/items/."""
    if not os.path.exists(_ITEMS_DIR):
        return []
    return [f[:-5] for f in os.listdir(_ITEMS_DIR) if f.endswith(".json")]
