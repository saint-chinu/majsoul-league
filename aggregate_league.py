from pathlib import Path
from collections import defaultdict, Counter
from dataclasses import dataclass, field
import csv

import ms.protocol_pb2 as pb
from google.protobuf.json_format import MessageToDict

RAW_DIR = Path("records_raw")
SUMMARY_OUT = Path("summary.csv")
YAKUMAN_OUT = Path("yakuman_summary.csv")
YAKUMAN_DETAILS_OUT = Path("yakuman_details.csv")

YAKUMAN_NAMES = {
    37: "大三元",
    38: "四暗刻",
    39: "四暗刻単騎",
    40: "字一色",
    41: "清老頭",
    42: "国士無双",
    43: "国士無双十三面",
    44: "大四喜",
    45: "小四喜",
    46: "緑一色",
    47: "九蓮宝燈",
    48: "純正九蓮宝燈",
    49: "四槓子",
    50: "天和",
    51: "地和",
}

@dataclass
class PlayerStats:
    games: int = 0
    score_sum: float = 0.0
    rank_sum: int = 0
    rank_counts: Counter = field(default_factory=Counter)
    rounds: int = 0
    hu: int = 0
    tsumo: int = 0
    hu_point_sum: int = 0
    houjuu: int = 0
    called: int = 0
    riichi: int = 0
    final_points: list = field(default_factory=list)
    yakuman_count: int = 0
    yakuman_names: Counter = field(default_factory=Counter)


RANK_SCORE_OFFSETS = {
    1: 20,
    2: 35,
    3: 50,
}

def read_varint(data, pos):
    value = 0
    shift = 0
    while pos < len(data):
        b = data[pos]
        pos += 1
        value |= (b & 0x7F) << shift
        if not (b & 0x80):
            return value, pos
        shift += 7
    raise ValueError("bad varint")

def read_fields(data):
    pos = 0
    fields = []
    while pos < len(data):
        key, pos = read_varint(data, pos)
        field_no = key >> 3
        wire_type = key & 7

        if wire_type == 0:
            value, pos = read_varint(data, pos)
            fields.append((field_no, wire_type, value))
        elif wire_type == 2:
            size, pos = read_varint(data, pos)
            chunk = data[pos:pos + size]
            pos += size
            fields.append((field_no, wire_type, chunk))
        elif wire_type == 5:
            pos += 4
        elif wire_type == 1:
            pos += 8
        else:
            break
    return fields

def first_payload_from_ws_response(path):
    raw = path.read_bytes()
    body = raw[3:] if raw and raw[0] == 3 else raw

    for field_no, wire_type, value in read_fields(body):
        if field_no == 2 and wire_type == 2:
            return value

    raise RuntimeError(f"payload not found: {path}")

def try_read_wrapper(data, pos):
    start = pos

    try:
        key, pos = read_varint(data, pos)
        if key != 10:
            return None

        name_len, pos = read_varint(data, pos)
        name = data[pos:pos + name_len].decode("utf-8", errors="ignore")
        pos += name_len

        if not name.startswith(".lq.Record"):
            return None

        key, pos = read_varint(data, pos)
        if key != 18:
            return None

        body_len, pos = read_varint(data, pos)
        body = data[pos:pos + body_len]
        pos += body_len

        return {
            "start": start,
            "end": pos,
            "name": name,
            "body": body,
        }
    except Exception:
        return None

def find_wrappers(data):
    wrappers = []
    pos = 0

    while pos < len(data):
        wrapper = try_read_wrapper(data, pos)
        if wrapper:
            wrappers.append(wrapper)
            pos = wrapper["end"]
        else:
            pos += 1

    return wrappers

def decode_record(name, body):
    cls = getattr(pb, name.split(".")[-1], None)
    if cls is None:
        return None

    msg = cls()
    try:
        msg.ParseFromString(body)
        return msg
    except Exception:
        return None

def load_detail(detail_path):
    payload = first_payload_from_ws_response(detail_path)

    msg = pb.ResGameRecordsDetailV2()
    msg.ParseFromString(payload)

    data = MessageToDict(msg, preserving_proto_field_name=True)
    entry = data["entries"][0]

    seat_to_name = {}
    player_details = {}

    for player in entry.get("players", []):
        seat = int(player.get("seat", 0))
        name = player["nickname"]

        seat_to_name[seat] = name
        player_details[seat] = {
            "name": name,
            "rank": int(player.get("rank", 0)),
            "point": int(player.get("point", 0)),
        }

    return seat_to_name, player_details

