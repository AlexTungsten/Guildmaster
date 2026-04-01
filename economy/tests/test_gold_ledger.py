import unittest
from game_runtime.event_bus import EventBus
from economy.gold_ledger import GoldLedger, Transaction


class TestGoldLedger(unittest.TestCase):
    def setUp(self):
        self.bus = EventBus()
        self.events = []
        self.bus.subscribe("gold.earned", lambda d: self.events.append(("gold.earned", d)))
        self.bus.subscribe("gold.spent", lambda d: self.events.append(("gold.spent", d)))
        self.bus.subscribe("gold.insufficient", lambda d: self.events.append(("gold.insufficient", d)))

    def test_starting_balance(self):
        ledger = GoldLedger(self.bus, starting_gold=250)
        self.assertEqual(ledger.balance, 250)

    def test_default_starting_balance(self):
        ledger = GoldLedger(self.bus)
        self.assertEqual(ledger.balance, 100)

    def test_earn_increases_balance_and_returns_new_balance(self):
        ledger = GoldLedger(self.bus, starting_gold=50)
        result = ledger.earn(30)
        self.assertEqual(result, 80)
        self.assertEqual(ledger.balance, 80)

    def test_spend_decreases_balance_and_returns_true(self):
        ledger = GoldLedger(self.bus, starting_gold=100)
        result = ledger.spend(40)
        self.assertTrue(result)
        self.assertEqual(ledger.balance, 60)

    def test_spend_insufficient_returns_false_no_change(self):
        ledger = GoldLedger(self.bus, starting_gold=20)
        result = ledger.spend(50)
        self.assertFalse(result)
        self.assertEqual(ledger.balance, 20)

    def test_gold_earned_event_published(self):
        ledger = GoldLedger(self.bus, starting_gold=0)
        ledger.earn(10, reason="test_earn")
        self.assertEqual(len(self.events), 1)
        event_type, data = self.events[0]
        self.assertEqual(event_type, "gold.earned")
        self.assertEqual(data["amount"], 10)
        self.assertEqual(data["balance"], 10)
        self.assertEqual(data["reason"], "test_earn")

    def test_gold_spent_event_published(self):
        ledger = GoldLedger(self.bus, starting_gold=100)
        ledger.spend(25, reason="test_purchase")
        self.assertEqual(len(self.events), 1)
        event_type, data = self.events[0]
        self.assertEqual(event_type, "gold.spent")
        self.assertEqual(data["amount"], 25)
        self.assertEqual(data["balance"], 75)
        self.assertEqual(data["reason"], "test_purchase")

    def test_gold_insufficient_event_published(self):
        ledger = GoldLedger(self.bus, starting_gold=10)
        ledger.spend(50)
        self.assertEqual(len(self.events), 1)
        event_type, data = self.events[0]
        self.assertEqual(event_type, "gold.insufficient")
        self.assertEqual(data["amount"], 50)
        self.assertEqual(data["balance"], 10)

    def test_history_records_all_transactions(self):
        ledger = GoldLedger(self.bus, starting_gold=100)
        ledger.earn(50, reason="quest")
        ledger.spend(30, reason="shop")
        history = ledger.history
        self.assertEqual(len(history), 2)
        self.assertEqual(history[0].amount, 50)
        self.assertEqual(history[0].reason, "quest")
        self.assertEqual(history[0].balance_after, 150)
        self.assertEqual(history[1].amount, 30)
        self.assertEqual(history[1].reason, "shop")
        self.assertEqual(history[1].balance_after, 120)

    def test_history_returns_copy(self):
        ledger = GoldLedger(self.bus, starting_gold=100)
        ledger.earn(10)
        history = ledger.history
        history.clear()
        self.assertEqual(len(ledger.history), 1)

    def test_to_dict_from_dict_round_trip(self):
        ledger = GoldLedger(self.bus, starting_gold=100)
        ledger.earn(50, reason="quest")
        ledger.spend(20, reason="item")
        data = ledger.to_dict()
        new_bus = EventBus()
        restored = GoldLedger.from_dict(data, new_bus)
        self.assertEqual(restored.balance, ledger.balance)
        self.assertEqual(len(restored.history), 2)
        self.assertEqual(restored.history[0].amount, 50)
        self.assertEqual(restored.history[0].reason, "quest")
        self.assertEqual(restored.history[1].amount, 20)
        self.assertEqual(restored.history[1].reason, "item")


if __name__ == "__main__":
    unittest.main()
