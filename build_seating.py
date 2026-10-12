"""Publish only verified new-season-4 participation; never read old league CSVs."""
from datetime import datetime, timezone, timedelta
from pathlib import Path
import csv
import json
from collections import Counter
from invalid_games import INVALID_GAMES

ROOT = Path(__file__).resolve().parent
PLAYERS = [
    {"id": 101939586, "name": "流れ者", "account_name": "流れ者金融"},
    {"id": 68348480, "name": "29ch", "account_name": "29ちゃん"},
    {"id": 108312204, "name": "ひなんじょ", "account_name": "ひなんじょ"},
    {"id": 101665767, "name": "アリス", "account_name": "アリスkey"},
    {"id": 102159970, "name": "さこち", "account_name": "さこch"},
    {"id": 108386176, "name": "鯛", "account_name": "鯛ofカルピス"},
]


def read_entry(path, uuid):
    from aggregate_league import first_payload_from_ws_response
    from ms.protocol_pb2 import ResGameRecordsDetailV2
    msg = ResGameRecordsDetailV2.FromString(first_payload_from_ws_response(path))
    entries = [entry for entry in msg.entries if entry.uuid == uuid]
    if len(entries) != 1:
        raise ValueError("牌譜IDと成績詳細が一致しません")
    return entries[0]


def apply_combination_cap(records):
    counts = Counter()
    valid, excluded = [], []
    for record in sorted(records, key=lambda r: (r['start'], r['uuid'])):
        key = tuple(sorted(record['players']))
        counts[key] += 1
        if counts[key] > 3:
            excluded.append({**record, 'occurrence': counts[key], 'reason': '同じ3人組の4回目以降'})
        else:
            valid.append(record)
    return valid, excluded


def build_data(root=ROOT, loader=read_entry):
    source = root / "data/new/admin_paifu_ids_new_season4.csv"
    rows = []
    if source.exists():
        with source.open(encoding="utf-8-sig", newline="") as f:
            rows = list(csv.DictReader(f))
    records, issues, seen, excluded = [], [], set(), []
    allowed = {p["id"] for p in PLAYERS}
    for row in rows:
        uuid = row.get("uuid", "")
        if not uuid or any(c not in "0123456789abcdef-" for c in uuid):
            issues.append({"uuid": "", "reason": "不正な牌譜ID"})
            continue
        if uuid in seen:
            continue
        seen.add(uuid)
        if row.get("season") != "4":
            issues.append({"uuid": uuid, "reason": "シーズン番号が4ではありません"})
            continue
        if uuid in INVALID_GAMES:
            excluded.append({"uuid": uuid, **INVALID_GAMES[uuid], "reason": "ユーザー指定の無効対局"})
            continue
        try:
            entry = loader(root / "records_raw" / f"{uuid}_detail.bin", uuid)
            ids = sorted(p.account_id for p in entry.players)
            if len(ids) != 3 or len(set(ids)) != 3 or not set(ids) <= allowed:
                raise ValueError("対象6名以外の参加者、または3人卓ではない対局")
            if not entry.start_time or not entry.end_time:
                raise ValueError("開始・終了時刻のない対局")
            records.append({"uuid": uuid, "players": ids, "start": entry.start_time,
                            "end": entry.end_time})
        except Exception as e:
            reason = "成績詳細が未取得" if isinstance(e, FileNotFoundError) else str(e)
            issues.append({"uuid": uuid, "reason": reason[:160]})
    _, over_recommended = apply_combination_cap(records)
    return {"season": 4, "target": 30, "players": PLAYERS,
            "source_available": source.exists(), "source_count": len(seen),
            "updated": datetime.now(timezone(timedelta(hours=9))).isoformat(timespec="seconds"),
            "records": records, "excluded": excluded, "over_recommended": over_recommended, "issues": issues}


def write_seating_data(root=ROOT):
    data = build_data(root)
    output = root / "docs/seating/data.js"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text("window.SEATING_DATA = " + json.dumps(data, ensure_ascii=False, indent=2)
                      + ";\n", encoding="utf-8")
    print(f"seating: {len(data['records'])} games, {len(data['issues'])} unresolved")
    from audit_seating import audit
    audit(data, root)


if __name__ == "__main__":
    write_seating_data()
