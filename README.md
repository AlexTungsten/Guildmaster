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
├── quest/                  # Quest model, pool draw, travel phases, and tick-based executor
│   ├── quest_model.py          # Quest dataclass: type, difficulty, status, rewards, consequences
│   ├── quest_pool.py           # Loads quest pools from data/quests/; weighted draw (easy 60%, hard 30%, elite 10%)
│   ├── critical_injector.py    # Timed injection of story-critical quests per act
│   ├── travel_phase.py         # Random travel events affecting hero HP, XP, and exhaustion
│   ├── stat_check_resolver.py  # d20 stat checks — passes if any hero in the party succeeds
│   ├── reward_distributor.py   # XP, exhaustion, and gold distribution after quest success
│   ├── quest_pipeline.py       # Orchestrates travel → resolution → rewards → completion
│   └── quest_executor.py       # Tick-based quest lifecycle using TimeEngine.schedule()
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
│   ├── roster_manager.py       # Hero roster with cap enforcement and name/ID lookup
│   ├── guild_inventory.py      # Shared guild item storage with stackable quantities
│   └── economy_controller.py   # Top-level facade connecting all economy sub-systems
│
├── data/                   # Data-driven content (JSON)
│   ├── archetypes/             # Hero class definitions (barbarian, cleric, mage, rogue)
│   ├── enemies/                # Enemy templates (goblin, bandit, bandit_captain, ogre)
│   ├── bosses/                 # Boss definitions (baron_midas)
│   ├── encounters.json         # Difficulty-to-enemy spawn table per act
│   └── quests/                 # Quest definitions split by act
│       ├── act1/               # 7 quests (4 easy, 2 hard, 1 elite)
│       ├── act2/               # 6 quests (3 easy, 2 hard, 1 elite)
│       └── act3/               # 6 quests (3 easy, 2 hard, 1 elite)
│
├── ui/                     # Pure rendering layer and the main game loop
│   ├── action_dispatcher.py    # Parses text commands and publishes player events to the bus
│   ├── game_loop.py            # Wires all systems; drives tick(), handle_input(), and rendering
│   └── renderers/
│       ├── draft_renderer.py   # Hero draft and run-start screens
│       ├── map_renderer.py     # Overworld map HUD: quest list, active quests, shops, heroes
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
4. **quest** — Uses combat and hero. Implements the full travel → resolution → reward pipeline.
5. **overworld / economy** — Use quest and hero. Manage the map, roster, and gold.
6. **ui** — Uses everything above. Pure rendering functions plus the top-level GameLoop.

### Design Principles

- **Event-driven**: systems publish and subscribe rather than calling each other directly. Any module can be replaced or extended without touching other modules.
- **Data-driven**: hero archetypes, enemy templates, boss definitions, quest definitions, and encounter tables are all JSON files in `data/`. Adding a new quest requires only a new JSON file — no code changes.
- **Single source of truth**: MapState owns all live map data; GoldLedger owns the gold balance; RosterManager owns the hero list. No second copies.
- **Tick-based time**: quest phases (travel, resolution, return) take real ticks to complete via `TimeEngine.schedule()`. Heroes are visibly busy while on a quest and recover exhaustion only when truly idle.

---

## Key Systems

### Time System

The `TimeEngine` drives all time-sensitive logic via simulated ticks. Callers advance the clock with `advance(n)` and schedule future events with `schedule(ticks_from_now, event_type, data)`. Pausing uses a named-reason stack so multiple systems can each hold a pause without accidentally resuming each other.

### Quest Lifecycle

Quests go through three timed phases after a hero is assigned:

| Phase | Duration | Hero Status | Quest Status |
|-------|----------|-------------|--------------|
| Travel there | `travel_time` ticks | TRAVELING | ASSIGNED |
| Resolution | `resolution_time` ticks | ON_QUEST | RESOLVING |
| Travel back | `travel_time` ticks | TRAVELING | RESOLVING |
| Home | — | IDLE | removed from map |

Each phase is scheduled via `TimeEngine.schedule()` so time genuinely passes. Gold is only credited when heroes arrive back home.

### Quest Data

All quest content lives in `data/quests/act{N}/`. Each file is a JSON object matching the `Quest` model fields. Dropping a new `.json` file into the right act folder is enough to add it to the pool — `quest_pool.py` scans the directory on startup.

**Quest fields:**

