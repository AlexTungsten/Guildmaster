# Guildmaster — Roguelike Guild Management Game

You are a guild leader. Heroes need quests, quests need heroes, and a boss is always on the clock.

Guildmaster is a roguelike guild management game played across a 3-act run. You recruit heroes, send them on quests to earn gold and XP, manage their exhaustion, and shop between missions. Every act ends with a boss encounter whose power grows each time you let a critical quest expire. One run, win or lose, is a complete game.

---

## Project Structure

```
Guildmaster/
├── game_runtime/           # Foundation layer: event bus, simulated clock, state store
│   ├── event_bus.py        # Publish/subscribe message bus — all systems communicate through this
│   ├── time_engine.py      # Tick-based clock with pause stack, speed multiplier, and scheduled events
│   └── state_manager.py    # Nested key/value state store with JSON serialization
│
├── hero/                   # Hero entity, stat system, exhaustion, and XP
│   ├── hero_entity.py      # Full hero data model: stats, exhaustion, skills, behavior profile
│   └── exhaustion.py       # Per-tick exhaustion recovery helper
│
├── enemy/                  # Enemy entity, attack patterns, and act scaling
│   └── enemy.py            # Enemy stat block, cyclic AttackPattern, make_enemy() factory
│
├── combat/                 # Dice pool, assignment, skill execution, and combat simulation
│   ├── dice_pool_compositor.py    # Builds d4/d10 dice pools from hero exhaustion state
│   ├── dice_assignment_engine.py  # Distributes rolled dice to skill slots per behavior profile
│   ├── skill_executor.py          # Converts assignments to SkillResult (dice + stat modifier)
│   └── combat_engine.py           # Round-by-round combat loop with pre-simulate support
│
├── quest/                  # Quest model, pool draw, critical injection, and full pipeline
│   ├── quest_model.py          # Quest dataclass: type, difficulty, status, rewards, consequences
│   ├── quest_pool.py           # Weighted act pools (easy 60%, hard 30%, elite 10%)
│   ├── critical_injector.py    # Timed injection of story-critical quests per act
│   ├── travel_phase.py         # Random travel events affecting hero HP, XP, and exhaustion
│   ├── stat_check_resolver.py  # d20 stat checks — passes if any hero in the party succeeds
│   ├── reward_distributor.py   # XP, exhaustion, and gold distribution after quest success
│   └── quest_pipeline.py       # Orchestrates travel → resolution → rewards → completion
│
├── overworld/              # Map state, quest/shop spawning, boss timer, expiration tracking
│   ├── map_state.py            # Live map snapshot: active quests, shops, boss slot, act timing
│   ├── expiration_tracker.py   # Detects and processes expired quests and shops each tick
│   ├── hero_assignment.py      # Validates and commits hero-to-quest assignments
│   ├── quest_spawner.py        # Periodically draws quests from the act pool onto the map
│   ├── shop_spawner.py         # Periodically generates travelling merchant shops
│   ├── boss_timer.py           # Countdown timer that reveals the act boss after a fixed duration
│   └── overworld_controller.py # Façade that coordinates all overworld subsystems each tick
│
├── economy/                # Gold ledger, roster, inventory, shop actions
│   ├── gold_ledger.py          # Authoritative gold balance with full transaction history
│   ├── shop_inventory.py       # Typed item/hero/training listings for one shop visit
│   ├── shop_actions.py         # Executes hire, buy, and train purchases with validation
│   ├── roster_manager.py       # Hero roster with cap enforcement and exhaustion recovery
│   ├── guild_inventory.py      # Shared guild item storage with stackable quantities
│   └── economy_controller.py   # Top-level façade connecting all economy sub-systems
│
└── ui/                     # Pure rendering layer and the main game loop
    ├── action_dispatcher.py    # Parses text commands and publishes player events to the bus
    ├── game_loop.py            # Wires all systems; drives tick(), handle_input(), and rendering
    └── renderers/
        ├── draft_renderer.py   # Hero draft and run-start screens
        ├── map_renderer.py     # Overworld map HUD with quests, shops, boss, and heroes
        ├── hero_renderer.py    # Hero panel summary and full per-hero detail view
        ├── combat_renderer.py  # Combat screen with HP bars, dice pools, and pre-sim projection
        └── shop_renderer.py    # Merchant shop screen with three purchase categories
```

