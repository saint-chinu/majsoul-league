import unittest
from aggregate_league import classify_deal_in_event


class TopDealInTests(unittest.TestCase):
    def test_boundary_and_round(self):
        for chang, points, expected in ((0,39900,False),(0,40000,False),(0,40100,True),(1,40000,True),(2,40000,True)):
            cats, score = classify_deal_in_event(0,1,12000,None,[points,33000,32000],[],
                0,{'riichi':False},False,0,True,False,False,chang,0)
            self.assertEqual('top_haneman_deal_in' in cats,expected)
            self.assertIn('late_noten_deal_in',cats)
            self.assertEqual(score,-13 if expected else -5)

    def test_actual_points_after_riichi_deposit(self):
        cats, _ = classify_deal_in_event(0,1,12000,None,[41000,33000,31000],[],
            0,{'riichi':True,'good_shape':True},False,0,False,False,False,0,1,
            loser_points_before=40000)
        self.assertNotIn('top_haneman_deal_in',cats)

    def test_zero_scoring_still_counts_as_event(self):
        cats,score=classify_deal_in_event(0,1,12000,None,[40000,33000,32000],[],
            0,{'riichi':False},False,0,False,False,False,0,0)
        self.assertEqual((cats,score),(['other_deal_in'],0))
