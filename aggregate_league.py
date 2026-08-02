from pathlib import Path
from collections import defaultdict, Counter
from dataclasses import dataclass, field
from functools import lru_cache
import csv
import re

import ms.protocol_pb2 as pb
from google.protobuf.json_format import MessageToDict

RAW_DIR = Path("records_raw")
PAIFU_CSV = Path("admin_paifu_ids.csv")
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
    43: "小四喜",
    44: "大四喜",
    45: "小四喜",
    46: "緑一色",
    47: "九蓮宝燈",
    48: "四暗刻単騎",
    49: "四槓子",
    50: "天和",
    51: "地和",
}

RIICHI_QUALITY_CATEGORIES = [
    ("ryanmen_many", "リャンメン以上・4面張以上", True),
    ("ryanmen_3men", "リャンメン以上・3面張", True),
    ("ryanmen_5plus", "リャンメン・見た目5枚以上", True),
    ("tanki_1_cut_honor_manzu", "1枚切れ非役牌字牌・萬子単騎", True),
    ("tanki_2_cut_honor_manzu", "2枚切れ字牌・萬子単騎", True),
    ("tanki_0_cut_honor_manzu", "0枚切れ非役牌字牌・萬子単騎", True),
    ("yaochu_shanpon", "ヤオチュウ牌シャンポン", True),
    ("yakuhai_simple_shanpon", "役牌＋3～7数牌シャンポン", True),
    ("kanchan_2_8", "2・8待ちカンチャン", True),
    ("dora_bad_shape", "ドラ絡み愚形", True),
    ("bad_kanchan_penchan_3_7", "3～7カンチャン・ペンチャン", False),
    ("bad_simple_shanpon", "3～7シャンポン", False),
    ("bad_bulge_shanpon", "中ぶくれ・外ぶくれシャンポン", False),
    ("bad_simple_tanki", "3～7単騎（ドラなし）", False),
    ("bad_two_or_less", "残り2枚以下の待ち", False),
    ("bad_bulge_tanki", "中ぶくれ単騎", False),
    ("worst_double_bulge_shanpon", "ダブル中ぶくれ・外ぶくれシャンポン", False),
]
RIICHI_QUALITY_SCORE = {
    "ryanmen_many": 10,
    "ryanmen_3men": 7,
    "ryanmen_5plus": 5,
    "tanki_1_cut_honor_manzu": 5,
    "tanki_2_cut_honor_manzu": 4,
    "tanki_0_cut_honor_manzu": 3,
    "yaochu_shanpon": 3,
    "yakuhai_simple_shanpon": 2,
    "kanchan_2_8": 1,
    "dora_bad_shape": 0,
    "bad_kanchan_penchan_3_7": -2,
    "bad_simple_shanpon": -2,
    "bad_bulge_shanpon": -4,
    "bad_simple_tanki": -4,
    "bad_two_or_less": -4,
    "bad_bulge_tanki": -5,
    "worst_double_bulge_shanpon": -5,
}
RIICHI_QUALITY_LABELS = {
    key: label for key, label, _recommended in RIICHI_QUALITY_CATEGORIES
}
RIICHI_QUALITY_RECOMMENDED = {
    key: recommended for key, _label, recommended in RIICHI_QUALITY_CATEGORIES
}
RIICHI_QUALITY_DEFAULT = "bad_two_or_less"

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
    called_hu: int = 0
    called_hu_point_sum: int = 0
    open_tanyao_hu: int = 0
    chiitoi_hu: int = 0
    honitsu_hu: int = 0
    chinitsu_hu: int = 0
    houjuu: int = 0
    houjuu_point_sum: int = 0
    called: int = 0
    riichi: int = 0
    riichi_miss: int = 0
    bad_shape_riichi: int = 0
    top_riichi: int = 0
    riichi_quality_score_sum: int = 0
    riichi_quality_counts: Counter = field(default_factory=Counter)
    late_noten_discards: int = 0
    late_noten_houjuu: int = 0
    late_noten_fresh_discards: int = 0
    winning_run_chances: int = 0
    winning_run_point_sum: int = 0
    final_points: list = field(default_factory=list)
    yakuman_count: int = 0
    yakuman_names: Counter = field(default_factory=Counter)
    top_keep_chances: int = 0
    top_keep_successes: int = 0
    first_tenpai: int = 0
    top_stay_rounds: int = 0
    second_stay_rounds: int = 0
    last_stay_rounds: int = 0
    opening_shanten_sum: int = 0
    opening_dora_sum: int = 0
    opening_samples: int = 0


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

def normalize_tile(tile):
    if not tile:
        return tile
    if tile[0] == "0":
        return "5" + tile[1:]
    return tile

def tile_index(tile):
    tile = normalize_tile(tile)
    if len(tile) != 2:
        return None

    number = int(tile[0])
    suit = tile[1]
    if suit == "m":
        return number - 1
    if suit == "p":
        return 9 + number - 1
    if suit == "s":
        return 18 + number - 1
    if suit == "z":
        return 27 + number - 1
    return None

def tile_counts(tiles):
    counts = [0] * 34
    for tile in tiles:
        index = tile_index(tile)
        if index is not None:
            counts[index] += 1
    return counts

