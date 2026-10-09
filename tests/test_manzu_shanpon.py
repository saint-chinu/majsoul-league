import unittest
from collections import Counter

import aggregate_league as a


class ManzuShanponTests(unittest.TestCase):
    def classify(self, first, second, indicators=()):
        tiles = [first, first, second, second] + "1s 2s 3s 4s 5s 6s 7s 8s 9s".split()
        return a.classify_riichi_quality(tiles, [first, second], Counter(), 0, 0, 0, indicators)

    def test_manzu_middle_pairs(self):
        for manzu in ("1m", "9m"):
            for suit in ("p", "s"):
                for number in range(3, 8):
                    with self.subTest(manzu=manzu, suit=suit, number=number):
                        key = self.classify(manzu, f"{number}{suit}")
                        self.assertEqual(key, "manzu_simple_shanpon")
                        self.assertEqual(a.RIICHI_QUALITY_SCORE[key], 0)

    def test_other_categories_unchanged(self):
        self.assertEqual(self.classify("1m", "9p"), "yaochu_shanpon")
        self.assertEqual(self.classify("5z", "5p"), "yakuhai_simple_shanpon")
        self.assertEqual(self.classify("1m", "2p"), "bad_two_or_less")
        self.assertEqual(self.classify("1m", "8p"), "bad_two_or_less")

    def test_red_and_dora(self):
        self.assertEqual(self.classify("9m", "0p", ["4p"]), "manzu_simple_shanpon")

    def test_bulge_override(self):
        tiles = "1m 1m 3p 4p 4p 4p 5p 1s 2s 3s 7s 8s 9s".split()
        self.assertEqual(set(a.winning_waits(tiles)), {"1m", "4p"})
        self.assertEqual(a.classify_riichi_quality(tiles, [], Counter(), 0, 0, 0, []),
                         "manzu_simple_shanpon")


if __name__ == "__main__":
    unittest.main()
