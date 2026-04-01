import unittest
from unittest.mock import patch, MagicMock

from hero.hero_entity import HeroEntity, HeroStatus, Skill, Stat
from enemy.enemy import AttackPattern, Enemy
from combat.combat_engine import CombatEngine, CombatResult
from game_runtime.event_bus import EventBus


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_skill(name: str = "Strike", effect_type: str = "damage", stat: Stat = Stat.STR) -> Skill:
    return Skill(
        name=name,
        description="Test skill",
        associated_stat=stat,
        dice_slots=3,
        effect_type=effect_type,
    )


def _make_strong_hero(hero_id: str = "h1") -> HeroEntity:
    """A hero with very high stats and lots of dice."""
    skill = _make_skill()
    return HeroEntity(
        hero_id=hero_id,
        name="Tank",
        archetype="warrior",
        strength=30,
        dexterity=30,
        intelligence=30,
        charisma=30,
        constitution=30,
        max_health=500,
        current_health=500,
        base_dice_count=10,
        skills=[skill, None, None],
    )


def _make_weak_hero(hero_id: str = "h1") -> HeroEntity:
    """A hero that will die very quickly."""
    skill = _make_skill()
    return HeroEntity(
        hero_id=hero_id,
        name="Minion",
        archetype="warrior",
        strength=1,
        dexterity=1,
        intelligence=1,
        charisma=1,
        constitution=1,
        max_health=1,
        current_health=1,
        base_dice_count=1,
        skills=[skill, None, None],
    )


def _make_weak_enemy(enemy_id: str = "e1") -> Enemy:
    """An enemy that will be killed in a single hit."""
    skill = _make_skill()
    return Enemy(
        enemy_id=enemy_id,
        name="Wisp",
        archetype="spirit",
        act=1,
        strength=1,
        dexterity=1,
        intelligence=1,
        charisma=1,
        constitution=1,
        max_health=1,
        current_health=1,
        skills=[skill],
        base_dice_count=1,
        pattern=AttackPattern([0]),
    )


