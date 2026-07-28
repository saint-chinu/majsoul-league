from __future__ import annotations

import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent
CAPTURES_DIR = ROOT / "captures"
GIT = Path(r"C:\Users\pgzdv\AppData\Local\GitHubDesktop\app-3.5.9\resources\app\git\cmd\git.exe")


def run(args: list[str], *, check: bool = True) -> subprocess.CompletedProcess:
    print()
    print(">>> " + " ".join(args))
    return subprocess.run(args, cwd=ROOT, check=check, text=True)


def latest_team_snapshot() -> Path | None:
    snapshots = sorted(CAPTURES_DIR.glob("team-page-*.json"))
    return snapshots[-1] if snapshots else None


def staged_changes_exist() -> bool:
    result = subprocess.run(
        [str(GIT), "diff", "--cached", "--quiet"],
        cwd=ROOT,
        text=True,
    )
    return result.returncode == 1


def ensure_file(name: str) -> None:
    path = ROOT / name
    if not path.exists():
        raise SystemExit(f"必要なファイルが見つかりません: {path}")


def commit_and_push(season: int) -> None:
    if not GIT.exists():
        raise SystemExit(f"GitHub Desktop の git.exe が見つかりません: {GIT}")

    files = [
        "team_members.csv",
        "docs/index.html",
    ]
    existing = [name for name in files if (ROOT / name).exists()]
    if not existing:
        print("GitHubに反映するファイルがありません。")
        return

    run([str(GIT), "add", *existing])

    if not staged_changes_exist():
        print("チーム情報とHTMLに変更はありません。Pushはスキップします。")
        return

    run([str(GIT), "commit", "-m", f"Update season {season} teams"])
    run([str(GIT), "push", "origin", "main"])


def parse_season() -> int:
    if len(sys.argv) >= 2 and sys.argv[1].isdigit():
        return int(sys.argv[1])

    raw = input("チーム名を取得するシーズン番号を入力: ").strip()
    if not raw.isdigit():
        raise SystemExit("シーズン番号は数字で入力してください。例: 9")
    return int(raw)


def main() -> None:
    season = parse_season()

    ensure_file("capture_team_page.py")
    ensure_file("extract_team_members.py")
    ensure_file("make_site.py")

    before = latest_team_snapshot()

    print(f"シーズン{season}のチーム名取得から公開まで実行します。")
    print("ブラウザが開いたら、対象シーズンのチーム名とメンバーが見える画面まで手で移動してください。")
    print("PowerShellに戻ってEnterを押すと、CSV更新、HTML生成、GitHub Pages公開まで進みます。")

    run([sys.executable, "capture_team_page.py"])

    after = latest_team_snapshot()
    if after is None:
        raise SystemExit("チームページのキャプチャJSONが見つかりません。")
    if before is not None and after == before:
        print(f"新しいキャプチャが見つからないため、最新ファイルを使います: {after}")

    run([sys.executable, "extract_team_members.py", str(season), str(after)])
    run([sys.executable, "make_site.py"])
    commit_and_push(season)

    print()
    print("完了しました。")
    print("GitHub Pages: https://saint-chinu.github.io/majsoul-league/")


if __name__ == "__main__":
    main()
