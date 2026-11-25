import unittest
from collections import Counter
from types import SimpleNamespace as M

from deal_in_suji import SujiTracker, categories_for, suji_evidence
import aggregate_league as league


class SujiTests(unittest.TestCase):
    def test_note_mapping(self):
        for source, targets in {2: (4, 7), 3: (5, 8), 4: (6, 9), 6: (1, 4), 7: (2, 5), 8: (3, 6)}.items():
            for target in targets:
                self.assertIn('senki_nonriichi', categories_for(suji_evidence(f'{target}p', [f'{source}p'], Counter())))
        for tile in ('1p', '5p', '9p'):
            self.assertEqual(categories_for(suji_evidence('6p', [tile], Counter())), [])

    def test_anko_is_pair_total_not_four_of_one_tile(self):
        for count, expected in ((1, False), (2, True), (3, True)):
            evidence = suji_evidence('3p', [], Counter({'3p': 2, '6p': count}))
            self.assertEqual('anko_suji_nonriichi' in categories_for(evidence), expected)

    def test_red_five_and_same_pair_overlap(self):
        e = suji_evidence('0p', ['3p'], Counter({'5p': 2, '8p': 2}))
        self.assertEqual(categories_for(e), ['senki_nonriichi', 'anko_suji_nonriichi', 'honmei_suji_overlap'])
        e = suji_evidence('4p', ['2p'], Counter({'1p': 3, '4p': 1}))
        self.assertEqual(categories_for(e), ['senki_nonriichi', 'anko_suji_nonriichi'])

    def test_furiten_wall_other_suit_honors_manzu(self):
        for river, visible in ((['3p', '8p'], {'5p': 2, '8p': 2}),
                               (['3p'], {'5p': 2, '8p': 2, '6p': 4})):
            self.assertEqual(categories_for(suji_evidence('5p', river, Counter(visible))), [])
        self.assertEqual(categories_for(suji_evidence('5p', ['3s'], Counter())), [])
        for t in ('1m', '9m', '5z'):
            self.assertEqual(suji_evidence(t, ['3p'], Counter()), [])

    def test_half_suji_does_not_erase_other_pair(self):
        e = suji_evidence('4p', ['1p', '2p'], Counter({'4p': 2, '7p': 2}))
        self.assertEqual(e[0]['pair'], ['4p', '7p'])
        self.assertTrue(e[0]['overlap'])

    def score(self, patterns, riichi=False, declaration=False):
        return league.classify_deal_in_event(0, 1, 4000, None, [35000]*3, [31000,39000,35000],
            0, {'riichi': riichi, 'good_shape': True}, False, 0, False, declaration, False, 0, 1, patterns)

    def test_points_and_riichi_exclusion(self):
        e = suji_evidence('5p', ['3p'], Counter({'5p': 2, '8p': 2}))
        self.assertEqual(self.score(e)[1], -15)
        self.assertEqual(self.score(e, riichi=True)[1], 0)
        self.assertEqual(self.score(e, declaration=True)[1], 0)
        self.assertEqual(self.score(suji_evidence('5p', ['3p'], Counter()))[1], -5)
        self.assertEqual(self.score(suji_evidence('5p', [], Counter({'5p': 2, '8p': 2})))[1], -3)

    def tracker(self):
        t = SujiTracker()
        t.observe('.lq.RecordNewRound', M(tiles0=['0p','8p'], tiles1=['3p','8p'], tiles2=['8p'], doras=['5p']))
        return t

    def discard(self, t, seat, tile, **kw):
        t.observe('.lq.RecordDiscardTile', M(seat=seat, tile=tile, is_liqi=False, is_wliqi=False, **kw))

    def test_only_visible_tiles_before_discard(self):
        t = self.tracker()
        self.discard(t, 1, '3p')
        self.discard(t, 0, '0p')
        e = t.evidence(0, 1)[0]
        self.assertEqual(e['visible'], [2, 1])  # hand + indicator, not opponents' hands
        self.assertFalse(e['anko'])
        self.assertEqual(t.evidence(0, 2), [])

    def test_exposed_tiles_and_doras_not_double_counted(self):
        t = self.tracker()
        self.discard(t, 2, '8p')
        self.discard(t, 1, '3p')
        self.discard(t, 0, '0p', doras=['5p'])
        e = t.evidence(0, 1)[0]
        self.assertEqual(e['visible'], [2, 2])
        self.assertTrue(e['overlap'])

    def test_calls_kans_and_robbery_not_discard(self):
        t = SujiTracker()
        t.observe('.lq.RecordNewRound', M(tiles0=['6p']*4+['5p']*3, tiles1=['5p'], tiles2=[], doras=[]))
        t.observe('.lq.RecordAnGangAddGang', M(seat=0, type=3, tiles='6p'))
        self.assertEqual(t.public['6p'], 4)
        self.assertEqual(t.hands[0]['6p'], 0)
        self.discard(t, 1, '5p')
        t.observe('.lq.RecordChiPengGang', M(seat=0, tiles=['5p']*3, froms=[0,0,1]))
        self.assertEqual(t.public['5p'], 3)
        t.observe('.lq.RecordAnGangAddGang', M(seat=0, type=2, tiles='5p'))
        self.assertEqual(t.public['5p'], 4)
        self.assertEqual(t.evidence(0, 1), [])

    def test_reset_and_declaration_excluded(self):
        t = self.tracker()
        self.discard(t, 1, '3p')
        t.observe('.lq.RecordDiscardTile', M(seat=0,tile='0p',is_liqi=True,is_wliqi=False))
        self.assertEqual(t.evidence(0, 1), [])
        t.observe('.lq.RecordNewRound', M(tiles0=[],tiles1=[],tiles2=[],doras=[]))
        self.assertEqual(t.riichi, set())
        self.assertEqual(t.rivers[1], [])

    def test_kokushi_signal_types_and_north(self):
        t = SujiTracker()
        t.rivers[1] = ['1p', '1p', '5p', '4z']
        t.kita.add(1)
        self.assertEqual(t.kokushi_signals(1), ['1p', '4z'])
        t.rivers[1].append('7z')
        self.assertEqual(len(t.kokushi_signals(1)), 3)
        t.rivers[2] = ['9m']
        self.assertEqual(t.kokushi_signals(2), ['9m'])

    def test_kokushi_score_exclusive_tiers_and_riichi(self):
        for signals, score in ((['1p'], 0), (['1p','4z'], -15), (['1p','4z','7z'], -25), (['1p','4z','7z','9m'], -25)):
            for riichi in (False, True):
                cats, value = league.classify_deal_in_event(0,1,8000,None,[35000]*3,[27000,43000,35000],
                    0,{'riichi':riichi,'good_shape':True},False,0,False,False,False,0,1,[],signals)
                self.assertEqual(value, 0 if riichi else score)
                self.assertFalse('kokushi_two_signals' in cats and 'kokushi_three_signals' in cats)

    def test_cumulative_quality_uses_ron_events_not_rounds(self):
        import make_site as site
        rows=[{'player':'A','games':'1','rounds':'10','houjuu_rate':'10%',
               'deal_in_event_count':'2','deal_in_quality_score':'-7.5',
               'deal_in_quality_breakdown':'senki_nonriichi:1|anko_suji_nonriichi:1|honmei_suji_overlap:1'}]
        combined=site.combine_player_rows([{'rows':rows}])[0]
        self.assertEqual(combined['deal_in_event_count'],'2')
        self.assertEqual(float(combined['deal_in_quality_score']),-7.5)


if __name__ == '__main__':
    unittest.main()
