"""Compare shared provisional games with collected season 4 results."""
import json
from datetime import datetime
from pathlib import Path
from urllib.request import Request, urlopen

API = 'https://majsoul-seating.doppel-tag.workers.dev/season4'


def reconcile(data, drafts):
    excluded = {r['uuid'] for r in data.get('excluded', [])}
    actual = {r['uuid']: r for r in data['records'] + data.get('excluded', [])}.values()
    cutoff = datetime.fromisoformat(data['updated']).timestamp() - 900
    result = []
    for draft in drafts:
        candidates = [] if draft.get('cancelled') else [r['uuid'] for r in actual
            if sorted(r['players']) == sorted(draft['players']) and
            (r['uuid'] == draft['uuid'] if draft.get('uuid') else abs(r['end'] - draft['end']) <= 600)]
        status = ('cancelled' if draft.get('cancelled') else 'matched' if len(candidates) == 1
                  else 'review' if len(candidates) > 1 or draft['end'] <= cutoff else 'pending')
        result.append({**draft, 'status': status, 'candidates': candidates})
    uses = {}
    for row in result:
        for uuid in row['candidates']:
            uses[uuid] = uses.get(uuid, 0) + 1
    for row in result:
        if any(uses[uuid] > 1 for uuid in row['candidates']):
            row['status'] = 'review'
        elif row['status'] == 'matched' and row['candidates'][0] in excluded:
            row['status'] = 'excluded'
    return result


def audit(data, root):
    path = Path(root) / 'captures/seating-reconciliation.json'
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        request = Request(API, headers={'User-Agent': 'Mozilla/5.0 majsoul-league-audit/1.0', 'Accept': 'application/json'})
        with urlopen(request, timeout=15) as response:
            shared = json.load(response)
        if shared['season'] != 4:
            raise ValueError('Wrong season')
        rows = reconcile(data, shared['rows'])
        report = {'checked_at': data['updated'], 'revision': shared['revision'], 'rows': rows,
                  'counts': {status: sum(r['status'] == status for r in rows)
                             for status in ('matched', 'pending', 'review', 'excluded', 'cancelled')}}
        active = [r for r in rows if r['status'] != 'cancelled']
        matched = {uuid for r in active for uuid in r['candidates']}
        start = min((r['end'] for r in active), default=float('inf'))
        report['record_only_since_first_entry'] = [r for r in data['records']
                                                  if r['end'] >= start and r['uuid'] not in matched]
        print('seating reconciliation:', report['counts'])
        for row in rows:
            if row['status'] == 'review':
                print('SEATING_REVIEW:', row['id'], row['players'], row['end'])
    except Exception as exc:
        report = {'checked_at': data['updated'], 'error': str(exc)}
        print('SEATING_AUDIT_FAILED: shared entries were NOT checked:', exc)
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    return report


if __name__ == '__main__':
    from build_seating import build_data, ROOT
    audit(build_data(), ROOT)
