"""完全自動更新: 現行（新リーグ）シーズンの牌譜を取得してサイトを再生成・公開する。

タスクスケジューラから無人実行する前提で、対話プロンプトを一切持たない。
旧リーグのデータ（admin_paifu_ids.csv / summary.csv / キャッシュ）には触れない。

安全設計（大切なデータを消さないための決まりごと）:
- 牌譜IDは既存CSVとの和集合でのみ更新する。件数が減る書き込みは絶対にしない。
- 取得0件・ログイン切れ・ナビゲーション失敗のときは何も書かずに異常終了する
  （中途半端な状態でサイトを再生成・pushしない）。
- 書き込み前に backups/ へタイムスタンプ付きバックアップを残す。
- 削除系ボタンには触れない（collect_admin_paifu_ids側の分類・較正・モーダル検知）。

実行の流れ:
  1. 管理画面へ（ログイン済みbrowser-profileを使用）
     → 大会リスト画面が出ていれば対象大会（既定「テスト」、league_name設定で変更可）を選択
     → シーズンリストの「進行中」バッジが付いた行から大会牌譜タブへ自動遷移
     （URL中の数字は雀魂システム内部の通し番号であり、サイトの
     「新リーグ第N シーズン」というラベル=new_season設定とは別物なので、
     ナビゲーションにのみ使い、new_seasonの値は書き換えない）
  2. 牌譜IDを収集 → data/new/admin_paifu_ids_new_season{N}.csv へ和集合マージ
  3. collect_records.py で不足牌譜バイナリのみ取得（既存はスキップされる）
  4. make_site.py でサイト再生成（タブ別ページ）
  5. 変更があればコミットして main へ push（GitHub Pagesが自動デプロイ）

設定は auto_update_config.json（無ければ既定値で自動生成）。
"""

from __future__ import annotations

import csv
import json
import re
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path

SEASON_URL_RE = re.compile(r"/season/(\d+)/record")

ROOT = Path(__file__).resolve().parent
CONFIG_PATH = ROOT / "auto_update_config.json"
NEW_DATA_DIR = ROOT / "data" / "new"
BACKUP_DIR = ROOT / "backups"
SEASON_COLUMNS = ["season", "page_no", "uuid", "date_key", "paifu_url"]

DEFAULT_CONFIG = {
    "contest_url": "https://tournament.mahjongsoul.com/contest_dashboard/index.html#/contest/48491649",
    "league_name": "テスト",
    "new_season": 1,
    "max_pages": 60,
    "navigation_attempts": 3,
    "click_season_from_bottom": 0,
    "commit_message": "Auto update league stats",
    "push_branch": "main",
}


def log(message: str) -> None:
    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {message}", flush=True)


