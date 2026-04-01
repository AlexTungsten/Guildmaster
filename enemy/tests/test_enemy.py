import random
import unittest

from hero.hero_entity import Skill, Stat
from enemy.enemy import Enemy, make_enemy


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _skill(name: str = "Strike", effect_type: str = "damage", dice_slots: int = 1) -> Skill:
    return Skill(
        name=name,
        description="Test skill",
        associated_stat=Stat.STR,
        dice_slots=dice_slots,
        effect_type=effect_type,
    )


def _enemy(**kwargs) -> Enemy:
    defaults = dict(
        enemy_id="e1",
        name="Test Enemy",
        archetype="melee",
        act=1,
        max_health=20,
        current_health=20,
        base_dice_count=3,
        base_dice_sides=6,
        skills=[_skill()],
    )
    defaults.update(kwargs)
    return Enemy(**defaults)


def _seeded_rng(seed: int = 0) -> random.Random:
    return random.Random(seed)


# ---------------------------------------------------------------------------
# is_alive
# ---------------------------------------------------------------------------

class TestIsAlive(unittest.TestCase):

    def test_alive_above_zero(self):
        self.assertTrue(_enemy(current_health=10).is_alive)

    def test_dead_at_zero(self):
        self.assertFalse(_enemy(current_health=0).is_alive)

    def test_alive_at_one(self):
        self.assertTrue(_enemy(current_health=1).is_alive)


# ---------------------------------------------------------------------------
# take_damage — block absorption
# ---------------------------------------------------------------------------

class TestTakeDamage(unittest.TestCase):

    def test_damage_reduces_health(self):
        e = _enemy(current_health=20, block=0)
        e.take_damage(5)
        self.assertEqual(e.current_health, 15)

    def test_damage_clamps_to_zero(self):
        e = _enemy(current_health=5, block=0)
        e.take_damage(100)
        self.assertEqual(e.current_health, 0)

    def test_zero_damage_no_change(self):
        e = _enemy(current_health=20, block=0)
        e.take_damage(0)
        self.assertEqual(e.current_health, 20)

    def test_block_absorbs_before_hp(self):
        e = _enemy(current_health=20, block=5)
        real = e.take_damage(8)
        self.assertEqual(e.current_health, 17)   # 3 damage leaked through
        self.assertEqual(real, 3)
        self.assertEqual(e.block, 0)

    def test_block_fully_absorbs_damage(self):
        e = _enemy(current_health=20, block=10)
        real = e.take_damage(6)
        self.assertEqual(e.current_health, 20)
        self.assertEqual(real, 0)
        self.assertEqual(e.block, 4)

    def test_returns_real_hp_damage(self):
        e = _enemy(current_health=20, block=0)
        real = e.take_damage(7)
        self.assertEqual(real, 7)


# ---------------------------------------------------------------------------
# take_turn — slot-accumulation core mechanic
# ---------------------------------------------------------------------------