---

## Architecture

The project is organized into **6 implementation layers**, built bottom-up so that each layer only depends on the layers below it:

1. **game_runtime** — EventBus, TimeEngine, StateManager. No game concepts; pure infrastructure.
2. **hero / enemy** — Domain entities. No references to quests, economy, or UI.
3. **combat** — Uses hero and enemy entities. Fully deterministic when given a seed.
4. **quest** — Uses combat and hero. Implements the full travel→resolution→reward pipeline.
5. **overworld / economy** — Use quest and hero. Manage the map, roster, and gold.
6. **ui** — Uses everything above. Pure rendering functions plus the top-level GameLoop.

### Design principles

- **Event-driven**: systems publish and subscribe rather than calling each other directly. This means any module can be replaced or extended without touching other modules.
- **Data-driven**: quest pools, enemy templates, and shop merchandise are plain Python data structures, not hard-coded logic. Swapping content requires only changing the data.
- **Single source of truth**: the MapState owns all live map data; the GoldLedger owns the gold balance; the RosterManager owns the hero list. No other module holds a second copy.
- **Every module independently tested**: each layer can be instantiated and exercised in isolation using `unittest`.

---

## Key Systems

### Time System

The `TimeEngine` drives all time-sensitive logic via simulated ticks. Callers advance the clock with `advance(n)` and schedule future events with `schedule(ticks_from_now, event_type)`. Pausing uses a named-reason stack: multiple systems can each hold a pause without accidentally resuming each other.

### Dice System

Every hero rolls a pool of dice each combat round:
- **Normal dice**: d10 (1–10), the base die type for a rested hero.
- **Locked dice**: d4 (1–4), replacing normal dice when the hero is exhausted.

The `DiceAssignmentEngine` distributes the rolled values to the hero's skill slots according to four behavior profiles:

| Profile | Strategy |
|---------|----------|
| `focus` | Fill skill 0 completely, then overflow to later skills |
| `balanced` | Round-robin across all skills with remaining capacity |
| `greedy` | Highest dice go to the skill with the most remaining slots |
| `dump` | Lowest dice go to the last skill first; protect skill 0 |

### Exhaustion System

Exhaustion is a floating-point value (0–100+) that maps to five severity levels:

| Level | Range | Locked Dice | Stat Penalty |
|-------|-------|-------------|--------------|
| 1 (Rested) | 0–19 | 0 | none |
| 2 (Tired) | 20–39 | 1 | top 1 stat −2 |
| 3 (Weary) | 40–59 | 2 | top 2 stats −2 |
| 4 (Drained) | 60–99 | 3 | all stats −2 |
| 5 (Critical) | 100+ | 4 | all stats −2 + death roll |

At level 5, after each combat the hero rolls against their exhaustion score (1d1000 < exhaustion) to determine whether they suffer a permanent stat loss. Heroes only recover exhaustion when IDLE.

### Behavior Profiles

Each hero has a `behavior_profile` that governs how their combat dice are distributed across skill slots. Profiles are designed to support specialization (focus), versatility (balanced), power concentration (greedy), or sacrifice strategies (dump).

---

## How to Run

### Requirements

- Python 3.10 or later
- No external dependencies — the standard library is sufficient

### Run all tests

From the project root:

```bash
python -m unittest discover -s . -p "test_*.py"
```

### Start the game loop

```python
from ui.game_loop import GameLoop

loop = GameLoop.create(starting_gold=100)

# Advance the simulation and read the rendered output
loop.tick()
print(loop.last_output)

# Send a player command
feedback = loop.handle_input("heroes")
print(feedback)
```

---

## Quick Start

```python
from ui.game_loop import GameLoop

def run_headless(ticks: int = 200) -> None:
    """Run the game for a fixed number of ticks and print the final map screen."""
    loop = GameLoop.create(starting_gold=150)

    for _ in range(ticks):
        loop.tick()

    print(loop.last_output)

if __name__ == "__main__":
    run_headless()
```

To wire up interactivity, read input from stdin and pass each line to `loop.handle_input()` between ticks:

```python
loop = GameLoop.create()
while True:
    loop.tick()
    print(loop.last_output)
    cmd = input("> ")
    if cmd.strip() == "quit":
        break
    print(loop.handle_input(cmd))
```
