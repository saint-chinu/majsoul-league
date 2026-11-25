import unittest

from aggregate_league import classify_deal_in_event


class ChildToDealerDealInTests(unittest.TestCase):
    def classify(self, loser=1, winner=0, dealer=0, riichi=False,
                 declaration=False, late=False, payment=1000, chang=0):
        return classify_deal_in_event(
            loser, winner, payment, None, [35000, 40000, 30000], [],
            0, {'riichi': riichi, 'good_shape': True}, False, 0,
            late, declaration, False, chang, dealer,
        )

    def test_all_seat_combinations(self):
        for dealer in range(3):
            for loser in range(3):
                for winner in range(3):
                    if loser == winner:
                        continue
                    with self.subTest(dealer=dealer, loser=loser, winner=winner):
                        cats, score = self.classify(loser, winner, dealer)
                        expected = loser != dealer and winner == dealer
                        self.assertEqual('nonriichi_child_to_dealer' in cats, expected)
                        self.assertEqual(score, -3 if expected else 0)

    def test_riichi_and_declaration_excluded(self):
        for riichi, declaration in ((True, False), (False, True), (True, True)):
            cats, _ = self.classify(riichi=riichi, declaration=declaration)
            self.assertNotIn('nonriichi_child_to_dealer', cats)

    def test_stacks_and_east_exception_only_removes_top_penalty(self):
        cats, score = self.classify(late=True, payment=12000)
        self.assertIn('late_noten_deal_in', cats)
        self.assertIn('nonriichi_child_to_dealer', cats)
        self.assertNotIn('top_haneman_deal_in', cats)
        self.assertEqual(score, -8)
        cats, score = self.classify(late=True, payment=12000, chang=1)
        self.assertIn('top_haneman_deal_in', cats)
        self.assertEqual(score, -16)

    def test_double_ron_only_dealer_event_penalized(self):
        self.assertEqual(self.classify(loser=1, winner=0)[1], -3)
        self.assertEqual(self.classify(loser=1, winner=2)[1], 0)
