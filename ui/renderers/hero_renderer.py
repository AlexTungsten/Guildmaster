"""
hero_renderer.py — Pure text renderers for hero roster and detail views.

render_hero_panel() displays a compact multi-hero summary (one row per hero).
render_hero_detail() displays a full single-hero stat sheet with all skills,
items, stats, and exhaustion breakdown.

Both functions accept plain dicts so they can be tested without importing
hero domain objects.
"""

from typing import Dict, List


def exhaustion_label(exhaustion: float) -> str:
    """Convert a raw exhaustion float to a human-readable severity label."""
    if exhaustion >= 100:
        return "Critical"
    elif exhaustion >= 60:
        return "Drained"
    elif exhaustion >= 40:
        return "Weary"
    elif exhaustion >= 20:
        return "Tired"
    else:
        return "Rested"


def render_hero_panel(heroes: List[Dict]) -> str:
    """
    Render a compact roster overview showing one summarized line per hero.

    Each hero block shows: name, archetype, level, XP, HP, exhaustion,
    status, behavior profile, base stats, and equipped skills.
    Heroes are separated by a dashed rule.
    """
    lines = []
    lines.append("=== HEROES ===")
    for i, hero in enumerate(heroes):
        if i > 0:
            lines.append("-" * 40)   # Visual separator between heroes
        name = hero.get("name", "Unknown")
        archetype = hero.get("archetype", "Unknown")
        level = hero.get("level", 1)
        xp = hero.get("xp", 0)
        xp_to_next = hero.get("xp_to_next", 100)
        current_health = hero.get("current_health", 0)
        max_health = hero.get("max_health", 0)
        exhaustion = hero.get("exhaustion", 0.0)
        status = hero.get("status", "unknown")
        behavior = hero.get("behavior_profile", "balanced")

        label = exhaustion_label(exhaustion)
        lines.append(
            f"{name} | {archetype} | Lv{level} | XP: {xp}/{xp_to_next}"
            f" | HP: {current_health}/{max_health}"
            f" | Exhaustion: {exhaustion:.0f} ({label})"
            f" | {status} | {behavior}"
        )

        # Base stat row (loss-adjusted values are shown in render_hero_detail)
        strength = hero.get("strength", 10)
        dexterity = hero.get("dexterity", 10)
        intelligence = hero.get("intelligence", 10)
        charisma = hero.get("charisma", 10)
        constitution = hero.get("constitution", 10)
        lines.append(
            f"  STR:{strength} DEX:{dexterity} INT:{intelligence}"
            f" CHA:{charisma} CON:{constitution}"
        )

        # Show only non-None skill names in the summary row
        skills_raw = hero.get("skills", [])
        skill_names = [
            s["name"] for s in skills_raw if s is not None and isinstance(s, dict)
        ]
        skills_str = " | ".join(skill_names) if skill_names else "None"
        lines.append(f"  Skills: {skills_str}")
    return "\n".join(lines)


def render_hero_detail(hero: Dict) -> str:
    """
    Render a full stat sheet for a single hero.

    Shows level/XP, HP, exhaustion severity, all five stats with loss and
    effective modifier, skill slots, item slots, behavior profile, and status.
    """
    lines = []
    name = hero.get("name", "Unknown")
    archetype = hero.get("archetype", "Unknown")
    lines.append(f"=== {name} ({archetype}) ===")

    level = hero.get("level", 1)
    xp = hero.get("xp", 0)
    xp_to_next = hero.get("xp_to_next", 100)
    lines.append(f"Level: {level} | XP: {xp}/{xp_to_next}")

    current_health = hero.get("current_health", 0)
    max_health = hero.get("max_health", 0)
    lines.append(f"HP: {current_health}/{max_health}")

    exhaustion = hero.get("exhaustion", 0.0)
    label = exhaustion_label(exhaustion)
    lines.append(f"Exhaustion: {exhaustion:.1f} ({label})")

    lines.append("")
    lines.append("Stats (base / effective):")
    # Tuples of (base_key, loss_key, display_label) for the five ability scores
    stat_fields = [
        ("strength", "strength_loss", "STR"),
        ("dexterity", "dexterity_loss", "DEX"),
        ("intelligence", "intelligence_loss", "INT"),
        ("charisma", "charisma_loss", "CHA"),
        ("constitution", "constitution_loss", "CON"),
    ]
    for base_key, loss_key, label_str in stat_fields:
        base = hero.get(base_key, 10)
        loss = hero.get(loss_key, 0)
        effective = max(0, base - loss)
        # D&D modifier formula: floor(effective / 2) - 5
        modifier = (effective // 2) - 5
        sign = "+" if modifier >= 0 else ""
        lines.append(
            f"  {label_str}: {base} (loss: {loss}) -> effective: {effective}"
            f" (mod: {sign}{modifier})"
        )

    lines.append("")
    lines.append("Skills:")
    skills_raw = hero.get("skills", [None, None, None])
    for slot_i, skill in enumerate(skills_raw):
        if skill is not None and isinstance(skill, dict):
            skill_name = skill.get("name", "Unknown")
            dice_slots = skill.get("dice_slots", 0)
            lines.append(f"  Slot {slot_i}: {skill_name} ({dice_slots} dice slots)")
        else:
            lines.append(f"  Slot {slot_i}: (empty)")

    lines.append("")
    lines.append("Items:")
    item_slots = hero.get("item_slots", 1)
    equipped_items = hero.get("equipped_items", [None] * item_slots)
    for slot_i, item in enumerate(equipped_items):
        if item is not None:
            lines.append(f"  Slot {slot_i}: {item}")
        else:
            lines.append(f"  Slot {slot_i}: (empty)")

    lines.append("")
    behavior = hero.get("behavior_profile", "balanced")
    status = hero.get("status", "unknown")
    lines.append(f"Behavior Profile: {behavior}")
    lines.append(f"Status: {status}")

    return "\n".join(lines)
