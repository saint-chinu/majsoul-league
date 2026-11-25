"""Visible-information-only suji evidence, using the league owner's note rules."""
from collections import Counter

NOTE_URL = 'https://note.com/tanyao_chanta/n/n8076a9342703'
# Only the six explicit pairs in the note; 1/9 and the 5 exception are not scored.
SENKI = {2: (4, 7), 3: (5, 8), 4: (6, 9), 6: (1, 4), 7: (2, 5), 8: (3, 6)}
SUJI_KEYS = ('senki_nonriichi', 'anko_suji_nonriichi', 'honmei_suji_overlap')


def normalized(tile):
    return '5' + tile[1:] if tile.startswith('0') else tile


def suji_evidence(tile, river, visible, hand=None):
    tile = normalized(tile)
    if len(tile) != 2 or tile[1] not in 'ps' or tile[0] not in '123456789':
        return []
    number, suit = int(tile[0]), tile[1]
    river = [normalized(t) for t in river]
    hand = hand or Counter()
    pairs = []
    for low in range(1, 7):
        high = low + 3
        if number not in (low, high):
            continue
        ends = [f'{n}{suit}' for n in (low, high)]
        middle = [f'{n}{suit}' for n in (low + 1, low + 2)]
        if any(t in river for t in ends) or any(visible[t] >= 4 for t in middle):
            continue
        sources = sorted({t for t in river if len(t) == 2 and t[1] == suit and SENKI.get(int(t[0])) == (low, high)})
        counts = [visible[t] for t in ends]
        anko = sum(counts) >= 4
        if sources or anko:
            pairs.append({'pair': ends, 'senki_sources': sources, 'visible': counts,
                          'hand': [hand[t] for t in ends], 'middle_visible': [visible[t] for t in middle],
                          'anko': anko, 'overlap': bool(sources) and anko})
    return pairs


def categories_for(evidence):
    return [key for key, matches in zip(SUJI_KEYS, (
        any(p['senki_sources'] for p in evidence), any(p['anko'] for p in evidence),
        any(p['overlap'] for p in evidence))) if matches]


class SujiTracker:
    """Separate from legacy hand estimates so their other metrics stay unchanged."""
    def __init__(self):
        self.hands = {s: Counter() for s in range(3)}
        self.public = Counter()
        self.doras = []
        self.rivers = {s: [] for s in range(3)}
        self.riichi = set()
        self.kita = set()
        self.discard = None

    def expose(self, seat, tiles):
        for raw in tiles:
            tile = normalized(raw)
            if self.hands[seat][tile] <= 0:
                raise ValueError(f'Missing concealed tile in suji tracker: {seat} {tile}')
            self.hands[seat][tile] -= 1
            self.public[tile] += 1

    def observe(self, name, msg):
        if msg is None:
            return
        if name == '.lq.RecordNewRound':
            self.__init__()
            self.hands = {s: Counter(normalized(t) for t in getattr(msg, f'tiles{s}')) for s in range(3)}
        # doras contains the full currently revealed list, never uradoras.
        doras = list(getattr(msg, 'doras', []))
        if not doras and name == '.lq.RecordNewRound' and getattr(msg, 'dora', ''):
            doras = [msg.dora]
        if doras and name != '.lq.RecordHule':
            self.doras = [normalized(t) for t in doras]
        seat = int(getattr(msg, 'seat', -1))
        if name == '.lq.RecordDiscardTile':
            tile = normalized(msg.tile)
            declaration = bool(msg.is_liqi or msg.is_wliqi)
            visible = self.public + self.hands[seat] + Counter(self.doras)
            self.discard = {'seat': seat, 'tile': tile, 'eligible': seat not in self.riichi and not declaration,
                            'visible': visible, 'hand': self.hands[seat].copy(),
                            'rivers': {s: list(r) for s, r in self.rivers.items()}}
            self.expose(seat, [tile])
            self.rivers[seat].append(tile)
            if declaration:
                self.riichi.add(seat)
        elif name == '.lq.RecordDealTile':
            self.discard = None
            self.hands[seat][normalized(msg.tile)] += 1
        elif name == '.lq.RecordBaBei':
            self.discard = None
            self.kita.add(seat)
            self.expose(seat, ['4z'])
        elif name == '.lq.RecordChiPengGang':
            tiles, froms = list(msg.tiles), list(msg.froms)
            if len(tiles) == len(froms):
                own = [t for t, s in zip(tiles, froms) if s == seat]
            else:
                own = list(tiles)
                if self.discard is None:
                    raise ValueError('Call without discard/froms in suji tracker')
                claimed = next(t for t in own if normalized(t) == self.discard['tile'])
                own.remove(claimed)
            self.expose(seat, own)
            self.discard = None
        elif name == '.lq.RecordAnGangAddGang':
            self.discard = None
            self.expose(seat, [msg.tiles] * (4 if msg.type == 3 else 1))

    def kokushi_signals(self, winner):
        tiles = {t for t in self.rivers[winner] if t[1] == 'z' or t[0] in '19'}
        if winner in self.kita:
            tiles.add('4z')
        return sorted(tiles)

    def evidence(self, loser, winner):
        d = self.discard
        if not d or d['seat'] != loser or not d['eligible']:
            return []
        return suji_evidence(d['tile'], d['rivers'][winner], d['visible'], d['hand'])
