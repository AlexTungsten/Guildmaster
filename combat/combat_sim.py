"""
combat_sim.py — Standalone combat simulator for Guildmaster.

Run as:  python -m combat.combat_sim [options]

Examples
--------
  # Barbarian vs goblins
  python -m combat.combat_sim --heroes barbarian --enemies goblin goblin

  # Two heroes vs Baron Midas with 200 gold stolen, seeded
  python -m combat.combat_sim --heroes barbarian cleric --boss baron_midas --gold-stolen 200 --seed 42

  # Set starting conditions + verbose skill output
  python -m combat.combat_sim --heroes barbarian rogue --enemies bandit ogre --hero-hp 15 20 --verbose
"""

import argparse
import os
import sys

# Allow running from project root via python -m combat.combat_sim
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from game_runtime.event_bus import EventBus
from hero.archetype_loader import load_archetype, list_archetypes
from enemy.enemy_loader import load_enemy, list_enemies
from enemy.boss_loader import load_boss, load_kobold_king_encounter, list_bosses
from enemy.boss_enemy import BossEnemy
from enemy.special_enemies import KoboldKingEnemy, MechEnemy, CursedKnightBossEnemy
from combat.combat_engine import CombatEngine, CombatRound


# ---------------------------------------------------------------------------
# Display helpers
# ---------------------------------------------------------------------------

BAR_WIDTH = 20
FULL  = "#"
EMPTY = "."


def _hp_bar(current: int, maximum: int, width: int = BAR_WIDTH) -> str:
    if maximum <= 0:
        return f"[{'?' * width}] {current}/{maximum}"
    ratio = max(0.0, min(1.0, current / maximum))
    filled = round(ratio * width)
    return f"[{FULL * filled}{EMPTY * (width - filled)}] {current}/{maximum}"


def _skill_summary(results) -> str:
    """'SkillA (5), SkillB (3)' — only skills that actually did something."""
    parts = []
    for r in results:
        if r.effectiveness > 0 or r.hit_count > 0:
            if r.hit_count > 1:
                eff_str = f"{r.hit_count}x{r.per_hit_damage}"
            else:
                eff_str = str(r.effectiveness)
            parts.append(f"{r.skill.name} ({eff_str})")
    return ", ".join(parts) if parts else "(none)"


def _phase_transition_in(cr: CombatRound) -> bool:
    """Return True if a phase_advance skill fired this round."""
    return any(
        getattr(r.skill, "special", None) == "phase_advance"
        for r in cr.enemy_results
    )


