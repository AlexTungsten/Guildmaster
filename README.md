# Guildmaster -- Roguelike Guild Management Game

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
│   ├── hero_entity.py      # Full hero data model: stats, HP, exhaustion, skills, status effects
│   ├── archetype_loader.py # Loads hero archetypes from JSON (barbarian, cleric, rogue, mage)
│   └── exhaustion.py       # Per-tick exhaustion recovery helper
│
├── enemy/                  # Enemy entity, boss system, and act scaling
│   ├── enemy.py            # Enemy stat block, slot-accumulation turn system, make_enemy() factory
│   ├── enemy_loader.py     # Loads enemy templates from JSON (goblin, bandit, ogre, etc.)
│   ├── boss_enemy.py       # BossEnemy subclass with multi-phase skills and permanent buffs
│   └── boss_loader.py      # Loads boss definitions from JSON with gold-stolen HP scaling
│
├── combat/                 # Dice pool, assignment, skill execution, status effects, and combat simulation
│   ├── dice_pool_compositor.py    # Builds d4/d10 dice pools from hero exhaustion state
│   ├── dice_assignment_engine.py  # Distributes rolled dice to skill slots per behavior profile
│   ├── skill_executor.py          # Converts assignments to SkillResult (dice + stat modifier)
│   ├── status_effects.py          # Status effect system: Poison, Burn, Bleed, Paralyze, Weak, etc.
│   └── combat_engine.py           # Round-by-round combat loop with pre-simulate and boss support
│
├── quest/                  # Quest model, pool draw, critical injection, pipeline, and executor
│   ├── quest_model.py          # Quest dataclass: type, difficulty, status, rewards, consequences
│   ├── quest_pool.py           # Weighted act pools (easy 60%, hard 30%, elite 10%)
│   ├── critical_injector.py    # Timed injection of story-critical quests per act
│   ├── travel_phase.py         # Random travel events affecting hero HP, XP, and exhaustion
│   ├── stat_check_resolver.py  # d20 stat checks — passes if any hero in the party succeeds
│   ├── reward_distributor.py   # XP, exhaustion, and gold distribution after quest success
│   ├── quest_pipeline.py       # Orchestrates travel → resolution → rewards → completion
│   └── quest_executor.py       # Wires player.assign_quest events to the full pipeline
│
├── overworld/              # Map state, quest/shop spawning, boss timer, expiration tracking
│   ├── map_state.py            # Live map snapshot: active quests, shops, boss slot, act timing
│   ├── expiration_tracker.py   # Detects and processes expired quests and shops each tick
│   ├── hero_assignment.py      # Validates and commits hero-to-quest assignments
│   ├── quest_spawner.py        # Periodically draws quests from the act pool onto the map
│   ├── shop_spawner.py         # Periodically generates travelling merchant shops
│   ├── boss_timer.py           # Countdown timer that reveals the act boss after a fixed duration
│   └── overworld_controller.py # Facade that coordinates all overworld subsystems each tick
│
├── economy/                # Gold ledger, roster, inventory, shop actions
│   ├── gold_ledger.py          # Authoritative gold balance with full transaction history
│   ├── shop_inventory.py       # Typed item/hero/training listings for one shop visit
│   ├── shop_actions.py         # Executes hire, buy, and train purchases with validation
│   ├── roster_manager.py       # Hero roster with cap enforcement and exhaustion recovery
│   ├── guild_inventory.py      # Shared guild item storage with stackable quantities
│   └── economy_controller.py   # Top-level facade connecting all economy sub-systems
│
├── data/                   # Data-driven content (JSON)
│   ├── archetypes/             # Hero class definitions (barbarian, cleric, mage, rogue)
│   ├── enemies/                # Enemy templates (goblin, bandit, bandit_captain, ogre)
│   ├── bosses/                 # Boss definitions (baron_midas)
│   └── encounters.json         # Difficulty-to-enemy spawn table per act
│
├── ui/                     # Pure rendering layer and the main game loop
│   ├── action_dispatcher.py    # Parses text commands and publishes player events to the bus
│   ├── game_loop.py            # Wires all systems; drives tick(), handle_input(), and rendering
│   └── renderers/
│       ├── draft_renderer.py   # Hero draft and run-start screens
│       ├── map_renderer.py     # Overworld map HUD with quests, shops, boss, and heroes
│       ├── hero_renderer.py    # Hero panel summary and full per-hero detail view
│       ├── combat_renderer.py  # Combat screen with HP bars, dice pools, and pre-sim projection
│       └── shop_renderer.py    # Merchant shop screen with three purchase categories
│
├── simulate.py             # Standalone Act 1 simulator with CLI options
└── main.py                 # Interactive game loop entry point
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
- **Data-driven**: hero archetypes, enemy templates, boss definitions, and encounter tables are all JSON files in the `data/` directory. Swapping content requires only changing JSON.
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

### Hero Archetypes

Heroes are loaded from JSON files in `data/archetypes/`. Each archetype defines base stats, dice configuration, starting skills, and passives.

