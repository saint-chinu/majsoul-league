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


def count_season_rows(seasons: set[int]) -> dict[int, int]:
    counts = {}

    for path in sorted(Path(".").glob("admin_paifu_ids_season*.csv")):
        match = SEASON_FILE_RE.match(path.name)
        if not match:
            continue

        season_no = int(match.group(1))
        if season_no not in seasons:
            continue

        count = 0
        for row in read_csv_rows(path):
            uuid = row.get("uuid", "")
            if not uuid:
                continue
            date_key = row.get("date_key") or uuid_date_key(uuid)
            if date_key >= STOP_BEFORE:
                count += 1

        counts[season_no] = count

    return counts


def existing_season_numbers() -> set[int]:
    seasons = set()

    for path in Path(".").glob("admin_paifu_ids_season*.csv"):
        match = SEASON_FILE_RE.match(path.name)
        if match:
            seasons.add(int(match.group(1)))

    return seasons


def merge_season_files(seasons: set[int]) -> int:
    rows_by_uuid: dict[str, dict[str, str]] = {}

    for path in sorted(Path(".").glob("admin_paifu_ids_season*.csv")):
        match = SEASON_FILE_RE.match(path.name)
        if not match:
            continue
        season_no = int(match.group(1))
        if season_no not in seasons:
            continue
        season = str(season_no)

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


def season_candidates(page: Page) -> list[dict[str, object]]:
    candidates = page.evaluate(
        """
        () => {
          const rejectText = /(大会牌譜|役満牌譜|牌譜削除|リロード|全て|選択|履歴|統計|ログアウト|備考|\\/ページ|JP|ID|点数|順位|獲得|プレイヤー|大会|テスト)/;

          function visible(el) {
            const rect = el.getBoundingClientRect();
            if (rect.width < 40 || rect.height < 18) return null;
            if (rect.bottom < 0 || rect.top > window.innerHeight) return null;
            const style = window.getComputedStyle(el);
            if (style.visibility === 'hidden' || style.display === 'none') return null;
            return rect;
          }

          function uniq(rows) {
            const out = [];
            for (const row of rows.sort((a, b) => a.y - b.y || a.x - b.x)) {
              if (out.some(x => Math.abs(x.y - row.y) < 8 && Math.abs(x.x - row.x) < 16)) continue;
              out.push(row);
            }
            return out;
          }

          function collectSeasonText() {
            const rows = [];
            const elements = Array.from(document.querySelectorAll('button,a,li,div,span,[role="button"]'));
            for (const el of elements) {
              const text = (el.innerText || el.textContent || '').trim().replace(/\\s+/g, ' ');
              if (!/(シーズン|Season)/i.test(text)) continue;
              if (text.length > 60) continue;
              const rect = visible(el);
              if (!rect) continue;
              rows.push({
                text: text || '(textなし)',
                x: rect.left,
                y: rect.top,
                width: rect.width,
                height: rect.height,
              });
            }
            return uniq(rows);
          }

          function collectClickableRows() {
            const rows = [];
            const elements = Array.from(document.querySelectorAll(
              'button,a,li,[role="button"],[class*="item"],[class*="Item"],[class*="season"],[class*="Season"]'
            ));
            for (const el of elements) {
            const text = (el.innerText || el.textContent || '').trim().replace(/\\s+/g, ' ');
              if (text.length > 90) continue;
              if (rejectText.test(text)) continue;
              const rect = visible(el);
              if (!rect) continue;
              if (rect.height > 90) continue;
              rows.push({
                text: text || '(textなし)',
                x: rect.left,
                y: rect.top,
                width: rect.width,
                height: rect.height,
              });
            }
            return uniq(rows);
          }

          const withText = collectSeasonText();
          if (withText.length) {
            return withText.map(row => ({...row, source: 'season-text'}));
          }

          return collectClickableRows().map(row => ({...row, source: 'clickable-row'}));
        }
        """
    )

    rows = []
    for item in candidates:
        # 同じ行に親子要素が重なって出ることがあるので、近い座標の重複を落とす。
        if any(abs(float(item["y"]) - float(row["y"])) < 8 for row in rows):
            continue
        rows.append(item)

    return sorted(rows, key=lambda item: (float(item["y"]), float(item["x"])))


