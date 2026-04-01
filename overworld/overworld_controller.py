"""
overworld_controller.py — Coordinates all overworld systems each game tick.

OverworldController is the top-level façade for the overworld layer.  Each
tick it:
  1. Runs ExpirationTracker to clean up stale quests and shops.
  2. Asks QuestSpawner to spawn a new quest if the interval and cap allow.
  3. Asks ShopSpawner to spawn a new shop if the interval and cap allow.
  4. Injects any critical story quests that are due.
  5. Checks the BossTimer and reveals the boss when the countdown expires.

It also subscribes to "quest.critical_expired" so that boss buffs are applied
to the MapState automatically when a critical quest times out.

The class method create() is the recommended factory for wiring up a complete
overworld from scratch with sensible defaults.
"""

from overworld.map_state import MapState, BossSlot
from overworld.expiration_tracker import ExpirationTracker
from overworld.quest_spawner import QuestSpawner
from overworld.shop_spawner import ShopSpawner
from overworld.boss_timer import BossTimer
from quest.critical_injector import CriticalInjector, build_default_injector
from game_runtime.event_bus import EventBus


class OverworldController:
    def __init__(
        self,
        event_bus: EventBus,
        map_state: MapState,
        quest_spawner: QuestSpawner,
        shop_spawner: ShopSpawner,
        boss_timer: BossTimer,
        critical_injector: CriticalInjector,
    ):
        self._event_bus = event_bus
        self.map_state = map_state
        self._quest_spawner = quest_spawner
        self._shop_spawner = shop_spawner
        self._boss_timer = boss_timer
        self._critical_injector = critical_injector
        # ExpirationTracker is created internally; it has no configuration options
        self._expiration_tracker = ExpirationTracker(event_bus)

        # Listen for critical quest expiry so this controller can propagate boss buffs
        self._event_bus.subscribe("quest.critical_expired", self._on_critical_expired)

    def _on_critical_expired(self, data: dict) -> None:
        """
        Handle a "quest.critical_expired" event.

        If the quest's consequence is a boss_buff, the buff string is appended
        to the current boss's buff list via MapState.apply_boss_buff().
        """
        consequence = data.get("consequence")
        if consequence is not None and consequence.type == "boss_buff":
            # Extract the buff value from consequence data and apply it to the boss
            buff = consequence.data.get("buff", "unknown")
            self.map_state.apply_boss_buff(buff)

    def tick(self, current_tick: int) -> None:
        """
        Run all overworld subsystems for one tick in priority order.

        Order matters: expiration runs first so expired entries are cleaned up
        before spawning potentially duplicates the same slot.
        """
        # 1. Remove expired quests and shops from the map
        self._expiration_tracker.tick(self.map_state, current_tick)

        # 2. Possibly spawn a new quest (respects spawn interval and active cap)
        self._quest_spawner.tick(self.map_state, current_tick)

        # 3. Possibly spawn a new shop (respects spawn interval and shop cap)
        self._shop_spawner.tick(self.map_state, current_tick)

        # 4. Inject any critical story quests due at this tick
        due_quests = self._critical_injector.get_due(current_tick)
        for quest in due_quests:
            self.map_state.add_quest(quest)

        # 5. Check the boss countdown; reveals boss and fires event when timer hits 0
        self._boss_timer.tick(self.map_state, current_tick)

    @classmethod
    def create(
        cls,
        event_bus: EventBus,
        act: int = 1,
        current_tick: int = 0,
    ) -> "OverworldController":
        """
        Factory method: wire up a complete OverworldController with default settings.

        Creates MapState, QuestSpawner, ShopSpawner, BossTimer, and
        CriticalInjector with sensible defaults for Act 1.
        """
        map_state = MapState(
            current_act=act,
            act_start_tick=current_tick,
            # Pre-create the boss slot so BossTimer always has a target
            boss=BossSlot(boss_id="boss_1", act=act),
        )
        quest_spawner = QuestSpawner(event_bus=event_bus)
        shop_spawner = ShopSpawner(event_bus=event_bus)
        boss_timer = BossTimer(event_bus=event_bus)
        critical_injector = build_default_injector(current_tick)
        return cls(
            event_bus=event_bus,
            map_state=map_state,
            quest_spawner=quest_spawner,
            shop_spawner=shop_spawner,
            boss_timer=boss_timer,
            critical_injector=critical_injector,
        )