| Archetype | HP | Dice | Key Stats | Skills | Passive |
|-----------|-----|------|-----------|--------|---------|
| Barbarian | 35 | 4d10 | STR 14, CON 15 | Bash, Blood Cleave, Bloodletting | Ironhide (locked dice d6) |
| Cleric | 28 | 4d10 | INT 12, CON 14 | Smite, Cleanse, Heal | Mender |
| Rogue | 25 | 4d10 | DEX 16 | Poisoned Dagger, Knockout, Eviscerate | Lucky Roll |
| Mage | 20 | 4d10 | INT 16 | Arcane Bolt, Fireball, Barrier | Prepared |

### Enemy Types

Enemies are loaded from JSON files in `data/enemies/`. Each uses the slot-accumulation turn system where dice fill skill slots across turns.

| Enemy | HP | Dice | Skills |
|-------|-----|------|--------|
| Goblin | 20 | 3d4 | Scratch (1 slot) |
| Bandit | 35 | 4d6 | Stab (1), Dodge (1), Poison Mist (3) |
| Bandit Captain | 55 | 5d6 | Plunder (2), Backstep (1), Poison Mist (3) |
| Ogre | 70 | 1d12 | Smash (5 slots, fires every 5 turns) |

### Status Effects

The combat engine supports a full status effect system with stacking, duration, and mutual cancellation:

**Debuffs**: Poison, Burn, Bleed, Paralyze, Vulnerable, Weak, Downgrade, Disadvantage
**Buffs**: Upgrade, Advantage
**Mechanics**: Taunt

### Encounter Table

Enemy compositions for quests are data-driven via `data/encounters.json`:

| Difficulty | Possible Encounters |
|------------|-------------------|
| Easy | 2 Goblins, or 1 Bandit |
| Hard | 1 Bandit + 1 Bandit Captain |
| Elite | 2 Goblins + 1 Ogre |

### Quest Executor

The `QuestExecutor` subscribes to `player.assign_quest` events and orchestrates the full quest lifecycle:

1. Looks up the quest and heroes from MapState and RosterManager
2. Validates and commits the assignment via HeroAssignment
3. Spawns enemies from the encounter table for combat quests
4. Runs the QuestPipeline (travel -> resolution -> rewards)
5. Credits gold to the GoldLedger on victory
6. Heals heroes (configurable percentage) and resets them to IDLE

---

## Boss System: Baron Midas

Baron Midas is the Act 1 boss. His HP scales with gold stolen during the act (base 100, +1 per gold, cap 666).

### Phase System

Phase transitions are triggered by Skill 3's accumulation counter reaching its cost. Overflow dice from Skills 1 and 2 feed into Skill 3's progress, and the Steal skill's effectiveness also reduces its remaining cost. Permanent buffs stack across phases.

| Phase | Dice | Skill 1 | Skill 2 | Skill 3 (Cost) | Permanent Buff Gained |
|-------|------|---------|---------|----------------|----------------------|
| 1 | 4d4 | Steal (1 slot, single) | Gilded Shield (1 slot, block) | I NEED GOLD (15) | +1 die |
| 2 | 5d4 | Steal (2 slots, single) | Gilded Shield (1 slot, block + 1 Paralyze all) | I NEED MORE GOLD (20) | All dice -> d8 |
| 3 | 5d8 | Steal (2 slots, single) | Gilded Shield (1 slot, block + 1 Paralyze all) | I NEED EVEN MORE GOLD (40) | Permanent Advantage |
| 4 | 5d8 + Advantage | Golden Wave (2 slots, 2 random heroes) | Gilded Armor (1 slot, block + 2 Paralyze all) | Golden Explosion (50, 30 flat AOE) | -- |

**Final form**: 5d8 with permanent Advantage, dealing heavy AOE damage.

---

## How to Run

### Requirements

- Python 3.10 or later
- No external dependencies -- the standard library is sufficient

### Run all tests

From the project root:

```bash
python -m pytest -v
```

### Act Simulator

The standalone simulator runs a full Act 1 with automated hero assignment, quest execution, and a boss fight:

```bash
# Default run (4 heroes, seed 42, full heal, 100 gold stolen by boss)
python simulate.py

# Hard mode: 2 heroes, max boss HP, 50% heal
python simulate.py --party barbarian,rogue --gold-stolen 566 --heal 0.5

# Verbose combat (see every round)
python simulate.py --verbose --seed 99
```

**Simulator options:**

| Flag | Default | Description |
|------|---------|-------------|
| `--seed N` | 42 | RNG seed for reproducible runs |
| `--gold N` | 500 | Starting guild gold |
| `--gold-stolen N` | 100 | Gold stolen by Baron Midas (bonus HP, cap 566) |
| `--heal 0.0-1.0` | 1.0 | Heal percentage after each quest (1.0 = full heal) |
| `--party a,b,c` | barbarian,cleric,rogue,mage | Comma-separated archetype names |
| `--verbose` | off | Show round-by-round combat detail |
| `--ticks N` | 800 | Maximum simulation ticks |

### Interactive mode

```bash
python main.py
```

Commands: `assign <quest_id> <hero_ids>`, `shop <id>`, `hire <id>`, `buy <id>`, `train <skill> <hero> <slot>`, `heroes`, `items`, `leave`, `pause`, `quit`

### Headless mode

```python
from ui.game_loop import GameLoop

loop = GameLoop.create(starting_gold=500)

for _ in range(200):
    loop.tick()

print(loop.last_output)

# Send a player command (quest assignment is now fully wired)
feedback = loop.handle_input("assign q_60 hero_0 hero_1")
print(feedback)
```
