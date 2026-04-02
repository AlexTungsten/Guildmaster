"""
economy_controller.py — Top-level façade for all guild economy systems.

EconomyController owns and connects:
  - GoldLedger    — tracks the guild's gold balance and transaction history.
  - RosterManager — manages the list of hired heroes and their cap.
  - GuildInventory — stores items purchased from shops.
  - ShopActions   — executes individual shop purchases (hire, buy, train).

Callers (GameLoop, tests) should use EconomyController rather than
instantiating these sub-systems individually.  tick() drives idle hero
exhaustion recovery each simulated time slice.
"""

from economy.gold_ledger import GoldLedger
from economy.roster_manager import RosterManager
from economy.guild_inventory import GuildInventory
from economy.shop_actions import ShopActions
from economy.shop_inventory import ShopInventory
from item.item_catalog import get_item
from game_runtime.event_bus import EventBus


class EconomyController:
    def __init__(self, event_bus: EventBus, starting_gold: int = 100, roster_cap: int = 15, inventory_max: int = 20):
        self._event_bus = event_bus
        self._ledger = GoldLedger(event_bus=event_bus, starting_gold=starting_gold)
        self._roster = RosterManager(event_bus=event_bus, cap=roster_cap)
        self._inventory = GuildInventory(event_bus=event_bus, max_size=inventory_max)
        # ShopActions is wired to share the same ledger and roster instances
        self._shop_actions = ShopActions(event_bus=event_bus, ledger=self._ledger, roster=self._roster)

        # When an item is bought from a shop, add it to the guild inventory
        def _on_item_bought(data: dict) -> None:
            item_id = data.get("item_id", "")
            item_def = get_item(item_id)
            if item_def:
                self._inventory.add_item(
                    item_id=item_def["item_id"],
                    name=item_def["name"],
                    category=item_def["category"],
                )

        event_bus.subscribe("shop.item_bought", _on_item_bought)

        # When the player equips an item, move it from inventory to the hero's slot
        def _on_equip_item(data: dict) -> None:
            hero_id = data.get("hero_id", "")
            item_id = data.get("item_id", "")
            hero = self._roster.get_hero(hero_id)
            if hero is None:
                event_bus.publish("equip.failed", {"reason": f"Hero '{hero_id}' not found"})
                return
            if self._inventory.get_item(item_id) is None:
                event_bus.publish("equip.failed", {"reason": f"Item '{item_id}' not in inventory"})
                return
            # Find the first empty equipped slot
            empty_slot = next(
                (i for i, s in enumerate(hero.equipped_items) if s is None), None
            )
            if empty_slot is None:
                event_bus.publish("equip.failed", {"reason": f"Hero '{hero_id}' has no empty item slots"})
                return
            # Move item: remove from inventory, place in hero slot
            self._inventory.remove_item(item_id)
            hero.equipped_items[empty_slot] = item_id
            event_bus.publish("equip.success", {"hero_id": hero_id, "item_id": item_id, "slot": empty_slot})

        event_bus.subscribe("player.equip_item", _on_equip_item)

    # --- Public read-only accessors for sub-systems ---

    @property
    def ledger(self) -> GoldLedger:
        return self._ledger

    @property
    def roster(self) -> RosterManager:
        return self._roster

    @property
    def inventory(self) -> GuildInventory:
        return self._inventory

    @property
    def shop_actions(self) -> ShopActions:
        return self._shop_actions

    def tick(self, seconds: float = 1.0) -> None:
        """
        Advance one time slice: recover exhaustion for all idle roster heroes.

        Called each game tick by GameLoop; seconds is the real-time equivalent
        of one tick at the current simulation speed.
        """
        self._roster.tick_exhaustion_recovery(seconds)

    def earn_gold(self, amount: int, reason: str = "quest_reward") -> int:
        """Convenience method: credit gold to the ledger and return new balance."""
        return self._ledger.earn(amount, reason=reason)

    def to_dict(self) -> dict:
        """Serialize the full economy state for save/load."""
        return {
            "ledger": self._ledger.to_dict(),
            "roster": self._roster.to_dict(),
            "inventory": self._inventory.to_dict(),
        }

    @classmethod
    def from_dict(cls, data: dict, event_bus: EventBus) -> "EconomyController":
        """
        Restore an EconomyController from a serialized dict.

        Constructs via __init__ with zero starting gold (the ledger is
        replaced immediately after), so all event subscriptions are wired
        correctly, then overwrites the sub-systems with deserialized data.
        """
        controller = cls(event_bus=event_bus, starting_gold=0)
        controller._ledger = GoldLedger.from_dict(data["ledger"], event_bus)
        controller._roster = RosterManager.from_dict(data["roster"], event_bus)
        controller._inventory = GuildInventory.from_dict(data["inventory"], event_bus)
        # ShopActions must reference the freshly deserialized ledger/roster
        controller._shop_actions = ShopActions(event_bus=event_bus, ledger=controller._ledger, roster=controller._roster)
        return controller
