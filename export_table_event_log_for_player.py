from __future__ import annotations

import csv
import json
import sys
from pathlib import Path

from google.protobuf.json_format import MessageToDict

from aggregate_league import (
    decode_record,
    is_riichi_discard,
    load_detail,
    load_record_wrappers,
    new_round_dora_indicators,
    normalize_tile,
)
from analyze_ryanmen_riichi_wait_patterns import msg_tiles


BASE_DIR = Path(__file__).resolve().parent
RECORDS_DIR = BASE_DIR / "records_raw"
PAIFU_CSV = BASE_DIR / "admin_paifu_ids.csv"
DEFAULT_PLAYER = "流れ者金融"
DEFAULT_OUTPUT = "nagaremono_table_event_log.csv"

ROUND_WINDS = ["東", "南", "西", "北"]


def get_bool(msg, *names: str) -> bool:
    for name in names:
        if hasattr(msg, name) and bool(getattr(msg, name)):
            return True
    return False


def get_int(msg, name: str, default=""):
    if msg is None or not hasattr(msg, name):
        return default
    value = getattr(msg, name)
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def round_label(chang, ju) -> str:
    if chang == "" or ju == "":
        return ""
    wind = ROUND_WINDS[chang] if 0 <= chang < len(ROUND_WINDS) else str(chang)
    return f"{wind}{ju + 1}局"


