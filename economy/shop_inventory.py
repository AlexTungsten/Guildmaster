"""
shop_inventory.py — Typed inventory model for a single merchant shop visit.

ShopInventory separates the three categories of shop merchandise into typed
lists (items, heroes for hire, training opportunities).  Each entry has a
sold flag so that already-purchased listings remain visible in the UI as
greyed-out rather than disappearing.

This module is purely a data container; no gold or hero logic lives here.
ShopActions (economy/shop_actions.py) handles the purchase flow.
"""

from dataclasses import dataclass, field
from typing import List, Optional


@dataclass
class ItemListing:
    """One purchasable equipment item in the shop."""
    item_id: str
    name: str
    category: str   # e.g. "consumable", "weapon", "armor"
    cost: int
    sold: bool = False


@dataclass
class HeroListing:
    """One hero available for hire in the shop."""
    hero_id: str
    name: str
    archetype: str
    cost: int
    sold: bool = False


@dataclass
class TrainingListing:
    """One skill-training course available in the shop."""
    skill_id: str
    name: str
    associated_stat: str   # Stat name string used to create the resulting Skill
    cost: int
    sold: bool = False


@dataclass
class ShopInventory:
    """Full inventory for one shop instance."""
    shop_id: str
    items: List[ItemListing] = field(default_factory=list)
    heroes: List[HeroListing] = field(default_factory=list)
    training: List[TrainingListing] = field(default_factory=list)

    def get_item(self, item_id: str) -> Optional[ItemListing]:
        """Look up an ItemListing by ID; returns None if not found."""
        for item in self.items:
            if item.item_id == item_id:
                return item
        return None

    def get_hero(self, hero_id: str) -> Optional[HeroListing]:
        """Look up a HeroListing by hero_id; returns None if not found."""
        for hero in self.heroes:
            if hero.hero_id == hero_id:
                return hero
        return None

    def get_training(self, skill_id: str) -> Optional[TrainingListing]:
        """Look up a TrainingListing by skill_id; returns None if not found."""
        for training in self.training:
            if training.skill_id == skill_id:
                return training
        return None

    def mark_sold(self, listing_id: str) -> bool:
        """
        Set sold=True on the listing matching listing_id.

        Searches items first, then heroes, then training.
        Returns True if a listing was found and marked, False otherwise.
        """
        for item in self.items:
            if item.item_id == listing_id:
                item.sold = True
                return True
        for hero in self.heroes:
            if hero.hero_id == listing_id:
                hero.sold = True
                return True
        for training in self.training:
            if training.skill_id == listing_id:
                training.sold = True
                return True
        return False

    def to_dict(self) -> dict:
        return {
            "shop_id": self.shop_id,
            "items": [
                {"item_id": i.item_id, "name": i.name, "category": i.category, "cost": i.cost, "sold": i.sold}
                for i in self.items
            ],
            "heroes": [
                {"hero_id": h.hero_id, "name": h.name, "archetype": h.archetype, "cost": h.cost, "sold": h.sold}
                for h in self.heroes
            ],
            "training": [
                {"skill_id": t.skill_id, "name": t.name, "associated_stat": t.associated_stat, "cost": t.cost, "sold": t.sold}
                for t in self.training
            ],
        }

    @classmethod
    def from_dict(cls, data: dict) -> "ShopInventory":
        """Reconstruct a ShopInventory from a serialized dict."""
        items = [
            ItemListing(
                item_id=i["item_id"], name=i["name"], category=i["category"],
                cost=i["cost"], sold=i.get("sold", False)
            )
            for i in data.get("items", [])
        ]
        heroes = [
            HeroListing(
                hero_id=h["hero_id"], name=h["name"], archetype=h["archetype"],
                cost=h["cost"], sold=h.get("sold", False)
            )
            for h in data.get("heroes", [])
        ]
        training = [
            TrainingListing(
                skill_id=t["skill_id"], name=t["name"], associated_stat=t["associated_stat"],
                cost=t["cost"], sold=t.get("sold", False)
            )
            for t in data.get("training", [])
        ]
        return cls(shop_id=data["shop_id"], items=items, heroes=heroes, training=training)
