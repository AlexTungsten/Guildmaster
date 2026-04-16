"""
hero_entity.py — Core data model for a Guildmaster hero.

Defines:
  - Stat / HeroStatus enums
  - Skill dataclass (a hero's learnable abilities)
  - HeroEntity dataclass — the full stat block, exhaustion state, XP, and
    inventory for a single hero

All mutation methods live on HeroEntity so that callers never reach directly
into the fields for game-logic changes (they do for rendering/serialization).
"""

import random
from dataclasses import dataclass, field
from enum import Enum
from math import floor
from typing import Any, List, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from combat.status_effects import StatusEffect, StatusType


def _load_status_effects(raw: list) -> list:
    """Deserialize status effects without creating a hard circular import."""
    if not raw:
        return []
    from combat.status_effects import StatusEffect
    return [StatusEffect.from_dict(d) for d in raw]


class Stat(Enum):
    """The five D&D-style ability scores used by heroes and enemies."""
    STR = "strength"
    DEX = "dexterity"
    INT = "intelligence"
    CHA = "charisma"
    CON = "constitution"


class HeroStatus(Enum):
    """Lifecycle state of a hero; governs what actions are permitted."""
    IDLE = "idle"
    TRAVELING = "traveling"
    ON_QUEST = "on_quest"
    IN_COMBAT = "in_combat"
    DEAD = "dead"


@dataclass
class Skill:
    """A learnable ability that occupies one of a hero's three skill slots."""
    name: str
    description: str
    associated_stat: Stat   # Stat modifier added to this skill's effectiveness roll
    dice_slots: int          # Dice reserved for this skill each turn
    effect_type: str         # e.g. "damage", "heal", "aoe", "defend", "cleanse", "self", "buff"
    special: Optional[str] = None  # Optional mechanic tag (e.g. "blood_cleave", "eviscerate")

    # Charge system: skills with charge_cost > 0 accumulate dice value across turns.
    # When current_charge >= charge_cost the skill fires with its fixed effect and
    # current_charge resets to 0.  charge_cost == 0 means the skill fires normally
    # each turn (dice result → effectiveness).
    charge_cost: int = 0
    current_charge: int = 0

    # Elemental tag — used by Mage Spellweave convergence tracking.
    # "fire" | "lightning" | "ice" | "earth" | "arcane" | None
    element: Optional[str] = None

    def is_charging(self) -> bool:
        """True when this is a charge-based skill that hasn't fired yet."""
        return self.charge_cost > 0 and self.current_charge < self.charge_cost

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "description": self.description,
            "associated_stat": self.associated_stat.value,
            "dice_slots": self.dice_slots,
            "effect_type": self.effect_type,
            "special": self.special,
            "charge_cost": self.charge_cost,
            "current_charge": self.current_charge,
            "element": self.element,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Skill":
        # Accept both old "refresh_cost" key (backwards compat) and new "charge_cost"
        charge_cost = data.get("charge_cost", data.get("refresh_cost", 0))
        current_charge = data.get("current_charge", data.get("refresh_progress", 0))
        return cls(
            name=data["name"],
            description=data["description"],
            associated_stat=Stat(data["associated_stat"]),
            dice_slots=data["dice_slots"],
            effect_type=data["effect_type"],
            special=data.get("special"),
            charge_cost=charge_cost,
            current_charge=current_charge,
            element=data.get("element"),
        )


