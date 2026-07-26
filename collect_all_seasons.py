from __future__ import annotations

import csv
import re
from pathlib import Path

from playwright.sync_api import Page, sync_playwright

from collect_admin_paifu_ids import (
    OUT,
    START_URL,
    STOP_BEFORE,
    USER_DATA_DIR,
    click_next_page,
    collect_visible_page,
    uuid_date_key,
)


SEASON_FILE_RE = re.compile(r"admin_paifu_ids_season(\d+)\.csv$")
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


def ensure_season1_backup() -> None:
    season1 = Path("admin_paifu_ids_season1.csv")
    if season1.exists() or not OUT.exists():
        return

    rows = []
    for row in read_csv_rows(OUT):
        uuid = row.get("uuid", "")
        if not uuid:
            continue
        rows.append(
            {
                "season": 1,
                "page_no": row.get("page_no", ""),
                "uuid": uuid,
                "date_key": row.get("date_key") or uuid_date_key(uuid),
                "paifu_url": row.get("paifu_url") or f"https://game.mahjongsoul.com/?paipu={uuid}",
            }
        )

    if rows:
        write_csv_rows(season1, rows)
        print(f"season1 backup: {season1} ({len(rows)}件)")


def merge_season_files() -> int:
    rows_by_uuid: dict[str, dict[str, str]] = {}

    for path in sorted(Path(".").glob("admin_paifu_ids_season*.csv")):
        match = SEASON_FILE_RE.match(path.name)
        if not match:
            continue
        season = match.group(1)

        for row in read_csv_rows(path):
            uuid = row.get("uuid", "")
            if not uuid:
                continue
            date_key = row.get("date_key") or uuid_date_key(uuid)
            if date_key < STOP_BEFORE:
                continue
            rows_by_uuid[uuid] = {
                "season": row.get("season") or season,
                "page_no": row.get("page_no", ""),
                "uuid": uuid,
                "date_key": date_key,
                "paifu_url": row.get("paifu_url") or f"https://game.mahjongsoul.com/?paipu={uuid}",
            }

    rows = sorted(rows_by_uuid.values(), key=lambda r: (int(r["season"]), r["uuid"]))
    write_csv_rows(OUT, rows)
    return len(rows)


def visible_box(locator) -> dict[str, float] | None:
    try:
        box = locator.bounding_box(timeout=700)
    except Exception:
        return None
    return box


def click_visible_text(page: Page, labels: list[str], *, exact: bool = True) -> bool:
    candidates = []
    for label in labels:
        try:
            locators = page.get_by_text(label, exact=exact).all()
        except Exception:
            continue
        for locator in locators:
            box = visible_box(locator)
            if not box:
                continue
            candidates.append((box["y"], box["x"], label, locator))

    if not candidates and exact:
        return click_visible_text(page, labels, exact=False)

    if not candidates:
        return False

    candidates.sort(key=lambda item: (item[0], item[1]))
    _, _, label, locator = candidates[0]
    print(f"click: {label}")
    locator.click(force=True, timeout=3000)
    page.wait_for_timeout(1600)
    return True


def click_season(page: Page, season: int) -> bool:
    labels = [
        f"シーズン{season}",
        f"シーズン {season}",
        f"Season {season}",
        str(season),
    ]

    if click_visible_text(page, labels):
        return True

    # シーズン一覧がスクロール領域にある場合の保険。
    for _ in range(8):
        page.mouse.wheel(0, 500)
        page.wait_for_timeout(250)
        if click_visible_text(page, labels):
            return True

    return False


def click_game_record_tab(page: Page) -> bool:
    return click_visible_text(page, ["大会牌譜", "牌譜"], exact=True)


def collect_current_season(page: Page, season: int, max_pages: int) -> list[dict[str, object]]:
    seen = set()
    rows: list[dict[str, object]] = []

    for page_no in range(1, max_pages + 1):
        print()
        print(f"season {season} page {page_no}")
        uuids = collect_visible_page(page)
        dates = []
        new_count = 0

        for uuid in uuids:
            date_key = uuid_date_key(uuid)
            dates.append(date_key)

            if date_key < STOP_BEFORE or uuid in seen:
                continue

            seen.add(uuid)
            new_count += 1
            rows.append(
                {
                    "season": season,
                    "page_no": page_no,
                    "uuid": uuid,
                    "date_key": date_key,
                    "paifu_url": f"https://game.mahjongsoul.com/?paipu={uuid}",
                }
            )
            print(" ", uuid)

        if dates:
            print(f"date range on page: {min(dates)} - {max(dates)}")
        print(f"visible={len(uuids)} new={new_count} season_total={len(rows)}")

        if not uuids:
            print("このページで牌譜IDが取れないので、このシーズンはここで止めます。")
            break

        if not click_next_page(page):
            print("次ページがないので、このシーズンは完了です。")
            break

    return rows


def main() -> None:
    start_text = input("開始シーズン。シーズン1は完了済みなので今回は2: ").strip()
    end_text = input("終了シーズン。今ある最新シーズン番号を入力、空なら8: ").strip()
    max_pages_text = input("1シーズン最大ページ数。分からなければ空Enterで50: ").strip()

    start_season = int(start_text or "2")
    end_season = int(end_text or "8")
    max_pages = int(max_pages_text or "50")

    ensure_season1_backup()

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
        print("必要ならログインして、リーグ「テスト」が見える画面まで進めてください。")
        print("スクリプトが各シーズン → 大会牌譜 → ページ送りを順に試します。")
        input("準備できたら Enter: ")

        for season in range(start_season, end_season + 1):
            print()
            print("=" * 40)
            print(f"season {season}")

            if not click_season(page, season):
                print(f"シーズン{season}を自動クリックできませんでした。")
                print(f"手でシーズン{season} → 大会牌譜を開いてください。")
                input("開けたら Enter: ")
            elif not click_game_record_tab(page):
                print("大会牌譜タブを自動クリックできませんでした。")
                print("手で大会牌譜を開いてください。")
                input("開けたら Enter: ")

            rows = collect_current_season(page, season, max_pages)
            out = Path(f"admin_paifu_ids_season{season}.csv")
            write_csv_rows(out, rows)
            print(f"saved: {out} ({len(rows)}件)")

        total = merge_season_files()
        print()
        print(f"merged: {OUT} ({total}件)")
        input("確認したら Enter: ")
        browser.close()


if __name__ == "__main__":
    main()
