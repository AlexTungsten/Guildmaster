"""
map_renderer.py — Pure text renderers for the overworld map screen.

render_map_screen() produces the main game HUD split into:
  - QUEST LIST: available quests not yet taken (can be assigned)
  - ACTIVE QUESTS: quests heroes are currently on
  - Hero status section showing idle vs on-quest heroes clearly

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

    Quests are split into two sections:
      QUEST LIST    — status == "available", heroes not yet assigned
      ACTIVE QUESTS — status is traveling / resolving / in_combat
    """
    lines = []
    lines.append(
        f"=== MAP - ACT {act} | Tick: {current_tick} | Boss in: {boss_ticks_remaining} ticks ==="
    )
    lines.append("")

    # Split quests into available (list) vs in-progress (active)
    available_quests = [q for q in active_quests if q.get("status") == "available"]
    in_progress_quests = [q for q in active_quests if q.get("status") != "available"]

    lines.append(f"QUEST LIST ({len(available_quests)}):")
    if available_quests:
        for quest in available_quests:
            quest_id = quest.get("quest_id", "?")
            title = quest.get("title", "Untitled")
            difficulty = quest.get("difficulty", "?")
            expiry = quest.get("expiry", quest.get("expiration_tick", "?"))
            req = quest.get("required_heroes", 1)
            lines.append(
                f"  [{quest_id}] {title} | {difficulty} | Expires in: {expiry} ticks | Need: {req} hero(es)"
            )
    else:
        lines.append("  No quests available")
    lines.append("")

    lines.append(f"ACTIVE QUESTS ({len(in_progress_quests)}):")
    if in_progress_quests:
        for quest in in_progress_quests:
            quest_id = quest.get("quest_id", "?")
            title = quest.get("title", "Untitled")
            difficulty = quest.get("difficulty", "?")
            status = quest.get("status", "unknown")
            assigned = quest.get("assigned_hero_ids", [])
            lines.append(
                f"  [{quest_id}] {title} | {difficulty} | {status.upper()} | Heroes: {assigned}"
            )
    else:
        lines.append("  No quests in progress")
    lines.append("")

    lines.append(f"SHOPS ({len(active_shops)}):")
    for shop in active_shops:
        shop_id = shop.get("shop_id", "?")
        expiry = shop.get("expiry", shop.get("expiration_tick", "?"))
        lines.append(f"  [{shop_id}] Shop | Expires in: {expiry} ticks")
    lines.append("")

    lines.append("BOSS:")
    if boss is not None and boss.get("revealed", False):
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
        if status == "idle":
            status_str = "IDLE"
        else:
            status_str = f"ON QUEST [{status.upper()}]"
        lines.append(f"  {name} | {status_str} | Exhaustion: {exhaustion:.0f}")
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
    """
    if total_ticks <= 0:
        filled = width
    else:
        filled = int(width * (total_ticks - ticks_remaining) / total_ticks)
    filled = max(0, min(width, filled))
    empty = width - filled
    bar = "#" * filled + "." * empty
    return f"[{bar}] {ticks_remaining}/{total_ticks} ticks"
