"""Publish only verified new-season-4 participation; never read old league CSVs."""
from datetime import datetime, timezone, timedelta
from pathlib import Path
import csv
import json

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


def build_data(root=ROOT, loader=read_entry):
    source = root / "data/new/admin_paifu_ids_new_season4.csv"
    rows = []
    if source.exists():
        with source.open(encoding="utf-8-sig", newline="") as f:
            rows = list(csv.DictReader(f))
    records, issues, seen = [], [], set()
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
        try:
            entry = loader(root / "records_raw" / f"{uuid}_detail.bin", uuid)
            ids = sorted(p.account_id for p in entry.players)
            if len(ids) != 3 or len(set(ids)) != 3 or not set(ids) <= allowed:
                raise ValueError("対象6名以外の参加者、または3人卓ではない対局")
            if not entry.end_time:
                raise ValueError("終了時刻のない対局")
            records.append({"uuid": uuid, "players": ids, "start": entry.start_time,
                            "end": entry.end_time})
        except Exception as e:
            reason = "成績詳細が未取得" if isinstance(e, FileNotFoundError) else str(e)
            issues.append({"uuid": uuid, "reason": reason[:160]})
    return {"season": 4, "target": 30, "players": PLAYERS,
            "source_available": source.exists(), "source_count": len(seen),
            "updated": datetime.now(timezone(timedelta(hours=9))).isoformat(timespec="seconds"),
            "records": sorted(records, key=lambda r: (r["end"], r["uuid"])), "issues": issues}


def write_seating_data(root=ROOT):
    data = build_data(root)
    output = root / "docs/seating/data.js"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text("window.SEATING_DATA = " + json.dumps(data, ensure_ascii=False, indent=2)
                      + ";\n", encoding="utf-8")
    print(f"seating: {len(data['records'])} games, {len(data['issues'])} unresolved")


if __name__ == "__main__":
    write_seating_data()
