import unittest
from game_runtime.event_bus import EventBus
from economy.guild_inventory import GuildInventory, InventoryItem


class TestGuildInventory(unittest.TestCase):
    def setUp(self):
        self.bus = EventBus()
        self.added_events = []
        self.removed_events = []
        self.full_events = []
        self.bus.subscribe("inventory.item_added", lambda d: self.added_events.append(d))
        self.bus.subscribe("inventory.item_removed", lambda d: self.removed_events.append(d))
        self.bus.subscribe("inventory.full", lambda d: self.full_events.append(d))

    def test_add_item_increases_count(self):
        inv = GuildInventory(self.bus, max_size=10)
        result = inv.add_item("sword_01", "Iron Sword", "weapon")
        self.assertTrue(result)
        self.assertEqual(inv.count, 1)

    def test_add_item_increments_quantity_for_same_id(self):
        inv = GuildInventory(self.bus, max_size=10)
        inv.add_item("potion_01", "Health Potion", "consumable")
        inv.add_item("potion_01", "Health Potion", "consumable")
        self.assertEqual(inv.count, 2)
        item = inv.get_item("potion_01")
        self.assertEqual(item.quantity, 2)

    def test_add_item_returns_false_when_full(self):
        inv = GuildInventory(self.bus, max_size=2)
        inv.add_item("a", "Item A", "cat")
        inv.add_item("b", "Item B", "cat")
        result = inv.add_item("c", "Item C", "cat")
        self.assertFalse(result)
        self.assertEqual(inv.count, 2)

    def test_add_item_publishes_inventory_full_when_full(self):
        inv = GuildInventory(self.bus, max_size=1)
        inv.add_item("a", "Item A", "cat")
        self.full_events.clear()
        inv.add_item("b", "Item B", "cat")
        self.assertEqual(len(self.full_events), 1)

    def test_remove_item_decrements_quantity(self):
        inv = GuildInventory(self.bus, max_size=10)
        inv.add_item("potion_01", "Health Potion", "consumable")
        inv.add_item("potion_01", "Health Potion", "consumable")
        removed = inv.remove_item("potion_01")
        self.assertIsNotNone(removed)
        self.assertEqual(inv.count, 1)
        item = inv.get_item("potion_01")
        self.assertIsNotNone(item)
        self.assertEqual(item.quantity, 1)

    def test_remove_item_removes_entry_when_quantity_reaches_zero(self):
        inv = GuildInventory(self.bus, max_size=10)
        inv.add_item("sword_01", "Iron Sword", "weapon")
        inv.remove_item("sword_01")
        self.assertIsNone(inv.get_item("sword_01"))
        self.assertEqual(inv.count, 0)

    def test_remove_item_returns_none_for_unknown(self):
        inv = GuildInventory(self.bus, max_size=10)
        result = inv.remove_item("nonexistent")
        self.assertIsNone(result)

    def test_item_added_event_published(self):
        inv = GuildInventory(self.bus, max_size=10)
        inv.add_item("sword_01", "Iron Sword", "weapon")
        self.assertEqual(len(self.added_events), 1)
        self.assertEqual(self.added_events[0]["item_id"], "sword_01")

    def test_item_removed_event_published(self):
        inv = GuildInventory(self.bus, max_size=10)
        inv.add_item("sword_01", "Iron Sword", "weapon")
        self.removed_events.clear()
        inv.remove_item("sword_01")
        self.assertEqual(len(self.removed_events), 1)
        self.assertEqual(self.removed_events[0]["item_id"], "sword_01")

    def test_to_dict_from_dict_round_trip(self):
        inv = GuildInventory(self.bus, max_size=15)
        inv.add_item("sword_01", "Iron Sword", "weapon")
        inv.add_item("potion_01", "Health Potion", "consumable")
        inv.add_item("potion_01", "Health Potion", "consumable")
        data = inv.to_dict()
        new_bus = EventBus()
        restored = GuildInventory.from_dict(data, new_bus)
        self.assertEqual(restored.count, 3)
        sword = restored.get_item("sword_01")
        self.assertIsNotNone(sword)
        self.assertEqual(sword.quantity, 1)
        potion = restored.get_item("potion_01")
        self.assertIsNotNone(potion)
        self.assertEqual(potion.quantity, 2)


if __name__ == "__main__":
    unittest.main()
