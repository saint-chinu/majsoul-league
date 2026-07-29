from __future__ import annotations

import csv
import sys
from pathlib import Path

from aggregate_league import (
    decode_record,
    is_riichi_discard,
    load_detail,
    load_record_wrappers,
    new_round_dora_indicators,
    normalize_tile,
)


BASE_DIR = Path(__file__).resolve().parent
RECORDS_DIR = BASE_DIR / "records_raw"
PAIFU_CSV = BASE_DIR / "admin_paifu_ids.csv"
DEFAULT_PLAYER = "流れ者金融"
DEFAULT_OUTPUT = "nagaremono_table_discards.csv"

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


def export_table_discards(target_player: str, output_name: str) -> None:
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
        "seat",
        "player",
        "is_target_player",
        "discard_no_in_round",
        "player_discard_no_in_round",
        "tile",
        "normalized_tile",
        "is_red_five",
        "is_tsumogiri",
        "is_riichi_declaration",
        "dora_indicators",
        "round_start_score",
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
        discard_no_in_round = 0
        player_discards = {seat: 0 for seat in range(3)}

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
                discard_no_in_round = 0
                player_discards = {seat: 0 for seat in range(3)}
                continue

            if record_name != ".lq.RecordDiscardTile":
                continue

            seat = get_int(msg, "seat")
            if seat == "":
                continue

            discard_no_in_round += 1
            player_discards[seat] = player_discards.get(seat, 0) + 1

            tile = getattr(msg, "tile", "")
            start_score = ""
            if isinstance(round_start_scores, list) and 0 <= seat < len(round_start_scores):
                start_score = int(round_start_scores[seat])

            exported.append(
                {
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
                    "seat": seat,
                    "player": seat_to_name.get(seat, f"seat{seat}"),
                    "is_target_player": 1 if seat in target_seats else 0,
                    "discard_no_in_round": discard_no_in_round,
                    "player_discard_no_in_round": player_discards[seat],
                    "tile": tile,
                    "normalized_tile": normalize_tile(tile),
                    "is_red_five": 1 if tile.startswith("0") else 0,
                    "is_tsumogiri": 1 if get_bool(msg, "moqie", "is_tsumogiri", "isTsumogiri") else 0,
                    "is_riichi_declaration": 1 if is_riichi_discard(msg) else 0,
                    "dora_indicators": " ".join(dora_indicators),
                    "round_start_score": start_score,
                }
            )

    with output_path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(exported)

    print(f"target player: {target_player}")
    print(f"source records: {len(source_rows)}")
    print(f"scanned target games: {scanned}")
    print(f"skipped missing raw files: {skipped_missing}")
    print(f"skipped no target player: {skipped_no_target_player}")
    print(f"discard rows: {len(exported)}")
    print(f"saved: {output_path}")


def main() -> None:
    target_player = sys.argv[1] if len(sys.argv) >= 2 else DEFAULT_PLAYER
    output_name = sys.argv[2] if len(sys.argv) >= 3 else DEFAULT_OUTPUT
    export_table_discards(target_player, output_name)


if __name__ == "__main__":
    main()
