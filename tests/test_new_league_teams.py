import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import make_site as site


class NewLeagueTeamTests(unittest.TestCase):
    def test_team_sources_are_separate(self):
        self.assertNotEqual(site.TEAM_CSV, site.NEW_TEAM_CSV)
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'teams.csv'
            path.write_text('season,team,player\n8,Blue,A\n8,Blue,A\n8,Red,B\n', encoding='utf-8')
            self.assertEqual(site.read_team_members(path), {8: {'Blue': ['A'], 'Red': ['B']}})

    def test_member_scores_are_summed_with_unplayed_members(self):
        rows = [{'player': 'A', 'games': '2', 'earned_score': '10.2'},
                {'player': 'B', 'games': '3', 'earned_score': '-3.1'},
                {'player': 'C', 'games': '1', 'earned_score': '-7.1'}]
        result = site.build_team_rows(rows, {'Blue': ['A', 'B', 'D'], 'Red': ['C']})
        self.assertEqual(result[0]['total_score'], 7.1)
        self.assertEqual(result[0]['total_games'], 5)
        self.assertIn('D', result[0]['member_details'])
        self.assertEqual(sum(r['total_score'] for r in result), 0)

    def test_only_completed_season_counts_as_team_championship(self):
        teams = [{'team': 'Blue', 'members': 'A / B'}]
        ongoing = {'label': '\u65b0\u30b7\u30fc\u30ba\u30f38\uff08\u9032\u884c\u4e2d\uff09', 'team_rows': teams}
        complete = {'label': '\u65b0\u30b7\u30fc\u30ba\u30f38', 'team_rows': teams}
        self.assertEqual(site.team_champion_rows([ongoing]), [])
        self.assertEqual([r['wins'] for r in site.team_champion_rows([ongoing, complete])], [1, 1])

    def test_team_average_uses_finish_counts_and_game_weights(self):
        rows = [
            {'player': 'A', 'games': '3', 'average_rank': '1.33',
             'rank1_rate': '66.67%', 'rank2_rate': '33.33%', 'rank3_rate': '0%'},
            {'player': 'B', 'games': '1', 'average_rank': '3.0',
             'rank1_rate': '0%', 'rank2_rate': '0%', 'rank3_rate': '100%'},
        ]
        result = site.build_team_rows(rows, {'Blue': ['A', 'B', 'C'], 'Empty': ['D']})
        self.assertEqual(result[0]['average_rank'], 1.75)
        self.assertIsNone(result[1]['average_rank'])

    def test_cards_only_for_mapped_seasons_and_escape_names(self):
        context = {'key': 'new-season-8', 'rows': [
            {'player': 'A', 'games': '1', 'earned_score': '10', 'rank1_rate': '100%'},
            {'player': 'B', 'games': '1', 'earned_score': '10', 'rank2_rate': '100%'},
            {'player': 'C', 'games': '1', 'earned_score': '-20', 'rank3_rate': '100%'},
        ]}
        with patch.object(site, 'read_team_members', return_value={8: {'<Blue>': ['A'], 'Red': ['B'], 'Green': ['C']}}) as read:
            html = site.team_summary_cards(context)
            read.assert_called_with(site.NEW_TEAM_CSV)
            self.assertIn('&lt;Blue&gt;', html)
            self.assertEqual(html.count('team-summary-rank">1'), 2)
            self.assertIn('team-summary-rank">3', html)
            self.assertIn('>1.00<', html)
            self.assertIn('team-score-negative">-20.0', html)
            self.assertEqual(site.team_summary_cards({**context, 'key': 'new-season-7'}), '')
            self.assertEqual(site.team_summary_cards({**context, 'is_cumulative': True}), '')
            self.assertEqual(site.team_summary_cards({**context, 'key': 'new-league'}), '')
            site.team_summary_cards({**context, 'key': 'old-season-8'})
            read.assert_called_with(site.TEAM_CSV)

    def test_team_mapping_passed_to_each_season(self):
        teams = {8: {'Blue': ['A']}}
        with patch.object(site, 'build_context', return_value={}) as build:
            site.build_season_contexts({8: {'uuid'}}, 'new', 'Season', 135, teams)
        self.assertEqual(build.call_args.kwargs['teams_by_season'], teams)
        self.assertEqual(build.call_args.kwargs['season'], 8)


if __name__ == '__main__':
    unittest.main()
