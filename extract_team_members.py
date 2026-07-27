from pathlib import Path
import csv
import json
import sys

TEAM_CSV = Path("team_members.csv")
CAPTURES_DIR = Path("captures")
HEADERS = ["season", "team", "player"]


def latest_snapshot():
    snapshots = sorted(CAPTURES_DIR.glob("team-page-*.json"))
    if not snapshots:
        raise SystemExit("captures\\team-page-*.json が見つかりません。先に capture_team_page.py を実行してください。")
    return snapshots[-1]


def read_existing():
    if not TEAM_CSV.exists():
        return []
    with TEAM_CSV.open("r", encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def write_rows(rows):
    with TEAM_CSV.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=HEADERS)
        writer.writeheader()
        writer.writerows(rows)


def normalize_cell(value):
    return str(value or "").strip()


def extract_rows(snapshot_path, season):
    data = json.loads(snapshot_path.read_text(encoding="utf-8"))
    extracted = []
    skipped = []

    for table in data.get("tables", []):
        rows = table.get("rows", [])
        if not rows:
            continue

        header = [normalize_cell(cell) for cell in rows[0]]
        if "プレイヤー名" not in header or "チームリスト" not in header:
            continue

        player_index = header.index("プレイヤー名")
        team_index = header.index("チームリスト")

        for raw_row in rows[1:]:
            row = [normalize_cell(cell) for cell in raw_row]
            if len(row) <= max(player_index, team_index):
                continue

            player = row[player_index]
            team = row[team_index]
            if not player or player == "データがありません":
                continue
            if not team:
                skipped.append(player)
                continue

            extracted.append(
                {
                    "season": str(season),
                    "team": team,
                    "player": player,
                }
            )

    seen = set()
    unique = []
    for row in extracted:
        key = (row["season"], row["team"], row["player"])
        if key in seen:
            continue
        unique.append(row)
        seen.add(key)

    return unique, skipped


def merge_for_season(existing, new_rows, season):
    season_text = str(season)
    merged = [row for row in existing if row.get("season") != season_text]
    merged.extend(new_rows)
    return sorted(merged, key=lambda row: (int(row["season"]), row["team"], row["player"]))


def main():
    if len(sys.argv) < 2 or not sys.argv[1].isdigit():
        print("使い方: python extract_team_members.py <シーズン番号> [captures\\team-page-日時.json]")
        print("例: python extract_team_members.py 3 captures\\team-page-20260727-210533.json")
        return

    season = int(sys.argv[1])
    snapshot_path = Path(sys.argv[2]) if len(sys.argv) >= 3 else latest_snapshot()
    if not snapshot_path.exists():
        raise SystemExit(f"ファイルが見つかりません: {snapshot_path}")

    new_rows, skipped = extract_rows(snapshot_path, season)
    if not new_rows:
        raise SystemExit("チーム所属を抽出できませんでした。チーム名が見える画面で capture_team_page.py を取り直してください。")

    existing = read_existing()
    merged = merge_for_season(existing, new_rows, season)
    write_rows(merged)

    print(f"snapshot: {snapshot_path}")
    print(f"saved: {TEAM_CSV}")
    print(f"season {season}: {len(new_rows)}件")
    for row in new_rows:
        print(f"  {row['team']}: {row['player']}")

    if skipped:
        print("チーム空欄のためスキップ:")
        for player in skipped:
            print(f"  {player}")


if __name__ == "__main__":
    main()