def shanten_kokushi(counts):
    terminals = [0, 8, 9, 17, 18, 26, 27, 28, 29, 30, 31, 32, 33]
    unique = sum(1 for index in terminals if counts[index] > 0)
    has_pair = any(counts[index] >= 2 for index in terminals)
    return 13 - unique - int(has_pair)

def shanten_chiitoi(counts):
    pairs = sum(1 for count in counts if count >= 2)
    unique = sum(1 for count in counts if count > 0)
    return 6 - pairs + max(0, 7 - unique)

def shanten_normal(counts, fixed_melds=0):
    best = 8

    def walk(local_counts, index, melds, taatsu, pair):
        nonlocal best

        while index < 34 and local_counts[index] == 0:
            index += 1

        if index >= 34:
            usable_taatsu = min(taatsu, 4 - melds)
            best = min(best, 8 - melds * 2 - usable_taatsu - pair)
            return

        if best <= -1:
            return

        if local_counts[index] >= 3:
            local_counts[index] -= 3
            walk(local_counts, index, melds + 1, taatsu, pair)
            local_counts[index] += 3

        if index < 27 and index % 9 <= 6 and local_counts[index + 1] and local_counts[index + 2]:
            local_counts[index] -= 1
            local_counts[index + 1] -= 1
            local_counts[index + 2] -= 1
            walk(local_counts, index, melds + 1, taatsu, pair)
            local_counts[index] += 1
            local_counts[index + 1] += 1
            local_counts[index + 2] += 1

        if pair == 0 and local_counts[index] >= 2:
            local_counts[index] -= 2
            walk(local_counts, index, melds, taatsu, 1)
            local_counts[index] += 2

        if local_counts[index] >= 2:
            local_counts[index] -= 2
            walk(local_counts, index, melds, taatsu + 1, pair)
            local_counts[index] += 2

        if index < 27 and index % 9 <= 7 and local_counts[index + 1]:
            local_counts[index] -= 1
            local_counts[index + 1] -= 1
            walk(local_counts, index, melds, taatsu + 1, pair)
            local_counts[index] += 1
            local_counts[index + 1] += 1

        if index < 27 and index % 9 <= 6 and local_counts[index + 2]:
            local_counts[index] -= 1
            local_counts[index + 2] -= 1
            walk(local_counts, index, melds, taatsu + 1, pair)
            local_counts[index] += 1
            local_counts[index + 2] += 1

        local_counts[index] -= 1
        walk(local_counts, index, melds, taatsu, pair)
        local_counts[index] += 1

    walk(counts[:], 0, fixed_melds, 0, 0)
    return best

@lru_cache(maxsize=None)
def shanten_from_counts(counts_key):
    counts = list(counts_key)
    return min(
        shanten_normal(counts),
        shanten_chiitoi(counts),
        shanten_kokushi(counts),
    )

def shanten(tiles):
    return shanten_from_counts(tuple(tile_counts(tiles)))

@lru_cache(maxsize=None)
def shanten_with_fixed_melds_from_counts(counts_key, fixed_melds):
    counts = list(counts_key)
    normal = shanten_normal(counts, fixed_melds)
    if fixed_melds:
        return normal
    return min(normal, shanten_chiitoi(counts), shanten_kokushi(counts))

def shanten_with_fixed_melds(tiles, fixed_melds):
    return shanten_with_fixed_melds_from_counts(tuple(tile_counts(tiles)), fixed_melds)

ALL_TILES = [
    *(f"{number}m" for number in range(1, 10)),
    *(f"{number}p" for number in range(1, 10)),
    *(f"{number}s" for number in range(1, 10)),
    *(f"{number}z" for number in range(1, 8)),
]

def hand_key(tiles):
    return tuple(sorted(normalize_tile(tile) for tile in tiles if tile))

@lru_cache(maxsize=None)
def winning_waits_from_key(key):
    if len(key) % 3 != 1:
        return []

    counts = Counter(key)
    waits = []
    for tile in ALL_TILES:
        if counts[tile] >= 4:
            continue
        if shanten(list(key) + [tile]) == -1:
            waits.append(tile)
    return waits

def winning_waits(tiles):
    return list(winning_waits_from_key(hand_key(tiles)))

def full_wait_count(tiles, waits):
    counts = Counter(normalize_tile(tile) for tile in tiles)
    return sum(max(0, 4 - counts[wait]) for wait in waits)

def visible_wait_count(tiles, waits, visible_counts):
    counts = Counter(normalize_tile(tile) for tile in tiles)
    return sum(max(0, 4 - counts[wait] - visible_counts[wait]) for wait in waits)

def tile_number(tile):
    tile = normalize_tile(tile)
    if len(tile) != 2 or tile[1] not in {"m", "p", "s"}:
        return None
    return int(tile[0])

def is_suited(tile):
    tile = normalize_tile(tile)
    return len(tile) == 2 and tile[1] in {"m", "p", "s"}

def is_simple_number(tile):
    number = tile_number(tile)
    return number is not None and 3 <= number <= 7

def is_yaochu(tile):
    tile = normalize_tile(tile)
    return tile.endswith("z") or tile in {"1m", "9m", "1p", "9p", "1s", "9s"}

def seat_wind_tile(seat, dealer):
    if seat not in {0, 1, 2} or dealer not in {0, 1, 2}:
        return None
    return ["1z", "2z", "3z"][(seat - dealer) % 3]

def round_wind_tile(chang):
    if chang == 0:
        return "1z"
    if chang == 1:
        return "2z"
    return None

