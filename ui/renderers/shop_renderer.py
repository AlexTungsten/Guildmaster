"""
shop_renderer.py — Pure text renderer for the merchant shop screen.

render_shop_screen() displays all available merchandise in three sections
(heroes for hire, items, and training courses) along with current gold and
the available purchase commands.

render_gold_bar() is a minimal helper for embedding the balance in other
screens (e.g. the map header).

Both functions accept plain dicts and ints so they can be tested without
any economy domain object dependencies.
"""

from typing import Dict, List


def render_gold_bar(gold: int) -> str:
    """Return a short formatted string showing the current gold balance."""
    return f"Gold: {gold}g"


def render_shop_screen(shop: Dict, gold: int) -> str:
    """
    Render the full shop screen as a multi-line text string.

    Parameters
    ----------
    shop : A dict describing the shop; expected keys:
             "shop_id"         : str
             "heroes_for_hire" : list of hero dicts (name, archetype, cost, sold)
             "items"           : list of item dicts (name, category, cost, sold)
             "training"        : list of training dicts (skill_name/name, stat, cost, sold)
    gold : The guild's current gold balance.
    """
    lines = []
    shop_id = shop.get("shop_id", "?")
    lines.append(f"=== SHOP [{shop_id}] | Gold: {gold}g ===")
    lines.append("")

    # --- Heroes for hire ---
    heroes_for_hire = shop.get("heroes_for_hire", [])
    lines.append("HEROES FOR HIRE:")
    for i, hero in enumerate(heroes_for_hire, start=1):
        name = hero.get("name", "Unknown")
        archetype = hero.get("archetype", "Unknown")
        cost = hero.get("cost", 0)
        sold = hero.get("sold", False)
        sold_str = " [SOLD]" if sold else ""
        lines.append(f"  {i}. {name} ({archetype}) — {cost}g{sold_str}")
    lines.append("")

    # --- Equipment and consumables ---
    items = shop.get("items", [])
    lines.append("ITEMS:")
    for i, item in enumerate(items, start=1):
        name = item.get("name", "Unknown")
        category = item.get("category", "misc")
        cost = item.get("cost", 0)
        sold = item.get("sold", False)
        sold_str = " [SOLD]" if sold else ""
        lines.append(f"  {i}. {name} ({category}) — {cost}g{sold_str}")
    lines.append("")

    # --- Skill training courses ---
    training = shop.get("training", [])
    lines.append("TRAINING:")
    for i, course in enumerate(training, start=1):
        # Support both "skill_name" (preferred) and "name" fallback keys
        name = course.get("skill_name", course.get("name", "Unknown"))
        stat = course.get("stat", "?")
        cost = course.get("cost", 0)
        sold = course.get("sold", False)
        sold_str = " [SOLD]" if sold else ""
        lines.append(f"  {i}. {name} ({stat}) — {cost}g{sold_str}")
    lines.append("")

    lines.append(
        "Commands: [hire <hero_id>] [buy <item_id>]"
        " [train <skill_id> <hero_id> <slot>] [leave]"
    )
    return "\n".join(lines)
