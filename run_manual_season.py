from __future__ import annotations

import csv
import re
import sys
from pathlib import Path

from run_all import ROOT, backup_if_exists, commit_and_push, count_csv, run


UUID_RE = re.compile(r"\d{6}-[0-9a-fA-F-]{36}")
MANUAL_INPUT = ROOT / "manual_paifu_ids.txt"
PAIFU_CSV = ROOT / "admin_paifu_ids.csv"
SEASON_RE = re.compile(r"admin_paifu_ids_season(\d+)\.csv$")
SEASON_COLUMNS = ["season", "page_no", "uuid", "date_key", "paifu_url"]


def read_csv_rows(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def write_csv_rows(path: Path, rows: list[dict[str, object]]) -> None:
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=SEASON_COLUMNS)
        writer.writeheader()
        writer.writerows(rows)


def parse_manual_uuids() -> list[str]:
    if not MANUAL_INPUT.exists():
        return []

    text = MANUAL_INPUT.read_text(encoding="utf-8-sig", errors="ignore")
    seen = set()
    uuids = []
    for match in UUID_RE.finditer(text):
        uuid = match.group(0)
        if uuid in seen:
            continue
        seen.add(uuid)
        uuids.append(uuid)
    return uuids


def write_manual_season_csv(season: int, uuids: list[str]) -> Path:
    out = ROOT / f"admin_paifu_ids_season{season}.csv"
    rows = []
    for index, uuid in enumerate(uuids, start=1):
        rows.append(
            {
                "season": season,
                "page_no": "",
                "uuid": uuid,
                "date_key": uuid.split("-", 1)[0],
                "paifu_url": f"https://game.mahjongsoul.com/?paipu={uuid}",
            }
        )

    write_csv_rows(out, rows)
    return out


def season_csv_path(season: int) -> Path:
    return ROOT / f"admin_paifu_ids_season{season}.csv"


def merge_seasons_through(season: int) -> int:
    rows_by_uuid: dict[str, dict[str, str]] = {}

    for path in sorted(ROOT.glob("admin_paifu_ids_season*.csv")):
        match = SEASON_RE.match(path.name)
        if not match:
            continue

        season_no = int(match.group(1))
        if season_no < 1 or season_no > season:
            continue

        for row in read_csv_rows(path):
            uuid = row.get("uuid", "")
            if not uuid:
                continue
            rows_by_uuid[uuid] = {
                "season": row.get("season") or str(season_no),
                "page_no": row.get("page_no", ""),
                "uuid": uuid,
                "date_key": row.get("date_key") or uuid.split("-", 1)[0],
                "paifu_url": row.get("paifu_url") or f"https://game.mahjongsoul.com/?paipu={uuid}",
            }

    rows = sorted(rows_by_uuid.values(), key=lambda row: (int(row["season"]), row["uuid"]))
    write_csv_rows(PAIFU_CSV, rows)
    return len(rows)


def print_season_counts(season: int) -> None:
    print("season counts:")
    for season_no in range(1, season + 1):
        path = season_csv_path(season_no)
        if path.exists():
            print(f"  season {season_no}: {count_csv(path)}件")


def count_complete_records_for_current_csv() -> int:
    count = 0
    for row in read_csv_rows(PAIFU_CSV):
        uuid = row.get("uuid", "")
        if not uuid:
            continue
        record_bin = ROOT / "records_raw" / f"{uuid}_record.bin"
        detail_bin = ROOT / "records_raw" / f"{uuid}_detail.bin"
        if record_bin.exists() and detail_bin.exists():
            count += 1
    return count


def main() -> None:
    print("手動IDリストから、単一シーズンを集計してHPへ反映します。")
    print("manual_paifu_ids.txt に今回シーズンの牌譜URLまたはUUIDを貼っておくと、その内容でシーズンCSVを作ります。")
    print("manual_paifu_ids.txt が空なら、既存の admin_paifu_ids_seasonN.csv を使います。")
    print()

    season_text = input("今回反映するシーズン番号。例: 2: ").strip()
    if not season_text.isdigit():
        raise SystemExit("シーズン番号は数字で入力してください。")

    season = int(season_text)
    uuids = parse_manual_uuids()

    if uuids:
        out = write_manual_season_csv(season, uuids)
        print(f"saved: {out.name} ({len(uuids)}件)")
    else:
        out = season_csv_path(season)
        if not out.exists() or count_csv(out) == 0:
            raise SystemExit(
                f"{out.name} がありません。manual_paifu_ids.txt にUUIDか牌譜URLを貼ってから再実行してください。"
            )
        print(f"use existing: {out.name} ({count_csv(out)}件)")

    backup_if_exists(PAIFU_CSV)
    total = merge_seasons_through(season)
    print(f"merged cumulative: {PAIFU_CSV.name} ({total}件)")
    print_season_counts(season)

    if total == 0:
        raise SystemExit("牌譜IDが0件です。")

    run([sys.executable, "collect_records.py"])
    record_count = count_complete_records_for_current_csv()
    print(f"取得済み牌譜: {record_count} / {total} 件")

    if record_count < total:
        print("未取得が残っているので、もう一度だけ collect_records.py を再実行します。")
        run([sys.executable, "collect_records.py"])
        record_count = count_complete_records_for_current_csv()
        print(f"取得済み牌譜: {record_count} / {total} 件")

    run([sys.executable, "aggregate_league.py"])
    run([sys.executable, "make_site.py"])
    commit_and_push()

    if MANUAL_INPUT.exists():
        MANUAL_INPUT.write_text("", encoding="utf-8")
        print(f"cleared: {MANUAL_INPUT.name}")

    print()
    print("完了しました。")
    print("GitHub Pages: https://saint-chinu.github.io/majsoul-league/")


if __name__ == "__main__":
    main()
