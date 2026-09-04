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

# 破壊的ボタン（削除・クリア等）の兆候。class/aria-label/アイコンHTMLのどこかに
# これが見えたら、そのボタンには絶対に触れない。管理画面には牌譜削除ボタンが
# あり、座標だけの判定で誤クリックすると大会データが消えるため、判定は
# 「危険が否定できないものは押さない」方向に倒す。
DANGER_MARKER_RE = re.compile(
    r"delete|trash|remove|minus|close|clear|danger|削除|消去|クリア", re.IGNORECASE
)
# コピーボタンの兆候（Ant Designのanticon-copy等）。
COPY_MARKER_RE = re.compile(r"copy|コピー", re.IGNORECASE)
# 較正後に同じ「コピー列」とみなすx座標の許容ずれ。
COPY_COLUMN_TOLERANCE_PX = 12


def install_dialog_guard(page):
    """confirm/alert等のネイティブダイアログが出たら常に拒否する。
    誤って破壊的ボタンに触れても、確認ダイアログで必ず止まるようにする保険。"""
    if getattr(page, "_cq_dialog_guard", False):
        return
    page.on("dialog", lambda dialog: dialog.dismiss())
    page._cq_dialog_guard = True


def install_clipboard_write_capture(page):
    """コピーAPIへ渡される文字列をページ内にも記録する。

    Windowsの共有クリップボードがロックされていても、ボタンのコピー処理が
    渡そうとした牌譜URLをここから取れるため、OS側のClipboardを読めない
    バックグラウンド実行でも止まらない。
    """
    if getattr(page, "_cq_clipboard_capture", False):
        return
    page.evaluate(
        """
        () => {
          if (window.__cqClipboardCaptureInstalled) return;
          window.__cqClipboardCaptureInstalled = true;
          window.__cqLastCopiedText = '';
          const remember = (text) => {
            window.__cqLastCopiedText = String(text || '');
          };
          try {
            const original = navigator.clipboard.writeText.bind(navigator.clipboard);
            navigator.clipboard.writeText = async (text) => {
              remember(text);
              return original(text);
            };
          } catch (_) {}
          try {
            const originalExecCommand = document.execCommand.bind(document);
            document.execCommand = (command, ...args) => {
              if (String(command).toLowerCase() === 'copy') {
                remember(window.getSelection ? window.getSelection().toString() : '');
              }
              return originalExecCommand(command, ...args);
            };
          } catch (_) {}
          document.addEventListener('copy', (event) => {
            const text = (event.clipboardData && event.clipboardData.getData('text/plain'))
              || String(window.getSelection ? window.getSelection().toString() : '');
            if (text) remember(text);
          });
        }
        """
    )
    page._cq_clipboard_capture = True


def dismiss_unexpected_overlay(page) -> bool:
    """クリック後にモーダル/ポップ確認が出ていたらEscapeで閉じてTrueを返す。
    コピーボタンはクリップボードへ書くだけでUIは開かないので、何かが開いた=
    押してはいけないボタンだったサイン。確認ボタンには一切触れずEscapeのみ。"""
    appeared = page.evaluate(
        """
        () => {
          const selectors = ['.ant-modal-wrap', '.ant-popover:not(.ant-popover-hidden)', '.ant-popconfirm', '.ant-modal-confirm'];
          for (const selector of selectors) {
            for (const el of document.querySelectorAll(selector)) {
              const rect = el.getBoundingClientRect();
              const style = window.getComputedStyle(el);
              if (rect.width > 50 && rect.height > 40 && style.display !== 'none' && style.visibility !== 'hidden') {
                return true;
              }
            }
          }
          return false;
        }
        """
    )
    if appeared:
        page.keyboard.press("Escape")
        page.wait_for_timeout(500)
        page.keyboard.press("Escape")
        page.wait_for_timeout(300)
    return appeared


def classify_button(button) -> tuple[str, str]:
    """ボタンを 'copy' / 'unknown' / 'danger' に分類する。判定材料も返す。"""
    try:
        info = button.evaluate(
            "(el) => (el.className || '') + ' | ' + (el.getAttribute('aria-label') || '')"
            " + ' | ' + el.innerHTML.slice(0, 400)"
        )
    except Exception:
        return "unknown", ""
    if DANGER_MARKER_RE.search(info):
        return "danger", info[:120]
    if COPY_MARKER_RE.search(info):
        return "copy", info[:120]
    return "unknown", info[:120]


