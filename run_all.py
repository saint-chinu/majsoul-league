from __future__ import annotations

import csv
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path


ROOT = Path(__file__).resolve().parent
GIT = Path(r"C:\Users\pgzdv\AppData\Local\GitHubDesktop\app-3.5.9\resources\app\git\cmd\git.exe")


def run(args: list[str], *, check: bool = True) -> subprocess.CompletedProcess:
    print()
    print(">>> " + " ".join(args))
    return subprocess.run(args, cwd=ROOT, check=check)


def count_csv(path: Path) -> int:
    if not path.exists():
        return 0
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        return sum(1 for _ in csv.DictReader(f))


def count_records() -> int:
    raw_dir = ROOT / "records_raw"
    return len(list(raw_dir.glob("*_record.bin")))


def backup_if_exists(path: Path) -> None:
    if not path.exists():
        return
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    backup = path.with_name(f"{path.stem}_backup_{stamp}{path.suffix}")
    shutil.copy2(path, backup)
    print(f"backup: {backup.name}")


def git_status_short() -> str:
    if not GIT.exists():
        return ""
    result = subprocess.run(
        [str(GIT), "status", "--short"],
        cwd=ROOT,
        check=True,
        text=True,
        capture_output=True,
    )
    return result.stdout.strip()


def commit_and_push() -> None:
    if not GIT.exists():
        print("GitHub Desktop の git.exe が見つからないので、GitHub反映はスキップします。")
        return

    files = [
        "admin_paifu_ids.csv",
        "summary.csv",
        "yakuman_summary.csv",
        "docs/index.html",
        "admin_paifu_ids_season1.csv",
        "admin_paifu_ids_season2.csv",
        "admin_paifu_ids_season3.csv",
        "admin_paifu_ids_season4.csv",
        "admin_paifu_ids_season5.csv",
        "admin_paifu_ids_season6.csv",
        "admin_paifu_ids_season7.csv",
        "admin_paifu_ids_season8.csv",
        "collect_admin_paifu_ids.py",
        "collect_all_seasons.py",
        "make_site.py",
        "run_all.py",
        "run_all.bat",
    ]

    existing = [name for name in files if (ROOT / name).exists()]
    if existing:
        run([str(GIT), "add", *existing])

    if not git_status_short():
        print("GitHubに反映する変更はありません。")
        return

    message = "Update majsoul league stats"
    run([str(GIT), "commit", "-m", message], check=False)
    run([str(GIT), "push", "origin", "main"])


def main() -> None:
    print("雀魂リーグ集計をまとめて実行します。")
    print("途中でブラウザが開いたら、管理画面でリーグ「テスト」が見える状態にしてEnterしてください。")

    input("開始するなら Enter: ")

    backup_if_exists(ROOT / "admin_paifu_ids.csv")

    run([sys.executable, "collect_all_seasons.py"])
    paifu_count = count_csv(ROOT / "admin_paifu_ids.csv")
    print(f"牌譜ID: {paifu_count} 件")

    if paifu_count == 0:
        raise SystemExit("牌譜IDが0件です。大会牌譜ページを開けているか確認してください。")

    run([sys.executable, "collect_records.py"])
    record_count = count_records()
    print(f"取得済み牌譜: {record_count} / {paifu_count} 件")

    if record_count < paifu_count:
        print("未取得が残っているので、もう一度だけ collect_records.py を再実行します。")
        run([sys.executable, "collect_records.py"])
        record_count = count_records()
        print(f"取得済み牌譜: {record_count} / {paifu_count} 件")

    if record_count < paifu_count:
        print("まだ未取得があります。あとで run_all.bat をもう一度実行すれば未取得分だけ再挑戦します。")

    run([sys.executable, "aggregate_league.py"])
    run([sys.executable, "make_site.py"])

    commit_and_push()

    print()
    print("完了しました。")
    print("GitHub Pages: https://saint-chinu.github.io/majsoul-league/")


if __name__ == "__main__":
    main()