def load_record_wrappers(record_path):
    payload = first_payload_from_ws_response(record_path)

    outer = pb.GameDetailRecords()
    outer.ParseFromString(payload)

    inner_payload = None

    for field_no, wire_type, value in read_fields(outer.bar):
        if field_no == 2 and wire_type == 2:
            inner_payload = value

    if inner_payload is None:
        raise RuntimeError(f"inner payload not found: {record_path}")

    return find_wrappers(inner_payload)

def is_riichi_discard(msg):
    if msg is None:
        return False

    for name in ["is_liqi", "liqi", "isLiqi"]:
        if hasattr(msg, name) and getattr(msg, name):
            return True

    return False

def is_ron_hule(msg):
    if msg is None or not hasattr(msg, "hules"):
        return False

    return any(not getattr(hule, "zimo", False) for hule in msg.hules)

def get_houjuu_seat(msg):
    if msg is None or not hasattr(msg, "delta_scores"):
        return None

    delta_scores = list(msg.delta_scores)
    if not delta_scores:
        return None

    loser = min(range(len(delta_scores)), key=lambda i: delta_scores[i])
    if delta_scores[loser] < 0:
        return loser

    return None

def percent(numerator, denominator):
    if denominator == 0:
        return "0.00%"
    return f"{numerator / denominator:.2%}"

def average(numerator, denominator, digits=2):
    if denominator == 0:
        return 0
    return round(numerator / denominator, digits)

def hule_point(hule):
    for field_name in ["point_sum", "dadian", "point_rong", "point_zimo_qin", "point_zimo_xian"]:
        if hasattr(hule, field_name):
            value = int(getattr(hule, field_name))
            if value:
                return value
    return 0

def ron_payment_point(hule):
    for field_name in ["point_rong", "dadian"]:
        if hasattr(hule, field_name):
            value = int(getattr(hule, field_name))
            if value:
                return value
    return hule_point(hule)

def yakuman_names_from_hule(hule):
    names = []

    if not hasattr(hule, "fans"):
        return names

    for fan in hule.fans:
        fan_id = int(getattr(fan, "id", 0))
        fan_val = int(getattr(fan, "val", 0))

        if fan_id in YAKUMAN_NAMES:
            names.append(YAKUMAN_NAMES[fan_id])
        elif fan_val >= 13:
            names.append(f"役満ID{fan_id}")

    return names

def game_score(point, rank):
    return round(point / 1000 - RANK_SCORE_OFFSETS.get(rank, 0), 1)

def victim_rows_from_hule(uuid, round_no, msg, hule, yakuman_name, seat_to_name):
    delta_scores = list(getattr(msg, "delta_scores", []))
    seat = int(getattr(hule, "seat", -1))
    winner = seat_to_name.get(seat, "")
    victims = []

    if getattr(hule, "zimo", False):
        win_type = "ツモ"
        for victim_seat, delta in enumerate(delta_scores):
            if victim_seat == seat or delta >= 0:
                continue
            victims.append({
                "name": seat_to_name.get(victim_seat, f"seat{victim_seat}"),
                "point": -int(delta),
            })
    else:
        win_type = "ロン"
        loser = get_houjuu_seat(msg)
        if loser is not None:
            victims.append({
                "name": seat_to_name.get(loser, f"seat{loser}"),
                "point": ron_payment_point(hule) or -int(delta_scores[loser]),
            })

    return [
        {
            "uuid": uuid,
            "round_no": round_no,
            "player": winner,
            "yakuman_name": yakuman_name,
            "win_type": win_type,
            "victim": victim["name"],
            "payment": victim["point"],
        }
        for victim in victims
    ]

