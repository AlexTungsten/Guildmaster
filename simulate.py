"""
simulate.py — Standalone Act simulator for Guildmaster.

Runs a full Act with automated hero assignment, quest execution, and a boss
fight when the boss timer expires. Produces a detailed turn-by-turn log.

Usage:
    python simulate.py                          # Default: Act 1, seed 42
    python simulate.py --seed 99                # Custom RNG seed
    python simulate.py --gold-stolen 300        # Boss gets 300 bonus HP
    python simulate.py --heal 0.5               # 50% heal between quests
    python simulate.py --party barbarian,cleric # Pick 2 heroes
    python simulate.py --verbose                # Show round-by-round combat
"""

import argparse
import random
import sys
from typing import List

# Ensure Unicode characters print correctly on Windows terminals
if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from ui.game_loop import GameLoop
from hero.hero_entity import HeroEntity, HeroStatus
from hero.archetype_loader import load_archetype, list_archetypes
from enemy.boss_loader import load_boss
from combat.combat_engine import CombatEngine, CombatResult
from game_runtime.event_bus import EventBus


# ── Available hero names per archetype ──────────────────────────────
HERO_NAMES = {
    "barbarian": "Grimjaw the Savage",
    "cleric":    "Sister Elara",
    "rogue":     "Vex Shadowstep",
    "mage":      "Aldric Spellweave",
}


def _parse_args():
    parser = argparse.ArgumentParser(description="Guildmaster Act Simulator")
    parser.add_argument("--seed", type=int, default=42, help="RNG seed (default: 42)")
    parser.add_argument("--gold", type=int, default=500, help="Starting gold (default: 500)")
    parser.add_argument("--gold-stolen", type=int, default=100,
                        help="Gold stolen by Baron Midas during act (bonus HP, default: 100)")
    parser.add_argument("--heal", type=float, default=1.0,
                        help="Heal percent after quests, 0.0-1.0 (default: 1.0 = full)")
    parser.add_argument("--party", type=str, default=None,
                        help="Comma-separated archetypes (default: barbarian,cleric,rogue,mage)")
    parser.add_argument("--verbose", action="store_true", help="Show round-by-round combat detail")
    parser.add_argument("--ticks", type=int, default=800, help="Max ticks to simulate (default: 800)")
    return parser.parse_args()


def _recruit_party(econ, archetypes: List[str]) -> List[HeroEntity]:
    """Load archetype heroes and add them to the roster."""
    heroes = []
    for i, arch in enumerate(archetypes):
        name = HERO_NAMES.get(arch, f"Hero {arch.title()}")
        hero = load_archetype(arch, f"hero_{i}", name)
        econ.roster.add_hero(hero)
        heroes.append(hero)
    return heroes


def _run_boss_fight(heroes: List[HeroEntity], gold_stolen: int, eb: EventBus,
                    boss_buffs: List[str], verbose: bool) -> CombatResult:
    """Run the Baron Midas boss fight and return the result."""
    boss = load_boss("baron_midas", gold_stolen=gold_stolen)

    print()
    print("=" * 65)
    print("          BOSS FIGHT: BARON MIDAS")
    print("=" * 65)
    print(f"  HP: {boss.current_health}/{boss.max_health} "
          f"(base 100 + {min(gold_stolen, 566)} gold stolen)")
    print(f"  Dice: {boss.effective_dice_count}d{boss.effective_dice_sides} | "
          f"Phase: {boss.current_phase}")
    print(f"  Buffs from expired critical quests: {boss_buffs}")
    print()

    living = [h for h in heroes if h.current_health > 0]
    print(f"  CHALLENGERS ({len(living)}):")
    for h in living:
        skills = [s.name if s else "-" for s in h.skills]
        print(f"    {h.name:22s} | HP {h.current_health:>3}/{h.max_health:<3} | "
              f"Lvl {h.level} | Skills: {skills}")
    print()
    print("-" * 65)

    engine = CombatEngine(eb)
    result = engine.simulate(living, [boss], max_rounds=50)

    # Round-by-round output
    for r in result.rounds:
        hero_skills = [sr.skill.name for sr in r.hero_results if sr.effectiveness > 0]
        boss_skills = [sr.skill.name for sr in r.enemy_results]
        boss_str = ", ".join(boss_skills) if boss_skills else "charging..."

        if verbose:
            print(f"  Round {r.round_number:>2} | "
                  f"Boss HP: {boss.current_health:>4} | "
                  f"Phase {boss.current_phase} | "
                  f"Boss: [{boss_str}] | "
                  f"Hero dmg taken: {r.hero_damage_taken}")
        else:
            # Compact: only show phase transitions and big hits
            phase_skills = [s for s in boss_skills
                            if "GOLD" in s or "Explosion" in s]
            if phase_skills or r.hero_damage_taken >= 10 or r.round_number == 1:
                marker = f" *** {phase_skills[0]} ***" if phase_skills else ""
                print(f"  Round {r.round_number:>2} | "
                      f"Boss HP: {boss.current_health:>4} | "
                      f"Phase {boss.current_phase} | "
                      f"Hero dmg: {r.hero_damage_taken:>3}{marker}")

    print()
    if result.victory:
        print("  >>> VICTORY! Baron Midas has been defeated! <<<")
    else:
        print("  >>> DEFEAT! The guild has fallen... <<<")

    print()
    print(f"  Combat: {len(result.rounds)} rounds | "
          f"Total hero damage: {result.total_hero_damage_taken}")
    print(f"  Boss final: HP {boss.current_health}/{boss.max_health} | "
          f"Phase {boss.current_phase} | "
          f"{boss.effective_dice_count}d{boss.effective_dice_sides} | "
          f"Advantage: {boss.has_permanent_advantage}")
    print()
    print("  POST-FIGHT:")
    for h in heroes:
        alive = "ALIVE" if h.current_health > 0 else "DEAD"
        print(f"    {h.name:22s} | {alive:5s} | HP {h.current_health:>3}/{h.max_health:<3}")
    print("=" * 65)

    return result


