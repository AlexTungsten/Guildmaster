"""
map_renderer.py — Pure text renderers for the overworld map screen.

render_map_screen() produces the main game HUD: active quests, open shops,
boss status, hero statuses, and the command reference.

render_boss_timer_bar() renders a progress bar showing how much of the boss
countdown has elapsed, useful as a compact inset within the map screen.

Both functions are pure (no side effects) and accept plain dicts so they can
be tested without any game state dependencies.
"""

from typing import Dict, List, Optional


def render_map_screen(
    active_quests: List[Dict],
    active_shops: List[Dict],
    boss: Optional[Dict],
    current_tick: int,
    act: int,
    boss_ticks_remaining: int,
    hero_statuses: List[Dict],
) -> str:
    """
    Render the full overworld map as a multi-line text string.

    Parameters
    ----------
    active_quests        : List of quest dicts; each should have "quest_id",
                           "title", "difficulty", "expiry", "status", and
                           "assigned_hero_ids".
    active_shops         : List of shop dicts with "shop_id" and "expiry".
    boss                 : Optional boss dict with "boss_id", "act", "revealed",
                           "defeated", and "buffs"; None if no boss this act.
    current_tick         : The current simulation tick for the header display.
    act                  : Current act number (1–3).
    boss_ticks_remaining : How many ticks until the boss is revealed.
    hero_statuses        : List of hero dicts for the HEROES section.
    """
    lines = []
    lines.append(
        f"=== MAP - ACT {act} | Tick: {current_tick} | Boss in: {boss_ticks_remaining} ticks ==="
    )
    lines.append("")

    lines.append(f"ACTIVE QUESTS ({len(active_quests)}):")
    for quest in active_quests:
        quest_id = quest.get("quest_id", "?")
        title = quest.get("title", "Untitled")
        difficulty = quest.get("difficulty", "?")
        # expiry may be pre-computed ticks remaining or the raw expiration_tick
        expiry = quest.get("expiry", quest.get("expiration_tick", "?"))
        status = quest.get("status", "unknown")
        assigned = quest.get("assigned_hero_ids", [])
        lines.append(
            f"  [{quest_id}] {title} | {difficulty} | Expires in: {expiry} ticks"
            f" | Status: {status} | Heroes: {assigned}"
        )
    lines.append("")

    lines.append(f"SHOPS ({len(active_shops)}):")
    for shop in active_shops:
        shop_id = shop.get("shop_id", "?")
        expiry = shop.get("expiry", shop.get("expiration_tick", "?"))
        lines.append(f"  [{shop_id}] Shop | Expires in: {expiry} ticks")
    lines.append("")

    lines.append("BOSS:")
    if boss is not None and boss.get("revealed", False):
        # Boss is on the map — show its identity and accumulated buffs
        boss_id = boss.get("boss_id", "?")
        boss_act = boss.get("act", act)
        buffs = boss.get("buffs", [])
        lines.append(f"  {boss_id} (Act {boss_act}) | Buffs: {buffs}")
    else:
        lines.append("  Not yet revealed")
    lines.append("")

    lines.append("HEROES:")
    for hero in hero_statuses:
        name = hero.get("name", "Unknown")
        status = hero.get("status", "unknown")
        exhaustion = hero.get("exhaustion", 0.0)
        lines.append(f"  {name} | {status} | Exhaustion: {exhaustion:.0f}")
    lines.append("")

    lines.append(
        "Commands: [assign <quest_id> <hero_ids...>] [shop <shop_id>]"
        " [heroes] [items] [pause] [quit]"
    )
    return "\n".join(lines)


def render_boss_timer_bar(
    ticks_remaining: int, total_ticks: int, width: int = 40
) -> str:
    """
    Render an ASCII progress bar representing boss countdown progress.

    The bar fills from left to right as ticks elapse.
    '#' characters = elapsed time; '.' characters = remaining time.

    Parameters
    ----------
    ticks_remaining : Ticks left until the boss appears.
    total_ticks     : Full duration of the boss countdown for this act.
    width           : Character width of the bar (default 40).
    """
    if total_ticks <= 0:
        filled = width   # Degenerate case: treat as fully elapsed
    else:
        # filled = proportion elapsed × width
        filled = int(width * (total_ticks - ticks_remaining) / total_ticks)
    filled = max(0, min(width, filled))   # Clamp to [0, width]
    empty = width - filled
    bar = "#" * filled + "." * empty
    return f"[{bar}] {ticks_remaining}/{total_ticks} ticks"