def is_yakuhai(tile, seat, chang, dealer):
    tile = normalize_tile(tile)
    if tile in {"5z", "6z", "7z"}:
        return True
    return tile in {seat_wind_tile(seat, dealer), round_wind_tile(chang)}

def is_shanpon_wait(tiles, waits):
    counts = Counter(normalize_tile(tile) for tile in tiles)
    normalized_waits = [normalize_tile(wait) for wait in waits]
    return len(normalized_waits) == 2 and all(counts[wait] >= 2 for wait in normalized_waits)

def is_tanki_wait(tiles, waits):
    counts = Counter(normalize_tile(tile) for tile in tiles)
    normalized_waits = [normalize_tile(wait) for wait in waits]
    return len(normalized_waits) == 1 and counts[normalized_waits[0]] == 1

def is_penchan_wait(tiles, waits):
    if len(waits) != 1:
        return False
    wait = normalize_tile(waits[0])
    number = tile_number(wait)
    if number not in {3, 7}:
        return False
    counts = Counter(normalize_tile(tile) for tile in tiles)
    suit = wait[1]
    if number == 3:
        return counts[f"1{suit}"] > 0 and counts[f"2{suit}"] > 0
    return counts[f"8{suit}"] > 0 and counts[f"9{suit}"] > 0

def is_kanchan_wait(tiles, waits):
    if len(waits) != 1:
        return False
    wait = normalize_tile(waits[0])
    number = tile_number(wait)
    if number is None or number <= 1 or number >= 9:
        return False
    counts = Counter(normalize_tile(tile) for tile in tiles)
    return counts[f"{number - 1}{wait[1]}"] > 0 and counts[f"{number + 1}{wait[1]}"] > 0

def has_bulge_shape(tiles, wait):
    wait = normalize_tile(wait)
    number = tile_number(wait)
    if number is None:
        return False
    counts = Counter(normalize_tile(tile) for tile in tiles)
    suit = wait[1]
    left = f"{number - 1}{suit}" if number > 1 else None
    right = f"{number + 1}{suit}" if number < 9 else None
    return (
        counts[wait] >= 1
        and left is not None
        and right is not None
        and counts[left] > 0
        and counts[right] > 0
    )

def is_bulge_shanpon(tiles, waits):
    if not is_shanpon_wait(tiles, waits):
        return False
    return any(has_bulge_shape(tiles, wait) for wait in waits)

def is_double_bulge_shanpon(tiles, waits):
    if not is_shanpon_wait(tiles, waits):
        return False
    return all(has_bulge_shape(tiles, wait) for wait in waits)

def riichi_dora_tiles(dora_indicators):
    return Counter(next_dora(tile) for tile in dora_indicators)

def tile_is_dora(tile, dora_tiles):
    if not tile:
        return False
    return tile.startswith("0") or dora_tiles[normalize_tile(tile)] > 0

def riichi_has_dora_bad_shape(tiles, waits, dora_indicators):
    if len(waits) > 2 or is_double_bulge_shanpon(tiles, waits) or any(
        has_bulge_shape(tiles, wait) for wait in waits
    ):
        return False
    dora_tiles = riichi_dora_tiles(dora_indicators)
    return any(tile_is_dora(tile, dora_tiles) for tile in list(tiles) + list(waits))

def classify_riichi_quality(tiles, waits, visible_counts, seat, chang, dealer, dora_indicators):
    if not waits:
        waits = winning_waits(tiles)
    waits = [normalize_tile(wait) for wait in waits if wait]
    if not waits:
        return RIICHI_QUALITY_DEFAULT

    visible_remaining = visible_wait_count(tiles, waits, visible_counts)
    counts = Counter(normalize_tile(tile) for tile in tiles)
    is_shanpon = is_shanpon_wait(tiles, waits)
    is_tanki = is_tanki_wait(tiles, waits)
    wait = waits[0] if len(waits) == 1 else None
    dora_tiles = riichi_dora_tiles(dora_indicators)

    if len(waits) >= 2 and visible_remaining >= 5 and not is_shanpon:
        if len(waits) >= 4:
            return "ryanmen_many"
        if len(waits) == 3:
            return "ryanmen_3men"
        return "ryanmen_5plus"

    if is_tanki and wait:
        visible_cut = visible_counts[wait]
        honor_or_manzu = wait.endswith("z") or wait.endswith("m")
        non_yakuhai = not is_yakuhai(wait, seat, chang, dealer)
        if honor_or_manzu and non_yakuhai and visible_cut == 1:
            return "tanki_1_cut_honor_manzu"
        if honor_or_manzu and visible_cut == 2:
            return "tanki_2_cut_honor_manzu"
        if honor_or_manzu and non_yakuhai and visible_cut == 0:
            return "tanki_0_cut_honor_manzu"

    if is_shanpon:
        if is_double_bulge_shanpon(tiles, waits):
            return "worst_double_bulge_shanpon"
        if all(is_yaochu(wait_tile) for wait_tile in waits):
            return "yaochu_shanpon"
        if any(is_yakuhai(wait_tile, seat, chang, dealer) for wait_tile in waits) and any(
            is_simple_number(wait_tile) for wait_tile in waits
        ):
            return "yakuhai_simple_shanpon"

    if wait and is_kanchan_wait(tiles, waits) and tile_number(wait) in {2, 8}:
        return "kanchan_2_8"

    if riichi_has_dora_bad_shape(tiles, waits, dora_indicators):
        return "dora_bad_shape"

    if wait and (is_kanchan_wait(tiles, waits) or is_penchan_wait(tiles, waits)) and is_simple_number(wait):
        return "bad_kanchan_penchan_3_7"

    if is_bulge_shanpon(tiles, waits):
        return "bad_bulge_shanpon"

    if is_shanpon and any(is_simple_number(wait_tile) for wait_tile in waits):
        return "bad_simple_shanpon"

    if is_tanki and wait and has_bulge_shape(tiles, wait):
        return "bad_bulge_tanki"

    if is_tanki and wait and is_simple_number(wait) and not tile_is_dora(wait, dora_tiles):
        return "bad_simple_tanki"

    if visible_remaining <= 2:
        return "bad_two_or_less"

    return RIICHI_QUALITY_DEFAULT


