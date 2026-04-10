"""
game_loop.py — Top-level game loop that ties all systems together.

GameLoop owns references to every major subsystem (time engine, overworld,
economy, action dispatcher) and drives them forward one tick at a time.
Each tick:
  1. Advances the TimeEngine by 1 simulated tick.
  2. Ticks the OverworldController (quest/shop spawn, expiration, boss timer).
  3. Ticks the EconomyController (exhaustion recovery for idle heroes).
  4. Renders the current screen to a string and stores it in output_lines.

Screen state is tracked by the _screen field which can be switched via input
commands ("heroes", "leave", "items", …) or by subscribed EventBus handlers.

The class method create() wires up a complete game from scratch with defaults.
"""

import time
from typing import List, Optional

from game_runtime.event_bus import EventBus
from game_runtime.time_engine import TimeEngine
from game_runtime.state_manager import StateManager
from overworld.overworld_controller import OverworldController
from economy.economy_controller import EconomyController
from ui.action_dispatcher import ActionDispatcher
from ui.renderers.map_renderer import render_map_screen, render_boss_timer_bar
from ui.renderers.hero_renderer import render_hero_panel
from quest.quest_executor import QuestExecutor
from combat.combat_engine import CombatEngine
from hero.archetype_loader import load_archetype


class GameLoop:
    def __init__(
        self,
        event_bus: EventBus,
        time_engine: TimeEngine,
        state_manager: StateManager,
        overworld: OverworldController,
        economy: EconomyController,
        dispatcher: ActionDispatcher,
        ticks_per_second: int = 10,   # Simulation ticks that equal one real second
    ):
        self._event_bus = event_bus
        self._time_engine = time_engine
        self._state_manager = state_manager
        self._overworld = overworld
        self._economy = economy
        self._dispatcher = dispatcher
        self._ticks_per_second = ticks_per_second

        self._running: bool = False
        self._screen: str = "map"            # Current active screen ("map", "heroes", "items")
        self._output_lines: List[str] = []   # History of rendered screen strings

    @property
    def last_output(self) -> str:
        """Return the most recently rendered screen string, or empty string."""
        if self._output_lines:
            return self._output_lines[-1]
        return ""

    def tick(self) -> None:
        """
        Advance the simulation by one tick and render the current screen.

        Advances time, triggers overworld logic, drives economy recovery,
        then appends the rendered output to output_lines for retrieval.
        """
        self._time_engine.advance(1)
        self._overworld.tick(self._time_engine.tick)
        # Economy tick: 1 second worth of time = 1/ticks_per_second seconds per tick
        self._economy.tick(1.0 / self._ticks_per_second)
        rendered = self._render_current_screen()
        self._output_lines.append(rendered)

    def _render_current_screen(self) -> str:
        """
        Dispatch rendering to the appropriate renderer based on _screen.

        For the map screen, assembles all required data slices from overworld
        and economy, then passes plain dicts to the pure renderer functions.
        """
        if self._screen == "map":
            map_state = self._overworld.map_state
            current_tick = self._time_engine.tick
            act = map_state.current_act
            boss_duration = map_state.boss_timer_duration
            act_start = map_state.act_start_tick
            # Compute remaining boss ticks from act timing (avoids importing BossTimer here)
            boss_ticks_remaining = max(0, boss_duration - (current_tick - act_start))

            # Convert Quest objects to dicts, injecting a pre-computed expiry delta
            active_quests = []
            for quest in map_state.active_quests.values():
                q_dict = quest.to_dict() if hasattr(quest, "to_dict") else dict(quest)
                # expiry = ticks until this quest auto-expires
                expiration_tick = q_dict.get("expiration_tick", 0)
                q_dict["expiry"] = max(0, expiration_tick - current_tick)
                active_quests.append(q_dict)

            # Convert ShopSlot objects to minimal dicts for the renderer
            active_shops = []
            for shop in map_state.active_shops.values():
                s_dict = {
                    "shop_id": shop.shop_id,
                    "expiry": max(0, shop.expiration_tick - current_tick),
                    "expiration_tick": shop.expiration_tick,
                }
                active_shops.append(s_dict)

            # Convert the BossSlot to a plain dict if one exists
            boss = None
            if map_state.boss is not None:
                boss = {
                    "boss_id": map_state.boss.boss_id,
                    "act": map_state.boss.act,
                    "revealed": map_state.boss.revealed,
                    "defeated": map_state.boss.defeated,
                    "buffs": list(map_state.boss.buffs),
                }

            # Hero status row for the bottom of the map screen
            hero_statuses = [h.to_dict() for h in self._economy.roster.heroes]

            return render_map_screen(
                active_quests=active_quests,
                active_shops=active_shops,
                boss=boss,
                current_tick=current_tick,
                act=act,
                boss_ticks_remaining=boss_ticks_remaining,
                hero_statuses=hero_statuses,
            )

        elif self._screen == "heroes":
            hero_dicts = [h.to_dict() for h in self._economy.roster.heroes]
            return render_hero_panel(hero_dicts)

        else:
            return "Unknown screen"

    def handle_input(self, raw: str) -> str:
        """
        Parse and dispatch a player command, then update the active screen.

        Screen transitions are driven by command name rather than events so
        the screen switches synchronously with the input rather than waiting
        for the next tick.  Returns the dispatcher's feedback string.
        """
        success, feedback = self._dispatcher.dispatch(raw)

        # Derive the command from the raw input for screen-switch logic
        command = raw.strip().lower().split()[0] if raw.strip() else ""
        if command == "heroes":
            self._screen = "heroes"
        elif command in ("leave", "map"):
            self._screen = "map"
        elif command == "items":
            self._screen = "items"

        return feedback

    @classmethod
    def create(cls, starting_gold: int = 100) -> "GameLoop":
        """
        Factory method: wire all sub-systems and return a ready-to-run GameLoop.

        Sets up EventBus, TimeEngine, StateManager, OverworldController,
        EconomyController, and ActionDispatcher with sensible defaults,
        then subscribes screen-transition event handlers to the bus.
        """
        event_bus = EventBus()
        time_engine = TimeEngine(event_bus)
        state_manager = StateManager(event_bus)
        overworld = OverworldController.create(event_bus)
        economy = EconomyController(event_bus, starting_gold)
        dispatcher = ActionDispatcher(event_bus)

        # Quest executor: wires player.assign_quest -> pipeline -> rewards -> hero reset
        combat_engine = CombatEngine(event_bus)
        quest_executor = QuestExecutor(
            event_bus=event_bus,
            time_engine=time_engine,
            map_state=overworld.map_state,
            roster=economy.roster,
            ledger=economy.ledger,
            combat_engine=combat_engine,
        )

        loop = cls(
            event_bus=event_bus,
            time_engine=time_engine,
            state_manager=state_manager,
            overworld=overworld,
            economy=economy,
            dispatcher=dispatcher,
        )
        loop._quest_executor = quest_executor

        # Add one hero of each archetype as the starting roster
        starting_heroes = [
            ("hero_start_1", "barbarian", "Ragnar"),
            ("hero_start_2", "cleric",    "Seraphine"),
            ("hero_start_3", "mage",      "Aldric"),
            ("hero_start_4", "rogue",     "Vex"),
        ]
        for hero_id, archetype, name in starting_heroes:
            hero = load_archetype(archetype, hero_id, name)
            economy.roster.add_hero(hero)

        # Wire event subscriptions for screen transitions (these capture `loop` via closure)
        def _on_view_heroes(data):
            loop._screen = "heroes"

        def _on_leave_shop(data):
            loop._screen = "map"

        def _on_view_items(data):
            loop._screen = "items"

        event_bus.subscribe("player.view_heroes", _on_view_heroes)
        event_bus.subscribe("player.leave_shop", _on_leave_shop)
        event_bus.subscribe("player.view_items", _on_view_items)

        return loop