@dataclass
class HeroEntity:
    """
    Full representation of one hero in the guild.

    Base stats (strength, dexterity, …) represent the hero's permanent training.
    *_loss fields track irreversible stat degradation from critical failures.
    Exhaustion is a 0–100+ float; higher values lock dice and degrade stats.
    """

    hero_id: str
    name: str
    archetype: str

    # Base (permanent) ability scores — start at 10 (D&D-style "average")
    strength: int = 10
    dexterity: int = 10
    intelligence: int = 10
    charisma: int = 10
    constitution: int = 10

    # Permanent stat losses from death rolls or critical consequences
    strength_loss: int = 0
    dexterity_loss: int = 0
    intelligence_loss: int = 0
    charisma_loss: int = 0
    constitution_loss: int = 0

    level: int = 1
    xp: int = 0
    xp_to_next: int = 100   # XP needed for the next level (scales ×1.5 each level)
    # pending_stat_points: accumulated from level-ups, player distributes freely (+2/level)
    pending_stat_points: int = 0
    # Which level-3 passive was chosen (e.g. "blood_rage", "iron_will", "venomous", …)
    level3_passive_id: Optional[str] = None
    # Which level-5 upgrade was chosen (e.g. "blood_rage_upgrade", "lucky_roll_upgrade", …)
    level5_upgrade: Optional[str] = None

    max_health: int = 30
    current_health: int = 30

    # Exhaustion: 0 = fully rested, 100+ = critical / death-risk territory
    exhaustion: float = 0.0

    # Skill slots — None means the slot is empty
    skills: List[Optional[Skill]] = field(default_factory=lambda: [None, None, None])

    # Learnable skills available to this archetype (populated by archetype_loader)
    learnable_skills: List[Skill] = field(default_factory=list)

    behavior_profile: str = "focus"   # Controls dice assignment strategy in combat
    item_slots: int = 1
    equipped_items: List[Optional[Any]] = field(default_factory=lambda: [None])

    status: HeroStatus = HeroStatus.IDLE
    base_dice_count: int = 4   # Total dice in the hero's pool before exhaustion locks
    base_dice_sides: int = 10        # Die type for normal dice (d10 default, d12 for Barbarian)
    locked_dice_sides: int = 4       # Die type for exhaustion locked dice (d4 default, d6 with Ironhide)
    temp_hp: int = 0                 # Temporary HP — absorbs damage before real HP
    passives: List[dict] = field(default_factory=list)  # Named passives e.g. [{"passive_id": "ironhide", ...}]
    status_effects: List[Any] = field(default_factory=list)  # List[StatusEffect] — typed as Any to avoid circular import

    # ------------------------------------------------------------------
    # Hero block / retaliate (granted by Fortify)
    # ------------------------------------------------------------------
    block: int = 0                   # Absorbs incoming damage before temp HP / real HP
    retaliate_value: int = 0         # Damage dealt to attacker on first hit while block is up
    retaliate_active: bool = False   # True while retaliate has not yet triggered
    retaliate_consumed: bool = False # True after the single retaliate has fired

    # ------------------------------------------------------------------
    # Evasion state (Rogue learnable)
    # ------------------------------------------------------------------
    evasion_value: int = 0           # Flat damage reduction for this turn
    evasion_active: bool = False

    # ------------------------------------------------------------------
    # Advantage-next-turn flag (set by Cleric Battle Hymn)
    # ------------------------------------------------------------------
    advantage_next_turn: bool = False

    # ------------------------------------------------------------------
    # Barbarian combat state
    # ------------------------------------------------------------------
    blood_rage_stacks: int = 0       # Flat damage bonus per stack; resets each combat
    iron_will_used_this_quest: bool = False  # Once-per-quest survival trigger

    # ------------------------------------------------------------------
    # Mage combat state
    # ------------------------------------------------------------------
    blizzard_stored_damage: int = 0  # Tick damage while Blizzard is active
    blizzard_ticks_remaining: int = 0
    # Set[str] of spell elements fired this combat for Spellweave convergence.
    # Stored as a list for JSON serialisation; engine casts to set when checking.
    convergence_elements: List[str] = field(default_factory=list)
    arcane_bolt_cast_this_combat: bool = False
    # Prepared level-5 upgrade: free charge triggers (resets per quest)
    prepared_charges: int = 0

    # ------------------------------------------------------------------
    # Cleric combat state
    # ------------------------------------------------------------------
    regen_remaining: int = 0        # Turns of regeneration left on this hero
    regen_value: int = 0            # HP restored per Regen tick
    prayer_stacks: int = 0          # Resets each combat
    prayer_aoe_unlocked: bool = False  # True once ≥10 prayer stacks reached this combat

    # ------------------------------------------------------------------
    # Rogue combat state
    # ------------------------------------------------------------------
    second_wind_used: bool = False   # Once per combat; resets each combat

    # ------------------------------------------------------------------
    # Internal stat helpers
    # ------------------------------------------------------------------

    def _stat_value(self, stat: Stat) -> int:
        """Return the raw (unmodified by loss) value for the given stat."""
        mapping = {
            Stat.STR: self.strength,
            Stat.DEX: self.dexterity,
            Stat.INT: self.intelligence,
            Stat.CHA: self.charisma,
            Stat.CON: self.constitution,
        }
        return mapping[stat]

    def _stat_loss_value(self, stat: Stat) -> int:
        """Return the accumulated permanent loss for the given stat."""
        mapping = {
            Stat.STR: self.strength_loss,
            Stat.DEX: self.dexterity_loss,
            Stat.INT: self.intelligence_loss,
            Stat.CHA: self.charisma_loss,
            Stat.CON: self.constitution_loss,
        }
        return mapping[stat]

    def _set_stat_loss(self, stat: Stat, value: int) -> None:
        """Write an updated permanent loss value back to the correct field."""
        if stat == Stat.STR:
            self.strength_loss = value
        elif stat == Stat.DEX:
            self.dexterity_loss = value
        elif stat == Stat.INT:
            self.intelligence_loss = value
        elif stat == Stat.CHA:
            self.charisma_loss = value
        elif stat == Stat.CON:
            self.constitution_loss = value

    # ------------------------------------------------------------------
    # Public stat accessors
    # ------------------------------------------------------------------

    def effective_stat(self, stat: Stat) -> int:
        """Base stat minus permanent losses; clamped to 0."""
        return max(0, self._stat_value(stat) - self._stat_loss_value(stat))

    def stat_modifier(self, stat: Stat) -> int:
        """D&D-style modifier: floor(effective / 2) - 5."""
        return floor(self.effective_stat(stat) / 2) - 5

    # ------------------------------------------------------------------
    # Exhaustion system
    # ------------------------------------------------------------------

    def exhaustion_level(self) -> int:
        """
        Convert the floating exhaustion score to a discrete 1–5 severity level.

        Level 1: < 20   — Rested (no penalty)
        Level 2: 20–39  — Tired (1 locked die, 1 stat penalty)
        Level 3: 40–59  — Weary (2 locked dice, 2 stat penalties)
        Level 4: 60–99  — Drained (3 locked dice, all stat penalties)
        Level 5: >= 100 — Critical (4 locked dice, all stats penalised, death risk)
        """
        if self.exhaustion >= 100:
            return 5
        elif self.exhaustion >= 60:
            return 4
        elif self.exhaustion >= 40:
            return 3
        elif self.exhaustion >= 20:
            return 2
        else:
            return 1

    def exhaustion_temp_reduction(self) -> int:
        """Flat point reduction applied to affected stats at exhaustion level >= 2."""
        if self.exhaustion_level() >= 2:
            return 2
        return 0

    def _exhaustion_affected_stats(self) -> List[Stat]:
        """
        Return the list of stats that suffer the exhaustion penalty.

        Higher exhaustion levels affect more stats, targeting the hero's
        strongest stats first (to punish their primary effectiveness).
        """
        level = self.exhaustion_level()
        if level == 1:
            return []
        all_stats = list(Stat)
        sorted_stats = sorted(all_stats, key=lambda s: self.effective_stat(s), reverse=True)
        if level == 2:
            return sorted_stats[:1]
        elif level == 3:
            return sorted_stats[:2]
        else:
            return all_stats

    def effective_modifier(self, stat: Stat) -> int:
        """
        Modifier used during skill rolls, accounting for exhaustion penalties.

        If the stat is in the exhaustion-affected list, its effective value is
        reduced by exhaustion_temp_reduction() before the modifier calculation.
        """
        affected = self._exhaustion_affected_stats()
        reduction = self.exhaustion_temp_reduction()
        if stat in affected:
            return floor((self.effective_stat(stat) - reduction) / 2) - 5
        return self.stat_modifier(stat)

    def locked_dice_count(self) -> int:
        """
        Number of base dice replaced by locked dice due to exhaustion.

        Locked dice roll locked_dice_sides instead of base_dice_sides, and
        always appear at the front of the dice pool before normal dice.
        """
        level = self.exhaustion_level()
        mapping = {1: 0, 2: 1, 3: 2, 4: 3, 5: 4}
        return mapping[level]

    def add_exhaustion(self, amount: float) -> None:
        """Accumulate exhaustion from quest activity, travel, or damage."""
        self.exhaustion += amount

    def recover_exhaustion(self, seconds: float = 1.0) -> None:
        """
        Tick-based exhaustion recovery — only applies when the hero is IDLE.

        Passes silently if the hero is on a quest, traveling, or in combat.
        """
        if self.status != HeroStatus.IDLE:
            return
        self.exhaustion = max(0.0, self.exhaustion - seconds)

    # ------------------------------------------------------------------
    # Progression
    # ------------------------------------------------------------------

    def gain_xp(self, amount: int) -> bool:
        """
        Award XP; returns True if a level-up occurred.

        Uses self.xp_to_next as the per-level threshold.  On level-up, xp
        resets to the overflow amount and xp_to_next scales by ×1.5 (rounded).
        """
        from hero.hero_xp_config import MAX_LEVEL
        self.xp += amount
        if self.level >= MAX_LEVEL:
            return False
        if self.xp >= self.xp_to_next:
            overflow = self.xp - self.xp_to_next
            self.level += 1
            self.pending_stat_points += 2
            self.xp = overflow
            self.xp_to_next = round(self.xp_to_next * 1.5)
            return True
        return False

    def apply_permanent_stat_loss(self) -> Stat:
        """
        Randomly degrade one stat by 1 point permanently.

        Called on a failed death roll.  Returns the affected Stat so the
        caller can log or display what was lost.
        """
        stat = random.choice(list(Stat))
        self._set_stat_loss(stat, self._stat_loss_value(stat) + 1)
        return stat

    def death_roll(self) -> bool:
        """
        Roll against exhaustion to determine if the hero faces a permanent consequence.

        Returns True (death/consequence triggered) when the random 1–1000
        roll is less than the current exhaustion score.
        """
        roll = random.randint(1, 1000)
        return roll < self.exhaustion

    def allocate_stat_point(self, stat: Stat) -> bool:
        """
        Spend one pending stat point on the given stat.

        Returns True on success, False if no pending points remain or stat
        is already at the cap (20).
        """
        if self.pending_stat_points <= 0:
            return False
        current = self._stat_value(stat)
        if current >= 20:
            return False
        if stat == Stat.STR:
            self.strength = min(20, self.strength + 1)
        elif stat == Stat.DEX:
            self.dexterity = min(20, self.dexterity + 1)
        elif stat == Stat.INT:
            self.intelligence = min(20, self.intelligence + 1)
        elif stat == Stat.CHA:
            self.charisma = min(20, self.charisma + 1)
        elif stat == Stat.CON:
            self.constitution = min(20, self.constitution + 1)
        self.pending_stat_points -= 1
        return True

    # ------------------------------------------------------------------
    # Skills
    # ------------------------------------------------------------------

    def replace_skill(self, slot: int, new_skill: Skill) -> Optional[Skill]:
        """Swap the skill in the given slot (0–2) with new_skill; returns the displaced skill."""
        old = self.skills[slot]
        self.skills[slot] = new_skill
        return old

    # ------------------------------------------------------------------
    # Passives
    # ------------------------------------------------------------------

    def has_passive(self, passive_id: str) -> bool:
        """Return True if this hero has a passive with the given passive_id."""
        return any(p.get("passive_id") == passive_id for p in self.passives)

    def add_passive(self, passive: dict) -> None:
        """Add a passive dict to the hero's passive list if not already present."""
        pid = passive.get("passive_id")
        if pid and not self.has_passive(pid):
            self.passives.append(passive)

    # ------------------------------------------------------------------
    # Temp HP and damage absorption
    # ------------------------------------------------------------------

    def absorb_damage(self, amount: int) -> int:
        """
        Apply incoming damage through: Hero Block → Temp HP → Real HP.

        Returns the damage amount that reached real HP.
        Retaliate is NOT triggered here — the combat engine handles that
        separately so it can apply the retaliate to the correct enemy.
        """
        remaining = amount

        # Evasion: flat damage reduction this turn
        if self.evasion_active and self.evasion_value > 0:
            remaining = max(0, remaining - self.evasion_value)

        # Hero block (Fortify)
        if self.block > 0:
            absorbed_by_block = min(self.block, remaining)
            self.block -= absorbed_by_block
            remaining -= absorbed_by_block

        if remaining <= 0:
            return 0

        # Temp HP
        absorbed = min(self.temp_hp, remaining)
        self.temp_hp -= absorbed
        remaining -= absorbed

        # Real HP
        self.current_health = max(0, self.current_health - remaining)
        return remaining

    def apply_temp_hp(self, amount: int) -> None:
        """Set temp HP to amount, replacing any existing temp HP (does not stack)."""
        self.temp_hp = amount

    def add_temp_hp(self, amount: int) -> None:
        """Add amount to existing temp HP (stacking variant used by Lifeblood Slam etc.)."""
        self.temp_hp += amount

    # ------------------------------------------------------------------
    # Status effects — thin wrappers over combat.status_effects helpers
    # ------------------------------------------------------------------

    def apply_status(self, effect: Any) -> None:
        """Apply a status effect following stacking rules."""
        from combat.status_effects import apply_status
        self.status_effects = apply_status(self.status_effects, effect)

    def has_status(self, status_type: Any) -> bool:
        """Return True if this hero has an active status of the given type."""
        from combat.status_effects import has_status
        return has_status(self.status_effects, status_type)

    def get_status(self, status_type: Any) -> Optional[Any]:
        """Return the active StatusEffect of the given type, or None."""
        from combat.status_effects import get_status
        return get_status(self.status_effects, status_type)

    def has_any_debuff(self) -> bool:
        """Return True if any active status effect is a debuff."""
        from combat.status_effects import has_any_debuff
        return has_any_debuff(self.status_effects)

    def count_active_buffs(self) -> int:
        """Return total count of active buff effects (used by Holy Smite)."""
        from combat.status_effects import BUFFS
        return sum(1 for e in self.status_effects if e.status_type in BUFFS)

    def count_all_debuff_stacks(self) -> int:
        """
        Count all active debuff stacks on this hero (used by Cheap Shot).

        Counts: poison duration, bleed duration, vulnerable duration,
        weak duration, paralyze stacks, burn stacks, downgrade duration,
        disadvantage duration.
        """
        from combat.status_effects import StatusType
        total = 0
        for e in self.status_effects:
            st = e.status_type
            if st in (StatusType.POISON, StatusType.BLEED, StatusType.VULNERABLE,
                      StatusType.WEAK, StatusType.DOWNGRADE, StatusType.DISADVANTAGE):
                total += e.duration
            elif st in (StatusType.BURN, StatusType.PARALYZE):
                total += e.stacks
        return total

    def clear_status(self, status_type: Any) -> None:
        """Remove all effects of the given type."""
        self.status_effects = [e for e in self.status_effects if e.status_type != status_type]

    # ------------------------------------------------------------------
    # Combat state lifecycle
    # ------------------------------------------------------------------

    def reset_combat_state(self) -> None:
        """
        Reset per-combat state.  Called at the start of every new combat
        (before the first round).
        """
        self.blood_rage_stacks = 0
        self.second_wind_used = False
        self.blizzard_stored_damage = 0
        self.blizzard_ticks_remaining = 0
        self.convergence_elements = []
        self.arcane_bolt_cast_this_combat = False
        self.prayer_stacks = 0
        self.prayer_aoe_unlocked = False
        self.evasion_value = 0
        self.evasion_active = False
        self.block = 0
        self.retaliate_value = 0
        self.retaliate_active = False
        self.retaliate_consumed = False
        self.advantage_next_turn = False
        self.regen_remaining = 0
        self.regen_value = 0
        # Reset all skill charge progress
        for skill in self.skills:
            if skill is not None and skill.charge_cost > 0:
                skill.current_charge = 0

    def reset_quest_state(self) -> None:
        """
        Reset per-quest state.  Called at the start of each new quest
        before any combat in that quest begins.
        """
        self.iron_will_used_this_quest = False
        # Serendipity level-5 (Prepared): restore free-charge tokens
        if self.has_passive("serendipity") and self.level5_upgrade == "prepared":
            self.prepared_charges = 3

    # ------------------------------------------------------------------
    # Serialization
    # ------------------------------------------------------------------

    def to_dict(self) -> dict:
        return {
            "hero_id": self.hero_id,
            "name": self.name,
            "archetype": self.archetype,
            "strength": self.strength,
            "dexterity": self.dexterity,
            "intelligence": self.intelligence,
            "charisma": self.charisma,
            "constitution": self.constitution,
            "strength_loss": self.strength_loss,
            "dexterity_loss": self.dexterity_loss,
            "intelligence_loss": self.intelligence_loss,
            "charisma_loss": self.charisma_loss,
            "constitution_loss": self.constitution_loss,
            "level": self.level,
            "xp": self.xp,
            "xp_to_next": self.xp_to_next,
            "pending_stat_points": self.pending_stat_points,
            "level3_passive_id": self.level3_passive_id,
            "level5_upgrade": self.level5_upgrade,
            "max_health": self.max_health,
            "current_health": self.current_health,
            "exhaustion": self.exhaustion,
            "skills": [s.to_dict() if s is not None else None for s in self.skills],
            "learnable_skills": [s.to_dict() for s in self.learnable_skills],
            "behavior_profile": self.behavior_profile,
            "item_slots": self.item_slots,
            "equipped_items": self.equipped_items,
            "status": self.status.value,
            "base_dice_count": self.base_dice_count,
            "base_dice_sides": self.base_dice_sides,
            "locked_dice_sides": self.locked_dice_sides,
            "temp_hp": self.temp_hp,
            "passives": self.passives,
            "status_effects": [e.to_dict() for e in self.status_effects],
            # Combat state (persisted so saves mid-combat work)
            "blood_rage_stacks": self.blood_rage_stacks,
            "iron_will_used_this_quest": self.iron_will_used_this_quest,
            "blizzard_stored_damage": self.blizzard_stored_damage,
            "blizzard_ticks_remaining": self.blizzard_ticks_remaining,
            "convergence_elements": self.convergence_elements,
            "arcane_bolt_cast_this_combat": self.arcane_bolt_cast_this_combat,
            "prepared_charges": self.prepared_charges,
            "regen_remaining": self.regen_remaining,
            "regen_value": self.regen_value,
            "prayer_stacks": self.prayer_stacks,
            "prayer_aoe_unlocked": self.prayer_aoe_unlocked,
            "second_wind_used": self.second_wind_used,
            "block": self.block,
            "retaliate_value": self.retaliate_value,
            "retaliate_active": self.retaliate_active,
            "retaliate_consumed": self.retaliate_consumed,
            "evasion_value": self.evasion_value,
            "evasion_active": self.evasion_active,
            "advantage_next_turn": self.advantage_next_turn,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "HeroEntity":
        """Reconstruct a HeroEntity from a previously serialized dict."""
        skills_raw = data.get("skills", [None, None, None])
        skills = [Skill.from_dict(s) if s is not None else None for s in skills_raw]
        learnable_raw = data.get("learnable_skills", [])
        learnable = [Skill.from_dict(s) for s in learnable_raw]
        item_slots = data.get("item_slots", 1)
        equipped_items = data.get("equipped_items", [None] * item_slots)
        return cls(
            hero_id=data["hero_id"],
            name=data["name"],
            archetype=data["archetype"],
            strength=data.get("strength", 10),
            dexterity=data.get("dexterity", 10),
            intelligence=data.get("intelligence", 10),
            charisma=data.get("charisma", 10),
            constitution=data.get("constitution", 10),
            strength_loss=data.get("strength_loss", 0),
            dexterity_loss=data.get("dexterity_loss", 0),
            intelligence_loss=data.get("intelligence_loss", 0),
            charisma_loss=data.get("charisma_loss", 0),
            constitution_loss=data.get("constitution_loss", 0),
            level=data.get("level", 1),
            xp=data.get("xp", 0),
            xp_to_next=data.get("xp_to_next", 100),
            pending_stat_points=data.get("pending_stat_points", 0),
            level3_passive_id=data.get("level3_passive_id"),
            level5_upgrade=data.get("level5_upgrade"),
            max_health=data.get("max_health", 30),
            current_health=data.get("current_health", 30),
            exhaustion=data.get("exhaustion", 0.0),
            skills=skills,
            learnable_skills=learnable,
            behavior_profile=data.get("behavior_profile", "focus"),
            item_slots=item_slots,
            equipped_items=equipped_items,
            status=HeroStatus(data.get("status", "idle")),
            base_dice_count=data.get("base_dice_count", 4),
            base_dice_sides=data.get("base_dice_sides", 10),
            locked_dice_sides=data.get("locked_dice_sides", 4),
            temp_hp=data.get("temp_hp", 0),
            passives=data.get("passives", []),
            status_effects=_load_status_effects(data.get("status_effects", [])),
            blood_rage_stacks=data.get("blood_rage_stacks", 0),
            iron_will_used_this_quest=data.get("iron_will_used_this_quest", False),
            blizzard_stored_damage=data.get("blizzard_stored_damage", 0),
            blizzard_ticks_remaining=data.get("blizzard_ticks_remaining", 0),
            convergence_elements=data.get("convergence_elements", []),
            arcane_bolt_cast_this_combat=data.get("arcane_bolt_cast_this_combat", False),
            prepared_charges=data.get("prepared_charges", 0),
            regen_remaining=data.get("regen_remaining", 0),
            regen_value=data.get("regen_value", 0),
            prayer_stacks=data.get("prayer_stacks", 0),
            prayer_aoe_unlocked=data.get("prayer_aoe_unlocked", False),
            second_wind_used=data.get("second_wind_used", False),
            block=data.get("block", 0),
            retaliate_value=data.get("retaliate_value", 0),
            retaliate_active=data.get("retaliate_active", False),
            retaliate_consumed=data.get("retaliate_consumed", False),
            evasion_value=data.get("evasion_value", 0),
            evasion_active=data.get("evasion_active", False),
            advantage_next_turn=data.get("advantage_next_turn", False),
        )
