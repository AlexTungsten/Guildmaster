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
from game_runtime.event_bus import EventBus


class EconomyController:
    def __init__(self, event_bus: EventBus, starting_gold: int = 100, roster_cap: int = 15, inventory_max: int = 20):
        self._event_bus = event_bus
        self._ledger = GoldLedger(event_bus=event_bus, starting_gold=starting_gold)
        self._roster = RosterManager(event_bus=event_bus, cap=roster_cap)
        self._inventory = GuildInventory(event_bus=event_bus, max_size=inventory_max)
        # ShopActions is wired to share the same ledger and roster instances
        self._shop_actions = ShopActions(event_bus=event_bus, ledger=self._ledger, roster=self._roster)

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

        Uses __new__ to skip __init__ so the sub-systems are deserialized
        individually rather than re-initialized with default values.
        """
        controller = cls.__new__(cls)
        controller._event_bus = event_bus
        controller._ledger = GoldLedger.from_dict(data["ledger"], event_bus)
        controller._roster = RosterManager.from_dict(data["roster"], event_bus)
        controller._inventory = GuildInventory.from_dict(data["inventory"], event_bus)
        # ShopActions is always re-wired to the freshly deserialized ledger/roster
        controller._shop_actions = ShopActions(event_bus=event_bus, ledger=controller._ledger, roster=controller._roster)
        return controller
