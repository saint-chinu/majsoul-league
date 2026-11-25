"""Replay-level evidence for the existing deal-in quality score."""
import hashlib
import json
from collections import Counter, defaultdict
from pathlib import Path

import aggregate_league as league
from invalid_games import is_invalid

CACHE_DIR = Path('build/deal-in-audit')
OUTPUT_DIR = Path('docs/deal-in-audit')
import deal_in_suji
RULE_VERSION = hashlib.sha256(Path(league.__file__).read_bytes() + Path(deal_in_suji.__file__).read_bytes()).hexdigest()[:16]


def fingerprint(uuid):
    return [RULE_VERSION] + [
        [p.stat().st_size, p.stat().st_mtime_ns]
        for p in [league.RAW_DIR / f'{uuid}_record.bin', league.RAW_DIR / f'{uuid}_detail.bin']
    ]


def save_game_audit(uuid, events):
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    payload = {'fingerprint': fingerprint(uuid), 'events': events}
    (CACHE_DIR / f'{uuid}.json').write_text(json.dumps(payload, ensure_ascii=False), encoding='utf-8')


def game_events(uuid):
    path = CACHE_DIR / f'{uuid}.json'
    if path.exists():
        try:
            payload = json.loads(path.read_text(encoding='utf-8'))
            if payload.get('fingerprint') == fingerprint(uuid):
                return payload['events']
        except (ValueError, KeyError):
            pass
    events = []
    stats = defaultdict(league.PlayerStats)
    league.aggregate_game(uuid, stats, [], events)
    for name, stat in stats.items():
        own = [e for e in events if e['player'] == name]
        assert len(own) == stat.deal_in_events, uuid
        assert sum(e['score'] for e in own) == stat.deal_in_quality_score_sum, uuid
        assert Counter(c for e in own for c in e['categories']) == stat.deal_in_quality_counts, uuid
    save_game_audit(uuid, events)
    return events


def game_evidence(uuid):
    """Locate the actual winning action, including robbed kita/kan."""
    path = CACHE_DIR / f'{uuid}.evidence.json'
    stamp = fingerprint(uuid) + [1]
    if path.exists():
        cached = json.loads(path.read_text(encoding='utf-8'))
        if cached.get('fingerprint') == stamp:
            return cached['facts']
    turns, actions, facts = Counter(), {}, {}
    for index, wrapper in enumerate(league.load_record_wrappers(league.RAW_DIR / f'{uuid}_record.bin')):
        name = wrapper['name']
        if name not in {'.lq.RecordNewRound', '.lq.RecordDiscardTile', '.lq.RecordBaBei', '.lq.RecordAnGangAddGang', '.lq.RecordChiPengGang', '.lq.RecordHule'}:
            continue
        msg = league.decode_record(name, wrapper['body'])
        if name == '.lq.RecordNewRound':
            turns.clear(); actions.clear()
        elif name == '.lq.RecordHule':
            if not league.is_ron_hule(msg):
                continue
            loser = league.get_houjuu_seat(msg)
            action = actions.get(loser, {'action': 'unknown', 'turn': None, 'tile': ''})
            for hule in msg.hules:
                if hule.zimo:
                    continue
                facts[f'{uuid}:{index}:{hule.seat}'] = {
                    **action, 'tile': action['tile'] or hule.hu_tile,
                    'actual_scores_before': list(msg.old_scores),
                    'actual_scores_after': list(msg.scores),
                }
        else:
            seat = int(msg.seat)
            if name == '.lq.RecordDiscardTile':
                turns[seat] += 1
                actions[seat] = {'action': 'discard', 'turn': turns[seat], 'tile': msg.tile}
            else:
                actions[seat] = {'action': 'kita' if name == '.lq.RecordBaBei' else 'kan',
                                 'turn': turns[seat] + 1, 'tile': '4z' if name == '.lq.RecordBaBei' else ''}
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({'fingerprint': stamp, 'facts': facts}, ensure_ascii=False), encoding='utf-8')
    return facts


