from __future__ import annotations

import os
import runpy
import subprocess
import sys
from pathlib import Path


ROOT = Path(sys.executable).resolve().parent if getattr(sys, "frozen", False) else Path(__file__).resolve().parent
GIT = Path(r"C:\Users\pgzdv\AppData\Local\GitHubDesktop\app-3.5.9\resources\app\git\cmd\git.exe")


def run_script(script_name: str, *args: str) -> None:
    script_path = ROOT / script_name
    if not script_path.exists():
        raise SystemExit(f"ファイルが見つかりません: {script_path}")

    old_argv = sys.argv[:]
    old_cwd = Path.cwd()
    try:
        os.chdir(ROOT)
        sys.argv = [str(script_path), *args]
        print()
        print(">>> " + " ".join(sys.argv))
        runpy.run_path(str(script_path), run_name="__main__")
    finally:
        sys.argv = old_argv
        os.chdir(old_cwd)


def run_command(args: list[str]) -> None:
    print()
    print(">>> " + " ".join(args))
    subprocess.run(args, cwd=ROOT, check=True)


def publish_site_files() -> None:
    if not GIT.exists():
        raise SystemExit(f"GitHub Desktop の git.exe が見つかりません: {GIT}")

    files = [
        "admin_paifu_ids.csv",
        "summary.csv",
        "yakuman_summary.csv",
        "yakuman_details.csv",
        "team_members.csv",
        "docs/index.html",
    ]
    existing = [name for name in files if (ROOT / name).exists()]
    if not existing:
        print("公開対象ファイルがありません。")
        return

    run_command([str(GIT), "add", *existing])
    result = subprocess.run([str(GIT), "diff", "--cached", "--quiet"], cwd=ROOT)
    if result.returncode == 0:
        print("公開する変更はありません。")
        return

    run_command([str(GIT), "commit", "-m", "Update majsoul league site"])
    run_command([str(GIT), "push", "origin", "main"])
    print("GitHub Pages: https://saint-chinu.github.io/majsoul-league/")


def update_stats_and_site() -> None:
    run_script("aggregate_league.py")
    run_script("make_site.py")


def export_hand_log() -> None:
    players = {
        "1": ("流れ者金融", "nagaremono_table_event_log_with_hands.csv"),
        "2": ("葡萄海ぶどう", "budou_table_event_log_with_hands.csv"),
        "3": ("29ちゃん", "29chan_table_event_log_with_hands.csv"),
        "4": ("ひなんじょ", "hinanjo_table_event_log_with_hands.csv"),
        "5": ("アリスkey", "alicekey_table_event_log_with_hands.csv"),
        "6": ("鯛ofカルピス", "taiofcalpis_table_event_log_with_hands.csv"),
    }

    print()
    print("手牌つき完全ログを作るプレイヤー")
    for key, (name, _output) in players.items():
        print(f"  {key}. {name}")
    print("  7. 全員")
    choice = input("番号: ").strip()

    targets = players.values() if choice == "7" else [players.get(choice)]
    if not targets or targets == [None]:
        print("キャンセルしました。")
        return

    for name, output in targets:
        run_script("export_table_event_log_with_hands_for_player.py", name, output)

    print("CSV作成完了。URL公開する場合は、必要なファイルを docs に圧縮配置してGitHubへpushしてください。")


def menu() -> None:
    while True:
        print()
        print("=" * 48)
        print("魚群リーグ 集計メニュー")
        print("=" * 48)
        print("1. 単一シーズン取得 → 牌譜DL → 集計 → HTML公開")
        print("2. 全シーズンまとめて取得 → 牌譜DL → 集計 → HTML公開")
        print("3. チーム名取得 → HTML公開")
        print("4. 集計CSVとHTMLを作り直す")
        print("5. 集計CSVだけ作り直す")
        print("6. HTMLだけ作り直す")
        print("7. GitHub Pagesへ公開だけ実行")
        print("8. 手牌つき完全ログCSVを作る")
        print("9. 終了")
        choice = input("番号を入力: ").strip()

        try:
            if choice == "1":
                run_script("run_manual_season.py")
            elif choice == "2":
                run_script("run_all.py")
            elif choice == "3":
                run_script("run_team_publish.py")
            elif choice == "4":
                update_stats_and_site()
            elif choice == "5":
                run_script("aggregate_league.py")
            elif choice == "6":
                run_script("make_site.py")
            elif choice == "7":
                publish_site_files()
            elif choice == "8":
                export_hand_log()
            elif choice == "9":
                return
            else:
                print("1から9で選んでください。")
        except SystemExit as exc:
            print(exc)
        except subprocess.CalledProcessError as exc:
            print(f"コマンドが失敗しました: {exc}")
        except Exception as exc:
            print(f"エラー: {exc}")

        input("メニューへ戻るなら Enter: ")


def dispatch_script_mode() -> bool:
    if len(sys.argv) < 2:
        return False

    first = sys.argv[1]
    if not first.endswith(".py"):
        return False

    script_path = Path(first)
    if not script_path.is_absolute():
        script_path = ROOT / script_path
    if not script_path.exists():
        raise SystemExit(f"ファイルが見つかりません: {script_path}")

    old_argv = sys.argv[:]
    try:
        os.chdir(ROOT)
        sys.argv = [str(script_path), *old_argv[2:]]
        runpy.run_path(str(script_path), run_name="__main__")
    finally:
        sys.argv = old_argv
    return True


def main() -> None:
    os.chdir(ROOT)
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))
    if dispatch_script_mode():
        return
    menu()


if __name__ == "__main__":
    main()