def is_bad_shape_exception(tiles, waits, seat, chang, dealer):
    normalized_waits = [normalize_tile(wait) for wait in waits if wait]
    if not normalized_waits:
        return False

    if is_shanpon_wait(tiles, normalized_waits):
        return all(is_yaochu(wait) for wait in normalized_waits) or any(
            is_yakuhai(wait, seat, chang, dealer) for wait in normalized_waits
        )

    if is_tanki_wait(tiles, normalized_waits):
        wait = normalized_waits[0]
        return wait.endswith("z") or wait.endswith("m")

    return False

def should_count_bad_shape_riichi(tiles, waits, seat, chang, dealer):
    if not waits:
        waits = winning_waits(tiles)
    if not waits:
        return False
    return full_wait_count(tiles, waits) <= 4 and not is_bad_shape_exception(
        tiles,
        waits,
        seat,
        chang,
        dealer,
    )

def is_bad_shape_riichi(tiles):
    waits = winning_waits(tiles)
    if not waits:
        return False
    return full_wait_count(tiles, waits) <= 4

def riichi_quality_recommended_count(player_stats):
    return sum(
        count
        for key, count in player_stats.riichi_quality_counts.items()
        if RIICHI_QUALITY_RECOMMENDED.get(key, False)
    )

def riichi_quality_top_label(player_stats):
    if not player_stats.riichi_quality_counts:
        return ""
    key, _count = max(
        player_stats.riichi_quality_counts.items(),
        key=lambda item: (item[1], RIICHI_QUALITY_SCORE.get(item[0], 0)),
    )
    return RIICHI_QUALITY_LABELS.get(key, key)

def has_top_score(scores, seat):
    if len(scores) < 3 or seat not in {0, 1, 2}:
        return False
    score_list = [int(score) for score in scores[:3]]
    return score_list[seat] == max(score_list)

def score_rank(scores, seat):
    if len(scores) < 3 or seat not in {0, 1, 2}:
        return None
    score = int(scores[seat])
    return 1 + sum(1 for other in scores[:3] if int(other) > score)

def top_margin(scores, seat):
    if len(scores) < 3 or seat not in {0, 1, 2}:
        return None
    score_list = [int(score) for score in scores[:3]]
    score = score_list[seat]
    others = [value for index, value in enumerate(score_list) if index != seat]
    return score - max(others)

def is_oorasu(chang, dealer):
    return int(chang) == 1 and int(dealer) == 2

def is_late_noten_discard(msg, seat, turn_counts, riichi_seats):
    if seat not in {0, 1, 2}:
        return False
    if turn_counts[seat] < 12:
        return False
    if seat in riichi_seats:
        return False
    return not repeated_field_values(msg, "tingpais")

def next_dora(indicator):
    tile = normalize_tile(indicator)
    if len(tile) != 2:
        return tile

    number = int(tile[0])
    suit = tile[1]
    if suit in {"m", "p", "s"}:
        return f"{1 if number == 9 else number + 1}{suit}"
    if suit == "z":
        if 1 <= number <= 4:
            return f"{1 if number == 4 else number + 1}z"
        if 5 <= number <= 7:
            return f"{5 if number == 7 else number + 1}z"
    return tile

def count_opening_dora(tiles, dora_indicators, kita_count):
    dora_tiles = Counter(next_dora(tile) for tile in dora_indicators)
    count = kita_count
    for tile in tiles:
        normalized = normalize_tile(tile)
        count += dora_tiles[normalized]
        if tile.startswith("0"):
            count += 1
    return count

def remove_one_tile(tiles, tile):
    normalized = normalize_tile(tile)
    for index, hand_tile in enumerate(tiles):
        if normalize_tile(hand_tile) == normalized:
            del tiles[index]
            return True
    return False

def repeated_field_values(msg, field_name):
    if msg is None or not hasattr(msg, field_name):
        return []
    value = getattr(msg, field_name)
    if isinstance(value, str):
        return [value] if value else []
    return list(value)

def new_round_tiles(msg, seat):
    return repeated_field_values(msg, f"tiles{seat}")

def new_round_dora_indicators(msg):
    doras = repeated_field_values(msg, "doras")
    if doras:
        return doras
    return repeated_field_values(msg, "dora")

def hule_point(hule):
    for field_name in ["point_sum", "dadian", "point_rong", "point_zimo_qin", "point_zimo_xian"]:
        if hasattr(hule, field_name):
            value = int(getattr(hule, field_name))
            if value:
                return value
    return 0

