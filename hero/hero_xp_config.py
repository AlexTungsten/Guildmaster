"""
hero_xp_config.py — Tunable XP progression constants.

XP_THRESHOLDS[i] is the cumulative XP required to reach level (i+1).
Index 0 = level 1 (starting state, 0 XP needed).
Index 4 = level 5 (700 XP cumulative).

Level cap is MAX_LEVEL (5).  Heroes cannot exceed this level.
"""

# Cumulative XP to reach each level (index = level - 1)
XP_THRESHOLDS: list[int] = [0, 100, 250, 450, 700]

MAX_LEVEL: int = 5


def xp_for_level(level: int) -> int:
    """Return the cumulative XP required to have reached the given level."""
    if level <= 1:
        return 0
    if level > MAX_LEVEL:
        return XP_THRESHOLDS[MAX_LEVEL - 1]
    return XP_THRESHOLDS[level - 1]


def level_for_xp(xp: int) -> int:
    """Return the level a hero is at given total cumulative XP earned."""
    level = 1
    for threshold in XP_THRESHOLDS[1:]:
        if xp >= threshold:
            level += 1
        else:
            break
    return min(level, MAX_LEVEL)