def read_source_rows(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        rows = list(csv.DictReader(f))

    unique = {}
    for row in rows:
        uuid = row.get("uuid", "").strip()
        if uuid:
            unique[uuid] = row
    return list(unique.values())


def json_value(value) -> str:
    def convert(item):
        if isinstance(item, (str, int, float, bool)) or item is None:
            return item
        if isinstance(item, list):
            return [convert(child) for child in item]
        if isinstance(item, tuple):
            return [convert(child) for child in item]
        if isinstance(item, dict):
            return {key: convert(child) for key, child in item.items()}
        try:
            return MessageToDict(item, preserving_proto_field_name=True)
        except Exception:
            return str(item)

    return json.dumps(convert(value), ensure_ascii=False, separators=(",", ":"))


def score_at(scores: list[int], seat: int):
    if isinstance(scores, list) and 0 <= seat < len(scores):
        return int(scores[seat])
    return ""


def hule_payment_type(hule) -> str:
    return "ツモ" if bool(getattr(hule, "zimo", False)) else "ロン"


def hule_loser_seat(hule, delta_scores: list[int]):
    if bool(getattr(hule, "zimo", False)) or not delta_scores:
        return ""
    loser = min(range(len(delta_scores)), key=lambda i: delta_scores[i])
    return loser if delta_scores[loser] < 0 else ""


def hule_point_text(hule) -> str:
    candidates = [
        "point_sum",
        "point_rong",
        "point_zimo_qin",
        "point_zimo_xian",
        "dadian",
    ]
    parts = []
    for name in candidates:
        if hasattr(hule, name):
            value = int(getattr(hule, name))
            if value:
                parts.append(f"{name}={value}")
    return " ".join(parts)


def hule_fan_text(hule) -> str:
    fans = []
    if hasattr(hule, "fans"):
        for fan in hule.fans:
            fan_id = get_int(fan, "id")
            fan_val = get_int(fan, "val")
            fans.append(f"id{fan_id}:{fan_val}")
    return " ".join(fans)


def export_event_log(target_player: str, output_name: str) -> None:
    output_path = BASE_DIR / output_name
    source_rows = read_source_rows(PAIFU_CSV)

    fieldnames = [
        "season",
        "uuid",
        "date_key",
        "round_no",
        "round_label",
        "round_wind_index",
        "round_kyoku_index",
        "honba",
        "riichi_sticks",
        "target_player",
        "target_seat",
        "event_no_in_game",
        "event_no_in_round",
        "event_type",
        "seat",
        "player",
        "is_target_player",
        "tile",
        "normalized_tile",
        "is_red_five",
        "is_tsumogiri",
        "is_riichi_declaration",
        "call_tiles",
        "call_raw",
        "winner_seat",
        "winner",
        "loser_seat",
        "loser",
        "win_type",
        "hu_tile",
        "han_fu_points",
        "fan_ids",
        "delta_scores",
        "scores_after",
        "round_start_scores",
        "dora_indicators",
        "raw_record_type",
        "raw_json",
    ]

    exported = []
    scanned = 0
    skipped_missing = 0
    skipped_no_target_player = 0

    for source in source_rows:
        uuid = source.get("uuid", "").strip()
        if not uuid:
            continue

        record_path = RECORDS_DIR / f"{uuid}_record.bin"
        detail_path = RECORDS_DIR / f"{uuid}_detail.bin"
        if not record_path.exists() or not detail_path.exists():
            skipped_missing += 1
            continue

        seat_to_name, _player_details = load_detail(detail_path)
        target_seats = {seat for seat, name in seat_to_name.items() if name == target_player}
        if not target_seats:
            skipped_no_target_player += 1
            continue

        target_seat_text = " ".join(str(seat) for seat in sorted(target_seats))
        wrappers = load_record_wrappers(record_path)
        scanned += 1

        round_no = 0
        chang = ""
        ju = ""
        honba = ""
        riichi_sticks = ""
        dora_indicators = []
        round_start_scores = []
        event_no_in_game = 0
        event_no_in_round = 0

        def base_row(event_type: str, record_type: str, msg=None) -> dict[str, str]:
            nonlocal event_no_in_game, event_no_in_round
            event_no_in_game += 1
            event_no_in_round += 1
            return {
                "season": source.get("season", ""),
                "uuid": uuid,
                "date_key": source.get("date_key", uuid[:6]),
                "round_no": round_no,
                "round_label": round_label(chang, ju),
                "round_wind_index": chang,
                "round_kyoku_index": ju,
                "honba": honba,
                "riichi_sticks": riichi_sticks,
                "target_player": target_player,
                "target_seat": target_seat_text,
                "event_no_in_game": event_no_in_game,
                "event_no_in_round": event_no_in_round,
                "event_type": event_type,
                "seat": "",
                "player": "",
                "is_target_player": "",
                "tile": "",
                "normalized_tile": "",
                "is_red_five": "",
                "is_tsumogiri": "",
                "is_riichi_declaration": "",
                "call_tiles": "",
                "call_raw": "",
                "winner_seat": "",
                "winner": "",
                "loser_seat": "",
                "loser": "",
                "win_type": "",
                "hu_tile": "",
                "han_fu_points": "",
                "fan_ids": "",
                "delta_scores": "",
                "scores_after": "",
                "round_start_scores": json_value(round_start_scores),
                "dora_indicators": " ".join(dora_indicators),
                "raw_record_type": record_type,
                "raw_json": json_value(MessageToDict(msg, preserving_proto_field_name=True)) if msg is not None else "",
            }

        for wrapper in wrappers:
            record_name = wrapper["name"]
            msg = decode_record(record_name, wrapper["body"])
            if msg is None:
                continue

            if record_name == ".lq.RecordNewRound":
                round_no += 1
                chang = get_int(msg, "chang")
                ju = get_int(msg, "ju")
                honba = get_int(msg, "ben")
                riichi_sticks = get_int(msg, "liqibang")
                dora_indicators = new_round_dora_indicators(msg)
                round_start_scores = list(msg.scores) if hasattr(msg, "scores") else []
                event_no_in_round = 0
                row = base_row("局開始", record_name, msg)
                row["scores_after"] = json_value(round_start_scores)
                exported.append(row)
                continue

            if record_name == ".lq.RecordDiscardTile":
                seat = get_int(msg, "seat")
                if seat == "":
                    continue
                tile = getattr(msg, "tile", "")
                row = base_row("リーチ" if is_riichi_discard(msg) else "打牌", record_name, msg)
                row["seat"] = seat
                row["player"] = seat_to_name.get(seat, f"seat{seat}")
                row["is_target_player"] = 1 if seat in target_seats else 0
                row["tile"] = tile
                row["normalized_tile"] = normalize_tile(tile)
                row["is_red_five"] = 1 if tile.startswith("0") else 0
                row["is_tsumogiri"] = 1 if get_bool(msg, "moqie", "is_tsumogiri", "isTsumogiri") else 0
                row["is_riichi_declaration"] = 1 if is_riichi_discard(msg) else 0
                exported.append(row)
                continue

            if record_name in [".lq.RecordChiPengGang", ".lq.RecordAnGangAddGang"]:
                seat = get_int(msg, "seat")
                if seat == "":
                    continue
                tiles = msg_tiles(msg)
                row = base_row("鳴き/槓", record_name, msg)
                row["seat"] = seat
                row["player"] = seat_to_name.get(seat, f"seat{seat}")
                row["is_target_player"] = 1 if seat in target_seats else 0
                row["call_tiles"] = " ".join(tiles)
                row["call_raw"] = row["raw_json"]
                exported.append(row)
                continue

            if record_name == ".lq.RecordBaBei":
                seat = get_int(msg, "seat")
                if seat == "":
                    continue
                row = base_row("北抜き", record_name, msg)
                row["seat"] = seat
                row["player"] = seat_to_name.get(seat, f"seat{seat}")
                row["is_target_player"] = 1 if seat in target_seats else 0
                row["tile"] = "4z"
                row["normalized_tile"] = "4z"
                exported.append(row)
                continue

            if record_name == ".lq.RecordHule":
                delta_scores = list(msg.delta_scores) if hasattr(msg, "delta_scores") else []
                scores_after = list(msg.scores) if hasattr(msg, "scores") else []
                for hule in getattr(msg, "hules", []):
                    winner_seat = get_int(hule, "seat")
                    loser_seat = hule_loser_seat(hule, delta_scores)
                    row = base_row("和了", record_name, msg)
                    row["winner_seat"] = winner_seat
                    row["winner"] = seat_to_name.get(winner_seat, f"seat{winner_seat}") if winner_seat != "" else ""
                    row["loser_seat"] = loser_seat
                    row["loser"] = seat_to_name.get(loser_seat, f"seat{loser_seat}") if loser_seat != "" else ""
                    row["seat"] = winner_seat
                    row["player"] = row["winner"]
                    row["is_target_player"] = 1 if winner_seat in target_seats else 0
                    row["win_type"] = hule_payment_type(hule)
                    row["hu_tile"] = normalize_tile(getattr(hule, "hu_tile", ""))
                    row["tile"] = row["hu_tile"]
                    row["normalized_tile"] = row["hu_tile"]
                    row["han_fu_points"] = hule_point_text(hule)
                    row["fan_ids"] = hule_fan_text(hule)
                    row["delta_scores"] = json_value(delta_scores)
                    row["scores_after"] = json_value(scores_after)
                    exported.append(row)
                continue

            if record_name == ".lq.RecordNoTile":
                row = base_row("流局", record_name, msg)
                if hasattr(msg, "scores"):
                    row["scores_after"] = json_value(list(msg.scores))
                if hasattr(msg, "delta_scores"):
                    row["delta_scores"] = json_value(list(msg.delta_scores))
                exported.append(row)

    with output_path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(exported)

    print(f"target player: {target_player}")
    print(f"source records: {len(source_rows)}")
    print(f"scanned target games: {scanned}")
    print(f"skipped missing raw files: {skipped_missing}")
    print(f"skipped no target player: {skipped_no_target_player}")
    print(f"event rows: {len(exported)}")
    print(f"saved: {output_path}")


def main() -> None:
    target_player = sys.argv[1] if len(sys.argv) >= 2 else DEFAULT_PLAYER
    output_name = sys.argv[2] if len(sys.argv) >= 3 else DEFAULT_OUTPUT
    export_event_log(target_player, output_name)


if __name__ == "__main__":
    main()
