"""
combat_renderer.py — Pure text renderers for the combat screen.

Provides helpers for rendering HP bars, dice pool displays, skill
assignment tables, and the full combat view that the game loop displays
each round.

All functions accept plain dicts so they can be tested independently of
the combat domain objects.
"""

from typing import Dict, List, Optional


def render_hp_bar(current: int, maximum: int, width: int = 20) -> str:
    """
    Render a fixed-width ASCII HP bar.

    '#' characters = remaining HP; '.' characters = lost HP.
    Example: "[##########..........] 10/20"
    """
    if maximum <= 0:
        filled = 0   # Avoid division by zero; show empty bar
    else:
        filled = int(width * current / maximum)
    filled = max(0, min(width, filled))   # Clamp to valid range
    empty = width - filled
    bar = "#" * filled + "." * empty
    return f"[{bar}] {current}/{maximum}"


def render_dice_pool(locked_dice: List[int], normal_dice: List[int]) -> str:
    """
    Render a summary of one combat turn's rolled dice pool.

    Shows locked (d4) results and normal (d10) results separately so the
    player can see the exhaustion impact at a glance.
    """
    locked_str = ", ".join(str(d) for d in locked_dice) if locked_dice else ""
    normal_str = ", ".join(str(d) for d in normal_dice) if normal_dice else ""
    return f"Dice Pool: [LOCKED: {locked_str}] [Normal: {normal_str}]"


def render_skill_assignments(assignments: List[Dict]) -> str:
    """
    Render a table of skill-to-dice assignments for one hero's turn.

    Each row shows: skill name, number of dice slots, the actual dice
    assigned, and the total effectiveness before the stat modifier.
    """
    lines = []
    for assignment in assignments:
        skill_name = assignment.get("skill_name", "Unknown")
        dice_slots = assignment.get("dice_slots", 0)
        assigned_dice = assignment.get("assigned_dice", [])
        effectiveness = assignment.get("effectiveness", 0)
        lines.append(
            f"{skill_name} ({dice_slots} slots): Dice={assigned_dice}"
            f" -> Effectiveness={effectiveness}"
        )
    return "\n".join(lines)


def render_combat_view(
    heroes: List[Dict],
    enemies: List[Dict],
    round_number: int,
    pre_sim_result: Optional[Dict] = None,
    intervention_seconds_remaining: Optional[int] = None,
) -> str:
    """
    Render the full combat screen for one round.

    Shows HP bars for all heroes and enemies, the pre-simulation projection
    if available, and the intervention countdown when the player has a
    window to take manual control.

    Parameters
    ----------
    heroes                       : Hero dicts with HP and exhaustion fields.
    enemies                      : Enemy dicts with HP fields.
    round_number                 : Current combat round (1-based).
    pre_sim_result               : Optional dict with "victory" (bool) and
                                   "rounds" (list) from the pre-simulation.
    intervention_seconds_remaining : Seconds left in the manual-takeover window;
                                    None means autoplay is permanently active.
    """
    lines = []
    lines.append(f"=== COMBAT - Round {round_number} ===")
    lines.append("")

    lines.append("HEROES:")
    for hero in heroes:
        name = hero.get("name", "Unknown")
        current_hp = hero.get("current_health", 0)
        max_hp = hero.get("max_health", 0)
        exhaustion = hero.get("exhaustion", 0.0)
        hp_bar = render_hp_bar(current_hp, max_hp)
        lines.append(f"  {name}: {hp_bar} | Exhaustion: {exhaustion:.0f}")
    lines.append("")

    lines.append("ENEMIES:")
    for enemy in enemies:
        name = enemy.get("name", "Unknown")
        # Support both "current_health"/"max_health" and shorter "hp"/"max_hp" key names
        current_hp = enemy.get("current_health", enemy.get("hp", 0))
        max_hp = enemy.get("max_health", enemy.get("max_hp", 0))
        hp_bar = render_hp_bar(current_hp, max_hp)
        lines.append(f"  {name}: {hp_bar}")
    lines.append("")

    if pre_sim_result is not None:
        # Show the projected outcome from the pre-simulation dry run
        victory = pre_sim_result.get("victory", False)
        rounds = pre_sim_result.get("rounds", [])
        outcome = "VICTORY" if victory else "DEFEAT"
        lines.append(
            f"PRE-SIMULATION: {outcome} projected in {len(rounds)} rounds"
        )
        lines.append("")

    if intervention_seconds_remaining is not None:
        # Player has a limited window to override autoplay
        lines.append(
            f">>> Intervene manually? {intervention_seconds_remaining}s remaining."
            f" Type 'manual' to take control. <<<"
        )
        lines.append("")

    # Footer: show whether the player is in auto or manual control
    # manual_control is True when there is no intervention window (pure autoplay)
    manual_control = intervention_seconds_remaining is None or intervention_seconds_remaining <= 0
    if manual_control and intervention_seconds_remaining is None:
        lines.append("[auto] Autoplay active")
    else:
        lines.append("[manual] You have control")

    return "\n".join(lines)
