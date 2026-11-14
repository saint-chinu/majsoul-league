import json
import unittest

import make_site as site


class SiteRankingTests(unittest.TestCase):
    def setUp(self):
        self.rows = [
            {"player": "A", "games": "100", "average_rank": "2", "earned_score": "10"},
            {"player": "B", "games": "30", "average_rank": "2", "earned_score": "10"},
            {"player": "C", "games": "40", "average_rank": "2.5", "earned_score": "0"},
            {"player": "D", "games": "29", "average_rank": "1", "earned_score": "20"},
        ]

    def test_qualification_boundary_and_competition_ties(self):
        self.assertEqual(site.min_games_for(self.rows), 30)
        for name, expected in [("A", 1), ("B", 1), ("C", 3), ("D", 0)]:
            self.assertEqual(site.metric_rank(self.rows, name, "average_rank", False, True), (expected, 3))
        self.assertEqual(site.metric_rank(self.rows, "D", "earned_score", True, True), (1, 4))

    def test_tied_worst_and_reference_styles(self):
        self.rows[0]["average_rank"] = "2.5"
        for name in ["A", "C"]:
            item = next(r for r in site.player_metric_rank_rows(name, self.rows) if r["metric"] == site.LABELS["average_rank"])
            self.assertEqual(item["is_worst"], "1")
            self.assertEqual(item["rank_text"], "2 / 3")
        item = next(r for r in site.player_metric_rank_rows("D", self.rows) if r["metric"] == site.LABELS["average_rank"])
        self.assertIn("参考", item["rank_text"])
        self.assertFalse(item["is_best"] or item["is_worst"])

    def test_metadata_and_empty_ranking(self):
        data = json.loads(site.metric_directions_script().split(">", 1)[1].split("</script>")[0])
        self.assertEqual(data["directions"][site.LABELS["houjuu_rate"]], "low")
        self.assertEqual(data["directions"][site.LABELS["called_rate"]], "high-plain")
        self.assertIn(site.LABELS["winning_run_points"], data["countMetrics"])
        self.assertEqual(site.metric_rank([], "A", "average_rank", False, True), (0, 0))

    def test_rounding_and_ceiling(self):
        self.rows[0]["games"] = "103"
        self.assertEqual(site.min_games_for(self.rows), 31)
        self.assertFalse(site.is_qualified(self.rows[1], self.rows))
        self.rows[0]["average_hu_point"] = "10000.1"
        self.rows[2]["average_hu_point"] = "10000.2"
        self.assertEqual(site.displayed_metric_value(self.rows[0], "average_hu_point"),
                         site.displayed_metric_value(self.rows[2], "average_hu_point"))
        self.assertEqual(site.metric_rank(self.rows, "C", "average_hu_point", True, True)[0], 1)


if __name__ == "__main__":
    unittest.main()
