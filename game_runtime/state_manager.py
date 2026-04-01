"""
state_manager.py — Single-source-of-truth key/value store for Guildmaster.

The StateManager holds all persistent game state as a nested dict.  Any
subsystem can read or write via dot-path-style variadic keys, and every
mutation fires a "state.changed" event on the bus so that UI or other
systems can react.

This acts as an escape hatch for ad-hoc state that does not fit neatly into
a typed domain object.  Prefer typed classes for performance-critical data;
use StateManager for flags, counters, and configuration that must survive
serialisation.
"""

import copy
import json
from typing import Any

from game_runtime.event_bus import EventBus


class StateManager:
    def __init__(self, event_bus: EventBus) -> None:
        self._event_bus = event_bus
        self._state: dict = {}   # Root nested dict; all state lives here

    def get(self, *keys: str) -> Any:
        """
        Traverse the nested state dict by the given key path and return the value.

        Returns None if any intermediate node is missing or not a dict.
        Example: get("run", "act") returns state["run"]["act"].
        """
        node = self._state
        for key in keys:
            if not isinstance(node, dict):
                return None  # Path leads through a non-dict node
            node = node.get(key)
        return node

    def set(self, value: Any, *keys: str) -> None:
        """
        Write value at the given key path, creating intermediate dicts as needed.

        Publishes "state.changed" with the path and new value after writing.
        Silently ignores calls with no keys.
        """
        if not keys:
            return
        node = self._state
        # Walk down to the second-to-last key, auto-creating dict nodes
        for key in keys[:-1]:
            if key not in node or not isinstance(node[key], dict):
                node[key] = {}
            node = node[key]
        # Write the value at the leaf key
        node[keys[-1]] = value
        self._event_bus.publish("state.changed", {"keys": list(keys), "value": value})

    def snapshot(self) -> dict:
        """Return a deep copy of the full state tree (safe to inspect offline)."""
        return copy.deepcopy(self._state)

    def serialize(self) -> str:
        """Serialize the current state to a JSON string for saving to disk."""
        return json.dumps(self._state)

    def deserialize(self, json_str: str) -> None:
        """Replace the current state from a JSON string and notify listeners."""
        self._state = json.loads(json_str)
        self._event_bus.publish("state.loaded", {"state": self._state})