def click_season(page: Page, season: int) -> bool:
    # 管理画面では、シーズン1が一覧の一番下、シーズン2が下から2番目。
    # そのため文字の数字ではなく、表示位置の下からN番目でクリックする。
    candidates = season_candidates(page)

    if len(candidates) < season:
        page.mouse.wheel(0, 1000)
        page.wait_for_timeout(500)
        candidates = season_candidates(page)

    if len(candidates) < season:
        print(f"シーズン候補が足りません: found={len(candidates)} need={season}")
        for i, item in enumerate(reversed(candidates), start=1):
            print(f"  下から{i}: {item['text']} y={item['y']}")
        return False

    bottom_order = list(reversed(candidates))
    target = bottom_order[season - 1]

    print("シーズン候補:")
    for i, item in enumerate(bottom_order[: min(len(bottom_order), 12)], start=1):
        print(f"  下から{i}: {item['text']} source={item.get('source', '')} y={item['y']}")

    choice = input(
        f"シーズン{season}として押す候補。Enter=下から{season} / 数字=下からその番号 / m=手動: "
    ).strip().lower()

    if choice == "m":
        return False

    selected_no = season

    if choice:
        try:
            selected_no = int(choice)
        except ValueError:
            print("数字か m を入力してください。手動に切り替えます。")
            return False

        if selected_no < 1 or selected_no > len(bottom_order):
            print(f"候補番号が範囲外です: {selected_no}")
            return False

        target = bottom_order[selected_no - 1]
    else:
        target = bottom_order[season - 1]

    x = float(target["x"]) + float(target["width"]) / 2
    y = float(target["y"]) + float(target["height"]) / 2
    print(f"click season {season}: 下から{selected_no} {target['text']} source={target.get('source', '')} ({x:.1f}, {y:.1f})")
    page.mouse.click(x, y)
    page.wait_for_timeout(1800)
    return True


def click_game_record_tab(page: Page) -> bool:
    return click_visible_text(page, ["大会牌譜", "牌譜"], exact=True)


def capture_season_clicks(page: Page, start_season: int, end_season: int) -> dict[int, tuple[float, float]] | None:
    if start_season == end_season:
        return None

    page.evaluate(
        """
        () => {
          window.__seasonClicks = [];
          if (window.__seasonClickHandler) {
            document.removeEventListener('click', window.__seasonClickHandler, true);
          }
          window.__seasonClickHandler = (event) => {
            window.__seasonClicks.push({
              x: event.clientX,
              y: event.clientY,
              text: (event.target?.innerText || event.target?.textContent || '').trim().slice(0, 80),
            });
          };
          document.addEventListener('click', window.__seasonClickHandler, true);
        }
        """
    )

    print()
    print("シーズン座標を記録します。")
    print(f"ブラウザ上で、まず開始シーズン{start_season}を1回クリックしてください。")
    print(f"次に終了シーズン{end_season}を1回クリックしてください。")
    print("2回クリックしたら PowerShell に戻って Enter。")
    input("クリック完了後 Enter: ")

    clicks = page.evaluate("() => window.__seasonClicks || []")
    page.evaluate(
        """
        () => {
          if (window.__seasonClickHandler) {
            document.removeEventListener('click', window.__seasonClickHandler, true);
          }
        }
        """
    )

    if len(clicks) < 2:
        print(f"クリック記録が足りません: {len(clicks)}回")
        return None

    start_click = clicks[0]
    end_click = clicks[1]
    x1 = float(start_click["x"])
    y1 = float(start_click["y"])
    x2 = float(end_click["x"])
    y2 = float(end_click["y"])

    step_count = end_season - start_season
    if step_count == 0:
        return None

    dx = (x2 - x1) / step_count
    dy = (y2 - y1) / step_count

    coords = {}
    for season in range(start_season, end_season + 1):
        offset = season - start_season
        coords[season] = (x1 + dx * offset, y1 + dy * offset)

    print("推定シーズン座標:")
    for season, (x, y) in coords.items():
        print(f"  season {season}: ({x:.1f}, {y:.1f})")

    ok = input("この座標で進めるなら Enter。やめるなら n: ").strip().lower()
    if ok == "n":
        return None

    return coords


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
    season_text = input("今回取得するシーズン番号。例: 3: ").strip()
    max_pages_text = input("1シーズン最大ページ数。分からなければ空Enterで50: ").strip()

    season = int(season_text)
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
        print()
        print(f"手でシーズン{season} → 大会牌譜を開いてください。")
        print("大会牌譜の1ページ目が表示できたら PowerShell に戻って Enter。")
        input("開けたら Enter: ")

        print()
        print("=" * 40)
        print(f"season {season}")
        rows = collect_current_season(page, season, max_pages)
        out = Path(f"admin_paifu_ids_season{season}.csv")
        write_csv_rows(out, rows)
        print(f"saved: {out} ({len(rows)}件)")

        # ひとつずつ順番に取得する前提なので、今回のシーズンより後ろの誤取得ファイルは累計に混ぜない。
        merge_targets = {
            existing
            for existing in existing_season_numbers()
            if 1 <= existing <= season
        }
        merge_targets.add(season)
        merge_targets.add(1)
        total = merge_season_files(merge_targets)
        season_counts = count_season_rows(merge_targets)
        print()
        print(f"merged cumulative: {OUT} ({total}件)")
        print("season counts:")
        for season in sorted(season_counts):
            print(f"  season {season}: {season_counts[season]}件")
        input("確認したら Enter: ")
        browser.close()


if __name__ == "__main__":
    main()