def main():
    args = _parse_args()
    random.seed(args.seed)

    # Determine party composition
    if args.party:
        archetypes = [a.strip() for a in args.party.split(",")]
    else:
        archetypes = ["barbarian", "cleric", "rogue", "mage"]

    available = list_archetypes()
    for a in archetypes:
        if a not in available:
            print(f"Error: archetype '{a}' not found. Available: {available}")
            sys.exit(1)

    # ── Setup ───────────────────────────────────────────────────────
    loop = GameLoop.create(starting_gold=args.gold)
    eb = loop._event_bus
    ow = loop._overworld
    econ = loop._economy

    # Set heal percent on the quest executor
    loop._quest_executor.heal_percent = args.heal

    print("=" * 65)
    print("           GUILDMASTER — ACT 1 SIMULATION")
    print("=" * 65)
    print(f"  Seed: {args.seed} | Gold: {args.gold} | "
          f"Heal: {int(args.heal * 100)}% | Ticks: {args.ticks}")
    print(f"  Boss gold stolen: {args.gold_stolen} "
          f"(Boss HP will be {100 + min(args.gold_stolen, 566)})")
    print()

    # ── Recruit ─────────────────────────────────────────────────────
    heroes = _recruit_party(econ, archetypes)
    print("  PARTY:")
    for h in heroes:
        skills = [s.name if s else "-" for s in h.skills]
        print(f"    {h.name:22s} | {h.archetype:10s} | "
              f"HP {h.current_health:>2}/{h.max_health:<2} | "
              f"STR:{h.strength} DEX:{h.dexterity} INT:{h.intelligence} "
              f"CON:{h.constitution}")
        print(f"      Skills: {skills}")
    print()
    print("-" * 65)

    # ── Event tracking ──────────────────────────────────────────────
    quest_log = []
    quest_errors = []
    eb.subscribe("quest.executed", lambda d: quest_log.append(d))
    eb.subscribe("quest.error", lambda d: quest_errors.append(d))

    boss_appeared = [False]
    boss_defeated = [False]

    def _on_boss_appeared(data):
        boss_appeared[0] = True
    eb.subscribe("boss.appeared", _on_boss_appeared)

    # ── Main loop ───────────────────────────────────────────────────
    quest_count = 0
    boss_fight_done = False
    attempted_quests = set()

    for tick in range(1, args.ticks + 1):
        loop.tick()
        map_state = ow.map_state

        # Auto-assign idle heroes to available quests
        idle = [h for h in heroes
                if h.status == HeroStatus.IDLE and h.current_health > 0]

        for quest_id, quest in list(map_state.active_quests.items()):
            if quest_id in attempted_quests:
                continue
            if quest.status.value != "available" or not idle:
                continue
            if len(idle) < quest.required_heroes:
                continue  # Not enough idle heroes to meet minimum requirement

            send_count = min(quest.max_heroes, len(idle))
            sent = idle[:send_count]
            hero_ids_str = " ".join(h.hero_id for h in sent)

            attempted_quests.add(quest_id)
            prev_count = len(quest_log)
            loop.handle_input(f"assign {quest_id} {hero_ids_str}")

            # Check if a quest was executed
            if len(quest_log) > prev_count:
                quest_count += 1
                result = quest_log[-1]
                names = ", ".join(h.name for h in sent)
                outcome = "VICTORY" if result["victory"] else "DEFEAT"
                gold_str = ""
                if result["victory"]:
                    gold_str = f" | +{result['gold_earned']}g (Total: {econ.ledger.balance}g)"

                print(f"\n  Quest #{quest_count} [Tick {tick}] "
                      f"\"{quest.title}\" ({quest.difficulty.value}, "
                      f"{quest.quest_type.value})")
                print(f"    Party: {names}")
                print(f"    >> {outcome}{gold_str}")

                for h in sent:
                    print(f"      {h.name:22s} | HP {h.current_health:>3}/{h.max_health:<3} | "
                          f"Exhaust: {h.exhaustion:.0f} | "
                          f"XP: {h.xp} | Lvl: {h.level}")

            idle = [h for h in heroes
                    if h.status == HeroStatus.IDLE and h.current_health > 0]

        # Boss fight trigger: when boss is revealed and we have idle heroes
        if (map_state.boss and map_state.boss.revealed
                and not boss_fight_done):
            living = [h for h in heroes if h.current_health > 0]
            if living:
                # Reset all living heroes to IDLE for the boss fight
                for h in living:
                    if h.status != HeroStatus.IDLE:
                        h.status = HeroStatus.IDLE

                boss_result = _run_boss_fight(
                    heroes=living,
                    gold_stolen=args.gold_stolen,
                    eb=eb,
                    boss_buffs=list(map_state.boss.buffs),
                    verbose=args.verbose,
                )
                boss_fight_done = True
                boss_defeated[0] = boss_result.victory

                if boss_result.victory:
                    map_state.boss.defeated = True
                    # Heal survivors after boss fight
                    for h in heroes:
                        if h.current_health > 0:
                            h.status = HeroStatus.IDLE
                            h.current_health = min(
                                h.max_health,
                                h.current_health + int(h.max_health * args.heal),
                            )
                            h.status_effects.clear()
                            h.temp_hp = 0
                else:
                    break  # Game over

        # Status report every 200 ticks
        if tick % 200 == 0:
            print(f"\n  --- Status at Tick {tick} ---")
            print(f"  Gold: {econ.ledger.balance} | "
                  f"Quests: {len(quest_log)} | "
                  f"Errors: {len(quest_errors)}")
            for h in heroes:
                alive = "OK" if h.current_health > 0 else "DEAD"
                print(f"    {h.name:22s} | {alive:4s} | "
                      f"HP {h.current_health:>3}/{h.max_health:<3} | "
                      f"Lvl {h.level} | XP {h.xp:>4} | "
                      f"Exhaust: {h.exhaustion:.0f}")
            boss = map_state.boss
            if boss:
                status = ("Defeated" if boss.defeated else
                          "Revealed" if boss.revealed else
                          "Hidden")
                print(f"  Boss: {boss.boss_id} | {status} | "
                      f"Buffs: {len(boss.buffs)}")

    # ── Final Summary ───────────────────────────────────────────────
    victories = sum(1 for r in quest_log if r["victory"])
    defeats = sum(1 for r in quest_log if not r["victory"])
    map_state = ow.map_state

    print()
    print("=" * 65)
    print("              ACT 1 — FINAL REPORT")
    print("=" * 65)
    print(f"  Ticks Simulated: {min(tick, args.ticks)}")
    print(f"  Quests: {len(quest_log)} total | "
          f"{victories} victories | {defeats} defeats")
    if quest_errors:
        print(f"  Quest Errors: {len(quest_errors)}")
    print(f"  Gold: {args.gold} -> {econ.ledger.balance} "
          f"(+{econ.ledger.balance - args.gold})")
    print()

    print("  FINAL ROSTER:")
    for h in heroes:
        alive = "ALIVE" if h.current_health > 0 else "DEAD"
        print(f"    {h.name:22s} | {h.archetype:10s} | {alive:5s} | "
              f"HP {h.current_health:>3}/{h.max_health:<3} | "
              f"Lvl {h.level} | XP {h.xp:>4} | "
              f"Exhaust: {h.exhaustion:.0f}")

    print()
    boss = map_state.boss
    if boss:
        status = ("DEFEATED" if boss.defeated else
                  "UNDEFEATED" if boss.revealed else
                  "NEVER APPEARED")
        print(f"  BOSS: Baron Midas | {status}")
        if boss.buffs:
            print(f"  Boss Buffs: {boss.buffs}")

    print()
    if boss and boss.defeated:
        print("  *** ACT 1 COMPLETE — THE GUILD IS VICTORIOUS! ***")
    elif boss_fight_done and not boss_defeated[0]:
        print("  *** GAME OVER — THE GUILD HAS FALLEN ***")
    else:
        print("  *** ACT 1 INCOMPLETE — Boss not yet fought ***")

    print("=" * 65)


if __name__ == "__main__":
    main()
