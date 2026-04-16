# Guildmaster -- Roguelike Guild Management Game

You are a guild leader. Heroes need quests, quests need heroes, and a boss is always on the clock.

Guildmaster is a roguelike guild management game played across a 3-act run. You recruit heroes, send them on quests to earn gold and XP, manage their exhaustion, and shop between missions. Every act ends with a boss encounter whose power grows based on how the act played out. One run, win or lose, is a complete game.

---

## Project Structure

```
Guildmaster/
├── game_runtime/           # Foundation layer: event bus, simulated clock, state store, act state
│   ├── event_bus.py        # Publish/subscribe message bus — all systems communicate through this
│   ├── time_engine.py      # Tick-based clock with pause stack, speed multiplier, and scheduled events
│   ├── state_manager.py    # Nested key/value state store with JSON serialization
│   └── act_run_state.py    # Per-act accumulator: boss selection, gold stolen, CK damage, CQ count
│
├── hero/                   # Hero entity, stat system, exhaustion, and XP
│   ├── hero_entity.py      # Full hero data model: stats, HP, exhaustion, skills, status effects
│   ├── archetype_loader.py # Loads hero archetypes from JSON (barbarian, cleric, rogue, mage)
│   └── exhaustion.py       # Per-tick exhaustion recovery helper
│
├── enemy/                  # Enemy entity, boss system, and act scaling
│   ├── enemy.py            # Enemy stat block, slot-accumulation turn system, make_enemy() factory
│   ├── enemy_loader.py     # Loads enemy templates from JSON
│   ├── boss_enemy.py       # BossEnemy subclass with multi-phase skills and permanent buffs
│   ├── boss_loader.py      # Loads all three Act 1 bosses with gimmick state injection
│   └── special_enemies.py  # Subclasses: CursedKnightBossEnemy, KoboldKingEnemy, MechEnemy
│
├── combat/                 # Dice pool, assignment, skill execution, status effects, and combat simulation
│   ├── dice_pool_compositor.py    # Builds locked/normal dice pools from hero exhaustion state
│   ├── dice_assignment_engine.py  # Distributes rolled dice to skill slots per behavior profile
│   ├── skill_executor.py          # Converts assignments to SkillResult (dice + stat modifier)
│   ├── status_effects.py          # Status effect system: Poison, Burn, Bleed, Paralyze, Weak, etc.
│   ├── combat_engine.py           # Round-by-round combat loop with hero/enemy phases and boss support
│   └── combat_sim.py              # Standalone combat simulator CLI — test any hero/enemy matchup
│
├── quest/                  # Quest model, pool draw, critical injection, pipeline, and executor
│   ├── quest_model.py          # Quest dataclass: type, difficulty, status, rewards, enemy_composition
│   ├── quest_pool.py           # Weighted act pools (easy 60%, hard 30%, elite 10%)
│   ├── critical_injector.py    # Boss-specific critical quest injection (2 windows per act)
│   ├── kobold_king_ambush.py   # Pre-boss ambush gauntlet: stat checks with penalties on failure
│   ├── travel_phase.py         # Random travel events affecting hero HP, XP, and exhaustion
│   ├── stat_check_resolver.py  # d20 stat checks — passes if any hero in the party succeeds
│   ├── reward_distributor.py   # XP, exhaustion, and gold distribution after quest success
│   ├── quest_pipeline.py       # Orchestrates travel → resolution → rewards → completion
│   └── quest_executor.py       # Wires player.assign_quest events to the full pipeline
│
├── overworld/              # Map state, quest/shop spawning, boss timer, expiration tracking
│   ├── map_state.py            # Live map snapshot: active quests, shops, boss slot, act_run_state
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
│   ├── enemies/                # Enemy templates (11 types — see Enemy Types below)
│   ├── bosses/                 # Boss definitions (baron_midas, cursed_knight, kobold_king)
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

1. **game_runtime** — EventBus, TimeEngine, StateManager, ActRunState. No game concepts; pure infrastructure.
2. **hero / enemy** — Domain entities. No references to quests, economy, or UI.
3. **combat** — Uses hero and enemy entities. Fully deterministic when given a seed.
4. **quest** — Uses combat and hero. Implements the full travel→resolution→reward pipeline.
5. **overworld / economy** — Use quest and hero. Manage the map, roster, and gold.
6. **ui** — Uses everything above. Pure rendering functions plus the top-level GameLoop.

### Design principles

- **Event-driven**: systems publish and subscribe rather than calling each other directly.
- **Data-driven**: hero archetypes, enemy templates, boss definitions, and encounter tables are all JSON files in the `data/` directory. Swapping content requires only changing JSON.
- **Single source of truth**: the MapState owns all live map data; the GoldLedger owns the gold balance; the RosterManager owns the hero list. No other module holds a second copy.
- **Every module independently tested**: each layer can be instantiated and exercised in isolation using `unittest`.

---

## Key Systems

### Time System

The `TimeEngine` drives all time-sensitive logic via simulated ticks. Callers advance the clock with `advance(n)` and schedule future events with `schedule(ticks_from_now, event_type)`. Pausing uses a named-reason stack: multiple systems can each hold a pause without accidentally resuming each other.

### Dice System

Every hero rolls a pool of dice each combat round:
- **Normal dice**: archetype-specific die type (d12 for Barbarian, d10 for Mage, d8 for Cleric, d6 for Rogue).
- **Locked dice**: smaller-sided dice replacing normal dice when a hero is exhausted. Default d4; Barbarian uses d6 (Ironhide passive).

The `DiceAssignmentEngine` distributes rolled values to the hero's skill slots according to four behavior profiles:

| Profile | Strategy |
|---------|----------|
| `focus` | Fill skill 0 completely, then overflow to later skills |
| `balanced` | Round-robin across all skills with remaining capacity |
| `greedy` | Highest dice go to the skill with the most remaining slots |
| `dump` | Lowest dice go to the last skill first; protect skill 0 |

### Exhaustion System

Exhaustion is a floating-point value (0–100+) that maps to five severity levels. It drains at −1 per tick while the hero is idle.

| Level | Range | Locked Dice | Stat Penalty |
|-------|-------|-------------|--------------|
| 1 (Rested) | 0–19 | 0 | none |
| 2 (Tired) | 20–39 | 1 | top stat reduced |
| 3 (Weary) | 40–59 | 2 | top 2 stats reduced |
| 4 (Drained) | 60–99 | 3 | all stats reduced |
| 5 (Critical) | 100+ | 4 | all stats reduced + death roll |

At level 5, after each quest the hero rolls 1d1000 against their exhaustion score. If the roll is lower, the hero suffers a permanent random stat loss.

### Behavior Profiles

Each hero has a `behavior_profile` that governs how their combat dice are distributed across skill slots. The default profile (focus/1→2→3) fills skills in slot order. Profiles can be changed at hero level 3.

### Hero Archetypes

Heroes are loaded from JSON files in `data/archetypes/`. Each archetype defines base stats, dice configuration, starting skills, and passives.

| Archetype | HP | Dice | Key Stats | Starting Skills | Starting Passive |
|-----------|-----|------|-----------|-----------------|------------------|
| Barbarian (Beowulf) | 35 | 4d12 | STR 14, CON 15 | Bash, Blood Cleave, Bloodletting | Ironhide |
| Cleric (Hildegard) | 28 | 4d8 | CHA 16, CON 14 | Smite, Cleanse, Heal | Field Synthesis |
| Rogue (Odysseus) | 25 | 7d6 | DEX 16 | Poisoned Dagger, Knockout, Eviscerate | Lucky Roll |
| Mage (Merlin) | 20 | 5d10 | INT 16 | Arcane Bolt, Fireball, Barrier | Serendipity |

### Hero Leveling

| Level | Rewards |
|-------|---------|
| 1 | Starting state |
| 2 | +1 die to pool + 2 stat points |
| 3 | Choose level 3 passive + change behavior profile + 2 stat points |
| 4 | All base pool dice upgrade 1 tier permanently + 2 stat points |
| 5 | Upgrade chosen passive OR upgrade starting passive + 2 stat points |

Barbarian is capped at d12 (tier max), so level 4 grants +1 extra die instead of a tier upgrade.

### Enemy Types

Enemies use a **slot-accumulation** turn system: each turn they roll dice and fill skill slots. A skill fires when all its slots are full.

| Enemy | Tier | HP | Dice | Notable Skills / Mechanics |
|-------|------|----|------|----------------------------|
| Goblin | common | 20 | 2d4 | Stab Stab Stab (weak), Annoying (block + **Taunt**) |
| Bandit | common | 30 | 3d6 | Block, Backstab (2-turn accumulate), flees after 5 turns |
| Bandit Captain | common | 55 | 5d6 | Plunder (2 slots), Poison Mist (3 slots, AOE poison) |
| Bandit Leader | elite | 40 | 4d4 | Slash (weak), Assassinate (8 slots, massive single hit) |
| Kobold | common | 20 | 2d6 | Shovel Bash (paralyze), Trap (block + retaliate + bleed) |
| Kobold Tinkerer | common | 25 | 4d6 | Trap, Turret (spawns a Turret if none alive) |
| Turret | spawned | 10 | 1d6 | Shoot (single target) |
| Ogre | elite | 70 | 1d12 | Smash (5 slots — fires every 5 turns, massive damage) |
| Werewolf | elite | 35 | 3d6 | Bite (bleed), Slash (AOE) |
| Cursed Knight | critical quest | 250 | 3d4 | Slash (bleed + bloodlust), Blood Cleave (AOE + bloodlust) |

### Status Effects

The combat engine supports a full status effect system with stacking, duration, and mutual cancellation:

**Debuffs**: Poison, Burn, Bleed, Paralyze, Vulnerable, Weak, Downgrade, Disadvantage
**Buffs**: Upgrade, Advantage
**Mechanics**: Taunt (forces all single-target attacks onto the taunting unit)

### Encounter Table

Enemy compositions for quests are data-driven via `data/encounters.json`:

| Difficulty | Possible Encounters |
|------------|-------------------|
| Easy | 2 Goblins, or 1 Bandit |
| Hard | 1 Bandit + 1 Bandit Captain |
| Elite | 2 Goblins + 1 Ogre |

Critical quests override this table with boss-specific enemy compositions (see below).

### Quest Executor

The `QuestExecutor` subscribes to `player.assign_quest` events and orchestrates the full quest lifecycle:

1. Looks up the quest and heroes from MapState and RosterManager
2. Validates and commits the assignment via HeroAssignment
3. Spawns enemies — from `enemy_composition` if set (critical quests), otherwise from the encounter table
4. Runs the QuestPipeline (travel → resolution → rewards)
5. Credits gold to the GoldLedger on victory
6. Writes boss-progression data back to ActRunState on critical quest victory

### Act Run State

`ActRunState` tracks per-act boss progression data. A boss is randomly selected at act start; only that boss's critical quests are injected into the act pool.

| Field | Used By |
|-------|---------|
| `boss_id` | Routes boss loading and critical quest injection |
| `midas_gold` | Baron Midas HP scaling (base 100 + gold stolen, cap 666) |
| `cursed_knight_damage_dealt` | Reduces Cursed Knight starting HP and bloodlust |
| `critical_quests_completed` | Kobold King guard composition and ambush severity |

### Critical Quest Injection

`build_critical_injector(boss_id, act_start_tick)` injects two timed critical quests into the act pool (at tick +200 and +400). Each boss has a unique enemy composition:

| Boss | Critical Quest Enemies |
|------|----------------------|
| Baron Midas | 2× Bandit Captain + 1× Bandit Leader |
| Cursed Knight | 1× Cursed Knight |
| Kobold King | 1× Kobold + 2× Kobold Tinkerer |

Completing these quests reduces the boss's power or changes the fight composition.

---

## Act 1 Boss System

Three bosses are possible in Act 1. One is randomly selected at the start of the run; only that boss's critical quests appear.

### Baron Midas

HP scales with gold stolen during the act (base 100, +1 per gold, cap 666). Fights across 4 phases with permanent buffs gained at each transition.

| Phase | Dice | Skill 1 | Skill 2 | Phase Trigger (cost) | Permanent Buff |
|-------|------|---------|---------|----------------------|----------------|
| 1 | 4d4 | Steal (1 slot) | Gilded Shield (1 slot) | I Need Gold (15) | +1 die |
| 2 | 5d4 | Steal (2 slots) | Gilded Shield (1 slot, +Paralyze AOE) | I Need More Gold (20) | All dice → d8 |
| 3 | 5d8 | Steal (2 slots) | Gilded Shield (1 slot, +Paralyze AOE) | I Need Even More Gold (40) | Permanent Advantage |
| 4 | 5d8 + Adv. | Golden Wave (2 slots, 2 random heroes) | Gilded Armor (+2 Paralyze AOE) | Golden Explosion (50, 30 flat AOE) | — |

### Cursed Knight

HP and bloodlust reduced by damage dealt during critical quest encounters. Transforms into Werewolf form mid-fight when `bloodlust > current_hp`.

- **Knight form** (250 HP, 3d4): Slash, Worn Down Shield, Blood Cleave — gains bloodlust on damage dealt
- **Werewolf form** (6d6): Spiral Slash (AOE + Bleed 2, 6 slots) — all other skills removed on transform

### Kobold King

A two-phase encounter. Phase 1: King is untargetable; buffs a hidden Mech each turn for 6 turns. Phase 2 begins when all guards die or turn 7 is reached — Mech is revealed at full accumulated power.

**Phase 1 buff cycle (repeats every 3 turns):**
- Turn 1/4: Mech gains +25 max HP
- Turn 2/5: Mech gains +1 die
- Turn 3/6: Mech dice tier upgrades one step

**Guard composition scales with critical quests completed:**

| CQ Completed | Guards |
|-------------|--------|
| 0 | 4× Kobold Tinkerer |
| 1 | 2× Tinkerer + 2× Kobold |
| 2 | 1× Tinkerer + 3× Kobold |
| 3+ | 4× Kobold |

**Pre-fight Ambush Gauntlet**: The party faces stat-check ambushes before the fight. Number of ambushes scales with critical quests completed (5 / 3 / 1 / 1). Failing a check applies damage, exhaustion, Bleed, or Paralyze to all heroes.

---

## How to Run

### Requirements

- Python 3.10 or later
- No external dependencies — the standard library is sufficient

### Run all tests

```bash
python -m pytest -v
```

### Combat Simulator

The standalone combat simulator lets you test any hero/enemy matchup directly, including all three Act 1 bosses with their gimmick state:

```bash
# Barbarian vs two goblins
python -m combat.combat_sim --heroes barbarian --enemies goblin goblin

