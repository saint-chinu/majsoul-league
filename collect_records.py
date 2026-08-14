import base64
import csv
import json
import re
import sys
import time
from pathlib import Path

from playwright.sync_api import sync_playwright

USER_DATA_DIR = Path("browser-profile")
DEFAULT_RECORD_LIST = Path("admin_paifu_ids.csv")
OUT_DIR = Path("records_raw")

method_pattern = re.compile(rb"\.lq\.[A-Za-z0-9_.]+")

def read_records(record_list, limit=None):
    rows = []
    with record_list.open("r", encoding="utf-8-sig", newline="") as f:
        for row in csv.DictReader(f):
            rows.append(row)
    if limit:
        rows = rows[:limit]
    return rows

def frame_id(raw):
    if len(raw) < 3:
        return None
    return raw[1] + raw[2] * 256

def main():
    record_list = DEFAULT_RECORD_LIST
    limit = None

    if len(sys.argv) >= 2:
        first_arg = sys.argv[1]
        if first_arg.isdigit():
            limit = int(first_arg)
        else:
            record_list = Path(first_arg)

    if len(sys.argv) >= 3:
        limit = int(sys.argv[2])

    rows = read_records(record_list, limit)
    OUT_DIR.mkdir(exist_ok=True)

    print(f"対象CSV: {record_list}")
    print(f"対象: {len(rows)}件")

    with sync_playwright() as p:
        browser = p.chromium.launch_persistent_context(
            user_data_dir=str(USER_DATA_DIR),
            headless=False,
            viewport={"width": 1366, "height": 768},
        )

        for index, row in enumerate(rows, start=1):
            uuid = row["uuid"]
            url = row["paifu_url"]

            record_bin = OUT_DIR / f"{uuid}_record.bin"
            detail_bin = OUT_DIR / f"{uuid}_detail.bin"
            meta_json = OUT_DIR / f"{uuid}_meta.json"

            if record_bin.exists() and detail_bin.exists():
                print(f"[{index}/{len(rows)}] skip {uuid}")
                continue

            print(f"[{index}/{len(rows)}] open {uuid}")

            state = {
                "detail_request_ids": set(),
                "got_record": False,
                "got_detail": False,
            }

            page = browser.new_page()

            def save_meta(extra):
                meta = {
                    "uuid": uuid,
                    "url": url,
                    "source": row,
                    **extra,
                }
                meta_json.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")

            def on_websocket(ws):
                def save_frame(direction, payload):
                    if isinstance(payload, bytes):
                        raw = payload
                    else:
                        raw = str(payload).encode("utf-8", errors="ignore")

                    methods = [
                        m.decode("utf-8", errors="ignore")
                        for m in method_pattern.findall(raw)
                    ]

                    fid = frame_id(raw)

                    if direction == "sent":
                        if ".lq.Lobby.fetchGameRecordsDetailV2" in methods:
                            state["detail_request_ids"].add(fid)

                    if direction == "received":
                        if fid in state["detail_request_ids"] and len(raw) > 20:
                            detail_bin.write_bytes(raw)
                            state["got_detail"] = True

                        has_record_body = (
                            b".lq.RecordNewRound" in raw
                            and b".lq.RecordDiscardTile" in raw
                            and len(raw) > 1000
                        )

                        if has_record_body:
                            record_bin.write_bytes(raw)
                            state["got_record"] = True

                ws.on("framesent", lambda payload: save_frame("sent", payload))
                ws.on("framereceived", lambda payload: save_frame("received", payload))

            page.on("websocket", on_websocket)

            try:
                page.goto(url, wait_until="domcontentloaded", timeout=90000)

                deadline = time.time() + 90
                while time.time() < deadline:
                    if state["got_record"] and state["got_detail"]:
                        break
                    page.wait_for_timeout(1000)

                save_meta({
                    "got_record": state["got_record"],
                    "got_detail": state["got_detail"],
                })

                print(
                    f"  record={state['got_record']} "
                    f"detail={state['got_detail']}"
                )

            except Exception as e:
                save_meta({
                    "got_record": state["got_record"],
                    "got_detail": state["got_detail"],
                    "error": repr(e),
                })
                print(f"  ERROR {e}")

            finally:
                page.close()

        browser.close()

    print("完了")

if __name__ == "__main__":
    main()
