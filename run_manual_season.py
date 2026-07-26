from __future__ import annotations

import csv
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

from collect_admin_paifu_ids import START_URL, USER_DATA_DIR
from collect_all_seasons import collect_current_season
from run_all import ROOT, backup_if_exists, commit_and_push, count_csv, run


PAIFU_CSV = ROOT / "admin_paifu_ids.csv"
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


def season_csv_path(season: int) -> Path:
    return ROOT / f"admin_paifu_ids_season{season}.csv"


def merge_seasons_through(season: int) -> int:
    rows_by_uuid: dict[str, dict[str, str]] = {}

    for season_no in range(1, season + 1):
        path = season_csv_path(season_no)
        if not path.exists():
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


def collect_season_ids(season: int, max_pages: int) -> Path:
    with sync_playwright() as p:
        browser = p.chromium.launch_persistent_context(
            user_data_dir=str(USER_DATA_DIR),
            headless=False,
            viewport={"width": 1460, "height": 900},
        )

        page = browser.new_page()
        page.goto(START_URL, wait_until="domcontentloaded")

        print()
        print("ブラウザで管理画面を開きます。")
        print(f"手でシーズン{season} → 大会牌譜の1ページ目を開いてください。")
        print("そこから先のページ送りと牌譜ID取得は自動でやります。")
        input("開けたら Enter: ")

        print()
        print("=" * 40)
        print(f"season {season}")
        rows = collect_current_season(page, season, max_pages)
        browser.close()

    out = season_csv_path(season)
    write_csv_rows(out, rows)
    print(f"saved: {out.name} ({len(rows)}件)")
    return out


def main() -> None:
    print("単一シーズンを集計してHPへ反映します。")
    print("シーズン選択だけ手動です。大会牌譜1ページ目まで開けば、ページ送り以降は自動です。")
    print()

    season_text = input("今回反映するシーズン番号。例: 2: ").strip()
    if not season_text.isdigit():
        raise SystemExit("シーズン番号は数字で入力してください。")

    season = int(season_text)
    max_pages_text = input("1シーズン最大ページ数。分からなければ空Enterで50: ").strip()
    max_pages = int(max_pages_text or "50")

    collect_season_ids(season, max_pages)

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

    print()
    print("完了しました。")
    print("GitHub Pages: https://saint-chinu.github.io/majsoul-league/")


if __name__ == "__main__":
    main()