def aggregate_game(uuid, stats, yakuman_details):
    record_path = RAW_DIR / f"{uuid}_record.bin"
    detail_path = RAW_DIR / f"{uuid}_detail.bin"

    seat_to_name, player_details = load_detail(detail_path)

    for seat, detail in player_details.items():
        player_name = detail["name"]
        player_stats = stats[player_name]

        player_stats.games += 1
        player_stats.score_sum += game_score(detail["point"], detail["rank"])
        player_stats.rank_sum += detail["rank"]
        player_stats.rank_counts[detail["rank"]] += 1
        player_stats.final_points.append(detail["point"])

    wrappers = load_record_wrappers(record_path)

    round_no = 0
    riichi = set()
    called = set()
    houjuu = set()

    def flush_round():
        if round_no == 0:
            return

        for seat in [0, 1, 2]:
            player_name = seat_to_name.get(seat)
            if not player_name:
                continue

            player_stats = stats[player_name]
            player_stats.rounds += 1
            player_stats.riichi += int(seat in riichi)
            player_stats.called += int(seat in called)
            player_stats.houjuu += int(seat in houjuu)

    for wrapper in wrappers:
        record_name = wrapper["name"]
        msg = decode_record(record_name, wrapper["body"])

        if record_name == ".lq.RecordNewRound":
            flush_round()
            round_no += 1
            riichi = set()
            called = set()
            houjuu = set()

        elif record_name == ".lq.RecordDiscardTile":
            seat = getattr(msg, "seat", None)
            if seat is not None and is_riichi_discard(msg):
                riichi.add(int(seat))

        elif record_name in [".lq.RecordChiPengGang", ".lq.RecordAnGangAddGang"]:
            seat = getattr(msg, "seat", None)
            if seat is not None:
                called.add(int(seat))

        elif record_name == ".lq.RecordHule":
            if msg is None or not hasattr(msg, "hules"):
                continue

            if is_ron_hule(msg):
                loser = get_houjuu_seat(msg)
                if loser is not None:
                    houjuu.add(loser)

            for hule in msg.hules:
                seat = int(getattr(hule, "seat", -1))
                player_name = seat_to_name.get(seat)
                if not player_name:
                    continue

                player_stats = stats[player_name]
                player_stats.hu += 1
                player_stats.hu_point_sum += hule_point(hule)

                if getattr(hule, "zimo", False):
                    player_stats.tsumo += 1

                for yakuman_name in yakuman_names_from_hule(hule):
                    player_stats.yakuman_count += 1
                    player_stats.yakuman_names[yakuman_name] += 1
                    yakuman_details.extend(
                        victim_rows_from_hule(uuid, round_no, msg, hule, yakuman_name, seat_to_name)
                    )

    flush_round()

def write_summary(stats):
    with SUMMARY_OUT.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.writer(f)
        writer.writerow([
            "player",
            "games",
            "earned_score",
            "rank1_rate",
            "rank2_rate",
            "rank3_rate",
            "average_rank",
            "rounds",
            "average_hu_point",
            "hu_rate",
            "tsumo_rate",
            "houjuu_rate",
            "called_rate",
            "riichi_rate",
            "max_final_point",
            "min_final_point",
            "yakuman_count",
        ])

        for player_name, player_stats in sorted(stats.items(), key=lambda item: item[0]):
            writer.writerow([
                player_name,
                player_stats.games,
                round(player_stats.score_sum, 1),
                percent(player_stats.rank_counts[1], player_stats.games),
                percent(player_stats.rank_counts[2], player_stats.games),
                percent(player_stats.rank_counts[3], player_stats.games),
                average(player_stats.rank_sum, player_stats.games),
                player_stats.rounds,
                average(player_stats.hu_point_sum, player_stats.hu, 1),
                percent(player_stats.hu, player_stats.rounds),
                percent(player_stats.tsumo, player_stats.hu),
                percent(player_stats.houjuu, player_stats.rounds),
                percent(player_stats.called, player_stats.rounds),
                percent(player_stats.riichi, player_stats.rounds),
                max(player_stats.final_points) if player_stats.final_points else "",
                min(player_stats.final_points) if player_stats.final_points else "",
                player_stats.yakuman_count,
            ])

def write_yakuman_summary(stats):
    with YAKUMAN_OUT.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["player", "yakuman_name", "count"])

        for player_name, player_stats in sorted(stats.items(), key=lambda item: item[0]):
            for yakuman_name, count in sorted(player_stats.yakuman_names.items()):
                writer.writerow([player_name, yakuman_name, count])

def write_yakuman_details(rows):
    with YAKUMAN_DETAILS_OUT.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=["uuid", "round_no", "player", "yakuman_name", "win_type", "victim", "payment"],
        )
        writer.writeheader()
        writer.writerows(rows)

def main():
    stats = defaultdict(PlayerStats)
    yakuman_details = []

    record_files = sorted(RAW_DIR.glob("*_record.bin"))
    print(f"records: {len(record_files)}")

    for index, record_file in enumerate(record_files, start=1):
        uuid = record_file.name.removesuffix("_record.bin")
        print(f"[{index}/{len(record_files)}] {uuid}")
        aggregate_game(uuid, stats, yakuman_details)

    write_summary(stats)
    write_yakuman_summary(stats)
    write_yakuman_details(yakuman_details)

    print(f"saved: {SUMMARY_OUT}")
    print(f"saved: {YAKUMAN_OUT}")
    print(f"saved: {YAKUMAN_DETAILS_OUT}")

if __name__ == "__main__":
    main()