# Two heroes vs Baron Midas with 200 gold stolen
python -m combat.combat_sim --heroes barbarian cleric --boss baron_midas --gold-stolen 200

# Cursed Knight with prior damage (reduced HP/bloodlust)
python -m combat.combat_sim --heroes barbarian rogue mage --boss cursed_knight --bloodlust 80

# Kobold King encounter with 2 critical quests completed
python -m combat.combat_sim --heroes barbarian cleric rogue mage --boss kobold_king --critical-quests 2

# Override hero starting conditions and use verbose output
python -m combat.combat_sim --heroes barbarian rogue --enemies bandit ogre --hero-hp 15 20 --verbose --seed 42
```

**Combat simulator options:**

| Flag | Default | Description |
|------|---------|-------------|
| `--heroes ARCH...` | barbarian | One or more hero archetypes |
| `--enemies ID...` | goblin | Enemy IDs (mutually exclusive with --boss) |
| `--boss BOSS_ID` | — | Boss to fight (baron_midas, cursed_knight, kobold_king) |
| `--seed N` | random | RNG seed for reproducible runs |
| `--act N` | 1 | Act number for enemy HP scaling |
| `--rounds N` | 50 | Maximum combat rounds |
| `--verbose` | off | Show per-round skill activations |
| `--hero-hp HP...` | archetype default | Override starting HP per hero (positional) |
| `--hero-exhaustion EXH...` | 0 | Override starting exhaustion per hero |
| `--gold-stolen N` | 0 | Baron Midas: gold stolen during the act |
| `--bloodlust N` | 0 | Cursed Knight: prior damage dealt (reduces HP and bloodlust) |
| `--critical-quests N` | 0 | Kobold King: critical quests completed (scales guards and ambush) |

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

**Act simulator options:**

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

# Send a player command
feedback = loop.handle_input("assign q_60 hero_0 hero_1")
print(feedback)
```