def _make_strong_enemy(enemy_id: str = "e1") -> Enemy:
    """An enemy with overwhelming damage output."""
    skill = _make_skill()
    return Enemy(
        enemy_id=enemy_id,
        name="Dragon",
        archetype="boss",
        act=3,
        strength=30,
        dexterity=30,
        intelligence=30,
        charisma=30,
        constitution=30,
        max_health=500,
        current_health=500,
        skills=[skill],
        base_dice_count=20,
        pattern=AttackPattern([0]),
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestSimulateVictory(unittest.TestCase):

    def setUp(self):
        self.bus = EventBus()
        self.engine = CombatEngine(self.bus)

    def test_victory_when_heroes_overwhelm_enemies(self):
        heroes = [_make_strong_hero("h1")]
        enemies = [_make_weak_enemy("e1")]
        result = self.engine.simulate(heroes, enemies)
        self.assertIsInstance(result, CombatResult)
        self.assertTrue(result.victory)

    def test_defeat_when_enemies_too_strong(self):
        heroes = [_make_weak_hero("h1")]
        enemies = [_make_strong_enemy("e1")]
        result = self.engine.simulate(heroes, enemies)
        self.assertIsInstance(result, CombatResult)
        self.assertFalse(result.victory)

    def test_heroes_survived_populated_on_victory(self):
        heroes = [_make_strong_hero("h1"), _make_strong_hero("h2")]
        enemies = [_make_weak_enemy("e1")]
        result = self.engine.simulate(heroes, enemies)
        self.assertTrue(result.victory)
        self.assertIn("h1", result.heroes_survived)

    def test_heroes_survived_empty_on_defeat(self):
        heroes = [_make_weak_hero("h1")]
        enemies = [_make_strong_enemy("e1")]
        result = self.engine.simulate(heroes, enemies)
        self.assertFalse(result.victory)
        self.assertEqual(result.heroes_survived, [])


class TestSimulateMaxRounds(unittest.TestCase):

    def setUp(self):
        self.bus = EventBus()
        self.engine = CombatEngine(self.bus)

    def test_respects_max_rounds(self):
        # Both sides unkillable within 3 rounds
        hero = _make_strong_hero("h1")
        enemy = _make_strong_enemy("e1")
        result = self.engine.simulate([hero], [enemy], max_rounds=3)
        self.assertLessEqual(len(result.rounds), 3)

    def test_terminates_before_max_rounds_on_victory(self):
        heroes = [_make_strong_hero("h1")]
        enemies = [_make_weak_enemy("e1")]
        result = self.engine.simulate(heroes, enemies, max_rounds=50)
        # Should end after just 1 round
        self.assertLess(len(result.rounds), 50)


class TestPreSimulate(unittest.TestCase):

    def setUp(self):
        self.bus = EventBus()
        self.engine = CombatEngine(self.bus)

    def _make_pair(self):
        heroes = [_make_strong_hero("h1")]
        enemies = [_make_weak_enemy("e1"), _make_weak_enemy("e2")]
        return heroes, enemies

    def test_pre_simulate_returns_combat_result(self):
        heroes, enemies = self._make_pair()
        result = self.engine.pre_simulate(heroes, enemies)
        self.assertIsInstance(result, CombatResult)

    def test_pre_simulate_is_deterministic(self):
        heroes1, enemies1 = self._make_pair()
        heroes2, enemies2 = self._make_pair()
        result1 = self.engine.pre_simulate(heroes1, enemies1)
        result2 = self.engine.pre_simulate(heroes2, enemies2)
        self.assertEqual(result1.victory, result2.victory)
        self.assertEqual(result1.total_hero_damage_taken, result2.total_hero_damage_taken)
        self.assertEqual(len(result1.rounds), len(result2.rounds))

    def test_pre_simulate_does_not_publish_events(self):
        published = []
        self.bus.subscribe("combat.victory", lambda d: published.append("victory"))
        self.bus.subscribe("combat.defeat", lambda d: published.append("defeat"))
        self.bus.subscribe("combat.round_complete", lambda d: published.append("round"))

        heroes, enemies = self._make_pair()
        self.engine.pre_simulate(heroes, enemies)
        self.assertEqual(published, [])


class TestEventPublishing(unittest.TestCase):

    def setUp(self):
        self.bus = EventBus()
        self.engine = CombatEngine(self.bus)

    def test_victory_event_published_on_victory(self):
        events = []
        self.bus.subscribe("combat.victory", lambda d: events.append("victory"))

        heroes = [_make_strong_hero("h1")]
        enemies = [_make_weak_enemy("e1")]
        self.engine.simulate(heroes, enemies)

        self.assertIn("victory", events)

    def test_defeat_event_published_on_defeat(self):
        events = []
        self.bus.subscribe("combat.defeat", lambda d: events.append("defeat"))

        heroes = [_make_weak_hero("h1")]
        enemies = [_make_strong_enemy("e1")]
        self.engine.simulate(heroes, enemies)

        self.assertIn("defeat", events)

    def test_round_complete_event_published_each_round(self):
        round_numbers = []
        self.bus.subscribe("combat.round_complete", lambda d: round_numbers.append(d))

        heroes = [_make_strong_hero("h1")]
        enemies = [_make_weak_enemy("e1")]
        result = self.engine.simulate(heroes, enemies)

        self.assertEqual(len(round_numbers), len(result.rounds))
        self.assertEqual(round_numbers[0], 1)

    def test_only_victory_or_defeat_published_not_both(self):
        events = []
        self.bus.subscribe("combat.victory", lambda d: events.append("victory"))
        self.bus.subscribe("combat.defeat", lambda d: events.append("defeat"))

        heroes = [_make_strong_hero("h1")]
        enemies = [_make_weak_enemy("e1")]
        self.engine.simulate(heroes, enemies)

        victory_count = events.count("victory")
        defeat_count = events.count("defeat")
        self.assertEqual(victory_count + defeat_count, 1)


class TestTotalHeroDamageTaken(unittest.TestCase):

    def setUp(self):
        self.bus = EventBus()
        self.engine = CombatEngine(self.bus)

    def test_total_hero_damage_taken_non_negative(self):
        heroes = [_make_strong_hero("h1")]
        enemies = [_make_weak_enemy("e1")]
        result = self.engine.simulate(heroes, enemies)
        self.assertGreaterEqual(result.total_hero_damage_taken, 0)

    def test_total_hero_damage_taken_non_negative_on_defeat(self):
        heroes = [_make_weak_hero("h1")]
        enemies = [_make_strong_enemy("e1")]
        result = self.engine.simulate(heroes, enemies)
        self.assertGreaterEqual(result.total_hero_damage_taken, 0)

    def test_total_damage_matches_sum_of_rounds(self):
        heroes = [_make_strong_hero("h1")]
        enemies = [_make_weak_enemy("e1")]
        result = self.engine.simulate(heroes, enemies)
        expected = sum(r.hero_damage_taken for r in result.rounds)
        self.assertEqual(result.total_hero_damage_taken, expected)


if __name__ == "__main__":
    unittest.main()