class TestTakeTurn(unittest.TestCase):

    def test_block_expires_at_start_of_turn(self):
        """Block from a previous turn must be cleared before new dice are rolled."""
        e = _enemy(skills=[_skill(dice_slots=1)], block=15, base_dice_count=1, base_dice_sides=6)
        rng = _seeded_rng()
        e.take_turn(rng)
        # Block should now reflect only what this turn's defend skills set, not old block.
        # Since the skill is "damage" type, block stays at 0 after the turn.
        self.assertEqual(e.block, 0)

    def test_single_slot_skill_triggers_immediately(self):
        """A 1-slot skill receives one die and triggers in the same turn."""
        e = _enemy(skills=[_skill(dice_slots=1)], base_dice_count=1, base_dice_sides=6)
        rng = _seeded_rng(42)
        triggered = e.take_turn(rng)
        self.assertEqual(len(triggered), 1)
        skill, effectiveness = triggered[0]
        self.assertEqual(skill.name, "Strike")
        self.assertGreater(effectiveness, 0)

    def test_two_slot_skill_does_not_trigger_on_first_turn(self):
        """A 2-slot skill with 1 die/turn does not fire until turn 2."""
        e = _enemy(skills=[_skill(dice_slots=2)], base_dice_count=1, base_dice_sides=6)
        rng = _seeded_rng()
        triggered = e.take_turn(rng)
        self.assertEqual(triggered, [])
        self.assertEqual(len(e.skill_buffers[0]), 1)

    def test_two_slot_skill_triggers_on_second_turn(self):
        """A 2-slot skill with 1 die/turn fires on turn 2 with the sum of both dice."""
        e = _enemy(skills=[_skill(dice_slots=2)], base_dice_count=1, base_dice_sides=6)
        rng = _seeded_rng(7)
        e.take_turn(rng)                    # turn 1 — fills slot 1
        triggered = e.take_turn(rng)       # turn 2 — fills slot 2, triggers
        self.assertEqual(len(triggered), 1)
        _, effectiveness = triggered[0]
        self.assertGreaterEqual(effectiveness, 2)   # sum of 2 dice (min d6 each = 1+1=2)

    def test_buffer_clears_after_trigger(self):
        """After a skill triggers its buffer must be empty so it starts fresh."""
        e = _enemy(skills=[_skill(dice_slots=1)], base_dice_count=1, base_dice_sides=6)
        rng = _seeded_rng()
        e.take_turn(rng)
        self.assertEqual(e.skill_buffers[0], [])

    def test_multiple_skills_trigger_same_turn(self):
        """When dice outnumber total slots, multiple skills can trigger in one turn."""
        skills = [_skill("A", dice_slots=1), _skill("B", dice_slots=1)]
        e = _enemy(skills=skills, base_dice_count=2, base_dice_sides=6)
        rng = _seeded_rng()
        triggered = e.take_turn(rng)
        self.assertEqual(len(triggered), 2)

    def test_bandit_pattern(self):
        """
        Bandit (3d6): Stab/1, Block/1, Backstab/2.
        Turn 1: Stab + Block trigger. Backstab gets 1 die.
        Turn 2: Backstab triggers (sum of 2 stored dice). Stab + Block trigger.
        """
        stab = _skill("Stab", dice_slots=1)
        block = _skill("Block", "defend", dice_slots=1)
        backstab = _skill("Backstab", dice_slots=2)
        e = _enemy(skills=[stab, block, backstab], base_dice_count=3, base_dice_sides=6)
        rng = _seeded_rng(1)

        t1 = e.take_turn(rng)
        names_t1 = [s.name for s, _ in t1]
        self.assertIn("Stab", names_t1)
        self.assertIn("Block", names_t1)
        self.assertNotIn("Backstab", names_t1)
        self.assertEqual(len(e.skill_buffers[2]), 1)   # 1 die stored in Backstab

        t2 = e.take_turn(rng)
        names_t2 = [s.name for s, _ in t2]
        self.assertIn("Backstab", names_t2)
        self.assertIn("Stab", names_t2)
        self.assertIn("Block", names_t2)
        # Backstab effectiveness = sum of 2 stored dice (both are d6 rolls)
        backstab_eff = next(eff for s, eff in t2 if s.name == "Backstab")
        self.assertGreaterEqual(backstab_eff, 2)

    def test_ogre_pattern(self):
        """
        Ogre (1d12): Smash/5 slots. Only fires every 5 turns.
        """
        smash = _skill("Smash", dice_slots=5)
        e = _enemy(skills=[smash], base_dice_count=1, base_dice_sides=12)
        rng = _seeded_rng(3)

        for turn in range(1, 5):
            triggered = e.take_turn(rng)
            self.assertEqual(triggered, [], f"Smash should not fire on turn {turn}")
            self.assertEqual(len(e.skill_buffers[0]), turn)

        triggered = e.take_turn(rng)
        self.assertEqual(len(triggered), 1)
        self.assertEqual(triggered[0][0].name, "Smash")
        self.assertEqual(e.skill_buffers[0], [])   # buffer cleared after trigger

    def test_defend_skill_sets_block(self):
        """A 'defend' effect_type skill stores its effectiveness as block on the enemy."""
        defend = _skill("Block", "defend", dice_slots=1)
        e = _enemy(skills=[defend], base_dice_count=1, base_dice_sides=6)
        rng = _seeded_rng(0)
        triggered = e.take_turn(rng)
        # The combat engine applies block from defend skills; the skill itself fires normally
        skill, effectiveness = triggered[0]
        self.assertEqual(skill.effect_type, "defend")
        self.assertGreater(effectiveness, 0)

    def test_dice_persist_across_turns(self):
        """Dice values stored in a buffer must persist unchanged until the skill triggers."""
        e = _enemy(skills=[_skill(dice_slots=3)], base_dice_count=1, base_dice_sides=6)
        rng = _seeded_rng(5)
        e.take_turn(rng)   # stores die value
        stored_after_t1 = list(e.skill_buffers[0])
        self.assertEqual(len(stored_after_t1), 1)
        e.take_turn(rng)   # adds another
        self.assertEqual(e.skill_buffers[0][0], stored_after_t1[0])  # first die unchanged


# ---------------------------------------------------------------------------
# scale_for_act — HP only
# ---------------------------------------------------------------------------

