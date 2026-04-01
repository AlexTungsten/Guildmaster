"""
action_dispatcher.py — Translates raw text commands into EventBus events.

The ActionDispatcher is the single entry point for all player input.  It
parses a command string, validates basic syntax, and publishes a typed event
on the bus.  Game logic systems subscribe to these events and handle the
actual state changes.

Supported commands:
  assign <quest_id> <hero_id> [hero_id ...]  — Send heroes to a quest.
  shop <shop_id>                              — Open a shop screen.
  hire <hero_id>                              — Hire a hero from the active shop.
  buy <item_id>                               — Buy an item from the active shop.
  train <skill_id> <hero_id> <slot>          — Train a skill for a hero (slot 0–2).
  leave                                       — Exit the current shop.
  heroes                                      — Switch to the hero panel view.
  items                                       — Switch to the items view.
  pause                                       — Toggle time pause.
  manual                                      — Request manual combat control.
  draft <index>                               — Pick an archetype during the draft.
  quit                                        — Publish quit and exit the game loop.
"""

from typing import Tuple, Optional, List
from game_runtime.event_bus import EventBus


class ActionDispatcher:
    def __init__(self, event_bus: EventBus):
        self._event_bus = event_bus

    def dispatch(self, raw_input: str) -> Tuple[bool, str]:
        """
        Parse raw_input and publish the corresponding event.

        Returns (True, "OK: <command>") on success,
        or (False, "Unknown command: <input>") on parse failure.
        """
        text = raw_input.strip().lower()
        parts = text.split()
        if not parts:
            return (False, "Unknown command: ")

        command = parts[0]

        if command == "assign":
            # assign <quest_id> <hero_id1> [hero_id2 ...]
            if len(parts) < 3:
                return (False, f"Unknown command: {raw_input}")
            quest_id = parts[1]
            hero_ids = parts[2:]   # Remaining tokens are hero IDs
            self._event_bus.publish(
                "player.assign_quest",
                {"quest_id": quest_id, "hero_ids": hero_ids},
            )
            return (True, "OK: assign")

        elif command == "shop":
            if len(parts) < 2:
                return (False, f"Unknown command: {raw_input}")
            shop_id = parts[1]
            self._event_bus.publish("player.open_shop", {"shop_id": shop_id})
            return (True, "OK: shop")

        elif command == "hire":
            if len(parts) < 2:
                return (False, f"Unknown command: {raw_input}")
            hero_id = parts[1]
            self._event_bus.publish("player.hire_hero", {"hero_id": hero_id})
            return (True, "OK: hire")

        elif command == "buy":
            if len(parts) < 2:
                return (False, f"Unknown command: {raw_input}")
            item_id = parts[1]
            self._event_bus.publish("player.buy_item", {"item_id": item_id})
            return (True, "OK: buy")

        elif command == "train":
            # train <skill_id> <hero_id> <slot>
            if len(parts) < 4:
                return (False, f"Unknown command: {raw_input}")
            skill_id = parts[1]
            hero_id = parts[2]
            try:
                slot = int(parts[3])   # Slot must be an integer (0, 1, or 2)
            except ValueError:
                return (False, f"Unknown command: {raw_input}")
            self._event_bus.publish(
                "player.train_skill",
                {"skill_id": skill_id, "hero_id": hero_id, "slot": slot},
            )
            return (True, "OK: train")

        elif command == "leave":
            self._event_bus.publish("player.leave_shop", {})
            return (True, "OK: leave")

        elif command == "heroes":
            self._event_bus.publish("player.view_heroes", {})
            return (True, "OK: heroes")

        elif command == "items":
            self._event_bus.publish("player.view_items", {})
            return (True, "OK: items")

        elif command == "pause":
            self._event_bus.publish("player.toggle_pause", {})
            return (True, "OK: pause")

        elif command == "manual":
            self._event_bus.publish("player.manual_combat", {})
            return (True, "OK: manual")

        elif command == "draft":
            if len(parts) < 2:
                return (False, f"Unknown command: {raw_input}")
            try:
                index = int(parts[1])   # Archetype index (1-based in the UI)
            except ValueError:
                return (False, f"Unknown command: {raw_input}")
            self._event_bus.publish("player.draft_hero", {"index": index})
            return (True, "OK: draft")

        elif command == "quit":
            self._event_bus.publish("player.quit", {})
            return (True, "OK: quit")

        else:
            return (False, f"Unknown command: {raw_input}")
