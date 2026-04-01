"""
boss_timer.py — Countdown timer that reveals the act boss after a fixed duration.

The boss timer measures elapsed ticks since the start of the current act.
When ticks_remaining reaches 0 the boss is revealed on the map and the
"boss.appeared" event is published so the UI can display the encounter.

The timer uses an internal _triggered flag to ensure the appeared event fires
exactly once per act.  reset_for_act() clears this flag when a new act begins.
"""

from overworld.map_state import MapState, BossSlot
from game_runtime.event_bus import EventBus


class BossTimer:
    def __init__(self, event_bus: EventBus):
        self._event_bus = event_bus
        self._triggered: bool = False   # Prevents the boss.appeared event from firing twice

    def ticks_remaining(self, map_state: MapState, current_tick: int) -> int:
        """
        Calculate how many ticks remain until the boss is revealed.

        Returns 0 (never negative) once the countdown has expired.
        Formula: act_start_tick + boss_timer_duration - current_tick.
        """
        return max(
            0,
            map_state.act_start_tick + map_state.boss_timer_duration - current_tick,
        )

    def tick(self, map_state: MapState, current_tick: int) -> bool:
        """
        Check whether the boss timer has expired and reveal the boss if so.

        Returns True on the tick when the boss is first revealed, False otherwise.
        """
        if not self._triggered and self.ticks_remaining(map_state, current_tick) <= 0:
            self._triggered = True
            # Reveal the boss so the UI can display the encounter
            if map_state.boss is not None:
                map_state.boss.revealed = True
            self._event_bus.publish(
                "boss.appeared",
                {
                    "act": map_state.current_act,
                    "boss_id": map_state.boss.boss_id if map_state.boss is not None else None,
                    "buffs": map_state.boss.buffs if map_state.boss is not None else [],
                },
            )
            return True
        return False

    def on_boss_defeated(self, map_state: MapState) -> None:
        """Mark the boss as defeated and publish "boss.defeated" for act transition logic."""
        if map_state.boss is not None:
            map_state.boss.defeated = True
        self._event_bus.publish(
            "boss.defeated",
            {"act": map_state.current_act},
        )

    def reset_for_act(
        self, map_state: MapState, new_act: int, current_tick: int
    ) -> None:
        """
        Advance to a new act: update act number, reset the timer start, clear triggered flag.

        Publishes "act.started" so systems (quest spawner, critical injector) can
        recalibrate for the new act's content.
        """
        map_state.current_act = new_act
        map_state.act_start_tick = current_tick   # Boss countdown restarts from now
        self._triggered = False                    # Allow the boss.appeared event to fire again
        self._event_bus.publish("act.started", {"act": new_act})
