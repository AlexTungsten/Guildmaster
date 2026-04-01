"""
status_effects.py — Status effect definitions and resolution logic.

Defines:
  - StatusType: all status effect identifiers
  - DEBUFFS / BUFFS / CANCELS: classification sets
  - StatusEffect: runtime instance of one active status
  - apply_status(): add a new effect to an existing list with correct stacking
  - tick_statuses(): end-of-turn processing — deals damage and decrements durations

Debuffs (cleansable):  Poison, Burn, Bleed, Paralyze, Vulnerable, Weak,
                       Downgrade, Disadvantage
Buffs:                 Upgrade, Advantage
Mechanics:             Taunt
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from enum import Enum
from typing import List, Tuple


# ---------------------------------------------------------------------------
# Status type registry
# ---------------------------------------------------------------------------

class StatusType(Enum):
    # --- Debuffs ---
    POISON      = "poison"       # deals potency dmg/turn; stacks: higher potency wins, durations add
    BURN        = "burn"         # end-of-turn: deal stacks dmg then stacks -= 1
    BLEED       = "bleed"        # start-of-turn: discard 1 random die; duration-stacks only
    PARALYZE    = "paralyze"     # set N dice to 1 after rolling; stacks add; all removed EOT
    VULNERABLE  = "vulnerable"   # +50% incoming damage (last multiplier); duration only
    WEAK        = "weak"         # -25% outgoing damage; duration only
    DOWNGRADE   = "downgrade"    # all dice drop 1 tier; no stack; cancelled by UPGRADE
    DISADVANTAGE = "disadvantage" # roll twice keep worst; no stack; cancelled by ADVANTAGE
    # --- Buffs ---
    UPGRADE     = "upgrade"      # all dice gain 1 tier (incl. locked); no stack; cancelled by DOWNGRADE
    ADVANTAGE   = "advantage"    # roll twice keep best; no stack; cancelled by DISADVANTAGE
    # --- Mechanics ---
    TAUNT       = "taunt"        # single-target attacks must target this unit; duration only


# Sets used for classification queries
DEBUFFS: frozenset[StatusType] = frozenset({
    StatusType.POISON, StatusType.BURN, StatusType.BLEED, StatusType.PARALYZE,
    StatusType.VULNERABLE, StatusType.WEAK, StatusType.DOWNGRADE, StatusType.DISADVANTAGE,
})

BUFFS: frozenset[StatusType] = frozenset({
    StatusType.UPGRADE, StatusType.ADVANTAGE,
})

# Mutual-cancellation pairs (applying either immediately removes the other and itself)
CANCELS: dict[StatusType, StatusType] = {
    StatusType.UPGRADE:      StatusType.DOWNGRADE,
    StatusType.DOWNGRADE:    StatusType.UPGRADE,
    StatusType.ADVANTAGE:    StatusType.DISADVANTAGE,
    StatusType.DISADVANTAGE: StatusType.ADVANTAGE,
}


# ---------------------------------------------------------------------------
# Die tier helpers used by Upgrade / Downgrade
# ---------------------------------------------------------------------------

_TIERS = [4, 6, 8, 10, 12]


def upgrade_die(sides: int) -> int:
    """Return the next die tier above sides, capping at d12."""
    try:
        return _TIERS[min(_TIERS.index(sides) + 1, len(_TIERS) - 1)]
    except ValueError:
        return sides  # non-standard die — leave unchanged


def downgrade_die(sides: int) -> int:
    """Return the next die tier below sides, flooring at d4."""
    try:
        return _TIERS[max(_TIERS.index(sides) - 1, 0)]
    except ValueError:
        return sides


# ---------------------------------------------------------------------------
# StatusEffect dataclass
# ---------------------------------------------------------------------------

@dataclass
class StatusEffect:
    """
    One active status effect on a hero or enemy.

    Fields
    ------
    status_type : StatusType
    duration    : turns remaining (decremented EOT for most types)
    stacks      : for Burn = current stack count; for Paralyze = dice count;
                  for others = 1 (not meaningful)
    potency     : for Poison = damage dealt per turn; unused for other types
    """
    status_type: StatusType
    duration: int = 1
    stacks: int = 1
    potency: int = 0

    def is_debuff(self) -> bool:
        return self.status_type in DEBUFFS

    def is_buff(self) -> bool:
        return self.status_type in BUFFS

    def to_dict(self) -> dict:
        return {
            "status_type": self.status_type.value,
            "duration": self.duration,
            "stacks": self.stacks,
            "potency": self.potency,
        }

    @classmethod
    def from_dict(cls, data: dict) -> StatusEffect:
        return cls(
            status_type=StatusType(data["status_type"]),
            duration=data.get("duration", 1),
            stacks=data.get("stacks", 1),
            potency=data.get("potency", 0),
        )


# ---------------------------------------------------------------------------
# Applying a new status to an existing list
# ---------------------------------------------------------------------------

def apply_status(
    effects: List[StatusEffect],
    new: StatusEffect,
) -> List[StatusEffect]:
    """
    Merge new into the effects list following each type's stacking rules.

    Returns a new list — the original is not mutated.

    Cancellation (Upgrade↔Downgrade, Advantage↔Disadvantage):
      Applying either while the opposing type is active removes BOTH immediately.
      The new effect is NOT added.

    Stacking rules per type:
      Poison      — higher potency wins; durations add
      Burn        — stacks add
      Bleed       — durations add
      Paralyze    — stacks add
      Vulnerable  — durations add
      Weak        — durations add
      Taunt       — durations add
      Downgrade   — no stack; refresh to max(existing, new) duration
      Upgrade     — no stack; refresh to max duration
      Disadvantage— no stack; refresh to max duration
      Advantage   — no stack; refresh to max duration
    """
    st = new.status_type
    result = list(effects)

    # --- Cancellation check ---
    if st in CANCELS:
        cancel_type = CANCELS[st]
        if any(e.status_type == cancel_type for e in result):
            # Both removed; new effect not applied
            return [e for e in result if e.status_type != cancel_type]

    existing = next((e for e in result if e.status_type == st), None)

    if existing is None:
        result.append(StatusEffect(
            status_type=st,
            duration=new.duration,
            stacks=new.stacks,
            potency=new.potency,
        ))
        return result

    # --- Merge into existing ---
    if st == StatusType.POISON:
        existing.potency = max(existing.potency, new.potency)
        existing.duration += new.duration

    elif st == StatusType.BURN:
        existing.stacks += new.stacks

    elif st == StatusType.PARALYZE:
        existing.stacks += new.stacks

    elif st in (StatusType.BLEED, StatusType.VULNERABLE, StatusType.WEAK, StatusType.TAUNT):
        existing.duration += new.duration

    elif st in (StatusType.DOWNGRADE, StatusType.UPGRADE,
                StatusType.DISADVANTAGE, StatusType.ADVANTAGE):
        existing.duration = max(existing.duration, new.duration)

    return result


# ---------------------------------------------------------------------------
# End-of-turn ticking
# ---------------------------------------------------------------------------

def tick_statuses(
    effects: List[StatusEffect],
) -> Tuple[List[StatusEffect], List[Tuple[StatusType, int]]]:
    """
    Process end-of-turn effects and decrement durations.

    Returns
    -------
    updated_effects : list with expired statuses removed
    damage_events   : list of (StatusType, damage_amount) for effects that
                      dealt damage this tick (Burn, Poison)
    """
    damage_events: List[Tuple[StatusType, int]] = []
    survivors: List[StatusEffect] = []

    for e in effects:
        st = e.status_type

        if st == StatusType.BURN:
            damage_events.append((st, e.stacks))
            e.stacks -= 1
            if e.stacks > 0:
                survivors.append(e)
            # Burn expires when stacks hit 0 — no duration field involved

        elif st == StatusType.POISON:
            damage_events.append((st, e.potency))
            e.duration -= 1
            if e.duration > 0:
                survivors.append(e)

        elif st == StatusType.BLEED:
            # Bleed duration decremented EOT; the die-discard happened SOT
            e.duration -= 1
            if e.duration > 0:
                survivors.append(e)

        elif st == StatusType.PARALYZE:
            # All Paralyze stacks removed at end of turn
            pass  # drop from survivors

        elif st in (StatusType.TAUNT, StatusType.VULNERABLE, StatusType.WEAK):
            e.duration -= 1
            if e.duration > 0:
                survivors.append(e)

        elif st in (StatusType.DOWNGRADE, StatusType.UPGRADE,
                    StatusType.DISADVANTAGE, StatusType.ADVANTAGE):
            e.duration -= 1
            if e.duration > 0:
                survivors.append(e)

        else:
            survivors.append(e)  # unknown type — preserve

    return survivors, damage_events


# ---------------------------------------------------------------------------
# Convenience query helpers (used by HeroEntity / Enemy)
# ---------------------------------------------------------------------------

def has_status(effects: List[StatusEffect], st: StatusType) -> bool:
    return any(e.status_type == st for e in effects)


def get_status(effects: List[StatusEffect], st: StatusType) -> StatusEffect | None:
    return next((e for e in effects if e.status_type == st), None)


def has_any_debuff(effects: List[StatusEffect]) -> bool:
    """True if any active effect is a debuff (used by Eviscerate's enhanced-damage check)."""
    return any(e.status_type in DEBUFFS for e in effects)
