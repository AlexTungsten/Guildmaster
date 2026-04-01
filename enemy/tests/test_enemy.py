import unittest

from hero.hero_entity import Skill, Stat
from enemy.enemy import AttackPattern, Enemy, make_enemy


def _make_skill(name: str = "Strike", effect_type: str = "damage") -> Skill:
    return Skill(
        name=name,
        description="Test",
        associated_stat=Stat.STR,
        dice_slots=2,
        effect_type=effect_type,
    )


def _make_base_enemy(**kwargs) -> Enemy:
    defaults = dict(
        enemy_id="e1",
        name="Goblin",
        archetype="melee",
        act=1,
        strength=10,
        dexterity=10,
        intelligence=10,
        charisma=10,
        constitution=10,
        max_health=20,
        current_health=20,
        skills=[_make_skill()],
        base_dice_count=3,
        pattern=AttackPattern([0]),
    )
    defaults.update(kwargs)
    return Enemy(**defaults)


class TestEnemyIsAlive(unittest.TestCase):

    def test_is_alive_true_when_health_above_zero(self):
        enemy = _make_base_enemy(current_health=10)
        self.assertTrue(enemy.is_alive)

    def test_is_alive_false_at_zero(self):
        enemy = _make_base_enemy(current_health=0)
        self.assertFalse(enemy.is_alive)

    def test_is_alive_true_at_one(self):
        enemy = _make_base_enemy(current_health=1)
        self.assertTrue(enemy.is_alive)


class TestEnemyTakeDamage(unittest.TestCase):

    def test_take_damage_reduces_health(self):
        enemy = _make_base_enemy(current_health=20)
        enemy.take_damage(5)
        self.assertEqual(enemy.current_health, 15)

    def test_take_damage_clamps_to_zero(self):
        enemy = _make_base_enemy(current_health=5)
        enemy.take_damage(100)
        self.assertEqual(enemy.current_health, 0)

    def test_take_damage_zero_no_change(self):
        enemy = _make_base_enemy(current_health=20)
        enemy.take_damage(0)
        self.assertEqual(enemy.current_health, 20)

    def test_take_damage_exact_health(self):
        enemy = _make_base_enemy(current_health=10)
        enemy.take_damage(10)
        self.assertEqual(enemy.current_health, 0)


class TestEnemyScaleForAct(unittest.TestCase):

    def test_scale_act_1_no_change(self):
        enemy = _make_base_enemy(strength=10, max_health=20, current_health=20, base_dice_count=3)
        enemy.scale_for_act(1)
        self.assertEqual(enemy.strength, 10)
        self.assertEqual(enemy.max_health, 20)
        self.assertEqual(enemy.current_health, 20)
        self.assertEqual(enemy.base_dice_count, 3)

    def test_scale_act_2_increases_stats(self):
        enemy = _make_base_enemy(strength=10, max_health=20, current_health=20, base_dice_count=3)
        enemy.scale_for_act(2)
        self.assertEqual(enemy.strength, 13)
        self.assertEqual(enemy.max_health, 26)
        self.assertEqual(enemy.current_health, 26)
        self.assertEqual(enemy.base_dice_count, 4)

    def test_scale_act_3_increases_stats_more(self):
        enemy = _make_base_enemy(strength=10, max_health=20, current_health=20, base_dice_count=3)
        enemy.scale_for_act(3)
        self.assertEqual(enemy.strength, 16)
        self.assertEqual(enemy.max_health, 32)
        self.assertEqual(enemy.current_health, 32)
        self.assertEqual(enemy.base_dice_count, 5)

    def test_scale_increases_all_stats(self):
        enemy = _make_base_enemy(
            strength=10, dexterity=10, intelligence=10, charisma=10, constitution=10
        )
        enemy.scale_for_act(2)
        for attr in ("strength", "dexterity", "intelligence", "charisma", "constitution"):
            self.assertGreater(getattr(enemy, attr), 10, f"{attr} should increase")


