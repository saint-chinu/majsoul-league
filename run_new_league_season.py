from __future__ import annotations

import csv
import subprocess
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

from collect_admin_paifu_ids import START_URL, USER_DATA_DIR
from collect_all_seasons import collect_current_season
from run_all import ROOT, count_csv


NEW_DATA_DIR = ROOT / "data" / "new"
NEW_PAIFU_CSV = NEW_DATA_DIR / "admin_paifu_ids.csv"
SEASON_COLUMNS = ["season", "page_no", "uuid", "date_key", "paifu_url"]


def read_csv_rows(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def write_csv_rows(path: Path, rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=SEASON_COLUMNS)
        writer.writeheader()
        writer.writerows(rows)


def season_csv_path(new_season: int) -> Path:
    return NEW_DATA_DIR / f"admin_paifu_ids_new_season{new_season}.csv"


def merge_new_seasons() -> int:
    rows_by_uuid: dict[str, dict[str, str]] = {}
    for path in sorted(NEW_DATA_DIR.glob("admin_paifu_ids_new_season*.csv")):
        for row in read_csv_rows(path):
            uuid = row.get("uuid", "")
            season = row.get("season", "")
            if not uuid or not season:
                continue
            rows_by_uuid[uuid] = {
                "season": season,
                "page_no": row.get("page_no", ""),
                "uuid": uuid,
                "date_key": row.get("date_key") or uuid.split("-", 1)[0],
                "paifu_url": row.get("paifu_url") or f"https://game.mahjongsoul.com/?paipu={uuid}",
            }

    rows = sorted(rows_by_uuid.values(), key=lambda row: (int(row["season"]), row["uuid"]))
    write_csv_rows(NEW_PAIFU_CSV, rows)
    return len(rows)


def preview_collected_rows(new_season: int, rows: list[dict[str, object]]) -> str:
    dates = sorted({str(row.get("date_key", "")) for row in rows if row.get("date_key")})
    out = season_csv_path(new_season)

    print()
    print("新リーグ取得内容の確認")
    print(f"  保存先: {out}")
    print(f"  取得件数: {len(rows)}件")
    if dates:
        print(f"  日付範囲: {dates[0]} - {dates[-1]}")
    if out.exists():
        print(f"  既存件数: {count_csv(out)}件")
    print("  先頭5件:")
    for row in rows[:5]:
        print(f"    {row.get('uuid', '')}")

    if not rows:
        print("0件なので保存しません。")
        return "retry"

    print()
    print("操作を選んでください。")
    print("  y: この内容で保存して牌譜取得へ進む")
    print("  r: 保存せず、ブラウザを今のまま再取得する")
    print("  q: 終了する")
    while True:
        answer = input("y / r / q: ").strip().lower()
        if answer in {"y", "yes"}:
            return "save"
        if answer in {"", "r", "retry"}:
            return "retry"
        if answer in {"q", "quit"}:
            return "quit"
        print("y / r / q のどれかを入力してください。")


def run(args: list[str]) -> None:
    print()
    print(">>> " + " ".join(args))
    subprocess.run(args, cwd=ROOT, check=True)


def main() -> None:
    print("新リーグの単一シーズンを取得します。旧リーグCSVには混ぜません。")
    print("大会名が同じ「テスト」でも、新リーグ用データは data/new/ に分けて保存します。")
    print()

    season_text = input("新リーグ内のシーズン番号。最初なら 1: ").strip()
    if not season_text.isdigit():
        raise SystemExit("シーズン番号は数字で入力してください。")
    new_season = int(season_text)

    max_pages_text = input("最大ページ数。全135試合なら14。空Enterでも14: ").strip()
    max_pages = int(max_pages_text or "14")

    expected_text = input("現在の想定試合数。分からなければ空Enter: ").strip()
    expected_count = int(expected_text) if expected_text.isdigit() else None

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
        print("新リーグの対象シーズン → 大会牌譜の1ページ目を手で開いてください。")
        print("そこから先のページ送りと牌譜ID取得は自動でやります。")
        input("開けたら Enter: ")

        while True:
            rows = collect_current_season(page, new_season, max_pages)

            if expected_count is not None and len(rows) < expected_count:
                print()
                print(f"注意: 想定 {expected_count}件 に対して {len(rows)}件です。")
                print("ページ送り・表示シーズンが合っているか確認してください。")

            action = preview_collected_rows(new_season, rows)
            if action == "save":
                break
            if action == "quit":
                browser.close()
                raise SystemExit("保存を中止しました。")

            print()
            print("再取得します。")
            print("ブラウザで対象シーズンの大会牌譜1ページ目へ戻してください。")
            input("戻したら Enter: ")

        browser.close()

    write_csv_rows(season_csv_path(new_season), rows)
    total = merge_new_seasons()
    print(f"saved: {season_csv_path(new_season)} ({len(rows)}件)")
    print(f"merged new league: {NEW_PAIFU_CSV} ({total}件)")

    run([sys.executable, "collect_records.py", str(NEW_PAIFU_CSV)])
    print()
    print("新リーグ牌譜取得が完了しました。")
    print("次の工程は、新リーグ単体・通算の集計サイト生成です。")


if __name__ == "__main__":
    main()