def uuid_date_key(uuid):
    return uuid.split("-", 1)[0]

def collect_visible_page(page, *, max_scan_attempts=6):
    """表示中ページの大会牌譜コピーボタンを全て押してUUIDを回収する。

    強化点（従来は固定800ms待ち→座標一致のボタンを無差別クリックだった）:
    - テーブル描画をポーリングで待つ。0件なら軽くスクロールして再スキャン
      （「読み込みが遅くて0件で終わる」対策）。
    - ボタンをclass/aria/アイコンで分類し、削除系の兆候があるものは絶対に押さない。
    - 最初にUUIDが取れたボタンのx座標で「コピー列」を較正し、以後はその列だけ押す。
    - 較正前にクリップボードへUUIDが入らない不明ボタンを連打しない。
    - クリック後にモーダル/確認が開いたらEscapeで閉じ、そのボタンは二度と押さない。
    """
    install_dialog_guard(page)
    install_clipboard_write_capture(page)

    uuids = []
    seen_on_page = set()

    for attempt in range(max_scan_attempts):
        page.wait_for_timeout(800 if attempt == 0 else 1500)
        if attempt in (2, 4):
            # 遅延描画・仮想スクロール対策で軽く揺らす。
            page.mouse.wheel(0, -600)
            page.wait_for_timeout(300)
            page.mouse.wheel(0, 600)
            page.wait_for_timeout(500)

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

            # 大会牌譜の右側コピーボタン想定域。役満牌譜側を避けるため
            # 大会牌譜側ページャーより上だけを拾う。
            in_copy_area = (
                text == ""
                and 900 <= box["x"] <= 1500
                and -2000 <= box["y"] <= pager_y - 12
                and 18 <= box["width"] <= 52
                and 18 <= box["height"] <= 52
            )
            if not in_copy_area:
                continue

            kind, detail = classify_button(button)
            if kind == "danger":
                print(f"  skip danger button at ({box['x']:.0f},{box['y']:.0f}): {detail}")
                continue
            targets.append((kind, i, button, box))

        # コピーと確認できたボタンがあればそれだけに絞る（不明ボタンは押さない）。
        copy_targets = [t for t in targets if t[0] == "copy"]
        if copy_targets:
            targets = copy_targets
        targets.sort(key=lambda item: item[3]["y"])
        print(f"copy button candidates: {len(targets)} (scan {attempt + 1}/{max_scan_attempts})")

        calibrated_x = None
        blocked = False

        for kind, i, button, box in targets:
            if calibrated_x is not None and abs(box["x"] - calibrated_x) > COPY_COLUMN_TOLERANCE_PX:
                continue

            match = copy_uuid_from_button(page, button)

            if dismiss_unexpected_overlay(page):
                print(f"  モーダルが開いたため中断・このボタンは押しません ({box['x']:.0f},{box['y']:.0f})")
                if calibrated_x is None:
                    blocked = True
                    break
                continue

            if not match:
                # 較正前に「コピー確証のない」ボタンで空振りしたら、列を誤認して
                # いる可能性があるので連打せず次のスキャンへ回す。
                if calibrated_x is None and kind != "copy":
                    break
                continue

            calibrated_x = box["x"]
            uuid = match.group(0)
            if uuid in seen_on_page:
                continue
            seen_on_page.add(uuid)
            uuids.append(uuid)

        if uuids or blocked:
            break

    return uuids


