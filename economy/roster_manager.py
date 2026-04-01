"""
roster_manager.py — Manages the guild's pool of hired heroes.

RosterManager is the single authoritative list of heroes the player owns.
Key responsibilities:
  - Enforcing the roster cap (default 15, upgradeable via increase_cap()).
  - Providing filtered views (all heroes, idle heroes only).
  - Driving per-tick exhaustion recovery for idle heroes.

Heroes are stored in a dict keyed by hero_id so lookups are O(1).  The
heroes property returns a list sorted by hero_id for deterministic UI ordering.
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional
from hero.hero_entity import HeroEntity, HeroStatus
from game_runtime.event_bus import EventBus


class RosterManager:
    def __init__(self, event_bus: EventBus, cap: int = 15):
        self._event_bus = event_bus
        self._heroes: Dict[str, HeroEntity] = {}   # hero_id -> HeroEntity
        self._cap: int = cap

    @property
    def heroes(self) -> List[HeroEntity]:
        """All heroes sorted by hero_id for stable display ordering."""
        return sorted(self._heroes.values(), key=lambda h: h.hero_id)

    @property
    def count(self) -> int:
        """Current number of heroes in the roster."""
        return len(self._heroes)

    @property
    def cap(self) -> int:
        """Maximum number of heroes the roster can hold."""
        return self._cap

    def can_add_hero(self) -> bool:
        """True when the roster has at least one open slot."""
        return self.count < self._cap

    def add_hero(self, hero: HeroEntity) -> None:
        """Add a hero to the roster; raises ValueError if already at cap."""
        if not self.can_add_hero():
            raise ValueError("Roster full")
        self._heroes[hero.hero_id] = hero
        self._event_bus.publish("roster.hero_added", {"hero_id": hero.hero_id, "name": hero.name})

    def remove_hero(self, hero_id: str) -> Optional[HeroEntity]:
        """Remove and return a hero by ID; returns None if not found."""
        hero = self._heroes.pop(hero_id, None)
        if hero is not None:
            self._event_bus.publish("roster.hero_removed", {"hero_id": hero_id})
        return hero

    def get_hero(self, hero_id: str) -> Optional[HeroEntity]:
        """Look up a hero by ID without removing it."""
        return self._heroes.get(hero_id)

    def idle_heroes(self) -> List[HeroEntity]:
        """Return only heroes whose status is IDLE (available to be assigned quests)."""
        return [h for h in self._heroes.values() if h.status == HeroStatus.IDLE]

    def increase_cap(self, ledger, cost: int = 50, amount: int = 5) -> bool:
        """
        Expand the roster cap if the guild can afford it.

        Spends gold via the provided ledger; returns True if successful.
        Publishes "roster.cap_increased" on success.
        """
        if ledger.spend(cost, reason="roster_cap_increase"):
            self._cap += amount
            self._event_bus.publish("roster.cap_increased", {"new_cap": self._cap, "cost": cost})
            return True
        return False

    def tick_exhaustion_recovery(self, seconds: float = 1.0) -> None:
        """
        Advance exhaustion recovery for all idle heroes by one time slice.

        Called each game tick so heroes gradually recover while not on quests.
        Non-idle heroes are skipped automatically by recover_exhaustion().
        """
        for hero in self.idle_heroes():
            hero.recover_exhaustion(seconds)

    def to_dict(self) -> dict:
        return {
            "cap": self._cap,
            "heroes": [h.to_dict() for h in self.heroes],
        }

    @classmethod
    def from_dict(cls, data: dict, event_bus: EventBus) -> "RosterManager":
        """Restore a RosterManager from a serialized dict."""
        manager = cls(event_bus=event_bus, cap=data.get("cap", 15))
        for hero_data in data.get("heroes", []):
            hero = HeroEntity.from_dict(hero_data)
            # Insert directly to bypass the cap check during deserialization
            manager._heroes[hero.hero_id] = hero
        return manager