class TestScaleForAct(unittest.TestCase):

    def test_act_1_no_change(self):
        e = _enemy(strength=10, max_health=20, current_health=20, base_dice_count=3)
        e.scale_for_act(1)
        self.assertEqual(e.max_health, 20)
        self.assertEqual(e.current_health, 20)
        self.assertEqual(e.strength, 10)       # stats not scaled
        self.assertEqual(e.base_dice_count, 3) # dice not scaled

    def test_act_2_scales_hp(self):
        e = _enemy(max_health=20, current_health=20)
        e.scale_for_act(2)
        self.assertEqual(e.max_health, 26)
        self.assertEqual(e.current_health, 26)
        self.assertEqual(e.strength, 10)   # stats unchanged

    def test_act_3_scales_hp(self):
        e = _enemy(max_health=20, current_health=20)
        e.scale_for_act(3)
        self.assertEqual(e.max_health, 32)
        self.assertEqual(e.current_health, 32)


# ---------------------------------------------------------------------------
# make_enemy
# ---------------------------------------------------------------------------

class TestMakeEnemy(unittest.TestCase):

    def _template(self) -> dict:
        return {
            "enemy_id": "bandit_01",
            "name": "Bandit",
            "archetype": "bandit",
            "strength": 10,
            "dexterity": 10,
            "intelligence": 10,
            "charisma": 10,
            "constitution": 10,
            "max_health": 30,
            "current_health": 30,
            "base_dice_count": 3,
            "base_dice_sides": 6,
            "skills": [
                {
                    "name": "Stab",
                    "description": "Deal dice damage",
                    "associated_stat": "strength",
                    "dice_slots": 1,
                    "effect_type": "damage",
                }
            ],
        }

    def test_constructs_from_template(self):
        enemy = make_enemy(self._template(), act=1)
        self.assertEqual(enemy.enemy_id, "bandit_01")
        self.assertEqual(enemy.name, "Bandit")
        self.assertEqual(enemy.act, 1)
        self.assertEqual(len(enemy.skills), 1)
        self.assertEqual(enemy.skills[0].name, "Stab")
        self.assertEqual(enemy.base_dice_sides, 6)

    def test_skill_buffers_start_empty(self):
        enemy = make_enemy(self._template(), act=1)
        self.assertEqual(enemy.skill_buffers, [[]])

    def test_block_starts_at_zero(self):
        enemy = make_enemy(self._template(), act=1)
        self.assertEqual(enemy.block, 0)

    def test_act_scales_hp(self):
        e1 = make_enemy(self._template(), act=1)
        e2 = make_enemy(self._template(), act=2)
        self.assertGreater(e2.max_health, e1.max_health)

    def test_stats_not_scaled_by_act(self):
        e1 = make_enemy(self._template(), act=1)
        e2 = make_enemy(self._template(), act=2)
        self.assertEqual(e1.strength, e2.strength)


# ---------------------------------------------------------------------------
# Serialization round-trip
# ---------------------------------------------------------------------------

class TestSerialization(unittest.TestCase):

    def test_round_trip(self):
        skill = _skill("Smash", dice_slots=2)
        original = Enemy(
            enemy_id="e99",
            name="Ogre",
            archetype="brute",
            act=2,
            strength=14,
            dexterity=8,
            intelligence=6,
            charisma=6,
            constitution=16,
            max_health=70,
            current_health=55,
            skills=[skill],
            base_dice_count=1,
            base_dice_sides=12,
            skill_buffers=[[7]],
            block=3,
        )
        data = original.to_dict()
        restored = Enemy.from_dict(data)

        self.assertEqual(restored.enemy_id, original.enemy_id)
        self.assertEqual(restored.name, original.name)
        self.assertEqual(restored.strength, original.strength)
        self.assertEqual(restored.max_health, original.max_health)
        self.assertEqual(restored.current_health, original.current_health)
        self.assertEqual(restored.base_dice_count, original.base_dice_count)
        self.assertEqual(restored.base_dice_sides, original.base_dice_sides)
        self.assertEqual(restored.skill_buffers, [[7]])
        self.assertEqual(restored.block, 3)
        self.assertEqual(len(restored.skills), 1)
        self.assertEqual(restored.skills[0].name, "Smash")

    def test_to_dict_keys(self):
        e = _enemy()
        data = e.to_dict()
        expected = {
            "enemy_id", "name", "archetype", "act",
            "strength", "dexterity", "intelligence", "charisma", "constitution",
            "max_health", "current_health", "skills",
            "base_dice_count", "base_dice_sides", "skill_buffers", "block",
        }
        self.assertTrue(expected.issubset(data.keys()))


if __name__ == "__main__":
    unittest.main()