def copy_uuid_from_button(page, button):
    if not getattr(page, "_cq_clipboard_permission", False):
        try:
            page.context.grant_permissions(
                ["clipboard-read", "clipboard-write"],
                origin="https://tournament.mahjongsoul.com",
            )
        except Exception:
            pass
        page._cq_clipboard_permission = True

    def browser_clipboard_text():
        try:
            return page.evaluate(
                """async () => {
                    try { return await navigator.clipboard.readText(); }
                    catch (_) { return ''; }
                }"""
            )
        except Exception:
            return ""

    def captured_copy_text():
        try:
            return page.evaluate("() => window.__cqLastCopiedText || ''")
        except Exception:
            return ""

    for method in ("dom", "force", "mouse"):
        # Windowsのクリップボードはブラウザや常駐アプリに一瞬掴まれることがある。
        # ここで落ちると牌譜取得全体が止まるため、短く待って取り直す。
        try:
            pyperclip.copy("")
        except pyperclip.PyperclipException:
            # pyperclipが掴めない場合でも、ブラウザ側のClipboard APIで読めることがある。
            pass

        try:
            page.evaluate("() => { window.__cqLastCopiedText = ''; }")
        except Exception:
            pass

        try:
            if method == "dom":
                button.evaluate("(el) => el.click()")
            elif method == "force":
                button.click(force=True, timeout=3000)
            else:
                box = button.bounding_box(timeout=700)
                if not box:
                    continue
                page.mouse.click(box["x"] + box["width"] / 2, box["y"] + box["height"] / 2)
        except Exception:
            continue

        page.wait_for_timeout(260)
        match = UUID_RE.search(captured_copy_text())
        if match:
            return match
        match = UUID_RE.search(browser_clipboard_text())
        if match:
            return match
        for _ in range(6):
            try:
                copied = pyperclip.paste()
            except pyperclip.PyperclipException:
                page.wait_for_timeout(250)
                continue
            match = UUID_RE.search(copied)
            if match:
                return match
            page.wait_for_timeout(120)

    return None

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
    clicked_by_dom = page.evaluate(
        """
        () => {
          const paginations = Array.from(document.querySelectorAll('ul.ant-pagination'));
          const candidates = [];

          for (const pagination of paginations) {
            const rect = pagination.getBoundingClientRect();
            if (rect.width < 80 || rect.height < 20) continue;
            if (rect.bottom < 0 || rect.top > window.innerHeight + 800) continue;

            const next = pagination.querySelector('li.ant-pagination-next');
            if (!next) continue;

            const className = next.className || '';
            const disabled =
              className.includes('disabled') ||
              next.getAttribute('aria-disabled') === 'true' ||
              next.querySelector('button')?.disabled === true;

            if (disabled) continue;

            const active = pagination.querySelector('li.ant-pagination-item-active');
            const activeText = active ? (active.innerText || active.textContent || '').trim() : '';
            const nextRect = next.getBoundingClientRect();
            candidates.push({
              next,
              top: rect.top,
              left: rect.left,
              activeText,
              x: nextRect.left + nextRect.width / 2,
              y: nextRect.top + nextRect.height / 2,
            });
          }

          if (!candidates.length) return null;

          candidates.sort((a, b) => a.top - b.top || a.left - b.left);
          const target = candidates[0];
          const clickable = target.next.querySelector('button,a') || target.next;
          clickable.click();
          return {
            top: target.top,
            left: target.left,
            activeText: target.activeText,
            x: target.x,
            y: target.y,
          };
        }
        """
    )

    if clicked_by_dom:
        print(f"next page: ant pagination {clicked_by_dom}")
        page.wait_for_timeout(2500)
        return True

    pager_y = find_current_pager_y(page)

    # Ant Designのページャー本体を優先して押す。
    # 画面下に役満牌譜用のページャーもあるので、上側にある大会牌譜ページャーだけを候補にする。
    candidates = []
    pagers = page.locator("li.ant-pagination-next").all()

    for i, pager in enumerate(pagers):
        try:
            box = pager.bounding_box(timeout=500)
            class_name = pager.get_attribute("class", timeout=500) or ""
            aria_disabled = pager.get_attribute("aria-disabled", timeout=500)
            button = pager.locator("button").first
            button_disabled = button.is_disabled(timeout=500) if button.count() else False
        except Exception:
            continue

        if not box:
            continue

        disabled = (
            "disabled" in class_name
            or aria_disabled == "true"
            or button_disabled
        )
        if disabled:
            continue

        is_upper_record_pager = (
            250 <= box["y"] <= 1300
            and abs(box["y"] - pager_y) <= 90
            and 20 <= box["width"] <= 50
            and 20 <= box["height"] <= 50
        )

        if is_upper_record_pager:
            candidates.append((i, pager, box))

    if candidates:
        candidates.sort(key=lambda item: (item[2]["y"], item[2]["x"]))
        i, pager, box = candidates[0]
        print(f"next page: pagination {i} {box}")
        page.mouse.click(box["x"] + box["width"] / 2, box["y"] + box["height"] / 2)
        page.wait_for_timeout(2500)
        return True

    buttons = page.locator("button").all()
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
            and 600 <= box["x"] <= 950
            and pager_y - 90 <= box["y"] <= pager_y + 90
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
    page.wait_for_timeout(2500)
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
