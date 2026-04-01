"""
time_engine.py — Simulated tick-based clock for Guildmaster.

The TimeEngine drives all time-sensitive game logic.  Callers advance the
clock one or more ticks at a time; the engine fires any scheduled events
whose fire_at tick has been reached and then publishes a global "time.tick"
event so that any system can react to the passage of time.

Pausing uses a *set* of named reasons rather than a boolean flag so that
multiple independent systems can each request a pause without accidentally
resuming the clock when only one of them has finished.
"""

import heapq
from dataclasses import dataclass, field
from typing import Any, Optional

from game_runtime.event_bus import EventBus


@dataclass
class ScheduledEvent:
    """A future event stored in the time engine's priority queue."""

    fire_at: int       # Absolute tick at which this event should fire
    event_type: str    # Event string published to the bus when it fires
    data: Any = None   # Optional payload forwarded to subscribers

    # Comparison operators allow ScheduledEvent to be used directly in a heapq
    def __lt__(self, other: "ScheduledEvent") -> bool:
        return self.fire_at < other.fire_at

    def __le__(self, other: "ScheduledEvent") -> bool:
        return self.fire_at <= other.fire_at

    def __gt__(self, other: "ScheduledEvent") -> bool:
        return self.fire_at > other.fire_at

    def __ge__(self, other: "ScheduledEvent") -> bool:
        return self.fire_at >= other.fire_at

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, ScheduledEvent):
            return NotImplemented
        # Two events are equal when they would fire at the same tick with the same type
        return self.fire_at == other.fire_at and self.event_type == other.event_type


class TimeEngine:
    def __init__(self, event_bus: EventBus) -> None:
        self._event_bus = event_bus
        self._tick: int = 0                  # Current simulated tick counter
        self._pause_reasons: set = set()     # Named callers that have requested a pause
        self._speed: float = 1.0             # Multiplier applied to each advance() call
        self._scheduled: list = []           # Min-heap of ScheduledEvent sorted by fire_at

    @property
    def tick(self) -> int:
        """Current tick count (read-only)."""
        return self._tick

    @property
    def is_paused(self) -> bool:
        """True when at least one pause reason is active."""
        return len(self._pause_reasons) > 0

    def pause(self, reason: str) -> None:
        """Request a pause under a named reason.  Multiple reasons stack."""
        self._pause_reasons.add(reason)
        self._event_bus.publish("time.paused", {"reason": reason})

    def resume(self, reason: str) -> None:
        """Lift the pause for the given reason; publishes resumed only when all reasons clear."""
        self._pause_reasons.discard(reason)
        if not self._pause_reasons:
            # Only truly resume when no other system is still requesting a pause
            self._event_bus.publish("time.resumed", {"reason": reason})

    def set_speed(self, multiplier: float) -> None:
        """Override the simulation speed.  Values > 1.0 fast-forward; < 1.0 slow down."""
        if multiplier <= 0:
            raise ValueError("Speed multiplier must be greater than 0")
        self._speed = multiplier

    def schedule(self, ticks_from_now: int, event_type: str, data: Any = None) -> None:
        """Schedule an event to fire after ticks_from_now additional ticks."""
        fire_at = self._tick + ticks_from_now
        event = ScheduledEvent(fire_at=fire_at, event_type=event_type, data=data)
        heapq.heappush(self._scheduled, event)   # Maintain heap order by fire_at

    def advance(self, ticks: int = 1) -> None:
        """
        Advance the clock by ticks steps (scaled by speed).

        Each step:
          1. Increments _tick by 1.
          2. Drains any scheduled events whose fire_at <= current tick.
          3. Publishes "time.tick" so per-tick listeners can react.

        Does nothing when paused.
        """
        if self.is_paused:
            return
        # Speed scaling: round to the nearest whole number of steps
        steps = round(ticks * self._speed)
        for _ in range(steps):
            self._tick += 1
            # Fire all scheduled events due on this tick (heap pops in ascending fire_at order)
            while self._scheduled and self._scheduled[0].fire_at <= self._tick:
                event = heapq.heappop(self._scheduled)
                self._event_bus.publish(event.event_type, event.data)
            # Notify all per-tick listeners of the new tick value
            self._event_bus.publish("time.tick", {"tick": self._tick})

    def to_dict(self) -> dict:
        """Serialize engine state for save/load."""
        return {
            "tick": self._tick,
            "pause_reasons": list(self._pause_reasons),
            "speed": self._speed,
            "scheduled": [
                {"fire_at": e.fire_at, "event_type": e.event_type, "data": e.data}
                for e in self._scheduled
            ],
        }

    @classmethod
    def from_dict(cls, data: dict, event_bus: EventBus) -> "TimeEngine":
        """Restore a TimeEngine from a previously serialized dict."""
        engine = cls(event_bus)
        engine._tick = data["tick"]
        engine._pause_reasons = set(data.get("pause_reasons", []))
        engine._speed = data.get("speed", 1.0)
        # Re-insert all pending events back into the heap
        for entry in data.get("scheduled", []):
            event = ScheduledEvent(
                fire_at=entry["fire_at"],
                event_type=entry["event_type"],
                data=entry.get("data"),
            )
            heapq.heappush(engine._scheduled, event)
        return engine
