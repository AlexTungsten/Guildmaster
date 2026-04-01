"""
hero_assignment.py — Validates and commits hero-to-quest assignments.

Before heroes can travel to a quest the assignment must pass a set of rules:
  - Every hero must currently be IDLE (not already on a quest or dead).
  - The party size must be within [required_heroes, max_heroes].
  - The quest must still be in AVAILABLE status.

If validation passes, all hero statuses are updated to TRAVELING and the
quest is marked ASSIGNED.  A "quest.assigned" event is published so other
systems (UI, overworld controller) can react.
"""

from typing import List, Tuple

from hero.hero_entity import HeroEntity, HeroStatus
from quest.quest_model import Quest, QuestStatus
from game_runtime.event_bus import EventBus


class AssignmentError(Exception):
    """Raised when an assignment attempt violates a validation rule."""
    pass


class HeroAssignment:
    def __init__(self, event_bus: EventBus):
        self._event_bus = event_bus

    def validate(
        self, quest: Quest, heroes: List[HeroEntity]
    ) -> Tuple[bool, str]:
        """
        Check whether the given heroes can legally be assigned to the quest.

        Returns (True, "") on success, or (False, reason) on failure.
        Does NOT mutate any state.
        """
        for hero in heroes:
            if hero.status != HeroStatus.IDLE:
                return False, f"Hero {hero.name} is not idle"
        if len(heroes) < quest.required_heroes:
            return False, "Not enough heroes"
        if len(heroes) > quest.max_heroes:
            return False, "Too many heroes"
        if quest.status != QuestStatus.AVAILABLE:
            return False, "Quest not available"
        return True, ""

    def assign(self, quest: Quest, heroes: List[HeroEntity]) -> None:
        """
        Validate and commit an assignment.

        Raises AssignmentError if validation fails.  On success:
          - Sets each hero's status to TRAVELING.
          - Records hero IDs on the quest.
          - Sets quest status to ASSIGNED.
          - Publishes "quest.assigned".
        """
        valid, reason = self.validate(quest, heroes)
        if not valid:
            raise AssignmentError(reason)

        # Transition each hero away from idle so they cannot be double-assigned
        for hero in heroes:
            hero.status = HeroStatus.TRAVELING

        quest.assigned_hero_ids = [h.hero_id for h in heroes]
        quest.status = QuestStatus.ASSIGNED

        self._event_bus.publish(
            "quest.assigned",
            {
                "quest_id": quest.quest_id,
                "hero_ids": list(quest.assigned_hero_ids),
            },
        )
