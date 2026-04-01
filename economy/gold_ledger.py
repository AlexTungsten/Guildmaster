"""
gold_ledger.py — Authoritative record of the guild's gold balance.

All gold movement (earning and spending) goes through the GoldLedger so the
balance is never modified by direct field access.  Every transaction is
appended to an immutable history list for audit/display purposes, and the
corresponding event is published so the UI can refresh.

GoldLedger raises no exceptions on insufficient funds — spend() returns False
instead so callers can decide how to handle the failure.
"""

from dataclasses import dataclass, field
from typing import List
from game_runtime.event_bus import EventBus


@dataclass
class Transaction:
    """One record in the gold ledger history."""
    amount: int
    reason: str         # Human-readable label (e.g. "quest_reward", "hire_hero")
    balance_after: int  # Running balance after this transaction


class GoldLedger:
    def __init__(self, event_bus: EventBus, starting_gold: int = 100):
        self._event_bus = event_bus
        self._balance: int = starting_gold
        self._history: List[Transaction] = []

    @property
    def balance(self) -> int:
        """Current gold balance (read-only view)."""
        return self._balance

    def earn(self, amount: int, reason: str = "quest_reward") -> int:
        """
        Credit the guild's balance by amount.

        Publishes "gold.earned" and returns the new balance.
        """
        self._balance += amount
        self._history.append(Transaction(amount=amount, reason=reason, balance_after=self._balance))
        self._event_bus.publish("gold.earned", {"amount": amount, "balance": self._balance, "reason": reason})
        return self._balance

    def spend(self, amount: int, reason: str = "purchase") -> bool:
        """
        Debit the guild's balance by amount if funds are sufficient.

        Returns True and publishes "gold.spent" on success.
        Returns False and publishes "gold.insufficient" when the balance is too low.
        """
        if self._balance >= amount:
            self._balance -= amount
            self._history.append(Transaction(amount=amount, reason=reason, balance_after=self._balance))
            self._event_bus.publish("gold.spent", {"amount": amount, "balance": self._balance, "reason": reason})
            return True
        else:
            # Notify listeners that a purchase attempt failed — UI can show an error
            self._event_bus.publish("gold.insufficient", {"amount": amount, "balance": self._balance})
            return False

    @property
    def history(self) -> List[Transaction]:
        """Return a shallow copy of the transaction history (safe to iterate)."""
        return list(self._history)

    def to_dict(self) -> dict:
        return {
            "balance": self._balance,
            "history": [
                {"amount": t.amount, "reason": t.reason, "balance_after": t.balance_after}
                for t in self._history
            ],
        }

    @classmethod
    def from_dict(cls, data: dict, event_bus: EventBus) -> "GoldLedger":
        """Restore a GoldLedger from a serialized dict, including full history."""
        ledger = cls(event_bus=event_bus, starting_gold=data["balance"])
        ledger._history = [
            Transaction(amount=t["amount"], reason=t["reason"], balance_after=t["balance_after"])
            for t in data.get("history", [])
        ]
        return ledger