def hule_income(msg, hule):
    seat = int(getattr(hule, "seat", -1))
    delta_scores = list(getattr(msg, "delta_scores", []))
    if 0 <= seat < len(delta_scores) and int(delta_scores[seat]) > 0:
        return int(delta_scores[seat])
    return hule_point(hule)

def ron_payment_point(hule):
    for field_name in ["point_rong", "dadian"]:
        if hasattr(hule, field_name):
            value = int(getattr(hule, field_name))
            if value:
                return value
    return hule_point(hule)

def single_top_seat(scores):
    if not scores:
        return None

    score_list = [int(score) for score in scores[:3]]
    top_score = max(score_list)
    if score_list.count(top_score) != 1:
        return None

    return score_list.index(top_score)

def ming_tiles(ming):
    text = str(ming)
    return re.findall(r"[0-9][mpsz]", text)

def hule_tiles(hule):
    tiles = list(getattr(hule, "hand", []))
    hu_tile = getattr(hule, "hu_tile", "")
    if hu_tile:
        tiles.append(hu_tile)
    for ming in getattr(hule, "ming", []):
        tiles.extend(ming_tiles(ming))
    return tiles

def kokushi_name(hule):
    required = {
        "1m", "9m", "1p", "9p", "1s", "9s",
        "1z", "2z", "3z", "4z", "5z", "6z", "7z",
    }
    if list(getattr(hule, "ming", [])):
        return None

    hand = list(getattr(hule, "hand", []))
    hu_tile = getattr(hule, "hu_tile", "")
    tiles = hand + ([hu_tile] if hu_tile else [])
    counts = Counter(tiles)
    if set(counts) != required:
        return None
    if sorted(counts.values()) != [1] * 12 + [2]:
        return None
    if set(hand) == required and hu_tile in required:
        return "国士無双十三面"
    return "国士無双"

def wind_yakuman_name(hule):
    counts = Counter(hule_tiles(hule))
    winds = ["1z", "2z", "3z", "4z"]
    triplet_count = sum(1 for tile in winds if counts[tile] >= 3)
    pair_count = sum(1 for tile in winds if counts[tile] == 2)
    if triplet_count == 4:
        return "大四喜"
    if triplet_count == 3 and pair_count >= 1:
        return "小四喜"
    return None

def yakuman_name_from_fan(hule, fan_id):
    name = kokushi_name(hule)
    if name:
        return name

    name = wind_yakuman_name(hule)
    if name and fan_id in {43, 44, 45}:
        return name

    return YAKUMAN_NAMES.get(fan_id)

def yakuman_names_from_hule(hule):
    names = []

    if not hasattr(hule, "fans"):
        return names

    for fan in hule.fans:
        fan_id = int(getattr(fan, "id", 0))
        fan_val = int(getattr(fan, "val", 0))

        if fan_id in YAKUMAN_NAMES:
            names.append(yakuman_name_from_fan(hule, fan_id) or YAKUMAN_NAMES[fan_id])
        elif fan_val >= 13:
            names.append(f"役満ID{fan_id}")

    return names