def export_audit(seasons, contexts):
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    context_map = {c['key']: c for c in contexts}
    manifest = {'version': RULE_VERSION, 'categories': [
        {'key': key, 'label': label, 'points': league.DEAL_IN_QUALITY_SCORE[key]}
        for key, label in league.DEAL_IN_QUALITY_CATEGORIES
    ], 'seasons': [], 'expected': {
        key: {r['player']: r.get('deal_in_quality_score', '') for r in context.get('rows', [])}
        for key, context in context_map.items()
    }}
    for key, uuids in seasons.items():
        events, missing = [], []
        valid = sorted(u for u in uuids if not is_invalid(u))
        unavailable = [u for u in valid if not league.has_record_files(u)]
        previous_path = OUTPUT_DIR / f'{key}.json'
        preserved = None
        if unavailable and previous_path.exists():
            previous = json.loads(previous_path.read_text(encoding='utf-8'))
            if previous.get('game_ids') == valid and previous.get('rule_version') == RULE_VERSION and not previous.get('missing_games'):
                preserved = previous['events']
        if unavailable and preserved is None:
            raise ValueError(f'Audit sources missing: {key} ({len(unavailable)} games). Existing public results were not replaced.')
        print(f'deal-in audit: {key} ({len(valid)} games)', flush=True)
        if preserved is not None:
            events = preserved
        for i, uuid in enumerate(valid if preserved is None else []):
            if not league.has_record_files(uuid):
                missing.append(uuid)
                continue
            own = game_events(uuid)
            facts = game_evidence(uuid)
            detail = league.pb.ResGameRecordsDetailV2()
            detail.ParseFromString(league.first_payload_from_ws_response(league.RAW_DIR / f'{uuid}_detail.bin'))
            entry = detail.entries[0]
            events.extend({**e, **facts[e['id']], 'start_time': entry.start_time,
                           'players': [p.nickname for p in entry.players]} for e in own)
            if (i + 1) % 40 == 0:
                print(f'  {i + 1}/{len(valid)}', flush=True)
        assert len({e['id'] for e in events}) == len(events), key
        context = context_map.get(key, {})
        expected = {}
        for row in context.get('rows', []):
            expected[row['player']] = {'score': row.get('deal_in_quality_score', ''),
                                       'breakdown': row.get('deal_in_quality_breakdown', '')}
            if key.startswith('new-') and not missing:
                own = [e for e in events if e['player'] == row['player']]
                counts = Counter(c for e in own for c in e['categories'])
                target = Counter({k: int(v) for k, v in (p.split(':') for p in row.get('deal_in_quality_breakdown', '').split('|') if ':' in p)})
                if counts != target or len(own) != int(row.get('deal_in_event_count', len(own))):
                    raise ValueError(f'Audit count mismatch: {key} {row["player"]}')
                mean = round(sum(e['score'] for e in own) / len(own), 2) if own else 0
                if abs(mean - float(row.get('deal_in_quality_score', 0))) > 0.011:
                    raise ValueError(f'Audit score mismatch: {key} {row["player"]}')
        data = {'season': key, 'rule_version': RULE_VERSION, 'game_ids': valid,
                'events': events, 'expected': expected, 'missing_games': missing}
        (OUTPUT_DIR / f'{key}.json').write_text(json.dumps(data, ensure_ascii=False, separators=(',', ':')), encoding='utf-8')
        manifest['seasons'].append({'id': key, 'label': context.get('label', key),
                                    'file': f'{key}.json', 'games': len(valid),
                                    'missing_games': len(missing),
                                    'players': sorted(set(expected) | {e['player'] for e in events})})
    (OUTPUT_DIR / 'index.json').write_text(json.dumps(manifest, ensure_ascii=False, separators=(',', ':')), encoding='utf-8')


if __name__ == '__main__':
    import make_site as site
    old, old_seasons = site.build_old_contexts()
    seasons = {f'old-season-{s}': ids for s, ids in site.group_uuids_by_season(site.read_season_paifu_rows()).items()}
    seasons.update({f'new-season-{s}': ids for s, ids in site.group_uuids_by_season(site.read_new_league_paifu_rows()).items()})
    export_audit(seasons, old_seasons)
