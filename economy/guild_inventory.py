"""
guild_inventory.py — Shared item storage for the guild (not hero-specific).

GuildInventory tracks all items owned by the guild that are not currently
equipped to a specific hero.  Items are stored by item_id with a quantity
counter so stackable consumables (e.g. Health Potions) occupy a single slot.

The inventory has a max_size cap (default 20) measured in total item quantity
across all stacks.  Attempting to add when full publishes "inventory.full"
rather than raising an exception, so the caller can display a message.
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional
from game_runtime.event_bus import EventBus


@dataclass
class InventoryItem:
    """One unique item type in the guild's inventory, with a quantity count."""
    item_id: str
    name: str
    category: str
    quantity: int = 1


class GuildInventory:
    def __init__(self, event_bus: EventBus, max_size: int = 20):
        self._event_bus = event_bus
        self._items: Dict[str, InventoryItem] = {}   # item_id -> InventoryItem
        self._max_size: int = max_size

    @property
    def count(self) -> int:
        """Total number of items across all stacks."""
        return sum(item.quantity for item in self._items.values())

    @property
    def is_full(self) -> bool:
        """True when count has reached the max_size cap."""
        return self.count >= self._max_size

    def add_item(self, item_id: str, name: str, category: str) -> bool:
        """
        Add one unit of item_id to the inventory.

        If the item already exists, increments its quantity.  If at capacity,
        publishes "inventory.full" and returns False without adding.
        Returns True on success.
        """
        if self.is_full:
            self._event_bus.publish("inventory.full", {"item_id": item_id})
            return False
        if item_id in self._items:
            # Stack with existing entry rather than creating a duplicate
            self._items[item_id].quantity += 1
        else:
            self._items[item_id] = InventoryItem(item_id=item_id, name=name, category=category, quantity=1)
        self._event_bus.publish("inventory.item_added", {"item_id": item_id, "name": name})
        return True

    def remove_item(self, item_id: str) -> Optional[InventoryItem]:
        """
        Remove one unit of item_id from the inventory.

        Returns an InventoryItem with quantity=1 representing the removed unit,
        or None if item_id is not in the inventory.  Deletes the stack entry
        when quantity reaches zero.
        """
        item = self._items.get(item_id)
        if item is None:
            return None
        item.quantity -= 1
        # Snapshot the removed unit before potentially deleting the stack
        removed = InventoryItem(item_id=item.item_id, name=item.name, category=item.category, quantity=1)
        if item.quantity <= 0:
            del self._items[item_id]   # Stack exhausted; remove the entry
        self._event_bus.publish("inventory.item_removed", {"item_id": item_id})
        return removed

    def get_item(self, item_id: str) -> Optional[InventoryItem]:
        """Return the InventoryItem for item_id without removing it, or None."""
        return self._items.get(item_id)

    @property
    def items(self) -> List[InventoryItem]:
        """All inventory items as a list (unordered)."""
        return list(self._items.values())

    def to_dict(self) -> dict:
        return {
            "max_size": self._max_size,
            "items": [
                {"item_id": i.item_id, "name": i.name, "category": i.category, "quantity": i.quantity}
                for i in self._items.values()
            ],
        }

    @classmethod
    def from_dict(cls, data: dict, event_bus: EventBus) -> "GuildInventory":
        """Restore a GuildInventory from a serialized dict."""
        inventory = cls(event_bus=event_bus, max_size=data.get("max_size", 20))
        for i in data.get("items", []):
            # Insert directly to bypass the full-check during deserialization
            inventory._items[i["item_id"]] = InventoryItem(
                item_id=i["item_id"], name=i["name"], category=i["category"], quantity=i.get("quantity", 1)
            )
        return inventory
