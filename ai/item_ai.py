"""
item_ai.py — Simple AI that manages item buying and equipping automatically.

Two behaviours:

  AUTO-BUY (triggered by shop.spawned)
  ─────────────────────────────────────
  When a shop appears on the map the AI scans its inventory for items that
  exist in the item catalog (potions, glasses, etc.) and buys every one it
  can afford.  Items that are too expensive or would overflow the guild
  inventory are skipped silently.

  AUTO-EQUIP (triggered by player.assign_quest)
  ──────────────────────────────────────────────
  When heroes are assigned to a quest the AI equips potions from the guild
  inventory to any hero that has an empty item slot.  Heroes are loaded in
  roster order; items are handed out one per empty slot until inventory is
  empty or all slots are filled.

Both behaviours fire synchronously inside EventBus.publish() so they complete
before the downstream quest/shop logic runs.
"""

from economy.economy_controller import EconomyController
from economy.shop_inventory import ShopInventory, ItemListing
from item.item_catalog import get_item
from game_runtime.event_bus import EventBus


class ItemAI:
    """
    Subscribes to game events and automatically buys and equips items.

    Parameters
    ----------
    event_bus  : Shared event bus — used to subscribe to shop/quest events.
    economy    : EconomyController — provides ledger, inventory, shop_actions,
                 and roster access.
    overworld  : OverworldController — provides map_state to inspect shop slots.
    """

    def __init__(self, event_bus: EventBus, economy: EconomyController, overworld) -> None:
        self._event_bus = event_bus
        self._economy = economy
        self._overworld = overworld

        event_bus.subscribe("shop.spawned", self._on_shop_spawned)
        event_bus.subscribe("player.assign_quest", self._on_assign_quest)

    # ------------------------------------------------------------------
    # Auto-buy: purchase all affordable potions when a shop appears
    # ------------------------------------------------------------------

    def _on_shop_spawned(self, data: dict) -> None:
        """
        Buy every catalog item found in the shop's inventory if affordable.

        Builds a temporary ShopInventory from the raw slot data so the
        existing ShopActions.buy_item() path handles gold deduction and
        the shop.item_bought event (which adds the item to guild inventory).
        """
        shop_id = data.get("shop_id", "")
        shop_slot = self._overworld.map_state.active_shops.get(shop_id)
        if shop_slot is None:
            return

        # Build item listings only for entries that exist in the catalog
        item_listings = []
        for entry in shop_slot.inventory:
            item_id = entry.get("item_id", "")
            item_def = get_item(item_id)
            if item_def is None:
                continue  # not a catalog item (hero/training listing — skip)
            item_listings.append(ItemListing(
                item_id=item_def["item_id"],
                name=item_def["name"],
                category=item_def["category"],
                cost=item_def["cost"],
            ))

        if not item_listings:
            return

        # Wrap in a ShopInventory so ShopActions can validate and charge gold
        shop_inv = ShopInventory(shop_id=shop_id, items=item_listings)

        for listing in item_listings:
            # Stop trying if the guild inventory is already full
            if self._economy.inventory.is_full:
                break
            # Check affordability before attempting (avoids ShopError noise)
            if self._economy.ledger.balance < listing.cost:
                continue
            try:
                self._economy.shop_actions.buy_item(shop_inv, listing.item_id)
                # shop.item_bought event fires inside buy_item → economy_controller
                # subscriber adds the item to guild inventory automatically
            except Exception:
                pass  # already sold or other edge case — move on

    # ------------------------------------------------------------------
    # Auto-equip: fill empty hero slots before a quest starts
    # ------------------------------------------------------------------

    def _on_assign_quest(self, data: dict) -> None:
        """
        Equip items from guild inventory to heroes with empty slots.

        Runs before the quest pipeline so apply_passive_items() in the
        pipeline sees the newly equipped items from the start.
        """
        hero_ids = data.get("hero_ids", [])
        heroes = [
            self._economy.roster.get_hero(hid)
            for hid in hero_ids
            if self._economy.roster.get_hero(hid) is not None
        ]
        if not heroes:
            return

        # Gather available items from guild inventory (list of InventoryItem)
        available = list(self._economy.inventory.items)
        if not available:
            return

        for hero in heroes:
            for slot_idx, slot_content in enumerate(hero.equipped_items):
                if slot_content is not None:
                    continue  # slot already filled
                if not available:
                    return  # no more items to hand out

                # Take the next available item and equip it
                inv_item = available.pop(0)
                self._economy.inventory.remove_item(inv_item.item_id)
                hero.equipped_items[slot_idx] = inv_item.item_id
                self._event_bus.publish(
                    "equip.success",
                    {
                        "hero_id": hero.hero_id,
                        "item_id": inv_item.item_id,
                        "slot": slot_idx,
                        "source": "item_ai",
                    },
                )
