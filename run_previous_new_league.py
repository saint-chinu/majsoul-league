"""新リーグの過去シーズンを安全に再取得して公開まで更新する。

管理画面のシーズン内部番号は順番どおりとは限らないため、対象の過去シーズン
をブラウザで一度だけ選ぶ。それ以外（全ページ巡回、牌譜本体の不足分取得、
再集計、GitHub Pages公開）は自動で行う。
"""

from __future__ import annotations

import argparse
import subprocess
import sys

from pathlib import Path

from playwright.sync_api import sync_playwright

from collect_admin_paifu_ids import START_URL, USER_DATA_DIR
from collect_all_seasons import collect_current_season
from run_auto_update import (
    NEW_DATA_DIR,
    SEASON_COLUMNS,
    count_complete_records,
    find_git,
    log,
    merge_season_rows,
    read_csv_rows,
    sync_canonical_csv,
    write_season_csv,
)


ROOT = Path(__file__).resolve().parent


def season_csv_path(season: int) -> Path:
    return NEW_DATA_DIR / f"admin_paifu_ids_new_season{season}.csv"


def collect_rows(season: int, admin_season: int, max_pages: int) -> list[dict[str, object]]:
    with sync_playwright() as p:
        browser = p.chromium.launch_persistent_context(
            user_data_dir=str(USER_DATA_DIR),
            headless=False,
            viewport={"width": 1460, "height": 900},
        )
        try:
            page = browser.new_page()
            target_url = f"{START_URL}/season/{admin_season}/record"
            print(f"管理画面の過去シーズン（内部番号 {admin_season}）を開きます。")
            page.goto(target_url, wait_until="domcontentloaded")
            page.wait_for_timeout(4000)
            if "/record" not in page.url:
                raise SystemExit(
                    "過去シーズンの牌譜ページを開けませんでした。"
                    "管理画面で対象シーズンを一度確認してください。"
                )
            return collect_current_season(page, season, max_pages)
        finally:
            browser.close()


def commit_and_push() -> None:
    git = find_git()
    if not git:
        print("git が見つからないため、公開はスキップしました。")
        return

    targets = [
        str(path.relative_to(ROOT))
        for path in [NEW_DATA_DIR / "admin_paifu_ids.csv", *NEW_DATA_DIR.glob("admin_paifu_ids_new_season*.csv")]
        if path.exists()
    ]
    targets += [str(path.relative_to(ROOT)) for path in (ROOT / "docs").glob("*.html")]
    subprocess.run([git, "add", *targets], cwd=ROOT, check=True)
    staged = subprocess.run(
        [git, "diff", "--cached", "--quiet"], cwd=ROOT, check=False
    )
    if staged.returncode == 0:
        print("公開対象の変更はありません。")
        return
    subprocess.run([git, "commit", "-m", "Refresh previous league season"], cwd=ROOT, check=True)
    subprocess.run([git, "push", "origin", "main"], cwd=ROOT, check=True)
    print("GitHub Pages を更新しました。")


def main() -> None:
    parser = argparse.ArgumentParser(description="新リーグの過去シーズンを再取得して公開する")
    parser.add_argument("--season", type=int, default=1, help="新リーグ内の表示シーズン番号")
    parser.add_argument("--admin-season", type=int, default=11, help="管理画面の内部シーズン番号")
    parser.add_argument("--max-pages", type=int, default=14, help="巡回する最大ページ数")
    parser.add_argument("--expected", type=int, help="これ未満なら保存しない最低対局数")
    args = parser.parse_args()
    if args.season < 1 or args.admin_season < 1 or args.max_pages < 1:
        raise SystemExit("シーズン番号と最大ページ数は1以上にしてください。")

    print(f"新リーグ第{args.season}シーズンを再取得します。")
    collected = collect_rows(args.season, args.admin_season, args.max_pages)
    season = args.season
    expected = args.expected
    if expected is not None and len(collected) < expected:
        raise SystemExit(
            f"取得件数が少なすぎます: {len(collected)}件 / 想定 {expected}件。保存せず終了します。"
        )
    if not collected:
        raise SystemExit("0件のため保存せず終了します。")

    path = season_csv_path(season)
    existing = read_csv_rows(path)
    merged = merge_season_rows(existing, collected, season)
    if len(merged) < len(existing):
        raise SystemExit("既存件数より減るため保存しません。")
    write_season_csv(path, merged)
    canonical = sync_canonical_csv()
    log(f"過去シーズン{season}: {len(merged)}件を保存")
    log(f"新リーグ合計: {len(read_csv_rows(canonical))}件")

    subprocess.run([sys.executable, "collect_records.py", str(path)], cwd=ROOT, check=True)
    complete = count_complete_records(merged)
    if complete < len(merged):
        subprocess.run([sys.executable, "collect_records.py", str(path)], cwd=ROOT, check=True)
        complete = count_complete_records(merged)
    if complete < len(merged):
        raise SystemExit(f"牌譜本体が不足しています: {complete}/{len(merged)}。公開しません。")

    subprocess.run([sys.executable, "make_site.py"], cwd=ROOT, check=True)
    commit_and_push()


if __name__ == "__main__":
    main()