def _print_round(
    cr: CombatRound,
    heroes: list,
    enemies_final: list,   # full enemy list including all spawns, in append order
    verbose: bool,
    phase_tracker: list,   # [current_phase] mutable so we can update it
) -> None:
    print(f"\n{'-' * 52}")
    print(f"  Round {cr.round_number}")
    print(f"{'-' * 52}")

    # Heroes
    for hero in heroes:
        hp = cr.hero_hp_after.get(hero.hero_id, hero.current_health)
        bar = _hp_bar(max(0, hp), hero.max_health)
        dead = "  [DEAD]" if hp <= 0 else ""
        print(f"  {hero.name:<18} {bar}{dead}")

    print()

    # Enemies visible this round = enemies_final[:len(enemy_hp_after)]
    # because enemies are only ever appended, the first N entries always correspond
    # to the N entries captured in enemy_hp_after for this round.
    round_enemies = enemies_final[: len(cr.enemy_hp_after)]
    for i, enemy in enumerate(round_enemies):
        hp = cr.enemy_hp_after[i]
        bar = _hp_bar(max(0, hp), enemy.max_health)
        dead = "  [DEAD]" if hp <= 0 else ""
        spawn_tag = "  [spawn]" if enemy.owner_ref is not None else ""

        if isinstance(enemy, MechEnemy) and enemy.hidden:
            # Show hidden Mech with buffed stats so we can watch it grow
            print(f"  {enemy.name:<18} {bar}  [HIDDEN] (3d{enemy.base_dice_sides} {enemy.base_dice_count} dice)")
        elif isinstance(enemy, KoboldKingEnemy):
            tag = "  [UNTARGETABLE]" if hp > 0 else dead
            print(f"  {enemy.name:<18} {bar}{tag}")
        elif isinstance(enemy, CursedKnightBossEnemy):
            # transformed is sticky so showing it from final state is always accurate;
            # bloodlust is not tracked per-round so we omit it here (shown in summary)
            form = "  [WEREWOLF FORM]" if enemy.transformed else ""
            print(f"  {enemy.name:<18} {bar}{dead}{form}")
        elif isinstance(enemy, BossEnemy):
            phase_info = f"  [Phase {phase_tracker[0]}]"
            print(f"  {enemy.name:<18} {bar}{dead}{phase_info}")
        else:
            print(f"  {enemy.name:<18} {bar}{dead}{spawn_tag}")

    # Boss phase transition happened this round?
    if _phase_transition_in(cr):
        old_phase = phase_tracker[0]
        phase_tracker[0] += 1
        new_phase = phase_tracker[0]
        print(f"\n  *** PHASE TRANSITION: Phase {old_phase} -> Phase {new_phase} ***")

    # Verbose: skills + damage totals
    if verbose:
        print(f"\n  Heroes  -> {_skill_summary(cr.hero_results)}")
        print(f"  Enemies -> {_skill_summary(cr.enemy_results)}")
        print(f"  Dmg dealt: {cr.enemy_damage_dealt}  |  Dmg taken: {cr.hero_damage_taken}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    archetypes = list_archetypes()
    enemy_ids  = list_enemies()
    boss_ids   = list_bosses()

    parser = argparse.ArgumentParser(
        prog="combat_sim",
        description="Guildmaster combat simulator — test hero/enemy matchups directly",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Available archetypes: " + ", ".join(sorted(archetypes)) + "\n"
            "Available enemies:    " + ", ".join(sorted(enemy_ids)) + "\n"
            "Available bosses:     " + ", ".join(sorted(boss_ids))
        ),
    )

    # Party
    parser.add_argument(
        "--heroes", nargs="+", default=["barbarian"], metavar="ARCHETYPE",
        help="Hero archetypes (default: barbarian)",
    )

    # Opponents — enemies and boss are mutually exclusive
    opp = parser.add_mutually_exclusive_group()
    opp.add_argument(
        "--enemies", nargs="+", metavar="ENEMY_ID",
        help="Enemy IDs to fight (default: goblin)",
    )
    opp.add_argument(
        "--boss", metavar="BOSS_ID",
        help="Boss to fight instead of regular enemies",
    )

    # General
    parser.add_argument("--seed",   type=int,   default=None, help="RNG seed for reproducibility")
    parser.add_argument("--act",    type=int,   default=1,    help="Act number for enemy HP scaling (default: 1)")
    parser.add_argument("--rounds", type=int,   default=50,   help="Max combat rounds (default: 50)")
    parser.add_argument("--verbose", action="store_true",     help="Show per-round skill activations")

    # Starting conditions — heroes
    parser.add_argument(
        "--hero-hp", nargs="+", type=int, metavar="HP",
        help="Override starting HP per hero (positional, matches hero order)",
    )
    parser.add_argument(
        "--hero-exhaustion", nargs="+", type=float, metavar="EXH",
        help="Override starting exhaustion per hero",
    )

    # Boss gimmick controls
    parser.add_argument(
        "--gold-stolen", type=int, default=0, metavar="GOLD",
        help="Gold stolen during the act — Baron Midas gains 1 HP per gold (default: 0)",
    )
    parser.add_argument(
        "--bloodlust", type=int, default=0, metavar="STACKS",
        help="Cursed Knight starting bloodlust stacks (default: 0)",
    )
    parser.add_argument(
        "--critical-quests", type=int, default=0, metavar="N",
        help="Critical quests completed — Kobold King scaling (default: 0)",
    )

    args = parser.parse_args()

    # ── Load heroes ─────────────────────────────────────────────────────────
    heroes = []
    for i, arch in enumerate(args.heroes):
        try:
            h = load_archetype(arch, hero_id=f"h_{i}", name=arch.capitalize())
        except FileNotFoundError:
            print(f"Error: archetype '{arch}' not found.")
            print(f"Available: {', '.join(sorted(archetypes))}")
            sys.exit(1)
        heroes.append(h)

    # Apply HP / exhaustion overrides
    if args.hero_hp:
        for i, hp_val in enumerate(args.hero_hp):
            if i < len(heroes):
                heroes[i].current_health = min(hp_val, heroes[i].max_health)

    if args.hero_exhaustion:
        for i, exh_val in enumerate(args.hero_exhaustion):
            if i < len(heroes):
                heroes[i].exhaustion = exh_val

    # ── Load opponents ──────────────────────────────────────────────────────
    boss_obj = None
    kobold_king_encounter = False
    if args.boss:
        try:
            if args.boss == "kobold_king":
                enemies = load_kobold_king_encounter(args.critical_quests)
                boss_obj = None
                kobold_king_encounter = True
            else:
                boss_obj = load_boss(
                    args.boss,
                    gold_stolen=args.gold_stolen,
                    damage_dealt=args.bloodlust,  # --bloodlust doubles as damage_dealt for cursed_knight
                )
                enemies = [boss_obj]
        except FileNotFoundError:
            print(f"Error: boss '{args.boss}' not found.")
            print(f"Available: {', '.join(sorted(boss_ids))}")
            sys.exit(1)
    else:
        chosen_ids = args.enemies or ["goblin"]
        enemies = []
        for eid in chosen_ids:
            try:
                enemies.append(load_enemy(eid, args.act))
            except FileNotFoundError:
                print(f"Error: enemy '{eid}' not found.")
                print(f"Available: {', '.join(sorted(enemy_ids))}")
                sys.exit(1)

    # ── Print setup header ──────────────────────────────────────────────────
    print("=" * 52)
    print("  GUILDMASTER COMBAT SIMULATOR")
    print("=" * 52)
    seed_str = str(args.seed) if args.seed is not None else "random"
    print(f"  Seed: {seed_str}  |  Max rounds: {args.rounds}")
    print()

    print("  Party:")
    for h in heroes:
        print(f"    {h.name:<16} ({h.archetype})  HP {h.current_health}/{h.max_health}")

    print()
    print("  Enemies:")
    for e in enemies:
        if isinstance(e, KoboldKingEnemy):
            cq = args.critical_quests
            print(f"    {e.name:<16} ({e.archetype})  [UNTARGETABLE]  CQ={cq}")
        elif isinstance(e, MechEnemy):
            print(f"    {e.name:<16} ({e.archetype})  HP {e.current_health}/{e.max_health}  [HIDDEN]")
        elif isinstance(e, BossEnemy):
            phase_str = f"  [Phase {e.current_phase}]"
            print(f"    {e.name:<16} ({e.archetype})  HP {e.current_health}/{e.max_health}{phase_str}")
        else:
            print(f"    {e.name:<16} ({e.archetype})  HP {e.current_health}/{e.max_health}")

    if boss_obj and args.gold_stolen:
        bonus = boss_obj.gold_stolen  # already capped by loader
        print(f"    Gold stolen: {args.gold_stolen} -> +{bonus} HP applied")

    # Gimmick state echo
    extra = []
    if args.bloodlust:
        extra.append(f"bloodlust stacks: {args.bloodlust}")
    if args.critical_quests:
        extra.append(f"critical quests: {args.critical_quests}")
    if extra:
        print()
        print("  Boss gimmick state: " + "  |  ".join(extra))

    print()

    # ── Run combat ──────────────────────────────────────────────────────────
    event_bus = EventBus()
    engine    = CombatEngine(event_bus)
    result    = engine._run(
        heroes,
        enemies,
        max_rounds=args.rounds,
        publish_events=False,
        seed=args.seed,
    )

    # ── Display rounds ──────────────────────────────────────────────────────
    if isinstance(boss_obj, BossEnemy):
        phase_tracker = [1]
    else:
        phase_tracker = [0]

    enemies_final = result.enemies_final  # includes all spawned entities

    for cr in result.rounds:
        _print_round(cr, heroes, enemies_final, args.verbose, phase_tracker)

    # ── Summary ─────────────────────────────────────────────────────────────
    print(f"\n{'=' * 52}")
    outcome = "VICTORY" if result.victory else "DEFEAT"
    print(f"  {outcome}  --  {len(result.rounds)} round(s)")
    print(f"{'=' * 52}")

    total_dealt = sum(r.enemy_damage_dealt for r in result.rounds)
    print(f"  Total damage dealt:  {total_dealt}")
    print(f"  Total damage taken:  {result.total_hero_damage_taken}")
    print()

    print("  Final hero status:")
    for hero in heroes:
        hp = (
            result.rounds[-1].hero_hp_after.get(hero.hero_id, hero.current_health)
            if result.rounds else hero.current_health
        )
        status = "ALIVE" if hp > 0 else "DEAD"
        print(f"    {hero.name:<16} {hp}/{hero.max_health} HP  [{status}]")

    if kobold_king_encounter and result.rounds:
        mech = next((e for e in enemies_final if isinstance(e, MechEnemy)), None)
        if mech:
            mech_idx = enemies_final.index(mech)
            last_hp = next(
                (cr.enemy_hp_after[mech_idx] for cr in reversed(result.rounds)
                 if mech_idx < len(cr.enemy_hp_after)),
                mech.current_health,
            )
            print()
            print(f"  The Mech: {max(0, last_hp)}/{mech.max_health} HP"
                  f"  [{mech.base_dice_count}d{mech.base_dice_sides}]")
    elif boss_obj and result.rounds:
        final_hp = result.rounds[-1].enemy_hp_after[0] if result.rounds[-1].enemy_hp_after else boss_obj.current_health
        print()
        print(f"  {boss_obj.name}:")
        print(f"    HP remaining: {max(0, final_hp)}/{boss_obj.max_health}")
        if isinstance(boss_obj, BossEnemy):
            print(f"    Final phase:  {phase_tracker[0]}")
        elif isinstance(boss_obj, CursedKnightBossEnemy):
            form = "Werewolf" if boss_obj.transformed else "Knight"
            print(f"    Form:         {form}  (Bloodlust {boss_obj.bloodlust_current})")

    # Show any spawned entities in the final summary
    spawned = [e for e in enemies_final if e.owner_ref is not None]
    if spawned:
        print()
        print("  Spawned entities:")
        for e in spawned:
            last_hp = next(
                (cr.enemy_hp_after[enemies_final.index(e)]
                 for cr in reversed(result.rounds)
                 if enemies_final.index(e) < len(cr.enemy_hp_after)),
                e.current_health,
            )
            status = "ALIVE" if last_hp > 0 else "DEAD"
            print(f"    {e.name:<16} (owned by {e.owner_ref.name})  [{status}]")

    print()


if __name__ == "__main__":
    main()
