from pathlib import Path
from datetime import datetime
import base64
import json
import re

from playwright.sync_api import sync_playwright

USER_DATA_DIR = Path("browser-profile")
OUTPUT_DIR = Path("captures")
START_URL = "https://tournament.mahjongsoul.com/contest_dashboard/index.html#/contest/48491649"


def safe_text(value, limit=500000):
    if value is None:
        return ""
    return str(value)[:limit]


def main():
    OUTPUT_DIR.mkdir(exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")

    network_path = OUTPUT_DIR / f"team-page-network-{stamp}.jsonl"
    snapshot_path = OUTPUT_DIR / f"team-page-{stamp}.json"
    screenshot_path = OUTPUT_DIR / f"team-page-{stamp}.png"

    method_pattern = re.compile(rb"\.lq\.[A-Za-z0-9_.]+")

    print("雀魂大会の管理者画面を開きます。")
    print("手で、チーム内訳/チーム設定/参加者一覧など、チーム名とメンバー名が見える画面まで移動してください。")
    print("表示できたら PowerShell に戻って Enter。")

    with network_path.open("w", encoding="utf-8") as network_file:
        with sync_playwright() as p:
            browser = p.chromium.launch_persistent_context(
                user_data_dir=str(USER_DATA_DIR),
                headless=False,
                viewport={"width": 1366, "height": 768},
            )

            page = browser.new_page()

            def write_network(row):
                network_file.write(json.dumps(row, ensure_ascii=False) + "\n")
                network_file.flush()

            def on_response(response):
                url = response.url
                lowered = url.lower()
                if not any(
                    key in lowered
                    for key in [
                        "contest",
                        "team",
                        "player",
                        "participant",
                        "member",
                        "season",
                        "rank",
                        "mahjong",
                        "mahjongsoul",
                    ]
                ):
                    return

                try:
                    body = response.text()
                except Exception:
                    return

                write_network(
                    {
                        "type": "http_response",
                        "url": url,
                        "status": response.status,
                        "content_type": response.headers.get("content-type", ""),
                        "body": body[:800000],
                    }
                )

            def on_websocket(ws):
                print("WebSocket:", ws.url)

                def save_frame(direction, payload):
                    if isinstance(payload, bytes):
                        raw = payload
                        body = base64.b64encode(raw).decode("ascii")
                        encoding = "base64"
                    else:
                        body = str(payload)
                        raw = body.encode("utf-8", errors="ignore")
                        encoding = "text"

                    methods = [
                        m.decode("utf-8", errors="ignore")
                        for m in method_pattern.findall(raw)
                    ]

                    interesting_methods = [
                        m for m in methods
                        if any(
                            key in m.lower()
                            for key in [
                                "contest",
                                "team",
                                "player",
                                "member",
                                "season",
                                "rank",
                            ]
                        )
                    ]
                    if interesting_methods:
                        print(direction, interesting_methods)

                    write_network(
                        {
                            "type": "websocket_frame",
                            "direction": direction,
                            "ws_url": ws.url,
                            "methods": methods,
                            "encoding": encoding,
                            "body": body[:1000000],
                        }
                    )

                ws.on("framesent", lambda payload: save_frame("sent", payload))
                ws.on("framereceived", lambda payload: save_frame("received", payload))

            page.on("response", on_response)
            page.on("websocket", on_websocket)

            page.goto(START_URL, wait_until="domcontentloaded")
            input("チーム情報が見える画面まで移動できたら Enter: ")

            snapshot = page.evaluate(
                """
                () => {
                  const visible = (el) => {
                    const style = window.getComputedStyle(el);
                    const rect = el.getBoundingClientRect();
                    return style.visibility !== 'hidden'
                      && style.display !== 'none'
                      && rect.width > 0
                      && rect.height > 0;
                  };
                  const box = (el) => {
                    const r = el.getBoundingClientRect();
                    return {x: r.x, y: r.y, width: r.width, height: r.height};
                  };
                  const textOf = (el) => (el.innerText || el.textContent || '').trim();
                  const pick = (selector) => Array.from(document.querySelectorAll(selector))
                    .filter(visible)
                    .map((el, index) => ({
                      index,
                      tag: el.tagName.toLowerCase(),
                      text: textOf(el).slice(0, 5000),
                      value: el.value || '',
                      placeholder: el.getAttribute('placeholder') || '',
                      title: el.getAttribute('title') || '',
                      ariaLabel: el.getAttribute('aria-label') || '',
                      className: String(el.className || ''),
                      box: box(el),
                    }));

                  const tables = Array.from(document.querySelectorAll('table'))
                    .filter(visible)
                    .map((table, index) => ({
                      index,
                      text: textOf(table).slice(0, 50000),
                      rows: Array.from(table.querySelectorAll('tr')).map((tr) =>
                        Array.from(tr.querySelectorAll('th,td')).map((cell) => textOf(cell))
                      ),
                      box: box(table),
                    }));

                  return {
                    url: location.href,
                    title: document.title,
                    bodyText: textOf(document.body).slice(0, 300000),
                    buttons: pick('button,[role="button"],a'),
                    inputs: pick('input,textarea,[contenteditable="true"]'),
                    cards: pick('[class*="card"],[class*="Card"],[class*="team"],[class*="Team"],[class*="member"],[class*="Member"],[class*="player"],[class*="Player"]'),
                    tables,
                    localStorage: Object.fromEntries(Object.entries(window.localStorage || {})),
                    sessionStorage: Object.fromEntries(Object.entries(window.sessionStorage || {})),
                  };
                }
                """
            )

            snapshot_path.write_text(
                json.dumps(snapshot, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            page.screenshot(path=str(screenshot_path), full_page=True)
            browser.close()

    print(f"保存しました: {snapshot_path}")
    print(f"通信ログ: {network_path}")
    print(f"スクショ: {screenshot_path}")
    print("次は team-page-*.json の中身、または保存ファイル名を貼ってください。")


if __name__ == "__main__":
    main()