| Field | Description |
|-------|-------------|
| `quest_id` | Unique identifier |
| `title` | Display name |
| `description` | Flavour text |
| `quest_type` | `"combat"` or `"stat_check"` |
| `difficulty` | `"easy"`, `"hard"`, or `"elite"` |
| `required_heroes` | Minimum heroes needed |
| `max_heroes` | Maximum heroes allowed |
| `travel_time` | Ticks to travel each way |
| `resolution_time` | Ticks the quest itself takes |
| `expiration_time` | Ticks before an unassigned quest expires (default 50) |
| `base_exhaustion` | Exhaustion added to each hero on completion |
| `reward` | `{"gold": N, "xp": N}` |
| `stat_checks` | List of `{"stat": "...", "dc": N}` for stat_check quests |

### Map Screen

The map is split into two quest sections:

- **QUEST LIST** — available quests not yet taken, showing expiry countdown and hero requirements. Use `assign` to send heroes.
- **ACTIVE QUESTS** — quests currently in progress, showing which heroes are on them and their current phase.

Heroes show `IDLE` or `ON QUEST [TRAVELING / ON_QUEST]` so you can always tell who is available.

### Dice System

Every hero rolls a pool of dice each combat round:
- **Normal dice**: d10 (1–10), the base die type for a rested hero.
- **Locked dice**: d4 (1–4), replacing normal dice when the hero is exhausted.

The `DiceAssignmentEngine` distributes the rolled values to skill slots according to four behavior profiles:

| Profile | Strategy |
|---------|----------|
| `focus` | Fill skill 0 completely, then overflow to later skills |
| `balanced` | Round-robin across all skills with remaining capacity |
| `greedy` | Highest dice go to the skill with the most remaining slots |
| `dump` | Lowest dice go to the last skill first; protect skill 0 |

### Exhaustion System

Exhaustion is a floating-point value (0–100+) mapping to five severity levels:

| Level | Range | Locked Dice | Stat Penalty |
|-------|-------|-------------|--------------|
| 1 (Rested) | 0–19 | 0 | none |
| 2 (Tired) | 20–39 | 1 | top 1 stat −2 |
| 3 (Weary) | 40–59 | 2 | top 2 stats −2 |
| 4 (Drained) | 60–99 | 3 | all stats −2 |
| 5 (Critical) | 100+ | 4 | all stats −2 + death roll |

Heroes only recover exhaustion when IDLE. At level 5, heroes may suffer permanent stat loss after combat.

### Starting Roster

Every run begins with four heroes, one of each archetype:

| Name | Archetype | HP | Key Stats |
|------|-----------|-----|-----------|
| Ragnar | Barbarian | 35 | STR 14, CON 15 |
| Seraphine | Cleric | 28 | INT 12, CON 14 |
| Aldric | Mage | 20 | INT 16 |
| Vex | Rogue | 25 | DEX 16 |

### Hero Archetypes

| Archetype | HP | Dice | Skills | Passive |
|-----------|-----|------|--------|---------|
| Barbarian | 35 | 4d10 | Bash, Blood Cleave, Bloodletting | Ironhide (locked dice d6) |
| Cleric | 28 | 4d10 | Smite, Cleanse, Heal | Mender |
| Rogue | 25 | 4d10 | Poisoned Dagger, Knockout, Eviscerate | Lucky Roll |
| Mage | 20 | 4d10 | Arcane Bolt, Fireball, Barrier | Prepared |

### Enemy Types

| Enemy | HP | Dice | Skills |
|-------|-----|------|--------|
| Goblin | 20 | 3d4 | Stab Stab Stab (1 slot), Annoying (2 slots) |
| Bandit | 35 | 4d6 | Stab (1), Dodge (1), Poison Mist (3) |
| Bandit Captain | 55 | 5d6 | Plunder (2), Backstep (1), Poison Mist (3) |
| Ogre | 70 | 1d12 | Smash (5 slots, fires every 5 turns) |

### Status Effects

**Debuffs**: Poison, Burn, Bleed, Paralyze, Vulnerable, Weak, Downgrade, Disadvantage
**Buffs**: Upgrade, Advantage
**Mechanics**: Taunt

### Encounter Table

Enemy compositions per quest difficulty are defined in `data/encounters.json`:

| Act | Difficulty | Possible Encounters |
|-----|------------|-------------------|
| 1 | Easy | 2 Goblins, or 1 Bandit, or 2–3 Goblins (Goblin Attack) |
| 1 | Hard | 1 Bandit + 1 Bandit Captain |
| 1 | Elite | 2 Goblins + 1 Ogre |