def hule_fan_ids(hule):
    if not hasattr(hule, "fans"):
        return set()
    return {int(getattr(fan, "id", 0)) for fan in hule.fans}

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
    opening_hands = {0: [], 1: [], 2: []}
    opening_kita = {0: 0, 1: 0, 2: 0}
    opening_done = set()
    opening_dora_indicators = []
    current_dora_indicators = []
    had_single_top = {0: False, 1: False, 2: False}
    kept_single_top = {0: False, 1: False, 2: False}
    current_hands = {0: [], 1: [], 2: []}
    current_open_melds = {0: 0, 1: 0, 2: 0}
    current_scores = [35000, 35000, 35000]
    visible_counts = Counter()
    turn_counts = {0: 0, 1: 0, 2: 0}
    last_discard_late_noten = {0: False, 1: False, 2: False}
    riichi_winners = set()
    first_tenpai_seat = None
    round_start_scores = [35000, 35000, 35000]
    current_chang = 0
    current_dealer = 0
    winning_run_seat = None
    winning_run_start_score = None

    def observe_scores(scores):
        nonlocal current_scores

        if len(scores) < 3:
            return

        current_scores = [int(score) for score in scores[:3]]
        top = single_top_seat(scores)
        if top is None:
            for seat in [0, 1, 2]:
                if had_single_top[seat] and kept_single_top[seat]:
                    kept_single_top[seat] = False
            return

        for seat in [0, 1, 2]:
            if seat == top and not had_single_top[seat]:
                had_single_top[seat] = True
                kept_single_top[seat] = True
            elif had_single_top[seat] and kept_single_top[seat] and seat != top:
                kept_single_top[seat] = False

    def flush_round():
        nonlocal first_tenpai_seat

        if round_no == 0:
            return

        for seat in [0, 1, 2]:
            player_name = seat_to_name.get(seat)
            if not player_name:
                continue

            player_stats = stats[player_name]
            player_stats.rounds += 1
            player_stats.riichi += int(seat in riichi)
            player_stats.riichi_miss += int(seat in riichi and seat not in riichi_winners)
            player_stats.called += int(seat in called)
            player_stats.houjuu += int(seat in houjuu)
            player_stats.first_tenpai += int(first_tenpai_seat == seat)

            rank = score_rank(round_start_scores, seat)
            player_stats.top_stay_rounds += int(rank == 1)
            player_stats.second_stay_rounds += int(rank == 2)
            player_stats.last_stay_rounds += int(rank == 3)

    def record_opening_sample(seat):
        player_name = seat_to_name.get(seat)
        if not player_name or seat in opening_done:
            return

        tiles = opening_hands.get(seat, [])
        if not tiles:
            return

        player_stats = stats[player_name]
        player_stats.opening_shanten_sum += shanten(tiles)
        player_stats.opening_dora_sum += count_opening_dora(
            tiles,
            opening_dora_indicators,
            opening_kita.get(seat, 0),
        )
        player_stats.opening_samples += 1
        opening_done.add(seat)

    def observe_tenpai(seat, msg):
        nonlocal first_tenpai_seat

        if first_tenpai_seat is not None or seat not in {0, 1, 2}:
            return
        if repeated_field_values(msg, "tingpais"):
            first_tenpai_seat = seat

    def apply_call_tiles(msg, seat):
        tiles = [normalize_tile(tile) for tile in repeated_field_values(msg, "tiles")]
        froms = [int(value) for value in repeated_field_values(msg, "froms")]
        removed = 0

        if froms and len(froms) == len(tiles):
            for tile, from_seat in zip(tiles, froms):
                if from_seat == seat and remove_one_tile(current_hands[seat], tile):
                    removed += 1
        else:
            for tile in tiles:
                if remove_one_tile(current_hands[seat], tile):
                    removed += 1

        return removed

    for wrapper in wrappers:
        record_name = wrapper["name"]
        msg = decode_record(record_name, wrapper["body"])

        if record_name == ".lq.RecordNewRound":
            flush_round()
            round_no += 1
            current_chang = int(getattr(msg, "chang", 0))
            current_dealer = int(getattr(msg, "ju", 0))
            riichi = set()
            riichi_winners = set()
            called = set()
            houjuu = set()
            first_tenpai_seat = None
            opening_hands = {seat: new_round_tiles(msg, seat) for seat in [0, 1, 2]}
            current_hands = {
                seat: [normalize_tile(tile) for tile in new_round_tiles(msg, seat)]
                for seat in [0, 1, 2]
            }
            current_open_melds = {0: 0, 1: 0, 2: 0}
            visible_counts = Counter()
            turn_counts = {0: 0, 1: 0, 2: 0}
            last_discard_late_noten = {0: False, 1: False, 2: False}
            opening_kita = {0: 0, 1: 0, 2: 0}
            opening_done = set()
            opening_dora_indicators = new_round_dora_indicators(msg)
            current_dora_indicators = list(opening_dora_indicators)
            if msg is not None and hasattr(msg, "scores"):
                round_start_scores = [int(score) for score in list(msg.scores)[:3]]
                if (
                    winning_run_seat is None
                    and is_oorasu(current_chang, current_dealer)
                    and score_rank(round_start_scores, current_dealer) == 1
                    and (top_margin(round_start_scores, current_dealer) or 0) >= 30000
                ):
                    winning_run_seat = current_dealer
                    winning_run_start_score = round_start_scores[current_dealer]
                observe_scores(list(msg.scores))

        elif record_name == ".lq.RecordDiscardTile":
            seat = getattr(msg, "seat", None)
            if seat is not None:
                seat = int(seat)
                discard_tile = getattr(msg, "tile", "")
                remove_one_tile(current_hands[seat], discard_tile)
                turn_counts[seat] += 1
                late_noten = is_late_noten_discard(msg, seat, turn_counts, riichi)
                last_discard_late_noten[seat] = late_noten
                if late_noten:
                    player_name = seat_to_name.get(seat)
                    if player_name:
                        stats[player_name].late_noten_discards += 1
                        if discard_tile and visible_counts[normalize_tile(discard_tile)] == 0:
                            stats[player_name].late_noten_fresh_discards += 1
                if discard_tile:
                    visible_counts[normalize_tile(discard_tile)] += 1
                if seat not in opening_done:
                    remove_one_tile(opening_hands[seat], discard_tile)
                    record_opening_sample(seat)
                observe_tenpai(seat, msg)
                if is_riichi_discard(msg) and seat not in riichi:
                    riichi.add(seat)
                    player_name = seat_to_name.get(seat)
                    if player_name:
                        player_stats = stats[player_name]
                        waits = [
                            normalize_tile(getattr(info, "tile", ""))
                            for info in repeated_field_values(msg, "tingpais")
                            if getattr(info, "tile", "")
                        ]
                        bad_shape = should_count_bad_shape_riichi(
                            current_hands[seat],
                            waits,
                            seat,
                            current_chang,
                            current_dealer,
                        )
                        player_stats.bad_shape_riichi += int(bad_shape)
                        player_stats.top_riichi += int(has_top_score(current_scores, seat))
                        quality = classify_riichi_quality(
                            current_hands[seat],
                            waits,
                            visible_counts,
                            seat,
                            current_chang,
                            current_dealer,
                            current_dora_indicators,
                        )
                        player_stats.riichi_quality_counts[quality] += 1
                        player_stats.riichi_quality_score_sum += RIICHI_QUALITY_SCORE[quality]

        elif record_name == ".lq.RecordDealTile":
            seat = getattr(msg, "seat", None)
            if seat is not None:
                seat = int(seat)
                tile = getattr(msg, "tile", "")
                if tile:
                    current_hands[seat].append(normalize_tile(tile))
                if seat not in opening_done:
                    if tile:
                        opening_hands[seat].append(tile)

        elif record_name == ".lq.RecordBaBei":
            seat = getattr(msg, "seat", None)
            if seat is not None:
                seat = int(seat)
                remove_one_tile(current_hands[seat], "4z")
                visible_counts["4z"] += 1
                if seat not in opening_done:
                    remove_one_tile(opening_hands[seat], "4z")
                    opening_kita[seat] += 1

        elif record_name in [".lq.RecordChiPengGang", ".lq.RecordAnGangAddGang"]:
            seat = getattr(msg, "seat", None)
            if seat is not None:
                seat = int(seat)
                called.add(seat)
                call_tiles = [normalize_tile(tile) for tile in repeated_field_values(msg, "tiles")]
                call_froms = [int(value) for value in repeated_field_values(msg, "froms")]
                if call_froms and len(call_froms) == len(call_tiles):
                    for tile, from_seat in zip(call_tiles, call_froms):
                        if from_seat == seat:
                            visible_counts[tile] += 1
                else:
                    for tile in call_tiles:
                        visible_counts[tile] += 1
                removed = apply_call_tiles(msg, seat)
                if record_name == ".lq.RecordChiPengGang" or removed >= 3:
                    current_open_melds[seat] += 1

        elif record_name == ".lq.RecordHule":
            if msg is None or not hasattr(msg, "hules"):
                continue

            if is_ron_hule(msg):
                loser = get_houjuu_seat(msg)
                if loser is not None:
                    houjuu.add(loser)
                    loser_name = seat_to_name.get(loser)
                    if loser_name:
                        if last_discard_late_noten.get(loser, False):
                            stats[loser_name].late_noten_houjuu += 1
                        for hule in msg.hules:
                            if not getattr(hule, "zimo", False):
                                stats[loser_name].houjuu_point_sum += ron_payment_point(hule)

            for hule in msg.hules:
                seat = int(getattr(hule, "seat", -1))
                if seat in riichi:
                    riichi_winners.add(seat)
                player_name = seat_to_name.get(seat)
                if not player_name:
                    continue

                player_stats = stats[player_name]
                player_stats.hu += 1
                income = hule_income(msg, hule)
                player_stats.hu_point_sum += income
                if list(getattr(hule, "ming", [])):
                    player_stats.called_hu += 1
                    player_stats.called_hu_point_sum += income
                fan_ids = hule_fan_ids(hule)
                player_stats.open_tanyao_hu += int(12 in fan_ids and bool(list(getattr(hule, "ming", []))))
                player_stats.chiitoi_hu += int(25 in fan_ids)
                player_stats.honitsu_hu += int(27 in fan_ids)
                player_stats.chinitsu_hu += int(29 in fan_ids)

                if getattr(hule, "zimo", False):
                    player_stats.tsumo += 1

                for yakuman_name in yakuman_names_from_hule(hule):
                    player_stats.yakuman_count += 1
                    player_stats.yakuman_names[yakuman_name] += 1
                    yakuman_details.extend(
                        victim_rows_from_hule(uuid, round_no, msg, hule, yakuman_name, seat_to_name)
                    )

            if hasattr(msg, "scores"):
                observe_scores(list(msg.scores))

        elif record_name == ".lq.RecordNoTile":
            if msg is not None and hasattr(msg, "scores"):
                observe_scores(list(msg.scores))

    flush_round()

    for seat in [0, 1, 2]:
        player_name = seat_to_name.get(seat)
        detail = player_details.get(seat)
        if not player_name or not detail or not had_single_top[seat]:
            continue

        player_stats = stats[player_name]
        player_stats.top_keep_chances += 1
        if kept_single_top[seat] and detail["rank"] == 1:
            player_stats.top_keep_successes += 1

    if winning_run_seat is not None and winning_run_start_score is not None:
        player_name = seat_to_name.get(winning_run_seat)
        detail = player_details.get(winning_run_seat)
        if player_name and detail:
            player_stats = stats[player_name]
            player_stats.winning_run_chances += 1
            player_stats.winning_run_point_sum += int(detail["point"]) - int(winning_run_start_score)

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
            "last_avoid_rate",
            "average_rank",
            "rounds",
            "average_hu_point",
            "average_called_hu_point",
            "hu_rate",
            "open_tanyao_hu_rate",
            "chiitoi_hu_rate",
            "honitsu_hu_rate",
            "chinitsu_hu_rate",
            "tsumo_rate",
            "houjuu_rate",
            "average_houjuu_point",
            "top_keep_rate",
            "first_tenpai_rate",
            "top_stay_rate",
            "second_stay_rate",
            "last_stay_rate",
            "late_noten_houjuu_rate",
            "late_noten_fresh_discard_rate",
            "winning_run_points",
            "average_opening_shanten",
            "average_opening_dora",
            "called_rate",
            "riichi",
            "riichi_rate",
            "riichi_miss_rate",
            "bad_shape_riichi_rate",
            "top_riichi_rate",
            "max_final_point",
            "min_final_point",
            "yakuman_count",
            "riichi_quality_score",
            "riichi_recommended_rate",
            "riichi_not_recommended_rate",
            "riichi_quality_top_category",
        ])

        for player_name, player_stats in sorted(stats.items(), key=lambda item: item[0]):
            writer.writerow([
                player_name,
                player_stats.games,
                round(player_stats.score_sum, 1),
                percent(player_stats.rank_counts[1], player_stats.games),
                percent(player_stats.rank_counts[2], player_stats.games),
                percent(player_stats.rank_counts[3], player_stats.games),
                percent(player_stats.rank_counts[1] + player_stats.rank_counts[2], player_stats.games),
                average(player_stats.rank_sum, player_stats.games),
                player_stats.rounds,
                average(player_stats.hu_point_sum, player_stats.hu, 1),
                average(player_stats.called_hu_point_sum, player_stats.called_hu, 1),
                percent(player_stats.hu, player_stats.rounds),
                percent(player_stats.open_tanyao_hu, player_stats.hu),
                percent(player_stats.chiitoi_hu, player_stats.hu),
                percent(player_stats.honitsu_hu, player_stats.hu),
                percent(player_stats.chinitsu_hu, player_stats.hu),
                percent(player_stats.tsumo, player_stats.hu),
                percent(player_stats.houjuu, player_stats.rounds),
                average(player_stats.houjuu_point_sum, player_stats.houjuu, 1),
                percent(player_stats.top_keep_successes, player_stats.top_keep_chances),
                percent(player_stats.first_tenpai, player_stats.rounds),
                percent(player_stats.top_stay_rounds, player_stats.rounds),
                percent(player_stats.second_stay_rounds, player_stats.rounds),
                percent(player_stats.last_stay_rounds, player_stats.rounds),
                percent(player_stats.late_noten_houjuu, player_stats.late_noten_discards),
                percent(player_stats.late_noten_fresh_discards, player_stats.late_noten_discards),
                player_stats.winning_run_point_sum,
                average(player_stats.opening_shanten_sum, player_stats.opening_samples, 2),
                average(player_stats.opening_dora_sum, player_stats.opening_samples, 2),
                percent(player_stats.called, player_stats.rounds),
                player_stats.riichi,
                percent(player_stats.riichi, player_stats.rounds),
                percent(player_stats.riichi_miss, player_stats.riichi),
                percent(player_stats.bad_shape_riichi, player_stats.riichi),
                percent(player_stats.top_riichi, player_stats.riichi),
                max(player_stats.final_points) if player_stats.final_points else "",
                min(player_stats.final_points) if player_stats.final_points else "",
                player_stats.yakuman_count,
                average(player_stats.riichi_quality_score_sum, player_stats.riichi, 2),
                percent(riichi_quality_recommended_count(player_stats), player_stats.riichi),
                percent(
                    player_stats.riichi - riichi_quality_recommended_count(player_stats),
                    player_stats.riichi,
                ),
                riichi_quality_top_label(player_stats),
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

def has_record_files(uuid):
    return (
        (RAW_DIR / f"{uuid}_record.bin").exists()
        and (RAW_DIR / f"{uuid}_detail.bin").exists()
    )

def complete_season_rows(rows):
    rows_by_season = defaultdict(list)
    rows_without_season = []

    for row in rows:
        season = row.get("season", "").strip()
        if season.isdigit():
            rows_by_season[int(season)].append(row)
        else:
            rows_without_season.append(row)

    complete_rows = list(rows_without_season)
    for season, season_rows in sorted(rows_by_season.items()):
        missing = [
            row.get("uuid", "").strip()
            for row in season_rows
            if not has_record_files(row.get("uuid", "").strip())
        ]
        if missing:
            print(f"skip incomplete season {season}: {len(season_rows) - len(missing)}/{len(season_rows)} records ready")
            continue
        complete_rows.extend(season_rows)

    return complete_rows

def target_uuids():
    if not PAIFU_CSV.exists():
        return None

    with PAIFU_CSV.open("r", encoding="utf-8-sig", newline="") as f:
        rows = list(csv.DictReader(f))

    uuids = []
    seen = set()
    for row in complete_season_rows(rows):
        uuid = row.get("uuid", "").strip()
        if uuid and uuid not in seen:
            uuids.append(uuid)
            seen.add(uuid)

    return uuids or None

def main():
    stats = defaultdict(PlayerStats)
    yakuman_details = []

    uuids = target_uuids()
    if uuids is None:
        uuids = [path.name.removesuffix("_record.bin") for path in sorted(RAW_DIR.glob("*_record.bin"))]

    print(f"records: {len(uuids)}")

    for index, uuid in enumerate(uuids, start=1):
        record_path = RAW_DIR / f"{uuid}_record.bin"
        detail_path = RAW_DIR / f"{uuid}_detail.bin"
        if not record_path.exists() or not detail_path.exists():
            print(f"[{index}/{len(uuids)}] skip missing {uuid}")
            continue

        print(f"[{index}/{len(uuids)}] {uuid}")
        aggregate_game(uuid, stats, yakuman_details)

    write_summary(stats)
    write_yakuman_summary(stats)
    write_yakuman_details(yakuman_details)

    print(f"saved: {SUMMARY_OUT}")
    print(f"saved: {YAKUMAN_OUT}")
    print(f"saved: {YAKUMAN_DETAILS_OUT}")

if __name__ == "__main__":
    main()
