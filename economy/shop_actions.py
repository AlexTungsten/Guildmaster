"""
shop_actions.py — Executes purchase actions within a shop session.

ShopActions is the only code path that combines GoldLedger, RosterManager,
and ShopInventory to complete a purchase.  It validates preconditions (listing
exists, not already sold, funds available, roster has space) and raises
ShopError if anything fails — callers do not need to check individually.

Three purchase types are supported:
  hire_hero   — Create a new HeroEntity and add it to the roster.
  buy_item    — Debit gold (item goes into guild inventory, managed externally).
  train_skill — Create a Skill from a training listing and slot it into a hero.
"""

from dataclasses import dataclass
from typing import Optional, List
from hero.hero_entity import HeroEntity, Skill, Stat
from economy.gold_ledger import GoldLedger
from economy.shop_inventory import ShopInventory, HeroListing, ItemListing, TrainingListing
from economy.roster_manager import RosterManager
from game_runtime.event_bus import EventBus


class ShopError(Exception):
    """Raised when a shop purchase cannot be completed."""
    pass


@dataclass
class HireResult:
    """Returned by hire_hero() to confirm which hero was hired and at what cost."""
    hero_id: str
    cost: int


@dataclass
class BuyResult:
    """Returned by buy_item() to confirm which item was purchased."""
    item_id: str
    cost: int


@dataclass
class TrainResult:
    """Returned by train_skill() to confirm skill training details."""
    skill_id: str
    hero_id: str
    replaced_slot: int   # The skill slot index (0–2) that was overwritten
    cost: int


class ShopActions:
    def __init__(self, event_bus: EventBus, ledger: GoldLedger, roster: RosterManager):
        self._event_bus = event_bus
        self._ledger = ledger
        self._roster = roster

    def hire_hero(self, shop: ShopInventory, hero_listing_id: str) -> HireResult:
        """
        Hire a hero from the shop: debit gold, create HeroEntity, add to roster.

        Raises ShopError if the listing is not found, already sold, the roster
        is full, or the guild cannot afford the cost.
        """
        listing = shop.get_hero(hero_listing_id)
        if listing is None:
            raise ShopError(f"Hero listing '{hero_listing_id}' not found")
        if listing.sold:
            raise ShopError(f"Hero listing '{hero_listing_id}' already sold")
        if not self._roster.can_add_hero():
            raise ShopError("Roster is full")
        if not self._ledger.spend(listing.cost, reason="hire_hero"):
            raise ShopError(f"Insufficient gold to hire hero '{listing.name}' (cost={listing.cost})")
        # Instantiate a default HeroEntity using the listing's archetype
        hero = HeroEntity(
            hero_id=listing.hero_id,
            name=listing.name,
            archetype=listing.archetype,
        )
        self._roster.add_hero(hero)
        shop.mark_sold(hero_listing_id)   # Prevent double-purchase
        self._event_bus.publish("shop.hero_hired", {"hero_id": listing.hero_id, "name": listing.name, "cost": listing.cost})
        return HireResult(hero_id=listing.hero_id, cost=listing.cost)

    def buy_item(self, shop: ShopInventory, item_id: str, target_hero: Optional[HeroEntity] = None) -> BuyResult:
        """
        Purchase an item from the shop: debit gold and mark listing sold.

        The item is NOT automatically added to the guild inventory here;
        the caller (economy controller or UI) is responsible for that.
        Raises ShopError if listing not found, already sold, or unaffordable.
        """
        listing = shop.get_item(item_id)
        if listing is None:
            raise ShopError(f"Item listing '{item_id}' not found")
        if listing.sold:
            raise ShopError(f"Item listing '{item_id}' already sold")
        if not self._ledger.spend(listing.cost, reason="buy_item"):
            raise ShopError(f"Insufficient gold to buy item '{listing.name}' (cost={listing.cost})")
        shop.mark_sold(item_id)
        self._event_bus.publish("shop.item_bought", {"item_id": listing.item_id, "name": listing.name, "cost": listing.cost})
        return BuyResult(item_id=listing.item_id, cost=listing.cost)

    def train_skill(self, shop: ShopInventory, skill_id: str, hero: HeroEntity, replace_slot: int) -> TrainResult:
        """
        Purchase a training course and install the resulting skill in a hero's slot.

        replace_slot must be 0, 1, or 2.  The old skill in that slot is
        discarded (replace_skill returns it but ShopActions ignores it).
        Raises ShopError if listing not found, sold, invalid slot, or unaffordable.
        """
        listing = shop.get_training(skill_id)
        if listing is None:
            raise ShopError(f"Training listing '{skill_id}' not found")
        if listing.sold:
            raise ShopError(f"Training listing '{skill_id}' already sold")
        if replace_slot not in (0, 1, 2):
            raise ShopError(f"Invalid replace_slot '{replace_slot}'; must be 0, 1, or 2")
        if not self._ledger.spend(listing.cost, reason="train_skill"):
            raise ShopError(f"Insufficient gold to train skill '{listing.name}' (cost={listing.cost})")
        # Build a Skill from the training listing; dice_slots defaults to 2 for trained skills
        new_skill = Skill(
            name=listing.name,
            description="Trained skill",
            associated_stat=Stat[listing.associated_stat.upper()],  # e.g. "STR" -> Stat.STR
            dice_slots=2,
            effect_type="damage",
        )
        hero.replace_skill(replace_slot, new_skill)
        shop.mark_sold(skill_id)
        self._event_bus.publish(
            "shop.skill_trained",
            {"skill_id": skill_id, "hero_id": hero.hero_id, "slot": replace_slot, "cost": listing.cost},
        )
        return TrainResult(skill_id=skill_id, hero_id=hero.hero_id, replaced_slot=replace_slot, cost=listing.cost)