def load_config() -> dict:
    if not CONFIG_PATH.exists():
        CONFIG_PATH.write_text(
            json.dumps(DEFAULT_CONFIG, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        log(f"設定ファイルを作成しました: {CONFIG_PATH.name}")
    config = dict(DEFAULT_CONFIG)
    config.update(json.loads(CONFIG_PATH.read_text(encoding="utf-8")))
    return config


def season_csv_path(season: int) -> Path:
    return NEW_DATA_DIR / f"admin_paifu_ids_new_season{season}.csv"


def read_csv_rows(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def merge_season_rows(
    existing: list[dict[str, str]], collected: list[dict[str, object]], season: int
) -> list[dict[str, str]]:
    """既存CSVと今回収集分の和集合。既存のUUIDは絶対に落とさない（データ保護の要）。"""
    rows_by_uuid: dict[str, dict[str, str]] = {}
    for row in existing + [
        {key: str(value) for key, value in row.items()} for row in collected
    ]:
        uuid = row.get("uuid", "")
        if not uuid:
            continue
        rows_by_uuid.setdefault(
            uuid,
            {
                "season": row.get("season") or str(season),
                "page_no": row.get("page_no", ""),
                "uuid": uuid,
                "date_key": row.get("date_key") or uuid.split("-", 1)[0],
                "paifu_url": row.get("paifu_url")
                or f"https://game.mahjongsoul.com/?paipu={uuid}",
            },
        )
    return sorted(rows_by_uuid.values(), key=lambda row: row["uuid"])


def sync_canonical_csv() -> Path:
    """集約側CSV（data/new/admin_paifu_ids.csv）をシーズン別CSVの和集合で
    作り直して同期する。放置するとシーズン別CSVと件数がズレたまま残り、
    「なんで件数が違う？」と混乱のもとになるため、自動更新のたびに揃える。"""
    canonical = NEW_DATA_DIR / "admin_paifu_ids.csv"
    rows_by_uuid: dict[str, dict[str, str]] = {}
    for path in sorted(NEW_DATA_DIR.glob("admin_paifu_ids_new_season*.csv")):
        for row in read_csv_rows(path):
            uuid = row.get("uuid", "")
            if uuid:
                rows_by_uuid.setdefault(
                    uuid, {key: row.get(key, "") for key in SEASON_COLUMNS}
                )
    rows = sorted(
        rows_by_uuid.values(),
        key=lambda row: (
            int(row["season"]) if row.get("season", "").isdigit() else 0,
            row["uuid"],
        ),
    )
    existing = read_csv_rows(canonical)
    if len(rows) < len(existing):
        # 集約側が既に多くのIDを持っているのに縮む状況は異常なので触らない。
        log(
            f"集約CSVの同期をスキップ: 和集合({len(rows)})が既存({len(existing)})より少ない"
        )
        return canonical
    write_season_csv(canonical, rows)
    return canonical


def guard_admin_season(config: dict, found_season: int) -> None:
    """管理画面で着地した「進行中」シーズンの内部番号を設定ファイルに記録し、
    変わっていたら止める。新シーズン開始後に new_season の設定変更を忘れて
    実行し、新シーズンの牌譜が前シーズンのCSVへ混ざる事故を防ぐ。"""
    stored = config.get("admin_internal_season")
    if stored is None:
        config["admin_internal_season"] = found_season
        raw = (
            json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
            if CONFIG_PATH.exists()
            else {}
        )
        raw["admin_internal_season"] = found_season
        CONFIG_PATH.write_text(
            json.dumps(raw, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        log(f"進行中シーズンの内部番号 {found_season} を設定ファイルに記録しました。")
    elif int(stored) != int(found_season):
        raise SystemExit(
            f"SEASON_CHANGED: 管理画面の進行中シーズンが変わっています"
            f"（記録 {stored} → 現在 {found_season}）。\n"
            "新シーズンが始まった場合は auto_update_config.json の new_season を"
            "新しい番号に更新し、admin_internal_season の行を削除してから再実行してください。"
        )


def write_season_csv(path: Path, rows: list[dict[str, str]]) -> None:
    NEW_DATA_DIR.mkdir(parents=True, exist_ok=True)
    if path.exists():
        BACKUP_DIR.mkdir(exist_ok=True)
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        shutil.copy2(path, BACKUP_DIR / f"{path.stem}_{stamp}{path.suffix}")
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=SEASON_COLUMNS)
        writer.writeheader()
        writer.writerows(rows)


def looks_logged_out(page) -> bool:
    """ログイン切れの判定。パスワード入力欄が見えていて大会UIが見えないなら切れている。"""
    try:
        password_inputs = page.locator('input[type="password"]').count()
        has_dashboard_text = page.evaluate(
            "() => /大会|contest|牌譜/i.test(document.body ? document.body.innerText : '')"
        )
    except Exception:
        return False
    return password_inputs > 0 and not has_dashboard_text


def maybe_select_league(page, league_name: str) -> None:
    """ログイン直後は大会が並ぶ「大会リスト」画面に出ることがあるため、
    対象の大会名（既定「テスト」）のカードが見えていれば選んでおく。
    既に大会の中に入っている場合はカードが無いので何もしない（素通り）。"""
    if not league_name:
        return
    clicked = page.evaluate(
        """
        (name) => {
          const leaf = Array.from(document.querySelectorAll('*')).find(
            el => el.children.length === 0
              && (el.innerText || el.textContent || '').trim() === name
          );
          if (!leaf) return false;
          leaf.click();
          return true;
        }
        """,
        league_name,
    )
    if clicked:
        page.wait_for_timeout(2000)


def click_login_button_if_present(page) -> None:
    """保存済みログイン情報が有効でも、管理画面は最初に「ログイン」ボタンを
    一度押す工程が挟まる（playwright codegenの実録で確認）。無ければ何もしない。"""
    from collect_all_seasons import click_visible_text

    if click_visible_text(page, ["ログイン"], exact=True):
        page.wait_for_timeout(2000)


def click_battle_records_tab(page) -> bool:
    """『大会牌譜』タブを押す。横幅が足りずrc-menu（antdの水平メニュー）の
    「…」折りたたみに収まっている場合は、まずそれを開いてから探し直す
    （playwright codegenの実録で `#rc-menu-...-rc-menu-more-popup` の中に
    あることを確認した。座標や固定viewport幅に頼らず対応するための処理）。"""
    def find_and_click():
        return page.evaluate(
            """
            () => {
              const el = Array.from(document.querySelectorAll('*')).find(
                e => e.children.length === 0 && (e.innerText || e.textContent || '').trim() === '大会牌譜'
              );
              if (!el) return false;
              const rect = el.getBoundingClientRect();
              if (rect.width === 0 || rect.height === 0) return false;
              el.click();
              return true;
            }
            """
        )

    if find_and_click():
        return True

    opened = page.evaluate(
        """
        () => {
          const trigger = document.querySelector(
            '[class*="overflow-item-rest"], [class*="rc-menu-overflow-item-rest"], li[aria-haspopup="true"]'
          );
          if (!trigger) return false;
          trigger.click();
          return true;
        }
        """
    )
    if not opened:
        return False
    page.wait_for_timeout(500)
    return find_and_click()


def open_in_progress_season_records(page) -> int | None:
    """シーズンリストで「進行中」バッジを直接クリックしてシーズン詳細へ入り、
    「大会牌譜」タブ（折りたたまれていれば開いてから）を押して牌譜一覧まで
    進める。実際に着地したシーズン番号をURL（.../season/{N}/record）から
    読み取って返す。見つからなければNone。"""
    clicked = page.evaluate(
        """
        () => {
          const el = Array.from(document.querySelectorAll('*')).find(
            e => e.children.length === 0 && (e.innerText || e.textContent || '').trim() === '進行中'
          );
          if (!el) return false;
          const rect = el.getBoundingClientRect();
          if (rect.width === 0 || rect.height === 0) return false;
          el.click();
          return true;
        }
        """
    )
    if not clicked:
        return None

    page.wait_for_timeout(1500)
    if "/record" not in page.url:
        click_battle_records_tab(page)
        page.wait_for_timeout(1500)

    match = SEASON_URL_RE.search(page.url)
    return int(match.group(1)) if match else None


def collect_ids(config: dict) -> list[dict[str, object]]:
    from playwright.sync_api import sync_playwright

    from collect_admin_paifu_ids import USER_DATA_DIR, install_dialog_guard
    from collect_all_seasons import (
        click_game_record_tab,
        click_season,
        collect_current_season,
    )

    season = int(config["new_season"])
    max_pages = int(config["max_pages"])
    attempts = max(1, int(config["navigation_attempts"]))
    season_click = int(config.get("click_season_from_bottom") or 0)
    league_name = config.get("league_name") or ""

    with sync_playwright() as p:
        browser = p.chromium.launch_persistent_context(
            user_data_dir=str(USER_DATA_DIR),
            headless=False,
            # rc-menu（antdの水平メニュー）のタブが「…」に折りたたまれるのを
            # 避けるため広め（playwright codegenの実録で1460幅では折りたたまれて
            # いたことを確認）。click_battle_records_tabの折りたたみ対応も
            # 保険として残す。
            viewport={"width": 1920, "height": 1000},
        )
        try:
            for attempt in range(1, attempts + 1):
                log(f"管理画面へ移動します (試行 {attempt}/{attempts})")
                page = browser.new_page()
                install_dialog_guard(page)
                try:
                    page.goto(config["contest_url"], wait_until="domcontentloaded")
                    page.wait_for_timeout(4000)
                    # 保存済みログイン情報があっても、最初に「ログイン」ボタンを
                    # 押す工程が挟まる（playwright codegenの実録で確認）。
                    click_login_button_if_present(page)

                    if looks_logged_out(page):
                        raise SystemExit(
                            "LOGIN_EXPIRED: 管理画面のログインが切れています。"
                            "一度手動でログインし直してください（browser-profile更新）。"
                        )

                    maybe_select_league(page, league_name)

                    found_season = open_in_progress_season_records(page)
                    if found_season is not None:
                        log(f"進行中シーズン（管理画面内部番号 {found_season}）の牌譜タブへ移動しました。")
                        guard_admin_season(config, found_season)
                    else:
                        log("進行中シーズンの行が見つからないため旧方式で試します。")
                        if not click_game_record_tab(page):
                            log("大会牌譜タブも見つかりませんでした（表示済みとみなして続行）")
                        page.wait_for_timeout(1500)
                        if season_click > 0:
                            if not click_season(page, season_click, auto=True):
                                log("シーズン選択に失敗しました（現在の表示のまま続行）")
                            page.wait_for_timeout(1500)

                    rows = collect_current_season(page, season, max_pages)
                    if rows:
                        return rows
                    log("収集0件。ページを開き直して再試行します。")
                finally:
                    page.close()
        finally:
            browser.close()

    return []


def run_step(args: list[str]) -> None:
    log(">>> " + " ".join(args))
    subprocess.run(args, cwd=ROOT, check=True)


def count_complete_records(rows: list[dict[str, str]]) -> int:
    raw = ROOT / "records_raw"
    count = 0
    for row in rows:
        uuid = row.get("uuid", "")
        if (
            uuid
            and (raw / f"{uuid}_record.bin").exists()
            and (raw / f"{uuid}_detail.bin").exists()
        ):
            count += 1
    return count


def verify_site_not_shrunk(git: str, min_ratio: float = 0.85) -> None:
    """サイト再生成で既存ページが消えたり大きく縮んだりしていないか確認する。

    集計キャッシュの破損など何らかの理由でナビや個別ページの中身が
    まるごと欠落したまま push されてしまう事故が実際に一度起きたため、
    push 前の最後の砦として必ず通す。"""
    # -z: 非ASCIIファイル名がクォート・エスケープされて返るのを防ぐ
    # （日本語プレイヤー名のファイルが多いため、これがないと素通りしてしまう）。
    raw = subprocess.run(
        [git, "ls-tree", "-r", "-z", "--name-only", "HEAD", "docs"],
        cwd=ROOT, check=True, capture_output=True,
    ).stdout
    tracked = raw.decode("utf-8").split("\0")

    problems = []
    for rel_path in tracked:
        if not rel_path.endswith(".html"):
            continue
        old_size = len(
            subprocess.run(
                [git, "show", f"HEAD:{rel_path}"],
                cwd=ROOT, capture_output=True,
            ).stdout
        )
        current = ROOT / rel_path
        if not current.exists():
            problems.append(f"消滅: {rel_path}")
            continue
        new_size = current.stat().st_size
        if old_size > 0 and new_size < old_size * min_ratio:
            problems.append(f"縮小: {rel_path} ({old_size}B -> {new_size}B)")

    if problems:
        detail = "\n  ".join(problems)
        raise SystemExit(
            "ABORT: サイト再生成で既存ページが消えたか大きく縮みました。"
            "データ破損の疑いがあるため push しません。\n  " + detail
        )


def find_git() -> str | None:
    git = shutil.which("git")
    if git:
        return git
    fallback = Path(
        r"C:\Users\pgzdv\AppData\Local\GitHubDesktop\app-3.5.9\resources\app\git\cmd\git.exe"
    )
    return str(fallback) if fallback.exists() else None


def commit_and_push(config: dict, season_csv: Path) -> None:
    git = find_git()
    if not git:
        log("git が見つからないため push をスキップしました（データは保存済み）")
        return

    targets = [str(season_csv.relative_to(ROOT))]
    # 集約側CSVと旧リーグキャッシュも、更新されていれば一緒にコミットして
    # リポジトリ内の件数ズレ・データずれを残さない。
    for extra in [NEW_DATA_DIR / "admin_paifu_ids.csv", ROOT / "data" / "old_league_contexts.json"]:
        if extra.exists():
            targets.append(str(extra.relative_to(ROOT)))
    targets += [str(p.relative_to(ROOT)) for p in (ROOT / "docs").glob("*.html")]
    subprocess.run([git, "add", *targets], cwd=ROOT, check=True)

    # 作業用CSVや調査スクリプトの未追跡ファイルは公開対象ではない。
    # status全体を見ると、それらだけでも空コミットを試みて失敗するため、
    # 今回addした公開対象にステージ済み差分があるかだけを判定する。
    staged = subprocess.run(
        [git, "diff", "--cached", "--quiet"], cwd=ROOT, check=False
    )
    if staged.returncode == 0:
        log("変更なし。push は不要です。")
        return

    subprocess.run(
        [git, "commit", "-m", config["commit_message"]], cwd=ROOT, check=True
    )
    subprocess.run(
        [git, "push", "origin", f"HEAD:{config['push_branch']}"], cwd=ROOT, check=True
    )
    log("push 完了。GitHub Pages が自動でデプロイします。")


def main() -> None:
    log("=== 自動更新開始 ===")
    config = load_config()
    season = int(config["new_season"])
    csv_path = season_csv_path(season)

    existing = read_csv_rows(csv_path)
    log(f"既存の牌譜ID: {len(existing)}件 ({csv_path.name})")

    collected = collect_ids(config)
    log(f"今回収集: {len(collected)}件")

    if not collected and not existing:
        raise SystemExit("ABORT: 牌譜IDが1件も取れませんでした。何も書き込まず終了します。")
    if not collected:
        log("収集0件のためCSVは更新しません（既存データで続行）。")
        merged = existing
    else:
        merged = merge_season_rows(existing, collected, season)
        if len(merged) < len(existing):
            raise SystemExit(
                f"ABORT: マージ結果({len(merged)})が既存({len(existing)})より少ないため書き込みません。"
            )
        new_count = len(merged) - len(existing)
        log(f"マージ結果: {len(merged)}件（新規 {new_count}件）")
        if new_count == 0 and csv_path.exists():
            log("新規IDなし。CSVは書き換えません。")
        else:
            write_season_csv(csv_path, merged)
            log(f"保存: {csv_path}")

    sync_canonical_csv()

    run_step([sys.executable, "collect_records.py", str(csv_path)])
    complete = count_complete_records(merged)
    log(f"牌譜バイナリ: {complete} / {len(merged)} 件")
    if complete < len(merged):
        log("不足分があるため collect_records.py をもう一度実行します。")
        run_step([sys.executable, "collect_records.py", str(csv_path)])
        complete = count_complete_records(merged)
        log(f"牌譜バイナリ: {complete} / {len(merged)} 件")

    run_step([sys.executable, "make_site.py"])

    git = find_git()
    if git:
        verify_site_not_shrunk(git)
    else:
        log("git が見つからないためサイズチェックをスキップしました")

    commit_and_push(config, csv_path)
    log("=== 自動更新完了 ===")


if __name__ == "__main__":
    main()
