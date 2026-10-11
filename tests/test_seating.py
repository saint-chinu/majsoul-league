import csv
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from build_seating import PLAYERS, build_data, apply_combination_cap


class SeatingImportTests(unittest.TestCase):
    def make(self, root, rows):
        path = root / 'data/new/admin_paifu_ids_new_season4.csv'
        path.parent.mkdir(parents=True)
        with path.open('w', newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=['season','uuid'])
            writer.writeheader(); writer.writerows(rows)

    def loader(self, path, uuid):
        return SimpleNamespace(players=[SimpleNamespace(account_id=p['id'], nickname='Changed') for p in PLAYERS[:3]], start_time=10, end_time=20)

    def test_empty_never_uses_old_league(self):
        with tempfile.TemporaryDirectory() as t:
            root=Path(t); (root/'admin_paifu_ids_season4.csv').write_text('old')
            d=build_data(root,self.loader)
            self.assertFalse(d['source_available']); self.assertEqual(d['records'],[])

    def test_cap_uses_start_not_end_or_input_order(self):
        records = [{'uuid': str(i), 'players': [3, 1, 2], 'start': i, 'end': 100-i}
                   for i in [5, 2, 4, 1, 3]]
        valid, excluded = apply_combination_cap(records)
        self.assertEqual([r['uuid'] for r in valid], ['1', '2', '3'])
        self.assertEqual([r['uuid'] for r in excluded], ['4', '5'])
        self.assertEqual([r['occurrence'] for r in excluded], [4, 5])
        valid2, excluded2 = apply_combination_cap(records + [{'uuid':'6','players':[1,2,4],'start':6,'end':7}])
        self.assertEqual(len(valid2), 4)
        self.assertEqual(len(excluded2), 2)

    def test_deduplicate_and_match_by_account(self):
        with tempfile.TemporaryDirectory() as t:
            root=Path(t); self.make(root,[{'season':'4','uuid':'abcdef'}]*2)
            d=build_data(root,self.loader)
            self.assertEqual(len(d['records']),1); self.assertEqual(d['issues'],[])

    def test_over_recommended_games_remain_valid(self):
        with tempfile.TemporaryDirectory() as t:
            root=Path(t)
            self.make(root,[{'season':'4','uuid':str(i)} for i in range(5)])
            d=build_data(root,self.loader)
            self.assertEqual(len(d['records']),5)
            self.assertEqual(d['excluded'],[])
            self.assertEqual(len(d['over_recommended']),2)

    def test_wrong_season_missing_and_unknown_players(self):
        with tempfile.TemporaryDirectory() as t:
            root=Path(t); self.make(root,[{'season':'3','uuid':'aa'},{'season':'4','uuid':'bb'},{'season':'4','uuid':'cc'}])
            def loader(path,uuid):
                if uuid=='bb': raise FileNotFoundError()
                entry=self.loader(path,uuid); entry.players[0].account_id=1; return entry
            d=build_data(root,loader)
            self.assertEqual(len(d['issues']),3); self.assertEqual(d['records'],[])


if __name__=='__main__': unittest.main()