class TestAttackPattern(unittest.TestCase):

    def test_single_index_always_returns_same(self):
        pattern = AttackPattern([0])
        self.assertEqual(pattern.next_skill_index(), 0)
        self.assertEqual(pattern.next_skill_index(), 0)
        self.assertEqual(pattern.next_skill_index(), 0)

    def test_cycles_through_indices(self):
        pattern = AttackPattern([0, 1, 2])
        self.assertEqual(pattern.next_skill_index(), 0)
        self.assertEqual(pattern.next_skill_index(), 1)
        self.assertEqual(pattern.next_skill_index(), 2)
        self.assertEqual(pattern.next_skill_index(), 0)

    def test_two_skill_cycle(self):
        pattern = AttackPattern([1, 0])
        self.assertEqual(pattern.next_skill_index(), 1)
        self.assertEqual(pattern.next_skill_index(), 0)
        self.assertEqual(pattern.next_skill_index(), 1)

    def test_round_counter_advances(self):
        pattern = AttackPattern([0, 1])
        pattern.next_skill_index()
        self.assertEqual(pattern._round, 1)
        pattern.next_skill_index()
        self.assertEqual(pattern._round, 2)


class TestMakeEnemy(unittest.TestCase):

    def _template(self) -> dict:
        return {
            "enemy_id": "goblin_01",
            "name": "Goblin",
            "archetype": "melee",
            "strength": 10,
            "dexterity": 10,
            "intelligence": 10,
            "charisma": 10,
            "constitution": 10,
            "max_health": 20,
            "current_health": 20,
            "skills": [
                {
                    "name": "Strike",
                    "description": "Basic attack",
                    "associated_stat": "strength",
                    "dice_slots": 2,
                    "effect_type": "damage",
                }
            ],
            "base_dice_count": 3,
            "pattern": {"skill_indices": [0]},
        }

    def test_make_enemy_constructs_from_template(self):
        template = self._template()
        enemy = make_enemy(template, act=1)
        self.assertEqual(enemy.enemy_id, "goblin_01")
        self.assertEqual(enemy.name, "Goblin")
        self.assertEqual(enemy.act, 1)
        self.assertEqual(len(enemy.skills), 1)
        self.assertEqual(enemy.skills[0].name, "Strike")

    def test_make_enemy_scales_for_act(self):
        template = self._template()
        enemy_act1 = make_enemy(template, act=1)
        template2 = self._template()
        enemy_act2 = make_enemy(template2, act=2)
        self.assertGreater(enemy_act2.strength, enemy_act1.strength)
        self.assertGreater(enemy_act2.max_health, enemy_act1.max_health)

    def test_make_enemy_pattern_resets_round(self):
        template = self._template()
        enemy = make_enemy(template, act=1)
        self.assertEqual(enemy.pattern._round, 0)


class TestEnemyToFromDict(unittest.TestCase):

    def test_round_trip(self):
        skill = _make_skill()
        original = Enemy(
            enemy_id="e99",
            name="Troll",
            archetype="brute",
            act=2,
            strength=14,
            dexterity=8,
            intelligence=6,
            charisma=6,
            constitution=16,
            max_health=40,
            current_health=35,
            skills=[skill],
            base_dice_count=4,
            pattern=AttackPattern([0, 1]),
        )
        data = original.to_dict()
        restored = Enemy.from_dict(data)

        self.assertEqual(restored.enemy_id, original.enemy_id)
        self.assertEqual(restored.name, original.name)
        self.assertEqual(restored.strength, original.strength)
        self.assertEqual(restored.max_health, original.max_health)
        self.assertEqual(restored.current_health, original.current_health)
        self.assertEqual(restored.base_dice_count, original.base_dice_count)
        self.assertEqual(len(restored.skills), 1)
        self.assertEqual(restored.skills[0].name, skill.name)
        self.assertEqual(restored.pattern.skill_indices, [0, 1])

    def test_to_dict_contains_expected_keys(self):
        enemy = _make_base_enemy()
        data = enemy.to_dict()
        expected_keys = {
            "enemy_id", "name", "archetype", "act",
            "strength", "dexterity", "intelligence", "charisma", "constitution",
            "max_health", "current_health", "skills", "base_dice_count", "pattern",
        }
        self.assertTrue(expected_keys.issubset(data.keys()))


if __name__ == "__main__":
    unittest.main()