---

## Boss System: Baron Midas

Baron Midas is the Act 1 boss. His HP scales with gold stolen during the act (base 100, +1 per gold, cap 666).

### Phase System

| Phase | Dice | Skill 1 | Skill 2 | Skill 3 (Cost) | Permanent Buff |
|-------|------|---------|---------|----------------|----------------|
| 1 | 4d4 | Steal (1 slot) | Gilded Shield (1 slot) | I NEED GOLD (15) | +1 die |
| 2 | 5d4 | Steal (2 slots) | Gilded Shield (1 slot, Paralyze) | I NEED MORE GOLD (20) | All dice → d8 |
| 3 | 5d8 | Steal (2 slots) | Gilded Shield (1 slot, Paralyze) | I NEED EVEN MORE GOLD (40) | Permanent Advantage |
| 4 | 5d8 + Advantage | Golden Wave (2 slots, 2 random heroes) | Gilded Armor (1 slot, 2 Paralyze all) | Golden Explosion (50, 30 AOE) | — |

---

## How to Run

### Requirements

- Python 3.10 or later
- Standard library only for the core game
- `fastapi` and `uvicorn[standard]` for the web GUI server

### Web GUI (Recommended)

A browser-based UI built with FastAPI and WebSockets. The server runs the game tick loop and pushes state to the browser in real time.

**Install dependencies:**
```bash
pip install fastapi "uvicorn[standard]"
```

**Start the server:**
```bash
uvicorn server:app --reload
```

Then open `http://localhost:8000` in your browser.

**Features:**
- **Map tab** — Quest List (available) and Active Quests side by side
- **Heroes tab** — Full hero cards with HP bar, stats, exhaustion, skills, and status
- **Click-to-assign** — Click a quest to select it, then click idle heroes on the Heroes tab, then hit Assign
- **Boss timer** — Progress bar counts down in the top bar; turns red when the boss appears
- **Command bar** — Manual `assign <quest_id> <hero_id>` input also available

**Files:**
| File | Description |
|------|-------------|
| `server.py` | FastAPI app, WebSocket endpoint, game tick loop |
| `static/index.html` | UI shell |
| `static/style.css` | Dark fantasy theme |
| `static/app.js` | WebSocket client, rendering, and assignment logic |

---

### Interactive Mode (Terminal)

```bash
python main.py
```

**Commands:**

| Command | Description |
|---------|-------------|
| `assign <quest_id> <hero_name> [hero_name ...]` | Send named heroes on a quest |
| `shop <shop_id>` | Open a travelling merchant shop |
| `hire <hero_id>` | Hire a hero from the current shop |
| `buy <item_id>` | Buy an item from the current shop |
| `train <skill_id> <hero_id> <slot>` | Train a skill into a hero's slot (0–2) |
| `heroes` | Switch to the hero panel view |
| `items` | Switch to the items view |
| `leave` | Leave the current shop |
| `pause` | Toggle time pause |
| `quit` | Exit the game |

**Example session:**

```
> assign q_60 Ragnar
OK: assign

> assign q_120 Seraphine Aldric
OK: assign
```

### Act Simulator

Runs a full Act 1 automatically with no user input:

```bash
# Default run (4 heroes, seed 42, full heal)
python simulate.py

# Hard mode: 2 heroes, max boss HP, 50% heal
python simulate.py --party barbarian,rogue --gold-stolen 566 --heal 0.5

# Verbose combat (see every round)
python simulate.py --verbose --seed 99
```

| Flag | Default | Description |
|------|---------|-------------|
| `--seed N` | 42 | RNG seed for reproducible runs |
| `--gold N` | 500 | Starting guild gold |
| `--gold-stolen N` | 100 | Gold stolen by Baron Midas (bonus HP, cap 566) |
| `--heal 0.0–1.0` | 1.0 | Heal percentage after each quest |
| `--party a,b,...` | barbarian,cleric,rogue,mage | Comma-separated archetype names |
| `--verbose` | off | Show round-by-round combat detail |
| `--ticks N` | 800 | Maximum simulation ticks |

### Run All Tests

```bash
python -m pytest -v
```

### Headless Mode

```python
from ui.game_loop import GameLoop

loop = GameLoop.create(starting_gold=500)

for _ in range(200):
    loop.tick()

print(loop.last_output)

# Assign by hero name
feedback = loop.handle_input("assign q_60 Ragnar")
print(feedback)
```
