"""
draft_renderer.py — Pure text renderers for the hero draft and run-start screens.

Both functions accept plain dict data (not domain objects) so they can be
called without importing any game logic modules.  They return a single string
ready to print to the terminal.
"""

from typing import List, Dict


def render_draft_screen(
    archetypes: List[Dict],
    picks_remaining: int,
    current_roster: List[Dict],
) -> str:
    """
    Render the hero archetype selection screen shown at the start of a run.

    Parameters
    ----------
    archetypes       : List of archetype dicts with at least {"name": str} keys.
    picks_remaining  : How many more heroes the player can draft this session.
    current_roster   : Heroes already drafted, each a dict with a "name" key.
    """
    lines = []
    lines.append(f"=== HERO DRAFT === | Picks remaining: {picks_remaining}")
    lines.append("")
    lines.append("Available Archetypes:")
    for i, arch in enumerate(archetypes, start=1):
        name = arch.get("name", "Unknown")
        description = arch.get("description", "")
        if description:
            lines.append(f"  {i}. {name} — {description}")
        else:
            lines.append(f"  {i}. {name}")
    lines.append("")
    lines.append("Your Roster:")
    if current_roster:
        for hero in current_roster:
            lines.append(f"  - {hero.get('name', 'Unknown')}")
    else:
        lines.append("  Empty")
    lines.append("")
    lines.append("Enter archetype number to draft, or 'done' when finished.")
    return "\n".join(lines)


def render_run_start_screen(roster: List[Dict], first_boss: Dict) -> str:
    """
    Render the summary screen shown just before a run begins.

    Parameters
    ----------
    roster     : List of hero dicts with "name" and "archetype" keys.
    first_boss : Boss dict with at least {"boss_id": str, "act": int} keys.
                 A "name" key is used if present, otherwise boss_id is shown.
    """
    lines = []
    lines.append("=== RUN BEGINS ===")
    lines.append("")
    lines.append("Your Guild:")
    for hero in roster:
        name = hero.get("name", "Unknown")
        archetype = hero.get("archetype", "Unknown")
        lines.append(f"  - {name} ({archetype})")
    lines.append("")
    lines.append("First Boss:")
    # Prefer an explicit name field; fall back to boss_id for programmatically created bosses
    boss_name = first_boss.get("name", first_boss.get("boss_id", "Unknown"))
    act = first_boss.get("act", "?")
    lines.append(f"  {boss_name} (Act {act})")
    lines.append("")
    lines.append("Press ENTER to start.")
    return "\n".join(lines)
