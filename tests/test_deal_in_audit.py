import json
import tempfile
import unittest
from collections import defaultdict
from pathlib import Path
from unittest.mock import patch

import aggregate_league as league
import deal_in_audit as audit
import make_site as site
import run_auto_update as updater
from types import SimpleNamespace


class DealInAuditTests(unittest.TestCase):
    def test_missing_sources_preserve_complete_export(self):
        with tempfile.TemporaryDirectory() as folder, patch.object(audit, 'OUTPUT_DIR', Path(folder)), patch.object(league, 'has_record_files', return_value=False):
            path = Path(folder) / 'old-season-1.json'
            path.write_text(json.dumps({'game_ids': ['game'], 'rule_version': audit.RULE_VERSION,
                                        'missing_games': [], 'events': []}), encoding='utf-8')
            audit.export_audit({'old-season-1': {'game'}}, [])
            self.assertEqual(json.loads(path.read_text(encoding='utf-8'))['game_ids'], ['game'])
            before = path.read_bytes()
            with self.assertRaises(ValueError):
                audit.export_audit({'old-season-1': {'changed-game'}}, [])
            self.assertEqual(path.read_bytes(), before)

    def test_first_turn_robbed_kita_evidence(self):
        uuid = '260708-48545994-4060-48f2-a79d-dae923dacfd4'
        if not league.has_record_files(uuid):
            self.skipTest('Local kita fixture unavailable')
        with tempfile.TemporaryDirectory() as folder, patch.object(audit, 'CACHE_DIR', Path(folder)):
            evidence = audit.game_evidence(uuid)[uuid + ':56:0']
        self.assertEqual((evidence['action'], evidence['turn'], evidence['tile']), ('kita', 1, '4z'))

    def test_auto_update_stages_audit_data(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            data = root / 'docs/deal-in-audit'
            data.mkdir(parents=True)
            (data / 'index.json').write_text('{}', encoding='utf-8')
            (data / 'new-season-8.json').write_text('{}', encoding='utf-8')
            with patch.object(updater, 'ROOT', root), patch.object(updater, 'NEW_DATA_DIR', root / 'data/new'), patch.object(updater, 'find_git', return_value='git'), patch.object(updater.subprocess, 'run', return_value=SimpleNamespace(returncode=0)) as run:
                updater.commit_and_push({}, root / 'season.csv')
            staged = run.call_args_list[0].args[0]
            self.assertIn(str(Path('docs/deal-in-audit/index.json')), staged)
            self.assertIn(str(Path('docs/deal-in-audit/new-season-8.json')), staged)

    def test_scoring_still_stacks_conditions(self):
        categories, score = league.classify_deal_in_event(
            0, 1, 12000, None, [50000, 30000, 25000], [38000, 42000, 25000],
            2, {'riichi': False}, True, 0, True, False, False, 1, 2)
        self.assertEqual(set(categories), {'two_shanten_or_worse_vs_riichi', 'late_noten_deal_in',
                                           'top_haneman_deal_in', 'oorasu_rank_drop_deal_in'})
        self.assertEqual(score, -30)

    def test_score_link_preserves_player_and_scope(self):
        html = site.deal_in_quality_score_cell({'player': 'A&B', 'deal_in_audit_scope': 'old-season-2',
            'deal_in_quality_score': '-3', 'deal_in_quality_breakdown': 'bad_shape_riichi_deal_in:2'})
        self.assertIn('scope=old-season-2', html)
        self.assertIn('player=A%26B', html)
        self.assertIn('-6', html)

    def test_cache_invalidates_on_source_change(self):
        with tempfile.TemporaryDirectory() as folder, patch.object(audit, 'CACHE_DIR', Path(folder)):
            with patch.object(audit, 'fingerprint', return_value=['v1']):
                audit.save_game_audit('game', [])
                with patch.object(league, 'aggregate_game') as aggregate:
                    self.assertEqual(audit.game_events('game'), [])
                    aggregate.assert_not_called()
            with patch.object(audit, 'fingerprint', return_value=['v2']), patch.object(league, 'aggregate_game') as aggregate:
                audit.game_events('game')
                aggregate.assert_called_once()

    def test_saved_replay_events_match_original_totals(self):
        path = next(league.RAW_DIR.glob('*_record.bin'), None)
        if path is None:
            self.skipTest('Local replay fixture unavailable')
        uuid = path.name.removesuffix('_record.bin')
        stats, baseline, events = defaultdict(league.PlayerStats), defaultdict(league.PlayerStats), []
        league.aggregate_game(uuid, baseline, [])
        league.aggregate_game(uuid, stats, [], events)
        self.assertEqual(stats, baseline)
        self.assertEqual(len(events), len({e['id'] for e in events}))
        for name, stat in stats.items():
            own = [e for e in events if e['player'] == name]
            self.assertEqual(len(own), stat.deal_in_events)
            self.assertEqual(sum(e['score'] for e in own), stat.deal_in_quality_score_sum)
        for event in events:
            self.assertGreater(event['round_no'], 0)
            self.assertGreater(event['turn'], 0)
            self.assertTrue(event['tile'])
            self.assertEqual(sum(league.DEAL_IN_QUALITY_SCORE[c] for c in event['categories']), event['score'])


if __name__ == '__main__':
    unittest.main()
