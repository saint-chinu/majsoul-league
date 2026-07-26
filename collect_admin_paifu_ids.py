from pathlib import Path
import csv
import re
import pyperclip
from playwright.sync_api import sync_playwright

USER_DATA_DIR = Path("browser-profile")
START_URL = "https://tournament.mahjongsoul.com/contest_dashboard/index.html#/contest/48491649"
OUT = Path("admin_paifu_ids.csv")

UUID_RE = re.compile(r"\d{6}-[0-9a-fA-F-]{36}")
STOP_BEFORE = "260406"

def uuid_date_key(uuid):
    return uuid.split("-", 1)[0]

def collect_visible_page(page):
    buttons = page.locator("button").all()
    targets = []
    pager_y = find_current_pager_y(page)

    for i, button in enumerate(buttons):
        try:
            text = button.inner_text(timeout=500).strip()
            box = button.bounding_box(timeout=500)
        except Exception:
            continue

        if not box:
            continue

        # 大会牌譜の右側青ボタンだけ。
        # ページ下部の役満牌譜にも似たボタンがあるので、大会牌譜側のページャーより上だけ拾う。
        is_copy_button = (
            text == ""
            and 1180 <= box["x"] <= 1240
            and -1000 <= box["y"] <= pager_y - 20
            and 20 <= box["width"] <= 40
            and 20 <= box["height"] <= 40
        )

        if is_copy_button:
            targets.append((i, button, box))

    targets.sort(key=lambda item: item[2]["y"])

    uuids = []
    seen_on_page = set()

    for i, button, box in targets:
        pyperclip.copy("")

        try:
            button.click(force=True, timeout=3000)
        except Exception:
            continue

        page.wait_for_timeout(220)
        copied = pyperclip.paste()
        match = UUID_RE.search(copied)

        if not match:
            continue

        uuid = match.group(0)
        if uuid in seen_on_page:
            continue

        seen_on_page.add(uuid)
        uuids.append(uuid)

    return uuids

def find_current_pager_y(page):
    links = page.locator("a").all()
    ys = []

    for link in links:
        try:
            text = link.inner_text(timeout=500).strip()
            box = link.bounding_box(timeout=500)
        except Exception:
            continue

        if not box:
            continue

        if text.isdigit() and 450 <= box["y"] <= 1300:
            ys.append(box["y"])

    if not ys:
        return 1200

    return min(ys)

def click_page_number(page, page_number):
    links = page.locator("a").all()

    candidates = []
    for i, link in enumerate(links):
        try:
            text = link.inner_text(timeout=500).strip()
            box = link.bounding_box(timeout=500)
        except Exception:
            continue

        if not box:
            continue

        # 大会牌譜側のページ番号。画面の拡大率やスクロール位置でy座標が動くので広めに拾う。
        # 役満牌譜側のページャーもあるが、上にある候補を優先する。
        if (
            text == str(page_number)
            and 350 <= box["x"] <= 900
            and 250 <= box["y"] <= 1300
            and 20 <= box["width"] <= 45
            and 20 <= box["height"] <= 45
        ):
            candidates.append((i, link, box))

    if not candidates:
        return False

    candidates.sort(key=lambda item: (item[2]["y"], item[2]["x"]))
    i, link, box = candidates[0]
    print(f"click page {page_number}: a {i} {box}")

    link.click(force=True, timeout=3000)
    page.wait_for_timeout(1800)
    return True

def click_next_page(page):
    buttons = page.locator("button").all()
    pager_y = find_current_pager_y(page)

    candidates = []
    for i, button in enumerate(buttons):
        try:
            text = button.inner_text(timeout=500).strip()
            box = button.bounding_box(timeout=500)
            disabled = button.is_disabled(timeout=500)
        except Exception:
            continue

        if disabled or not box:
            continue

        # 大会牌譜側のページャーにある右矢印ボタン。
        # 役満牌譜側にもページャーがあるので、現在の大会牌譜ページャーの高さ付近だけを対象にする。
        is_next_button = (
            text == ""
            and 730 <= box["x"] <= 850
            and pager_y - 30 <= box["y"] <= pager_y + 30
            and 20 <= box["width"] <= 45
            and 20 <= box["height"] <= 45
        )

        if is_next_button:
            candidates.append((i, button, box))

    if not candidates:
        return False

    candidates.sort(key=lambda item: (item[2]["y"], item[2]["x"]))
    i, button, box = candidates[0]
    print(f"next page: button {i} {box}")
    button.click(force=True, timeout=3000)
    page.wait_for_timeout(1800)
    return True

def main():
    last_page_text = input("最終ページ番号。今回は12: ").strip()
    last_page = int(last_page_text or "12")

    with sync_playwright() as p:
        browser = p.chromium.launch_persistent_context(
            user_data_dir=str(USER_DATA_DIR),
            headless=False,
            viewport={"width": 1460, "height": 900},
        )

        page = browser.new_page()
        page.goto(START_URL, wait_until="domcontentloaded")

        print("手で テスト → シーズン1 → 大会牌譜 を開いてください。")
        print("ページ番号 1 2 3 ... 12 が見える状態にしてください。")
        input("表示できたら Enter: ")

        seen = set()
        rows = []

        for page_no in range(1, last_page + 1):
            print()
            print(f"page {page_no}")

            uuids = collect_visible_page(page)
            dates = []
            new_count = 0

            for uuid in uuids:
                date_key = uuid_date_key(uuid)
                dates.append(date_key)

                if date_key < STOP_BEFORE:
                    continue

                if uuid in seen:
                    continue

                seen.add(uuid)
                new_count += 1
                rows.append({
                    "page_no": page_no,
                    "uuid": uuid,
                    "date_key": date_key,
                    "paifu_url": f"https://game.mahjongsoul.com/?paipu={uuid}",
                })
                print(" ", uuid)

            if dates:
                print(f"date range on page: {min(dates)} - {max(dates)}")

            print(f"visible={len(uuids)} new={new_count} total={len(rows)}")

            if page_no < last_page:
                ok = click_next_page(page)
                if not ok:
                    print("次ページボタンが見つかりません。終了します。")
                    break

        rows.sort(key=lambda r: r["uuid"])

        with OUT.open("w", encoding="utf-8-sig", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=["page_no", "uuid", "date_key", "paifu_url"])
            writer.writeheader()
            writer.writerows(rows)

        print()
        print(f"saved: {OUT}")
        print(f"count: {len(rows)}")

        input("確認したら Enter: ")
        browser.close()

if __name__ == "__main__":
    main()
