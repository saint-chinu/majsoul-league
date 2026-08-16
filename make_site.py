from __future__ import annotations

import csv
import html
import json
import sys
from collections import Counter, defaultdict
from itertools import combinations
from pathlib import Path
import re
import urllib.parse


SUMMARY_CSV = Path("summary.csv")
YAKUMAN_CSV = Path("yakuman_summary.csv")
YAKUMAN_DETAILS_CSV = Path("yakuman_details.csv")
PAIFU_CSV = Path("admin_paifu_ids.csv")
TEAM_CSV = Path("team_members.csv")
OUTPUT_HTML = Path("docs") / "index.html"

# ---------------------------------------------------------------------------
# ページ分割書き出し
#
# 以前は全タブを1枚のHTML（約6.5MB・テーブル546個）に収めていたため、
# スマホでは初回レイアウトでメモリ不足になり白画面/リロードループに陥った
# （hidden焼き込みで緩和したが、根本対策としてタブごとに独立ページへ分割する）。
# 集計・パネル描画のロジックには一切触れず、組み立て済みの単一ページHTMLを
# 純粋に「分割」する後処理として実装してある。こうすることで、再集計できない
# 環境でも配信済みindex.htmlへ同じ関数を適用でき、生成器と実サイトが
# 同一コードパスで検証できる。
# ---------------------------------------------------------------------------

MERMAID_PAGE_SCRIPT = """  <script type="module">
    import mermaid from "https://cdn.jsdelivr.net/npm/mermaid@11/dist/mermaid.esm.min.mjs";
    mermaid.initialize({ startOnLoad: true, theme: "base", flowchart: { curve: "basis" } });
  </script>
"""

METRIC_MODAL_PAGE_SCRIPT = """  <script>
    window.addEventListener("DOMContentLoaded", () => {
      const metricModal = document.querySelector("[data-metric-modal]");
      const metricTitle = metricModal ? metricModal.querySelector("#metric-modal-title") : null;
      const metricBody = metricModal ? metricModal.querySelector("[data-metric-body]") : null;

      function closeMetricModal() {
        if (!metricModal) return;
        metricModal.hidden = true;
      }

      document.querySelectorAll("[data-metric-title]").forEach((button) => {
        button.addEventListener("click", () => {
          if (!metricModal || !metricTitle || !metricBody) return;
          metricTitle.textContent = button.dataset.metricTitle || "項目説明";
          if (button.dataset.metricHtml) {
            metricBody.innerHTML = button.dataset.metricHtml;
          } else {
            metricBody.textContent = button.dataset.metricBody || "";
          }
          metricModal.hidden = false;
          const closeButton = metricModal.querySelector(".metric-modal-close");
          if (closeButton) closeButton.focus();
        });
      });

      document.querySelectorAll("[data-metric-close]").forEach((button) => {
        button.addEventListener("click", closeMetricModal);
      });

      document.addEventListener("keydown", (event) => {
        if (event.key === "Escape") closeMetricModal();
      });
    });
  </script>
"""

METRIC_MODAL_MARKUP = """  <div class="metric-modal" data-metric-modal hidden>
    <div class="metric-modal-backdrop" data-metric-close></div>
    <section class="metric-modal-panel" role="dialog" aria-modal="true" aria-labelledby="metric-modal-title">
      <h2 id="metric-modal-title">項目説明</h2>
      <div class="metric-modal-body" data-metric-body></div>
      <button class="metric-modal-close" type="button" data-metric-close>閉じる</button>
    </section>
  </div>
"""


def _find_matching_section_end(html_text: str, open_end: int) -> int:
    """<section ...>の開始タグ終端位置から、対応する</section>の閉じ終端位置を返す。"""
    depth = 1
    i = open_end
    while depth > 0:
        next_open = html_text.find("<section", i)
        next_close = html_text.find("</section>", i)
        if next_close == -1:
            raise ValueError("unbalanced <section> while splitting site pages")
        if next_open != -1 and next_open < next_close:
            depth += 1
            i = next_open + len("<section")
        else:
            depth -= 1
            i = next_close + len("</section>")
    return i


def page_filename_for(key: str) -> str:
    """タブキー→出力ファイル名。トップ（新リーグ）だけはindex.htmlのまま。"""
    return "index.html" if key == "new-league" else f"{key}.html"


def split_site_pages(html_text: str) -> dict[str, str]:
    """組み立て済み単一ページHTMLを、タブごとの独立ページ群へ分割する。

    パネル本文はバイト単位でそのまま移し替える（hidden属性の除去のみ）。
    同じdata-panelキーを持つ複数セクション（個人ページの「リーグ通算＋
    シーズン別」の積み重ね表示）は、出現順を保ったまま同じページへ束ねる。
    """
    html_text = html_text.replace('<section class="tab-panel" hidden', '<section class="tab-panel"')

    style_match = re.search(r"<style>.*?</style>", html_text, re.S)
    if not style_match:
        raise ValueError("style block not found")
    style_block = style_match.group(0)
    # タブをbuttonからリンクに変えるため、リンクでも従来の見た目になるよう最小限の補正を足す。
    style_block = style_block.replace(
        "</style>",
        "    a.tab-button { text-decoration: none; display: inline-block; }\n  </style>",
    )

    nav_open = html_text.find('<section class="tab-groups"')
    if nav_open == -1:
        raise ValueError("tab-groups nav not found")
    nav_end = _find_matching_section_end(html_text, html_text.find(">", nav_open) + 1)
    nav_html = html_text[nav_open:nav_end]

    # タブボタン一覧（キー→表示名、出現順）
    button_pattern = re.compile(
        r'<button class="tab-button([^"]*)" type="button" data-tab="([^"]+)">([^<]+)</button>'
    )
    labels: dict[str, str] = {}
    for _, key, label in button_pattern.findall(nav_html):
        labels.setdefault(key, label)

    # タブパネル本体をキーごとに回収（同一キーは出現順に連結）
    panels: dict[str, list[str]] = {}
    order: list[str] = []
    panel_pattern = re.compile(r'<section class="tab-panel" id="panel-([^"]+)"[^>]*>')
    for match in panel_pattern.finditer(html_text):
        key = match.group(1)
        end = _find_matching_section_end(html_text, match.end())
        panels.setdefault(key, []).append(html_text[match.start():end])
        if key not in order:
            order.append(key)

    def nav_for(current_key: str) -> str:
        def replace(match: re.Match[str]) -> str:
            extra_classes, key, label = match.groups()
            classes = "tab-button" + extra_classes.replace(" active", "")
            current = ""
            if key == current_key:
                classes += " active"
                current = ' aria-current="page"'
            href = urllib.parse.quote(page_filename_for(key))
            return f'<a class="{classes}" href="{href}"{current}>{label}</a>'

        return button_pattern.sub(replace, nav_html)

    pages: dict[str, str] = {}
    for key in order:
        label = labels.get(key, key)
        body_panels = "\n".join(panels[key])
        title = "魚群リーグ" if key == "new-league" else f"{label} | 魚群リーグ"
        mermaid_script = MERMAID_PAGE_SCRIPT if 'class="mermaid"' in body_panels else ""
        pages[page_filename_for(key)] = f"""<!doctype html>
<html lang="ja">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{title}</title>
{mermaid_script}{METRIC_MODAL_PAGE_SCRIPT}{style_block}
</head>
<body>
  <header>
    <h1>魚群リーグ</h1>
  </header>
  <main>
    {nav_for(key)}
    {body_panels}
  </main>
{METRIC_MODAL_MARKUP}  <footer>
    Generated from collected Mahjong Soul records.
  </footer>
</body>
</html>
"""
    return pages


def write_site_pages(html_text: str) -> None:
    OUTPUT_HTML.parent.mkdir(parents=True, exist_ok=True)
    pages = split_site_pages(html_text)
    for filename, content in pages.items():
        (OUTPUT_HTML.parent / filename).write_text(content, encoding="utf-8")
    print(f"saved: {len(pages)} pages under {OUTPUT_HTML.parent}/ (index + {len(pages) - 1} tabs)")



RAW_DIR = Path("records_raw")
SEASON_FILE_RE = re.compile(r"admin_paifu_ids_season(\d+)\.csv$")
NEW_DATA_DIR = Path("data") / "new"
NEW_PAIFU_CSV = NEW_DATA_DIR / "admin_paifu_ids.csv"
NEW_SEASON_FILE_RE = re.compile(r"admin_paifu_ids_new_season(\d+)\.csv$")
OLD_LEAGUE_FULL_GAMES = 120
NEW_LEAGUE_FULL_GAMES = 135
OLD_CONTEXT_CACHE = Path("data") / "old_league_contexts.json"
OLD_CONTEXT_CACHE_VERSION = 2


LABELS = {
    "rank": "順位",
    "player": "プレイヤー",
    "games": "半荘数",
    "earned_score": "スコア",
    "rank1_rate": "1位率",
    "rank2_rate": "2位率",
    "rank3_rate": "3位率",
    "last_avoid_rate": "ラス回避率",
    "average_rank": "平均順位",
    "rounds": "参加局数",
    "average_hu_point": "平均和了点",
    "average_called_hu_point": "鳴き手平均打点",
    "hu_rate": "和了率",
    "open_tanyao_hu_rate": "喰いタン和了率",
    "chiitoi_hu_rate": "七対子和了率",
    "honitsu_hu_rate": "ホンイツ和了率",
    "chinitsu_hu_rate": "チンイツ和了率",
    "tsumo_rate": "ツモ率",
    "tsumo_loss_rate": "被ツモ率",
    "average_tsumo_loss_point": "平均被ツモ支払点",
    "houjuu_rate": "放銃率",
    "average_houjuu_point": "放銃平均打点",
    "noten_houjuu_rate": "ノーテン放銃率",
    "two_shanten_houjuu_rate": "2シャン以下放銃率",
    "riichi_after_houjuu_rate": "リーチ後放銃率",
    "vs_riichi_houjuu_rate": "対リーチ放銃率",
    "vs_dama_houjuu_rate": "対ダマ放銃率",
    "vs_called_houjuu_rate": "対鳴き放銃率",
    "vs_two_called_houjuu_rate": "2副露放銃率",
    "vs_haneman_houjuu_rate": "跳満以上放銃率",
    "late_noten_houjuu_share": "終盤ノーテン放銃",
    "deal_in_quality_score": "放銃質スコア",
    "deal_in_quality_top_category": "最多放銃分類",
    "called_houjuu_rate": "鳴き手放銃率",
    "two_called_houjuu_rate": "2副露以上放銃率",
    "called_haneman_houjuu_rate": "鳴き跳満以上放銃率",
    "top_keep_rate": "トップキープ率",
    "first_tenpai_rate": "先制テンパイ率",
    "tenpai_keep_rate": "テンパイ維持率",
    "top_stay_rate": "トップ滞在率",
    "second_stay_rate": "2位滞在率",
    "last_stay_rate": "ラス滞在率",
    "late_noten_houjuu_rate": "後半非聴放銃率",
    "late_noten_fresh_discard_rate": "終盤非聴生牌",
    "winning_run_points": "ウイニングラン加点",
    "average_opening_shanten": "平均配牌シャンテン",
    "average_opening_dora": "平均配牌ドラ",
    "called_rate": "副露率",
    "riichi": "リーチ数",
    "riichi_rate": "立直率",
    "riichi_miss_rate": "リーチ空振り率",
    "bad_shape_riichi_rate": "愚形リーチ率",
    "top_riichi_rate": "トップ目リーチ率",
    "riichi_quality_score": "リーチ質スコア",
    "riichi_recommended_rate": "リーチ可率",
    "riichi_not_recommended_rate": "非推奨リーチ率",
    "riichi_quality_top_category": "最多リーチ分類",
    "call_after_hu_rate": "鳴き後和了率",
    "call_after_houjuu_rate": "鳴き後放銃率",
    "two_called_rate": "2副露以上率",
    "two_called_hu_rate": "2副露以上和了率",
    "two_called_after_houjuu_rate": "2副露以上放銃率",
    "average_first_call_turn": "初副露巡目平均",
    "call_quality_score": "鳴き質スコア",
    "call_quality_top_category": "最多鳴き分類",
    "max_final_point": "最高終了時持ち点",
    "min_final_point": "最低終了時持ち点",
    "yakuman_count": "役満回数",
    "mvp_count": "MVP回数",
    "team_champion_count": "チーム優勝回数",
    "season": "シーズン",
    "metric": "項目",
    "value": "値",
    "rank_text": "順位",
    "direction": "評価",
}


METRIC_DESCRIPTIONS = {
    "games": "集計対象になった半荘数。",
    "earned_score": "最終持ち点と順位点を合わせた獲得スコア。",
    "average_rank": "半荘終了時順位の平均。低いほど良い。",
    "rank1_rate": "半荘で1位を取った割合。",
    "rank2_rate": "半荘で2位を取った割合。",
    "rank3_rate": "半荘で3位になった割合。",
    "last_avoid_rate": "1位または2位で終えた割合。",
    "top_keep_rate": "単独トップになった半荘を、そのまま1位で終えた割合。",
    "first_tenpai_rate": "各局で最初にテンパイした割合。",
    "tenpai_keep_rate": "全打牌のうち、打牌時点でテンパイ状態だった割合。",
    "top_stay_rate": "各局開始時にトップ目だった割合。",
    "second_stay_rate": "各局開始時に2位だった割合。",
    "last_stay_rate": "各局開始時にラス目だった割合。",
    "late_noten_houjuu_rate": "12巡目以降、非テンパイ打牌で放銃した割合。",
    "late_noten_fresh_discard_rate": "12巡目以降、非テンパイ打牌で生牌を切った割合。",
    "winning_run_points": "オーラス親の大トップ状態から半荘終了までに増減した持ち点。",
    "rounds": "集計対象の参加局数。",
    "hu_rate": "参加局のうち、自分が和了した割合。",
    "average_hu_point": "自分のツモ・ロンで実際に増えた点数の平均。",
    "average_called_hu_point": "鳴いた手で和了した時の平均獲得点。",
    "tsumo_rate": "和了のうち、ツモ和了だった割合。",
    "houjuu_rate": "参加局のうち、自分が放銃した割合。",
    "average_houjuu_point": "放銃時に支払った点数の平均。",
    "noten_houjuu_rate": "ロン放銃のうち、自分が非テンパイだった割合。",
    "two_shanten_houjuu_rate": "ロン放銃のうち、自分が2シャンテン以上遠い状態だった割合。",
    "riichi_after_houjuu_rate": "ロン放銃のうち、自分のリーチ後放銃だった割合。",
    "vs_riichi_houjuu_rate": "ロン放銃のうち、リーチ者へ放銃した割合。",
    "vs_dama_houjuu_rate": "ロン放銃のうち、門前非リーチの相手へ放銃した割合。",
    "vs_called_houjuu_rate": "ロン放銃のうち、鳴いた相手へ放銃した割合。",
    "vs_two_called_houjuu_rate": "ロン放銃のうち、2副露以上の相手へ放銃した割合。",
    "vs_haneman_houjuu_rate": "ロン放銃のうち、支払点12,000点以上だった割合。",
    "late_noten_houjuu_share": "ロン放銃のうち、12巡目以降の非テンパイ打牌で放銃した割合。",
    "deal_in_quality_score": "放銃時の押し理由と失点状況を採点した平均値。スコアをクリックすると分類内訳を表示。",
    "deal_in_quality_top_category": "そのプレイヤーで最も多かった放銃分類。",
    "called_houjuu_rate": "参加局のうち、鳴いた手へのロン放銃になった割合。",
    "two_called_houjuu_rate": "参加局のうち、2副露以上の手へのロン放銃になった割合。",
    "called_haneman_houjuu_rate": "参加局のうち、鳴いた跳満以上の手へのロン放銃になった割合。ロン支払点12,000点以上を跳満以上として集計。",
    "called_rate": "参加局のうち、副露した割合。",
    "riichi_rate": "参加局のうち、リーチした割合。",
    "riichi_miss_rate": "リーチした局で、自分が和了できなかった割合。",
    "bad_shape_riichi_rate": "リーチのうち、待ち枚数4枚以下の割合。両ヤオチュウ・役牌シャンポン、字牌・萬子単騎は除外。",
    "top_riichi_rate": "リーチ時点でトップ目だった割合。",
    "riichi_quality_score": "リーチ待ちを-5点から10点で採点した平均値。スコアをクリックすると分類内訳を表示。",
    "riichi_recommended_rate": "分類上、リーチしてよい待ちに入った割合。",
    "riichi_not_recommended_rate": "分類上、リーチすべきでない待ちに入った割合。",
    "riichi_quality_top_category": "そのプレイヤーで最も多かったリーチ待ち分類。",
    "call_after_hu_rate": "副露した局のうち、自分が和了した割合。",
    "call_after_houjuu_rate": "副露した局のうち、自分が放銃した割合。",
    "two_called_rate": "参加局のうち、2副露以上した割合。",
    "two_called_hu_rate": "2副露以上した局のうち、自分が和了した割合。",
    "two_called_after_houjuu_rate": "2副露以上した局のうち、自分が放銃した割合。",
    "average_first_call_turn": "その局で最初に鳴いた巡目の平均。",
    "call_quality_score": "副露判断を点数・形・局面で採点した平均値。スコアをクリックすると分類内訳を表示。",
    "call_quality_top_category": "そのプレイヤーで最も多かった副露分類。",
    "open_tanyao_hu_rate": "和了のうち、喰いタンだった割合。",
    "chiitoi_hu_rate": "和了のうち、七対子だった割合。",
    "honitsu_hu_rate": "和了のうち、ホンイツだった割合。",
    "chinitsu_hu_rate": "和了のうち、チンイツだった割合。",
    "average_opening_shanten": "配牌から北を抜き切って1枚打牌した時点の平均シャンテン数。",
    "average_opening_dora": "配牌時の平均ドラ枚数。北抜きと赤ドラも含む。",
    "tsumo_loss_rate": "参加局のうち、他家のツモ和了で失点した割合。",
    "average_tsumo_loss_point": "他家のツモ和了で支払った点数の平均。",
    "max_final_point": "半荘終了時持ち点の最高値。",
    "min_final_point": "半荘終了時持ち点の最低値。",
    "yakuman_count": "役満を和了した回数。ダブル役満は別役扱い。",
    "mvp_count": "シーズン内の獲得スコアが1位だった回数。累計ページのみ表示。",
    "team_champion_count": "所属チームがシーズン優勝した回数。累計ページのみ表示。",
}


MAIN_COLUMNS = [
    "player",
    "games",
    "earned_score",
    "average_rank",
    "rank1_rate",
    "rank2_rate",
    "rank3_rate",
    "last_avoid_rate",
    "hu_rate",
    "average_hu_point",
    "average_called_hu_point",
    "open_tanyao_hu_rate",
    "chiitoi_hu_rate",
    "honitsu_hu_rate",
    "chinitsu_hu_rate",
    "houjuu_rate",
    "average_houjuu_point",
    "tsumo_loss_rate",
    "average_tsumo_loss_point",
    "called_houjuu_rate",
    "two_called_houjuu_rate",
    "called_haneman_houjuu_rate",
    "top_keep_rate",
    "first_tenpai_rate",
    "tenpai_keep_rate",
    "top_stay_rate",
    "second_stay_rate",
    "last_stay_rate",
    "late_noten_houjuu_rate",
    "late_noten_fresh_discard_rate",
    "winning_run_points",
    "tsumo_rate",
    "average_opening_shanten",
    "average_opening_dora",
    "called_rate",
    "riichi_rate",
    "riichi_miss_rate",
    "bad_shape_riichi_rate",
    "top_riichi_rate",
    "yakuman_count",
]


DETAIL_COLUMNS = [
    "player",
    "rounds",
    "average_hu_point",
    "average_called_hu_point",
    "average_houjuu_point",
    "tsumo_loss_rate",
    "average_tsumo_loss_point",
    "called_houjuu_rate",
    "two_called_houjuu_rate",
    "called_haneman_houjuu_rate",
    "top_keep_rate",
    "first_tenpai_rate",
    "tenpai_keep_rate",
    "top_stay_rate",
    "second_stay_rate",
    "last_stay_rate",
    "late_noten_houjuu_rate",
    "late_noten_fresh_discard_rate",
    "winning_run_points",
    "average_opening_shanten",
    "average_opening_dora",
    "max_final_point",
    "min_final_point",
]


PLAYER_MAIN_COLUMNS = [
    "player",
    "games",
    "earned_score",
    "average_rank",
    "rank1_rate",
    "rank2_rate",
    "rank3_rate",
    "last_avoid_rate",
    "hu_rate",
    "average_hu_point",
    "average_called_hu_point",
    "open_tanyao_hu_rate",
    "chiitoi_hu_rate",
    "honitsu_hu_rate",
    "chinitsu_hu_rate",
    "houjuu_rate",
    "average_houjuu_point",
    "tsumo_loss_rate",
    "average_tsumo_loss_point",
    "called_houjuu_rate",
    "two_called_houjuu_rate",
    "called_haneman_houjuu_rate",
    "top_keep_rate",
    "first_tenpai_rate",
    "tenpai_keep_rate",
    "top_stay_rate",
    "second_stay_rate",
    "last_stay_rate",
    "late_noten_houjuu_rate",
    "late_noten_fresh_discard_rate",
    "winning_run_points",
    "tsumo_rate",
    "called_rate",
    "riichi_rate",
    "riichi_miss_rate",
    "bad_shape_riichi_rate",
    "top_riichi_rate",
    "yakuman_count",
]


PLAYER_SEASON_COLUMNS = [
    "season",
    "games",
    "earned_score",
    "average_rank",
    "last_avoid_rate",
    "hu_rate",
    "average_hu_point",
    "average_called_hu_point",
    "open_tanyao_hu_rate",
    "chiitoi_hu_rate",
    "honitsu_hu_rate",
    "chinitsu_hu_rate",
    "houjuu_rate",
    "average_houjuu_point",
    "tsumo_loss_rate",
    "average_tsumo_loss_point",
    "called_houjuu_rate",
    "two_called_houjuu_rate",
    "called_haneman_houjuu_rate",
    "top_keep_rate",
    "first_tenpai_rate",
    "tenpai_keep_rate",
    "top_stay_rate",
    "second_stay_rate",
    "last_stay_rate",
    "tsumo_rate",
    "called_rate",
    "riichi_rate",
    "riichi_miss_rate",
    "bad_shape_riichi_rate",
    "top_riichi_rate",
    "yakuman_count",
]


PLAYER_RANK_METRICS = [
    ("earned_score", True, "高い方が上位"),
    ("average_rank", False, "低い方が上位"),
    ("rank1_rate", True, "高い方が上位"),
    ("last_avoid_rate", True, "高い方が上位"),
    ("hu_rate", True, "高い方が上位"),
    ("average_hu_point", True, "高い方が上位"),
    ("average_called_hu_point", True, "高い方が上位"),
    ("open_tanyao_hu_rate", True, "高い順"),
    ("chiitoi_hu_rate", True, "高い順"),
    ("honitsu_hu_rate", True, "高い順"),
    ("chinitsu_hu_rate", True, "高い順"),
    ("tsumo_rate", True, "高い方が上位"),
    ("tsumo_loss_rate", False, "低い方が上位"),
    ("average_tsumo_loss_point", False, "低い方が上位"),
    ("houjuu_rate", False, "低い方が上位"),
    ("average_houjuu_point", False, "低い方が上位"),
    ("noten_houjuu_rate", False, "低い方が上位"),
    ("two_shanten_houjuu_rate", False, "低い方が上位"),
    ("riichi_after_houjuu_rate", False, "低い方が上位"),
    ("vs_riichi_houjuu_rate", False, "低い方が上位"),
    ("vs_dama_houjuu_rate", False, "低い方が上位"),
    ("vs_called_houjuu_rate", False, "低い方が上位"),
    ("vs_two_called_houjuu_rate", False, "低い方が上位"),
    ("vs_haneman_houjuu_rate", False, "低い方が上位"),
    ("deal_in_quality_score", True, "高い方が上位"),
    ("called_houjuu_rate", False, "低い方が上位"),
    ("two_called_houjuu_rate", False, "低い方が上位"),
    ("called_haneman_houjuu_rate", False, "低い方が上位"),
    ("top_keep_rate", True, "高い方が上位"),
    ("first_tenpai_rate", True, "高い方が上位"),
    ("tenpai_keep_rate", True, "高い方が上位"),
    ("top_stay_rate", True, "高い方が上位"),
    ("second_stay_rate", True, "高い順"),
    ("last_stay_rate", False, "低い方が上位"),
    ("late_noten_houjuu_rate", False, "低い方が上位"),
    ("late_noten_fresh_discard_rate", False, "低い方が上位"),
    ("winning_run_points", True, "高い方が上位"),
    ("called_rate", True, "高い順"),
    ("call_after_hu_rate", True, "高い方が上位"),
    ("call_after_houjuu_rate", False, "低い方が上位"),
    ("two_called_rate", True, "高い順"),
    ("call_quality_score", True, "高い方が上位"),
    ("riichi_rate", True, "高い順"),
    ("riichi_miss_rate", False, "低い方が上位"),
    ("bad_shape_riichi_rate", False, "低い方が上位"),
    ("top_riichi_rate", True, "高い順"),
    ("yakuman_count", True, "高い方が上位"),
]


MAIN_RANK_COLUMNS = [
    "player",
    "games",
    "earned_score",
    "average_rank",
    "rank1_rate",
    "rank2_rate",
    "rank3_rate",
    "last_avoid_rate",
    "top_keep_rate",
    "top_stay_rate",
    "second_stay_rate",
    "last_stay_rate",
    "winning_run_points",
]


CUMULATIVE_RANK_COLUMNS = MAIN_RANK_COLUMNS + [
    "mvp_count",
    "team_champion_count",
]


MAIN_WIN_COLUMNS = [
    "player",
    "first_tenpai_rate",
    "tenpai_keep_rate",
    "hu_rate",
    "average_hu_point",
    "average_called_hu_point",
    "tsumo_rate",
    "tsumo_loss_rate",
    "average_tsumo_loss_point",
    "houjuu_rate",
    "average_houjuu_point",
    "late_noten_houjuu_rate",
    "late_noten_fresh_discard_rate",
    "called_rate",
    "riichi_rate",
    "riichi_miss_rate",
    "bad_shape_riichi_rate",
    "top_riichi_rate",
    "open_tanyao_hu_rate",
    "chiitoi_hu_rate",
    "honitsu_hu_rate",
    "chinitsu_hu_rate",
    "yakuman_count",
]


RIICHI_QUALITY_COLUMNS = [
    "player",
    "riichi",
    "riichi_quality_score",
    "riichi_recommended_rate",
    "riichi_not_recommended_rate",
    "riichi_quality_top_category",
]


CALL_QUALITY_COLUMNS = [
    "player",
    "called_rate",
    "call_after_hu_rate",
    "average_called_hu_point",
    "call_after_houjuu_rate",
    "two_called_rate",
    "two_called_hu_rate",
    "two_called_after_houjuu_rate",
    "average_first_call_turn",
    "call_quality_score",
    "call_quality_top_category",
]


DEAL_IN_QUALITY_COLUMNS = [
    "player",
    "houjuu_rate",
    "average_houjuu_point",
    "noten_houjuu_rate",
    "two_shanten_houjuu_rate",
    "riichi_after_houjuu_rate",
    "vs_riichi_houjuu_rate",
    "vs_dama_houjuu_rate",
    "vs_called_houjuu_rate",
    "vs_two_called_houjuu_rate",
    "vs_haneman_houjuu_rate",
    "late_noten_houjuu_share",
    "late_noten_fresh_discard_rate",
    "deal_in_quality_score",
    "deal_in_quality_top_category",
]


DIGEST_METRICS = [
    ("earned_score", True),
    ("average_rank", False),
    ("hu_rate", True),
    ("houjuu_rate", False),
    ("max_final_point", True),
    ("min_final_point", True),
]


DETAIL_RANK_COLUMNS = [
    "player",
    "rounds",
    "top_keep_rate",
    "top_stay_rate",
    "second_stay_rate",
    "last_stay_rate",
    "winning_run_points",
    "max_final_point",
    "min_final_point",
]


DETAIL_WIN_COLUMNS = [
    "player",
    "first_tenpai_rate",
    "tenpai_keep_rate",
    "average_hu_point",
    "average_called_hu_point",
    "average_houjuu_point",
    "tsumo_loss_rate",
    "average_tsumo_loss_point",
    "called_houjuu_rate",
    "two_called_houjuu_rate",
    "called_haneman_houjuu_rate",
    "late_noten_houjuu_rate",
    "late_noten_fresh_discard_rate",
    "average_opening_shanten",
    "average_opening_dora",
]


PLAYER_RANK_COLUMNS = [
    "player",
    "games",
    "earned_score",
    "average_rank",
    "rank1_rate",
    "rank2_rate",
    "rank3_rate",
    "last_avoid_rate",
    "top_keep_rate",
    "top_stay_rate",
    "second_stay_rate",
    "last_stay_rate",
    "winning_run_points",
]


PLAYER_WIN_COLUMNS = [
    "player",
    "first_tenpai_rate",
    "tenpai_keep_rate",
    "hu_rate",
    "average_hu_point",
    "average_called_hu_point",
    "tsumo_rate",
    "tsumo_loss_rate",
    "average_tsumo_loss_point",
    "houjuu_rate",
    "average_houjuu_point",
    "late_noten_houjuu_rate",
    "late_noten_fresh_discard_rate",
    "called_rate",
    "riichi_rate",
    "riichi_miss_rate",
    "bad_shape_riichi_rate",
    "top_riichi_rate",
    "open_tanyao_hu_rate",
    "chiitoi_hu_rate",
    "honitsu_hu_rate",
    "chinitsu_hu_rate",
    "yakuman_count",
]


PLAYER_RIICHI_QUALITY_COLUMNS = [
    "player",
    "season",
    "riichi",
    "riichi_quality_score",
    "riichi_recommended_rate",
    "riichi_not_recommended_rate",
    "riichi_quality_top_category",
]


PLAYER_CALL_QUALITY_COLUMNS = [
    "player",
    "season",
    "called_rate",
    "call_after_hu_rate",
    "average_called_hu_point",
    "call_after_houjuu_rate",
    "two_called_rate",
    "two_called_hu_rate",
    "two_called_after_houjuu_rate",
    "average_first_call_turn",
    "call_quality_score",
    "call_quality_top_category",
]


PLAYER_DEAL_IN_QUALITY_COLUMNS = [
    "player",
    "season",
    "houjuu_rate",
    "average_houjuu_point",
    "noten_houjuu_rate",
    "two_shanten_houjuu_rate",
    "riichi_after_houjuu_rate",
    "vs_riichi_houjuu_rate",
    "vs_dama_houjuu_rate",
    "vs_called_houjuu_rate",
    "vs_two_called_houjuu_rate",
    "vs_haneman_houjuu_rate",
    "late_noten_houjuu_share",
    "deal_in_quality_score",
    "deal_in_quality_top_category",
]


PLAYER_SEASON_RANK_COLUMNS = [
    "season",
    "games",
    "earned_score",
    "average_rank",
    "last_avoid_rate",
    "top_keep_rate",
    "top_stay_rate",
    "second_stay_rate",
    "last_stay_rate",
    "winning_run_points",
]


PLAYER_SEASON_WIN_COLUMNS = [
    "season",
    "first_tenpai_rate",
    "tenpai_keep_rate",
    "hu_rate",
    "average_hu_point",
    "average_called_hu_point",
    "tsumo_rate",
    "tsumo_loss_rate",
    "average_tsumo_loss_point",
    "houjuu_rate",
    "average_houjuu_point",
    "called_houjuu_rate",
    "two_called_houjuu_rate",
    "called_haneman_houjuu_rate",
    "late_noten_houjuu_rate",
    "late_noten_fresh_discard_rate",
    "called_rate",
    "riichi_rate",
    "riichi_miss_rate",
    "bad_shape_riichi_rate",
    "top_riichi_rate",
    "open_tanyao_hu_rate",
    "chiitoi_hu_rate",
    "honitsu_hu_rate",
    "chinitsu_hu_rate",
    "yakuman_count",
]


MANUAL_PLAYER_ANALYSIS: dict[str, tuple[str, str, str]] = {
    "流れ者金融": (
        "累計トップの支配型。獲得スコア4,780.3、平均順位1.85は依然リーグ唯一の1.8台で、シーズン8には単季1,189.2・平均1.65・1位率57%という完全支配も見せた別格の軸。和了率32.33%、副露率35.29%、先制テンパイ率35.16%、テンパイ維持率21.56%と、門前でも副露でもどの入口からでも局に触れ、トップ滞在率45.44%で半荘の長い時間をリード側で進める。ただし直近シーズン10は初の単季マイナス(-54.0)・平均順位1.98で、シーズン1から続いた9季連続プラスが途切れた。",
        "強みは、攻撃量の多さと放銃の軽さの同居。これだけ局参加して放銃率15.11%・放銃平均8,803点はリーグ2番手の軽さで、放銃の質スコア-2.75はリーグで最も0に近い＝『刺さっても仕方ない放銃』で収まっている。リーチの質もリーチ可率84.61%・平均スコア2.95で上位、鳴き質スコア-0.11も最良級、トップキープ率36.36%はリーグ最高。押す局・曲げる局の選別が数字に出ており、リードしてからも局を終わらせに行くトップ。累計の全項目上位という土台はシーズン10でも崩れていない。",
        "シーズン10のマイナスは『運が悪かっただけ』か——概ねそう読める。この季に落ちたのは主にラス回避率で、累計73.70%に対しシーズン10は66.07%と自己ワースト級まで沈み、和了率も30.11%と過去最低だった。配牌の重さも、リーチ後におっかけられて掴まされる放銃も、巡り合わせ側の要因が大きく、リーチ質・放銃質・累計成績はいずれも最上位のまま。プロセスが最上位級のまま単季だけ沈むのは実力低下より分散のブレで、来季は放っておいても戻りやすい。唯一の伸びしろは、悪配牌の局と着順ビハインドでの撤退をあと一段だけ早め、良い季と悪い季の振れ幅そのものを縮めること。",
    ),
    "ひなんじょ": (
        "門前圧力型で、プラス域の2番手(獲得スコア1,190.7、平均順位1.97、1位率35.64%)。立直率31.15%はリーグ最多クラスで、自分からテンパイを入れてリーチで場を縛る。先制テンパイ率33.04%、テンパイ維持率20.66%、トップ滞在率41.63%と勝負どころでトップ目に立つ力は十分。季ごとの上下は大きいタイプだが、直近はシーズン9(+406.2)・シーズン10(+207.0)と2季連続プラスで、ここ最近はブレを抑えて浮かせられている。",
        "強みは、リーチを中心にした収入設計。リーチ率が高いのに和了率30.81%を保ち、平均和了点10,668点はリーグ最高で、ただ曲げるだけでなく収入のあるテンパイに到達できている。鳴き質スコア0.05はリーグ最良で、副露も速度・テンパイ補助として機能。リーチ質も平均スコア2.79・リーチ可率79.75%と、数を打ちながら質を保つ。シーズン10はラス回避率72.06%と累計(67.23%)より高く、負けても沈み方を浅く抑えられたのは好材料。",
        "改善点は、テンパイ前後の危険牌処理。放銃率16.88%・放銃平均9,412点はやや重く、良形へ向かう途中の失点が膨らみやすい。リーチ本数を減らすより、一向聴で親の濃い仕掛けに押す局、ドラが見えない終盤、2着目でトップが遠い局の押しを削る方が効く。課題はアクセルではなくブレーキ位置。単季で見ると±の振れが大きく、負けた季(シーズン5 -347.4、シーズン8 -128.9)はいずれも放銃過多が主因なので、沈む半荘の放銃を1つ減らせればトップ争いへさらに寄る。",
    ),
    "鯛ofカルピス": (
        "自力決着型。獲得スコア719.9・和了率31.69%でプラス。先制テンパイ率36.28%、テンパイ維持率22.62%はどちらもリーグ最高で、誰よりも早くテンパイし長く維持する。立直率24.15%は控えめで、テンパイ量の多さはリーチ乱発ではなくダマ・副露・押し返しを含む手牌進行の速さ由来。トップ滞在率40.98%、トップキープ率31.04%と先行時の押し切りも効く。シーズン8の不振(-306.7)からシーズン9(+304.7)・シーズン10(+100.2)と2季連続で立て直しており、直近は上向き。",
        "強みは、局を自力で終わらせに行く力。テンパイ維持率が高いので押し返されても完全撤退に回りにくく、流局まで相手に圧を残せる。リーチ質は平均スコア2.96・リーチ可率81.78%で曲げる局もよく選べ、和了率31.69%に対し平均和了点10,243点も十分。注目は防御面の改善で、かつて18〜20%あった放銃率を直近はシーズン9 16.53%・シーズン10 16.46%まで下げており、以前指摘された押しすぎの温度管理が結果に出始めている。",
        "残る改善点も同じ方向。累計放銃率17.98%はまだリーグで最も重い部類で、テンパイ維持率の高さがそのまま押しすぎに繋がりやすい。終盤の愚形・安手・残りツモの薄いテンパイ、親リーチ、ドラ周辺、明らかな高打点副露に対しては、直近で見せている『一段冷やす』判断を全季に定着させたい。攻撃を弱める必要はなく、非テンパイや価値の低いテンパイでの放銃をさらに減らせれば、最高クラスの先制力がそのまま順位に変わる。",
    ),
    "アリスkey": (
        "急上昇中の伸び盛り。累計は獲得スコア-369.0・平均順位1.99とまだマイナスだが、これはシーズン1〜5の負債(特にシーズン5 -650.2)を引きずったもので、実態は直近ほど強い。極めつけがシーズン10で、単季スコア+629.3・平均順位1.78・1位率45.31%・ラス回避率76.56%といずれもその季のリーグ最高。和了率も33.38%まで伸び、累計29.51%を大きく上回った。負けない土台の上に、ついに勝ち切る形が乗ってきたシーズンだった。",
        "強みは、局参加の柔軟さと守備の堅さの両立。鳴きで速度を作れるし立直率27.09%で門前も残す。累計放銃率15.37%はリーグ2〜3番手の軽さで、テンパイ維持率20.44%・ラス滞在率28.33%の低さもあって崩れにくい。もともと『負けない土台』は完成しており、直近はそれを得点力へ変換できている点が最大の変化。トップ滞在率40.14%をトップキープ率26.03%へ結び付ける課題も、シーズン10のトップキープ率41.30%を見る限り克服しつつある。",
        "改善点は、シーズン10の再現性を『単季の当たり年』で終わらせないこと。累計ではリーチ非推奨率22.28%がやや高く、押す局に余計な勝負が混ざる癖、鳴き質スコア-0.21という鳴き後の打点・テンパイ形の甘さも残る。トップ目では安い愚形リーチや遠い仕掛けを抑え、2着目や親ビハインドでは良形・高打点ルートを逃さない——この選別を続けられれば、累計スコアのマイナスもそう遠くないうちにプラス転換が見えてくる。",
    ),
    "29ちゃん": (
        "守備基盤型。放銃率14.73%はリーグ最少、放銃平均9,015点も軽めで、三麻でこの失点管理は価値が高い。一方で獲得スコア-1,598.9、平均順位2.04、和了率26.98%、副露率27.42%、立直率23.03%、テンパイ維持率18.36%はいずれも控えめ。守れてはいるが局を先に取りに行く量が足りず、守備力をスコアへ変換しきれていない。ただ和了率は初期の24〜27%から直近は上向きで、シーズン9は+179.9・平均1.90と、攻撃量が増えた季にはしっかり勝てることを示した。",
        "強みは、半荘を壊さない我慢とリーチ選別の丁寧さ。低放銃でも打点は落ちておらず平均和了点10,420点は高い。リーチ質は平均スコア3.00・リーチ可率81.83%でリーグ最上位級、待ちや打点の選別は誰よりも丁寧。だからこそ課題はリーチの質ではなく、先制テンパイ率30.76%・テンパイ維持率18.36%という到達回数と継続時間にある。シーズン9のように和了率が30%近くまで届くと即座に成績が反応するので、伸びしろは明確に攻撃側。",
        "改善点は、親番と南場ビハインド時の攻撃量。序盤の良形・役牌対子・ドラ周辺はもう少し前向きに残してよい。特に親番で先制できる一向聴、ラス目南場で打点がある手、2着目からトップを狙える局では、安牌を抱えすぎず手牌効率を優先したい。守備力があるので攻撃を増やしても大事故にはなりにくい。シーズン9(和了率29.88%→プラス)とシーズン10(28.55%→マイナス)の差が示す通り、和了率をあと1〜2ポイント上げて維持できれば、低放銃という長所がそのまま累計スコアに変わる。",
    ),
    "葡萄海ぶどう": (
        "高打点志向のロマン砲型。平均和了点10,601点・リーチ率29.83%で和了時の破壊力は十分だが、獲得スコア-4,723.0、平均順位2.14、和了率26.39%、ラス回避率59.11%、ラス滞在率33.51%とリーグで最も苦しい。先制テンパイ率30.67%・テンパイ維持率19.18%も下位で、高い手を狙う意識に対しテンパイまでの速度と継続時間が足りない。直近はシーズン9が底(-1,252.4・平均2.33・ラス回避46.97%)、シーズン10は-649.6・ラス回避51.92%とやや戻したが、依然マイナス最下位。",
        "強みは、打点ルートを見つけた時の押し切り力。七対子・ホンイツ・リーチ高打点を選べるので、細かく刻むより一撃の大物手で着順を変える麻雀。平均和了点はリーグ上位で、噛み合えば一発で着順が動く(好調だったシーズン5は+315.7・平均1.93)。放銃の質スコア-2.92は極端に悪いわけではなく、全てが無謀な押しというより、テンパイが遅れて押し返す局が増えた結果の苦しい放銃が混ざる印象。個性そのものを消す必要はない。",
        "改善点は、勝負手でない局の撤退速度と重い手を追う基準。累計リーチ非推奨率25.61%が高く、和了率が低いわりに放銃率17.24%が重い。打点種の薄い配牌、親の速い仕掛け、南場で2着を守れば十分な局では、満貫ルートを無理に追わず速度か守備に寄せたい。鳴き質スコア-0.37も最下位で、鳴き後の形・打点が足りない仕掛けが混ざる。放銃率はシーズン10で16.70%とやや改善の兆しがあるので、これを定着させつつ先制テンパイ率を上げれば、ラス回避率59.11%の底上げに直結する。",
    ),
}


def read_csv(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def esc(value: object) -> str:
    return html.escape(str(value), quote=True)


def number(value: str | int | float, digits: int = 0) -> str:
    try:
        n = float(value)
    except (TypeError, ValueError):
        return esc(value)
    if digits:
        return f"{n:,.{digits}f}"
    return f"{int(round(n)):,}"


def pct_number(value: str) -> float:
    try:
        return float(value.replace("%", ""))
    except (TypeError, ValueError):
        return 0.0


def metric_value(row: dict[str, str], col: str) -> float:
    value = row.get(col, "")
    if isinstance(value, str) and value.endswith("%"):
        return pct_number(value)
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def format_cell_value(col: str, value: str | int | float) -> str:
    if col == "earned_score":
        return number(value, 1)
    if col in {"riichi_quality_score", "call_quality_score", "deal_in_quality_score"}:
        return number(value, 2)
    if col == "average_first_call_turn":
        return number(value, 1)
    if col in {"average_opening_shanten", "average_opening_dora"}:
        return number(value, 2)
    if col in {
        "average_hu_point",
        "average_called_hu_point",
        "average_houjuu_point",
        "average_tsumo_loss_point",
        "max_final_point",
        "min_final_point",
        "winning_run_points",
    }:
        return number(value)
    return esc(value)


def metric_rank(rows: list[dict[str, str]], player: str, col: str, reverse: bool) -> tuple[int, int]:
    ranked_values = sorted(
        {metric_value(row, col) for row in rows},
        reverse=reverse,
    )
    player_row = next((row for row in rows if row.get("player") == player), None)
    if not player_row:
        return 0, len(rows)
    value = metric_value(player_row, col)
    rank = ranked_values.index(value) + 1 if value in ranked_values else 0
    return rank, len(rows)


def metric_popup_html(col: str) -> str:
    description = METRIC_DESCRIPTIONS.get(col, "")
    if col == "riichi_quality_score":
        table_html = riichi_quality_definition_table()
    elif col == "call_quality_score":
        table_html = call_quality_definition_table()
    elif col == "deal_in_quality_score":
        table_html = deal_in_quality_definition_table()
    else:
        return ""
    if not table_html:
        return ""
    return f"<p>{esc(description)}</p>{table_html}"


def percent_text(numerator: int, denominator: int) -> str:
    if denominator <= 0:
        return "0.0%"
    return f"{numerator / denominator * 100:.1f}%"


def parse_riichi_quality_breakdown(value: str) -> dict[str, int]:
    counts = {}
    for part in (value or "").split("|"):
        if ":" not in part:
            continue
        key, raw_count = part.split(":", 1)
        try:
            counts[key] = int(raw_count)
        except ValueError:
            continue
    return counts


def riichi_quality_breakdown_table(row: dict[str, str]) -> str:
    try:
        from aggregate_league import RIICHI_QUALITY_CATEGORIES, RIICHI_QUALITY_SCORE
    except Exception:
        return ""

    counts = parse_riichi_quality_breakdown(row.get("riichi_quality_breakdown", ""))
    total = sum(counts.values())
    if not counts or total <= 0:
        return "<p>分類内訳はありません。</p>"

    body_rows = []
    for key, label, recommended in RIICHI_QUALITY_CATEGORIES:
        count = counts.get(key, 0)
        if not count:
            continue
        body_rows.append(
            "<tr>"
            f"<td class=\"name\">{esc(label)}</td>"
            f"<td>{count}</td>"
            f"<td>{percent_text(count, total)}</td>"
            f"<td>{esc(RIICHI_QUALITY_SCORE.get(key, ''))}</td>"
            f"<td>{'リーチ可' if recommended else '非推奨'}</td>"
            "</tr>"
        )

    head = "<th>分類</th><th>回数</th><th>割合</th><th>スコア</th><th>判定</th>"
    return (
        "<h3>分類内訳</h3>"
        "<div class=\"table-wrap quality-breakdown\">"
        f"<table><thead><tr>{head}</tr></thead><tbody>{''.join(body_rows)}</tbody></table>"
        "</div>"
    )


def riichi_quality_score_cell(row: dict[str, str]) -> str:
    score = format_cell_value("riichi_quality_score", row.get("riichi_quality_score", ""))
    if not row.get("riichi_quality_breakdown"):
        return score
    subject = row.get("player") or row.get("season") or "リーチ質"
    popup_html = (
        "<p>この行のリーチを待ち分類ごとに分解した内訳です。</p>"
        f"{riichi_quality_breakdown_table(row)}"
        "<h3>配点表</h3>"
        f"{riichi_quality_definition_table()}"
    )
    return (
        f"<button class=\"metric-value-help\" type=\"button\" "
        f"data-metric-title=\"{esc(subject)} リーチ質内訳\" "
        f"data-metric-html=\"{esc(popup_html)}\">{score}</button>"
    )


def parse_call_quality_breakdown(value: str) -> dict[str, int]:
    counts = {}
    for part in (value or "").split("|"):
        if ":" not in part:
            continue
        key, raw_count = part.split(":", 1)
        try:
            counts[key] = int(raw_count)
        except ValueError:
            continue
    return counts


def call_quality_definition_table() -> str:
    try:
        from aggregate_league import CALL_QUALITY_CATEGORIES, CALL_QUALITY_SCORE
    except Exception:
        return ""

    body = []
    for key, label in CALL_QUALITY_CATEGORIES:
        body.append(
            "<tr>"
            f"<td>{esc(CALL_QUALITY_SCORE[key])}</td>"
            f"<td class=\"name\">{esc(label)}</td>"
            "</tr>"
        )
    head = "<th>スコア</th><th>分類</th>"
    return f"<div class=\"table-wrap quality-def\"><table><thead><tr>{head}</tr></thead><tbody>{''.join(body)}</tbody></table></div>"


def call_quality_breakdown_table(row: dict[str, str]) -> str:
    try:
        from aggregate_league import CALL_QUALITY_CATEGORIES, CALL_QUALITY_SCORE
    except Exception:
        return ""

    counts = parse_call_quality_breakdown(row.get("call_quality_breakdown", ""))
    total = sum(counts.values())
    if not counts or total <= 0:
        return "<p>分類内訳はありません。</p>"

    body_rows = []
    for key, label in CALL_QUALITY_CATEGORIES:
        count = counts.get(key, 0)
        if not count:
            continue
        body_rows.append(
            "<tr>"
            f"<td class=\"name\">{esc(label)}</td>"
            f"<td>{count}</td>"
            f"<td>{percent_text(count, total)}</td>"
            f"<td>{esc(CALL_QUALITY_SCORE.get(key, ''))}</td>"
            "</tr>"
        )

    head = "<th>分類</th><th>回数</th><th>割合</th><th>スコア</th>"
    return (
        "<h3>分類内訳</h3>"
        "<div class=\"table-wrap quality-breakdown\">"
        f"<table><thead><tr>{head}</tr></thead><tbody>{''.join(body_rows)}</tbody></table>"
        "</div>"
    )


def call_quality_score_cell(row: dict[str, str]) -> str:
    score = format_cell_value("call_quality_score", row.get("call_quality_score", ""))
    if not row.get("call_quality_breakdown"):
        return score
    subject = row.get("player") or row.get("season") or "鳴き質"
    popup_html = (
        "<p>この行の副露を分類ごとに分解した内訳です。複合条件は重複して数えています。</p>"
        f"{call_quality_breakdown_table(row)}"
        "<h3>配点表</h3>"
        f"{call_quality_definition_table()}"
    )
    return (
        f"<button class=\"metric-value-help\" type=\"button\" "
        f"data-metric-title=\"{esc(subject)} 鳴き質内訳\" "
        f"data-metric-html=\"{esc(popup_html)}\">{score}</button>"
    )


def parse_deal_in_quality_breakdown(value: str) -> dict[str, int]:
    counts = {}
    for part in (value or "").split("|"):
        if ":" not in part:
            continue
        key, raw_count = part.split(":", 1)
        try:
            counts[key] = int(raw_count)
        except ValueError:
            continue
    return counts


def deal_in_quality_definition_table() -> str:
    try:
        from aggregate_league import DEAL_IN_QUALITY_CATEGORIES, DEAL_IN_QUALITY_SCORE
    except Exception:
        return ""

    body = []
    for key, label in DEAL_IN_QUALITY_CATEGORIES:
        body.append(
            "<tr>"
            f"<td>{esc(DEAL_IN_QUALITY_SCORE[key])}</td>"
            f"<td class=\"name\">{esc(label)}</td>"
            "</tr>"
        )
    head = "<th>スコア</th><th>分類</th>"
    return f"<div class=\"table-wrap quality-def\"><table><thead><tr>{head}</tr></thead><tbody>{''.join(body)}</tbody></table></div>"


def deal_in_quality_breakdown_table(row: dict[str, str]) -> str:
    try:
        from aggregate_league import DEAL_IN_QUALITY_CATEGORIES, DEAL_IN_QUALITY_SCORE
    except Exception:
        return ""

    counts = parse_deal_in_quality_breakdown(row.get("deal_in_quality_breakdown", ""))
    total = sum(counts.values())
    if not counts or total <= 0:
        return "<p>分類内訳はありません。</p>"

    body_rows = []
    for key, label in DEAL_IN_QUALITY_CATEGORIES:
        count = counts.get(key, 0)
        if not count:
            continue
        body_rows.append(
            "<tr>"
            f"<td class=\"name\">{esc(label)}</td>"
            f"<td>{count}</td>"
            f"<td>{percent_text(count, total)}</td>"
            f"<td>{esc(DEAL_IN_QUALITY_SCORE.get(key, ''))}</td>"
            "</tr>"
        )

    head = "<th>分類</th><th>回数</th><th>割合</th><th>スコア</th>"
    return (
        "<h3>分類内訳</h3>"
        "<div class=\"table-wrap quality-breakdown\">"
        f"<table><thead><tr>{head}</tr></thead><tbody>{''.join(body_rows)}</tbody></table>"
        "</div>"
    )


def deal_in_quality_score_cell(row: dict[str, str]) -> str:
    score = format_cell_value("deal_in_quality_score", row.get("deal_in_quality_score", ""))
    if not row.get("deal_in_quality_breakdown"):
        return score
    subject = row.get("player") or row.get("season") or "放銃質"
    popup_html = (
        "<p>この行のロン放銃を分類ごとに分解した内訳です。複合条件は重複して数えています。</p>"
        f"{deal_in_quality_breakdown_table(row)}"
        "<h3>配点表</h3>"
        f"{deal_in_quality_definition_table()}"
    )
    return (
        f"<button class=\"metric-value-help\" type=\"button\" "
        f"data-metric-title=\"{esc(subject)} 放銃質内訳\" "
        f"data-metric-html=\"{esc(popup_html)}\">{score}</button>"
    )


def header_cell(col: str) -> str:
    label = esc(LABELS.get(col, col))
    description = METRIC_DESCRIPTIONS.get(col)
    if col == "rank":
        th_class = ' class="sticky-rank"'
    elif col == "player":
        th_class = ' class="sticky-name"'
    else:
        th_class = ""
    if not description:
        return f"<th{th_class}>{label}</th>"
    popup_html = metric_popup_html(col)
    body_attr = (
        f"data-metric-html=\"{esc(popup_html)}\""
        if popup_html
        else f"data-metric-body=\"{esc(description)}\""
    )
    return (
        f"<th{th_class}>"
        f"<button class=\"metric-help\" type=\"button\" data-metric-title=\"{label}\" "
        f"{body_attr} aria-label=\"{label}の説明を開く\">"
        f"{label}<span aria-hidden=\"true\">?</span>"
        "</button>"
        "</th>"
    )


def table(
    rows: list[dict[str, str]],
    columns: list[str],
    rank_by: str | None = None,
    reverse: bool = False,
) -> str:
    if rank_by:
        ranked = sorted(rows, key=lambda r: float(r.get(rank_by, "0") or 0), reverse=reverse)
    else:
        ranked = rows

    head = "".join(header_cell(c) for c in (["rank"] + columns if rank_by else columns))
    body_rows = []
    for i, row in enumerate(ranked, 1):
        cells = []
        if rank_by:
            cells.append(f"<td class=\"sticky-rank\">{i}</td>")
        for col in columns:
            value = row.get(col, "")
            cls = "name sticky-name" if col == "player" else ""
            if col == "riichi_quality_score":
                value = riichi_quality_score_cell(row)
            elif col == "call_quality_score":
                value = call_quality_score_cell(row)
            elif col == "deal_in_quality_score":
                value = deal_in_quality_score_cell(row)
            else:
                value = format_cell_value(col, value)
            cells.append(f"<td class=\"{cls}\">{value}</td>")
        body_rows.append("<tr>" + "".join(cells) + "</tr>")
    return f"<table><thead><tr>{head}</tr></thead><tbody>{''.join(body_rows)}</tbody></table>"


def riichi_quality_table(rows: list[dict[str, str]]) -> str:
    ordered = sorted(
        rows,
        key=lambda row: metric_value(row, "riichi_quality_score"),
        reverse=True,
    )
    return table(ordered, RIICHI_QUALITY_COLUMNS, rank_by="riichi_quality_score", reverse=True)


def call_quality_table(rows: list[dict[str, str]]) -> str:
    ordered = sorted(
        rows,
        key=lambda row: metric_value(row, "call_quality_score"),
        reverse=True,
    )
    return table(ordered, CALL_QUALITY_COLUMNS, rank_by="call_quality_score", reverse=True)


def deal_in_quality_table(rows: list[dict[str, str]]) -> str:
    ordered = sorted(
        rows,
        key=lambda row: metric_value(row, "deal_in_quality_score"),
        reverse=True,
    )
    return table(ordered, DEAL_IN_QUALITY_COLUMNS, rank_by="deal_in_quality_score", reverse=True)


def riichi_quality_definition_table() -> str:
    try:
        from aggregate_league import RIICHI_QUALITY_CATEGORIES, RIICHI_QUALITY_SCORE
    except Exception:
        return ""

    rows = []
    for key, label, recommended in RIICHI_QUALITY_CATEGORIES:
        rows.append(
            {
                "score": str(RIICHI_QUALITY_SCORE[key]),
                "category": label,
                "judgement": "リーチ可" if recommended else "非推奨",
            }
        )

    head = "<th>スコア</th><th>分類</th><th>判定</th>"
    body = "".join(
        "<tr>"
        f"<td>{esc(row['score'])}</td>"
        f"<td class=\"name\">{esc(row['category'])}</td>"
        f"<td>{esc(row['judgement'])}</td>"
        "</tr>"
        for row in rows
    )
    return f"<div class=\"table-wrap quality-def\"><table><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table></div>"


def split_tables(
    rows: list[dict[str, str]],
    groups: list[tuple[str, list[str]]],
    rank_by: str | None = None,
    reverse: bool = False,
) -> str:
    blocks = []
    for title, columns in groups:
        blocks.append(
            f"""
            <section class="stat-table-panel">
              <h3>{esc(title)}</h3>
              <div class="table-wrap">
                {table(rows, columns, rank_by=rank_by, reverse=reverse)}
              </div>
            </section>
            """
        )
    return f"<div class=\"split-tables\">{''.join(blocks)}</div>"


def read_team_members() -> dict[int, dict[str, list[str]]]:
    rows = read_csv(TEAM_CSV)
    teams: dict[int, dict[str, list[str]]] = defaultdict(lambda: defaultdict(list))
    for row in rows:
        season = row.get("season", "").strip()
        team = row.get("team", "").strip()
        player = row.get("player", "").strip()
        if not season.isdigit() or not team or not player:
            continue
        members = teams[int(season)][team]
        if player not in members:
            members.append(player)
    return teams


def build_team_rows(rows: list[dict[str, str]], season_teams: dict[str, list[str]]) -> list[dict[str, object]]:
    by_player = {row["player"]: row for row in rows}
    team_rows = []
    for team, members in sorted(season_teams.items()):
        member_details = []
        total_score = 0.0
        total_games = 0
        for player in members:
            row = by_player.get(player)
            if not row:
                member_details.append(f"{player}: 未出場")
                continue
            score = float(row.get("earned_score", 0) or 0)
            total_score += score
            total_games += int(row.get("games", 0) or 0)
            member_details.append(
                f"{player}: {number(score, 1)} / 平均{row.get('average_rank', '-')}"
            )
        team_rows.append(
            {
                "team": team,
                "members": " / ".join(members),
                "member_details": " / ".join(member_details),
                "total_score": round(total_score, 1),
                "total_games": total_games,
            }
        )
    return sorted(team_rows, key=lambda row: (-float(row["total_score"]), str(row["team"])))


def team_section(team_rows: list[dict[str, object]]) -> str:
    if not TEAM_CSV.exists():
        return (
            "<p class=\"empty\">team_members.csv が未設定です。"
            "season,team,player の列でチーム割り当てを入れると表示されます。</p>"
        )
    if not team_rows:
        return "<p class=\"empty\">このシーズンのチーム割り当てがありません。</p>"

    body = []
    for i, row in enumerate(team_rows, 1):
        body.append(
            "<tr>"
            f"<td class=\"sticky-rank\">{i}</td>"
            f"<td class=\"name sticky-name\">{esc(row['team'])}</td>"
            f"<td class=\"roles\">{esc(row['members'])}</td>"
            f"<td class=\"roles\">{esc(row['member_details'])}</td>"
            f"<td>{number(row['total_score'], 1)}</td>"
            f"<td>{number(row['total_games'])}</td>"
            "</tr>"
        )
    return (
        "<div class=\"table-wrap\">"
        "<table class=\"team-table\">"
        "<thead><tr><th class=\"sticky-rank\">チーム順位</th><th class=\"sticky-name\">チーム</th><th>メンバー</th><th>単体成績</th><th>合計成績</th><th>合計対戦数</th></tr></thead>"
        f"<tbody>{''.join(body)}</tbody></table>"
        "</div>"
    )


def team_champion_rows(season_contexts: list[dict[str, object]]) -> list[dict[str, object]]:
    grouped: dict[str, dict[str, object]] = defaultdict(
        lambda: {"wins": 0, "seasons": [], "members": set()}
    )
    for context in season_contexts:
        team_rows = list(context.get("team_rows", []))
        if not team_rows:
            continue
        champion = team_rows[0]
        season_label = context.get("label", "")
        members = str(champion.get("members", "")).split(" / ")
        for player in members:
            if not player:
                continue
            grouped[player]["wins"] = int(grouped[player]["wins"]) + 1
            grouped[player]["seasons"].append(str(season_label))
            grouped[player]["members"].add(str(champion.get("team", "")))

    rows = []
    for player, data in grouped.items():
        rows.append(
            {
                "player": player,
                "wins": int(data["wins"]),
                "seasons": " / ".join(data["seasons"]),
                "teams": " / ".join(sorted(data["members"])),
            }
        )
    return sorted(rows, key=lambda row: (-int(row["wins"]), row["player"]))


def team_champion_section(rows: list[dict[str, object]]) -> str:
    if not TEAM_CSV.exists():
        return (
            "<p class=\"empty\">team_members.csv が未設定です。"
            "チーム優勝経験はチーム割り当て入力後に表示されます。</p>"
        )
    if not rows:
        return "<p class=\"empty\">チーム優勝経験の集計対象がありません。</p>"

    body = []
    for i, row in enumerate(rows, 1):
        body.append(
            "<tr>"
            f"<td class=\"sticky-rank\">{i}</td>"
            f"<td class=\"name sticky-name\">{esc(row['player'])}</td>"
            f"<td>{esc(row['wins'])}</td>"
            f"<td class=\"roles\">{esc(row['seasons'])}</td>"
            f"<td class=\"roles\">{esc(row['teams'])}</td>"
            "</tr>"
        )
    return (
        "<div class=\"table-wrap\">"
        "<table class=\"team-table\">"
        "<thead><tr><th class=\"sticky-rank\">順位</th><th class=\"sticky-name\">プレイヤー</th><th>チーム優勝回数</th><th>優勝シーズン</th><th>優勝チーム</th></tr></thead>"
        f"<tbody>{''.join(body)}</tbody></table>"
        "</div>"
    )


def season_mvp_rows(season_contexts: list[dict[str, object]]) -> list[dict[str, object]]:
    grouped: dict[str, dict[str, object]] = defaultdict(
        lambda: {"wins": 0, "details": []}
    )
    for context in season_contexts:
        rows = list(context.get("rows", []))
        if not rows:
            continue

        best_score = max(float(row.get("earned_score", 0) or 0) for row in rows)
        season_label = str(context.get("label", ""))
        for row in rows:
            score = float(row.get("earned_score", 0) or 0)
            if score != best_score:
                continue
            player = row.get("player", "")
            if not player:
                continue
            grouped[player]["wins"] = int(grouped[player]["wins"]) + 1
            grouped[player]["details"].append(f"{season_label}: {number(score, 1)}")

    rows = []
    for player, data in grouped.items():
        rows.append(
            {
                "player": player,
                "wins": int(data["wins"]),
                "details": " / ".join(data["details"]),
            }
        )
    return sorted(rows, key=lambda row: (-int(row["wins"]), row["player"]))


def season_mvp_section(rows: list[dict[str, object]]) -> str:
    if not rows:
        return "<p class=\"empty\">シーズンMVPの集計対象がありません。</p>"

    body = []
    for i, row in enumerate(rows, 1):
        body.append(
            "<tr>"
            f"<td class=\"sticky-rank\">{i}</td>"
            f"<td class=\"name sticky-name\">{esc(row['player'])}</td>"
            f"<td>{esc(row['wins'])}</td>"
            f"<td class=\"roles\">{esc(row['details'])}</td>"
            "</tr>"
        )
    return (
        "<div class=\"table-wrap\">"
        "<table class=\"team-table\">"
        "<thead><tr><th class=\"sticky-rank\">順位</th><th class=\"sticky-name\">プレイヤー</th><th>MVP回数</th><th>内訳</th></tr></thead>"
        f"<tbody>{''.join(body)}</tbody></table>"
        "</div>"
    )


def add_cumulative_awards(
    context: dict[str, object],
    mvp_rows: list[dict[str, object]],
    team_champion_rows: list[dict[str, object]],
) -> None:
    mvp_counts = {
        str(row.get("player", "")): str(row.get("wins", 0))
        for row in mvp_rows
    }
    team_counts = {
        str(row.get("player", "")): str(row.get("wins", 0))
        for row in team_champion_rows
    }

    for row in list(context.get("rows", [])):
        player = row.get("player", "")
        row["mvp_count"] = mvp_counts.get(player, "0")
        row["team_champion_count"] = team_counts.get(player, "0")


def digest_cards(rows: list[dict[str, str]]) -> str:
    cards = []
    for row in sorted(rows, key=lambda r: metric_value(r, "earned_score"), reverse=True):
        name = row.get("player", "")
        metric_rows = []
        for col, reverse in DIGEST_METRICS:
            rank, _total = metric_rank(rows, name, col, reverse)
            metric_rows.append(
                "<div class=\"digest-metric\">"
                f"<span>{esc(LABELS[col])}</span>"
                f"<strong>{format_cell_value(col, row.get(col, ''))}</strong>"
                f"<em>{rank}位</em>"
                "</div>"
            )
        cards.append(
            f"""
            <article class="player-card">
              <div class="player-card-head">
                <h3>{esc(name)}</h3>
                <span>{esc(row.get("games", ""))}半荘</span>
              </div>
              <div class="digest-metrics">
                {''.join(metric_rows)}
              </div>
            </article>
            """
        )
    return "\n".join(cards)


def yakuman_section(yakuman_rows: list[dict[str, str]], detail_rows: list[dict[str, str]]) -> str:
    grouped: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in yakuman_rows:
        grouped[row["player"]].append(row)

    details_by_role: dict[tuple[str, str], list[dict[str, str]]] = defaultdict(list)
    for row in detail_rows:
        details_by_role[(row.get("player", ""), row.get("yakuman_name", ""))].append(row)

    if not yakuman_rows:
        return "<p class=\"empty\">役満記録なし</p>"

    blocks = []
    for player, rows in sorted(grouped.items()):
        items = []
        for r in sorted(rows, key=lambda r: (-int(r["count"]), r["yakuman_name"])):
            details = details_by_role.get((player, r["yakuman_name"]), [])
            if details:
                victims = "".join(
                    f"<div><span>{esc(d.get('victim', ''))}</span><strong>{number(d.get('payment', ''))}点</strong></div>"
                    for d in details
                )
            else:
                victims = "<div><span>不明</span><strong>-</strong></div>"
            items.append(
                f"""
                <li>
                  <div class="yakuman-title"><span>{esc(r['yakuman_name'])}</span><strong>{esc(r['count'])}回</strong></div>
                  <div class="victims"><em>被害者</em>{victims}</div>
                </li>
                """
            )
        items = "".join(items)
        blocks.append(f"<article class=\"yakuman-card\"><h3>{esc(player)}</h3><ul>{items}</ul></article>")
    return "\n".join(blocks)


def compact_role_counts(items: list[str]) -> str:
    counts: dict[str, int] = defaultdict(int)
    for item in items:
        counts[item] += 1
    return " / ".join(
        f"{name} x{count}" if count > 1 else name
        for name, count in sorted(counts.items(), key=lambda item: (-item[1], item[0]))
    )


def yakuman_victim_ranking(detail_rows: list[dict[str, str]]) -> str:
    grouped: dict[str, dict[str, object]] = defaultdict(
        lambda: {"count": 0, "payment": 0, "roles": []}
    )

    for row in detail_rows:
        victim = row.get("victim", "")
        if not victim:
            continue
        grouped[victim]["count"] = int(grouped[victim]["count"]) + 1
        grouped[victim]["payment"] = int(grouped[victim]["payment"]) + int(row.get("payment", 0) or 0)
        grouped[victim]["roles"].append(f"{row.get('yakuman_name', '')}({row.get('win_type', '')})")

    rows = []
    for victim, data in grouped.items():
        rows.append(
            {
                "player": victim,
                "count": int(data["count"]),
                "roles": compact_role_counts(list(data["roles"])),
                "payment": int(data["payment"]),
            }
        )

    rows.sort(key=lambda row: (-row["payment"], -row["count"], row["player"]))
    return yakuman_ranking_table(rows, "支払点数")


def yakuman_attacker_ranking(detail_rows: list[dict[str, str]]) -> str:
    events: dict[tuple[str, str, str, str], dict[str, object]] = {}

    for row in detail_rows:
        key = (
            row.get("uuid", ""),
            row.get("round_no", ""),
            row.get("player", ""),
            row.get("yakuman_name", ""),
        )
        if key not in events:
            events[key] = {
                "player": row.get("player", ""),
                "yakuman_name": row.get("yakuman_name", ""),
                "win_type": row.get("win_type", ""),
                "payment": 0,
            }
        events[key]["payment"] = int(events[key]["payment"]) + int(row.get("payment", 0) or 0)

    grouped: dict[str, dict[str, object]] = defaultdict(
        lambda: {"count": 0, "payment": 0, "roles": []}
    )

    for event in events.values():
        player = str(event["player"])
        if not player:
            continue
        grouped[player]["count"] = int(grouped[player]["count"]) + 1
        grouped[player]["payment"] = int(grouped[player]["payment"]) + int(event["payment"])
        grouped[player]["roles"].append(f"{event['yakuman_name']}({event['win_type']})")

    rows = []
    for player, data in grouped.items():
        rows.append(
            {
                "player": player,
                "count": int(data["count"]),
                "roles": compact_role_counts(list(data["roles"])),
                "payment": int(data["payment"]),
            }
        )

    rows.sort(key=lambda row: (-row["payment"], -row["count"], row["player"]))
    return yakuman_ranking_table(rows, "獲得点数")


def yakuman_ranking_table(rows: list[dict[str, object]], payment_label: str) -> str:
    if not rows:
        return "<p class=\"empty\">役満記録なし</p>"

    body = []
    for i, row in enumerate(rows, 1):
        body.append(
            "<tr>"
            f"<td class=\"sticky-rank\">{i}</td>"
            f"<td class=\"name sticky-name\">{esc(row['player'])}</td>"
            f"<td>{esc(row['count'])}</td>"
            f"<td class=\"roles\">{esc(row['roles'])}</td>"
            f"<td>{number(row['payment'])}</td>"
            "</tr>"
        )

    return (
        "<table class=\"yakuman-rank-table\">"
        f"<thead><tr><th class=\"sticky-rank\">順位</th><th class=\"sticky-name\">プレイヤー</th><th>回数</th><th>役</th><th>{esc(payment_label)}</th></tr></thead>"
        f"<tbody>{''.join(body)}</tbody></table>"
    )


def build_correlation_rows(uuids: set[str] | None = None) -> list[dict[str, object]]:
    try:
        from aggregate_league import load_detail
    except Exception:
        return []

    pair_net: dict[tuple[str, str], int] = defaultdict(int)
    pair_games: dict[tuple[str, str], int] = defaultdict(int)

    if uuids is None:
        detail_paths = sorted(RAW_DIR.glob("*_detail.bin"))
    else:
        detail_paths = sorted(
            RAW_DIR / f"{uuid}_detail.bin"
            for uuid in uuids
            if (RAW_DIR / f"{uuid}_detail.bin").exists()
        )

    for detail_path in detail_paths:
        try:
            _, player_details = load_detail(detail_path)
        except Exception:
            continue

        players = [
            {"name": detail["name"], "point": int(detail["point"])}
            for detail in player_details.values()
            if detail.get("name")
        ]
        for left, right in combinations(players, 2):
            a, b = sorted([left["name"], right["name"]])
            point_by_name = {left["name"]: left["point"], right["name"]: right["point"]}
            pair_net[(a, b)] += point_by_name[a] - point_by_name[b]
            pair_games[(a, b)] += 1

    rows = []
    for (a, b), net in pair_net.items():
        if net == 0:
            continue
        if net > 0:
            giver, receiver, amount = b, a, net
        else:
            giver, receiver, amount = a, b, -net
        rows.append(
            {
                "giver": giver,
                "receiver": receiver,
                "amount": amount,
                "games": pair_games[(a, b)],
            }
        )
    return sorted(rows, key=lambda row: (-int(row["amount"]), row["giver"], row["receiver"]))


def correlation_table(rows: list[dict[str, object]]) -> str:
    if not rows:
        return "<p class=\"empty\">相関図の元データがありません。</p>"

    body = []
    for i, row in enumerate(rows, 1):
        body.append(
            "<tr>"
            f"<td class=\"sticky-rank\">{i}</td>"
            f"<td class=\"name sticky-name\">{esc(row['giver'])}</td>"
            f"<td class=\"name\">{esc(row['receiver'])}</td>"
            f"<td>{number(row['amount'])}</td>"
            f"<td>{esc(row['games'])}</td>"
            "</tr>"
        )

    return (
        "<table class=\"relation-table\">"
        "<thead><tr><th class=\"sticky-rank\">順位</th><th class=\"sticky-name\">献上者</th><th>受取人</th><th>ネット献上点棒</th><th>直接対戦数</th></tr></thead>"
        f"<tbody>{''.join(body)}</tbody></table>"
    )


def correlation_mermaid(rows: list[dict[str, object]], limit: int = 15) -> str:
    if not rows:
        return ""

    names = sorted({str(row["giver"]) for row in rows} | {str(row["receiver"]) for row in rows})
    node_ids = {name: f"p{i + 1}" for i, name in enumerate(names)}
    lines = ["flowchart LR"]
    for name in names:
        lines.append(f'  {node_ids[name]}["{esc(name)}"]')
    for row in rows[:limit]:
        label = f"{number(row['amount'])}点 / {row['games']}戦"
        lines.append(f'  {node_ids[str(row["giver"])]} -->|"{esc(label)}"| {node_ids[str(row["receiver"])]}')

    return f"<pre class=\"mermaid\">{chr(10).join(lines)}</pre>"


def read_paifu_rows_from_files(
    canonical_csv: Path,
    season_glob: str,
    season_file_re: re.Pattern[str],
    base_dir: Path = Path("."),
    incomplete_label: str = "season",
    allow_partial: bool = False,
) -> list[dict[str, str]]:
    rows_by_uuid: dict[str, dict[str, str]] = {}
    canonical_rows = read_csv(canonical_csv)
    canonical_seasons = {
        int(row["season"])
        for row in canonical_rows
        if row.get("season", "").isdigit()
    }
    max_canonical_season = max(canonical_seasons) if canonical_seasons else None

    def add_rows(rows: list[dict[str, str]], fallback_season: int | None = None) -> None:
        for row in rows:
            uuid = row.get("uuid", "")
            if not uuid:
                continue
            season = row.get("season", "")
            if not season and fallback_season is not None:
                season = str(fallback_season)
            if not season.isdigit():
                continue
            rows_by_uuid[uuid] = {
                "season": season,
                "page_no": row.get("page_no", ""),
                "uuid": uuid,
                "date_key": row.get("date_key") or uuid.split("-", 1)[0],
                "paifu_url": row.get("paifu_url") or f"https://game.mahjongsoul.com/?paipu={uuid}",
            }

    add_rows(canonical_rows)

    for path in sorted(base_dir.glob(season_glob)):
        match = season_file_re.match(path.name)
        if not match:
            continue
        season = int(match.group(1))
        if max_canonical_season is not None and season > max_canonical_season:
            continue
        add_rows(read_csv(path), fallback_season=season)

    rows_by_season: dict[int, list[dict[str, str]]] = defaultdict(list)
    for row in rows_by_uuid.values():
        rows_by_season[int(row["season"])].append(row)

    complete_rows: list[dict[str, str]] = []
    for season, rows in sorted(rows_by_season.items()):
        ready = [
            row for row in rows
            if (RAW_DIR / f"{row['uuid']}_record.bin").exists()
            and (RAW_DIR / f"{row['uuid']}_detail.bin").exists()
        ]
        if len(ready) != len(rows):
            if not allow_partial:
                print(f"skip incomplete {incomplete_label} {season}: {len(ready)}/{len(rows)} records ready")
                continue
            print(f"use partial {incomplete_label} {season}: {len(ready)}/{len(rows)} records ready")
        complete_rows.extend(ready if allow_partial else rows)

    return sorted(complete_rows, key=lambda row: (int(row["season"]), row["uuid"]))


def read_season_paifu_rows() -> list[dict[str, str]]:
    return read_paifu_rows_from_files(
        PAIFU_CSV,
        "admin_paifu_ids_season*.csv",
        SEASON_FILE_RE,
        incomplete_label="old season",
    )


def read_new_league_paifu_rows() -> list[dict[str, str]]:
    return read_paifu_rows_from_files(
        NEW_PAIFU_CSV,
        "admin_paifu_ids_new_season*.csv",
        NEW_SEASON_FILE_RE,
        base_dir=NEW_DATA_DIR,
        incomplete_label="new season",
        allow_partial=True,
    )


def group_uuids_by_season(paifu_rows: list[dict[str, str]]) -> dict[int, set[str]]:
    season_to_uuids: dict[int, set[str]] = defaultdict(set)
    for row in paifu_rows:
        season = row.get("season", "")
        uuid = row.get("uuid", "")
        if season.isdigit() and uuid:
            season_to_uuids[int(season)].add(uuid)
    return season_to_uuids


def aggregate_uuids(uuids: set[str]) -> tuple[list[dict[str, str]], list[dict[str, str]], list[dict[str, str]]]:
    try:
        from aggregate_league import (
            PlayerStats,
            aggregate_game,
            average,
            call_quality_breakdown,
            call_quality_top_label,
            deal_in_quality_breakdown,
            deal_in_quality_top_label,
            percent,
            riichi_quality_breakdown,
            riichi_quality_recommended_count,
            riichi_quality_top_label,
        )
    except Exception as exc:
        raise SystemExit(f"aggregate_league.py を読み込めません: {exc}") from exc

    stats = defaultdict(PlayerStats)
    yakuman_details: list[dict[str, object]] = []

    for uuid in sorted(uuids):
        record_path = RAW_DIR / f"{uuid}_record.bin"
        detail_path = RAW_DIR / f"{uuid}_detail.bin"
        if not record_path.exists() or not detail_path.exists():
            continue
        try:
            aggregate_game(uuid, stats, yakuman_details)
        except Exception as exc:
            print(f"skip {uuid}: {exc}")

    summary_rows = []
    for player_name, player_stats in sorted(stats.items(), key=lambda item: item[0]):
        summary_rows.append(
            {
                "player": player_name,
                "games": str(player_stats.games),
                "earned_score": str(round(player_stats.score_sum, 1)),
                "rank1_rate": percent(player_stats.rank_counts[1], player_stats.games),
                "rank2_rate": percent(player_stats.rank_counts[2], player_stats.games),
                "rank3_rate": percent(player_stats.rank_counts[3], player_stats.games),
                "last_avoid_rate": percent(
                    player_stats.rank_counts[1] + player_stats.rank_counts[2],
                    player_stats.games,
                ),
                "average_rank": str(average(player_stats.rank_sum, player_stats.games)),
                "rounds": str(player_stats.rounds),
                "average_hu_point": str(average(player_stats.hu_point_sum, player_stats.hu, 1)),
                "average_called_hu_point": str(average(player_stats.called_hu_point_sum, player_stats.called_hu, 1)),
                "hu_rate": percent(player_stats.hu, player_stats.rounds),
                "open_tanyao_hu_rate": percent(player_stats.open_tanyao_hu, player_stats.hu),
                "chiitoi_hu_rate": percent(player_stats.chiitoi_hu, player_stats.hu),
                "honitsu_hu_rate": percent(player_stats.honitsu_hu, player_stats.hu),
                "chinitsu_hu_rate": percent(player_stats.chinitsu_hu, player_stats.hu),
                "tsumo_rate": percent(player_stats.tsumo, player_stats.hu),
                "tsumo_loss_rate": percent(player_stats.tsumo_loss, player_stats.rounds),
                "average_tsumo_loss_point": str(
                    average(player_stats.tsumo_loss_point_sum, player_stats.tsumo_loss, 1)
                ),
                "houjuu_rate": percent(player_stats.houjuu, player_stats.rounds),
                "average_houjuu_point": str(average(player_stats.houjuu_point_sum, player_stats.houjuu, 1)),
                "noten_houjuu_rate": percent(player_stats.noten_houjuu, player_stats.deal_in_events),
                "two_shanten_houjuu_rate": percent(player_stats.two_shanten_houjuu, player_stats.deal_in_events),
                "riichi_after_houjuu_rate": percent(player_stats.riichi_after_houjuu, player_stats.deal_in_events),
                "vs_riichi_houjuu_rate": percent(player_stats.vs_riichi_houjuu, player_stats.deal_in_events),
                "vs_dama_houjuu_rate": percent(player_stats.vs_dama_houjuu, player_stats.deal_in_events),
                "vs_called_houjuu_rate": percent(player_stats.vs_called_houjuu, player_stats.deal_in_events),
                "vs_two_called_houjuu_rate": percent(player_stats.two_called_houjuu, player_stats.deal_in_events),
                "vs_haneman_houjuu_rate": percent(player_stats.called_haneman_houjuu, player_stats.deal_in_events),
                "late_noten_houjuu_share": percent(player_stats.late_noten_houjuu, player_stats.deal_in_events),
                "deal_in_quality_score": str(
                    average(player_stats.deal_in_quality_score_sum, player_stats.deal_in_events, 2)
                ),
                "deal_in_quality_top_category": deal_in_quality_top_label(player_stats),
                "deal_in_quality_breakdown": deal_in_quality_breakdown(player_stats),
                "called_houjuu_rate": percent(player_stats.called_houjuu, player_stats.rounds),
                "two_called_houjuu_rate": percent(player_stats.two_called_houjuu, player_stats.rounds),
                "called_haneman_houjuu_rate": percent(
                    player_stats.called_haneman_houjuu,
                    player_stats.rounds,
                ),
                "call_after_hu_rate": percent(player_stats.called_hu, player_stats.called),
                "call_after_houjuu_rate": percent(player_stats.called_houjuu_rounds, player_stats.called),
                "two_called_rate": percent(player_stats.two_called_rounds, player_stats.rounds),
                "two_called_hu_rate": percent(player_stats.two_called_hu, player_stats.two_called_rounds),
                "two_called_after_houjuu_rate": percent(
                    player_stats.two_called_houjuu_rounds,
                    player_stats.two_called_rounds,
                ),
                "average_first_call_turn": str(
                    average(player_stats.first_call_turn_sum, player_stats.first_call_count, 1)
                ),
                "top_keep_rate": percent(player_stats.top_keep_successes, player_stats.top_keep_chances),
                "first_tenpai_rate": percent(player_stats.first_tenpai, player_stats.rounds),
                "tenpai_keep_rate": percent(player_stats.tenpai_discards, player_stats.discards),
                "top_stay_rate": percent(player_stats.top_stay_rounds, player_stats.rounds),
                "second_stay_rate": percent(player_stats.second_stay_rounds, player_stats.rounds),
                "last_stay_rate": percent(player_stats.last_stay_rounds, player_stats.rounds),
                "late_noten_houjuu_rate": percent(
                    player_stats.late_noten_houjuu,
                    player_stats.late_noten_discards,
                ),
                "late_noten_fresh_discard_rate": percent(
                    player_stats.late_noten_fresh_discards,
                    player_stats.late_noten_discards,
                ),
                "winning_run_points": str(player_stats.winning_run_point_sum),
                "average_opening_shanten": str(
                    average(player_stats.opening_shanten_sum, player_stats.opening_samples, 2)
                ),
                "average_opening_dora": str(
                    average(player_stats.opening_dora_sum, player_stats.opening_samples, 2)
                ),
                "called_rate": percent(player_stats.called, player_stats.rounds),
                "riichi": str(player_stats.riichi),
                "riichi_rate": percent(player_stats.riichi, player_stats.rounds),
                "riichi_miss_rate": percent(player_stats.riichi_miss, player_stats.riichi),
                "bad_shape_riichi_rate": percent(player_stats.bad_shape_riichi, player_stats.riichi),
                "top_riichi_rate": percent(player_stats.top_riichi, player_stats.riichi),
                "riichi_quality_score": str(
                    average(player_stats.riichi_quality_score_sum, player_stats.riichi, 2)
                ),
                "riichi_recommended_rate": percent(
                    riichi_quality_recommended_count(player_stats),
                    player_stats.riichi,
                ),
                "riichi_not_recommended_rate": percent(
                    player_stats.riichi - riichi_quality_recommended_count(player_stats),
                    player_stats.riichi,
                ),
                "riichi_quality_top_category": riichi_quality_top_label(player_stats),
                "riichi_quality_breakdown": riichi_quality_breakdown(player_stats),
                "call_quality_score": str(
                    average(player_stats.call_quality_score_sum, player_stats.call_quality_events, 2)
                ),
                "call_quality_top_category": call_quality_top_label(player_stats),
                "call_quality_breakdown": call_quality_breakdown(player_stats),
                "max_final_point": str(max(player_stats.final_points) if player_stats.final_points else ""),
                "min_final_point": str(min(player_stats.final_points) if player_stats.final_points else ""),
                "yakuman_count": str(player_stats.yakuman_count),
            }
        )

    yakuman_rows = []
    for player_name, player_stats in sorted(stats.items(), key=lambda item: item[0]):
        for yakuman_name, count in sorted(player_stats.yakuman_names.items()):
            yakuman_rows.append(
                {
                    "player": player_name,
                    "yakuman_name": yakuman_name,
                    "count": str(count),
                }
            )

    detail_rows = [
        {key: str(value) for key, value in row.items()}
        for row in yakuman_details
    ]

    return summary_rows, yakuman_rows, detail_rows


def build_context(
    key: str,
    label: str,
    uuids: set[str],
    season: int | None = None,
    teams_by_season: dict[int, dict[str, list[str]]] | None = None,
) -> dict[str, object]:
    rows, yakuman_rows, yakuman_detail_rows = aggregate_uuids(uuids)
    if not rows:
        return {
            "key": key,
            "label": label,
            "rows": [],
            "yakuman_rows": [],
            "yakuman_detail_rows": [],
            "correlation_rows": [],
            "total_games": 0,
            "total_rounds": 0,
            "total_yakuman": 0,
            "best_score": "",
            "best_top": "",
            "team_rows": [],
            "team_champion_rows": [],
            "season_mvp_rows": [],
            "is_cumulative": season is None,
        }

    total_player_games = sum(int(r["games"]) for r in rows)
    total_games = total_player_games // 3
    total_rounds = sum(int(r["rounds"]) for r in rows) // 3
    total_yakuman = sum(int(r.get("yakuman_count", 0)) for r in rows)
    best_score = max(rows, key=lambda r: float(r.get("earned_score", 0) or 0))
    best_top = max(rows, key=lambda r: pct_number(r["rank1_rate"]))
    team_rows = []
    if season is not None and teams_by_season is not None:
        team_rows = build_team_rows(rows, teams_by_season.get(season, {}))

    return {
        "key": key,
        "label": label,
        "rows": rows,
        "yakuman_rows": yakuman_rows,
        "yakuman_detail_rows": yakuman_detail_rows,
        "correlation_rows": build_correlation_rows(uuids),
        "total_games": total_games,
        "total_rounds": total_rounds,
        "total_yakuman": total_yakuman,
        "best_score": best_score,
        "best_top": best_top,
        "team_rows": team_rows,
        "team_champion_rows": [],
        "season_mvp_rows": [],
        "is_cumulative": season is None,
    }


def player_row_from(context: dict[str, object], player: str) -> dict[str, str] | None:
    return next(
        (row for row in list(context.get("rows", [])) if row.get("player") == player),
        None,
    )


def player_season_rows(player: str, season_contexts: list[dict[str, object]]) -> list[dict[str, str]]:
    rows = []
    for context in season_contexts:
        row = player_row_from(context, player)
        if not row:
            continue
        season_row = dict(row)
        season_row["season"] = str(context.get("label", ""))
        rows.append(season_row)
    return rows


def player_metric_rank_rows(player: str, cumulative_rows: list[dict[str, str]]) -> list[dict[str, str]]:
    row = next((r for r in cumulative_rows if r.get("player") == player), None)
    if not row:
        return []

    rank_rows = []
    for col, reverse, direction in PLAYER_RANK_METRICS:
        rank, total = metric_rank(cumulative_rows, player, col, reverse)
        rank_rows.append(
            {
                "metric": LABELS[col],
                "value": format_cell_value(col, row.get(col, "")),
                "rank_text": f"{rank} / {total}",
                "direction": direction,
                "is_best": "1" if rank == 1 else "",
                "is_worst": "1" if total > 1 and rank == total else "",
            }
        )
    return rank_rows


def player_rank_table(rows: list[dict[str, str]]) -> str:
    if not rows:
        return "<p class=\"empty\">順位データがありません。</p>"
    columns = ["metric", "value", "rank_text", "direction"]
    head = "".join(
        f"<th class=\"sticky-name\">{esc(LABELS[c])}</th>" if c == "metric" else f"<th>{esc(LABELS[c])}</th>"
        for c in columns
    )
    body = []
    for row in rows:
        classes = []
        if row.get("is_best"):
            classes.append("metric-best")
        if row.get("is_worst"):
            classes.append("metric-worst")
        tr_class = f" class=\"{' '.join(classes)}\"" if classes else ""
        body.append(
            f"<tr{tr_class}>"
            f"<td class=\"name sticky-name\">{esc(row['metric'])}</td>"
            f"<td>{row['value']}</td>"
            f"<td>{esc(row['rank_text'])}</td>"
            f"<td>{esc(row['direction'])}</td>"
            "</tr>"
        )
    return f"<table class=\"player-rank-table\"><thead><tr>{head}</tr></thead><tbody>{''.join(body)}</tbody></table>"


def player_analysis(
    player: str,
    cumulative_rows: list[dict[str, str]],
    use_manual: bool = True,
) -> tuple[str, str, str]:
    if use_manual and player in MANUAL_PLAYER_ANALYSIS:
        return MANUAL_PLAYER_ANALYSIS[player]

    row = next((r for r in cumulative_rows if r.get("player") == player), None)
    if not row:
        return "データ不足です。", "追加の牌譜取得後に再評価します。", "まだ傾向を断定できません。"

    ranks = {
        col: metric_rank(cumulative_rows, player, col, reverse)[0]
        for col, reverse, _ in PLAYER_RANK_METRICS
    }
    total = len(cumulative_rows)

    style_bits = []
    if ranks["earned_score"] <= 2:
        style_bits.append("獲得スコアで上位に入り、長期戦の収支を作れている")
    if ranks["hu_rate"] <= 2:
        style_bits.append("和了率が高く、局参加から着実にあがりまで持っていく")
    if ranks["average_hu_point"] <= 2:
        style_bits.append("平均和了点が高く、決め手の打点を作れる")
    if ranks["houjuu_rate"] <= 2:
        style_bits.append("放銃率が低く、守備の安定感がある")
    if ranks["top_keep_rate"] <= 2:
        style_bits.append("トップ目に立った後の押し引きが安定している")
    if ranks["called_rate"] <= 2:
        style_bits.append("副露率が高く、速度で局面を動かす")
    if ranks["riichi_rate"] <= 2:
        style_bits.append("立直率が高く、門前の圧を使う")

    if not style_bits:
        style_bits.append("大きな突出よりもバランス型で、局ごとの対応幅が広い")

    strength_bits = []
    if ranks["rank1_rate"] <= 2:
        strength_bits.append("トップ率が高く、勝ち切る半荘を作る力がある")
    if ranks["tsumo_rate"] <= 2:
        strength_bits.append("ツモ率が高く、リーチや仕掛け後に自力決着へ持ち込みやすい")
    if ranks["average_houjuu_point"] <= 2:
        strength_bits.append("放銃時の失点が軽く、刺さる場面でも致命傷を避けている")
    if ranks["yakuman_count"] <= 2:
        strength_bits.append("役満回数も上位で、爆発力が数字に残っている")

    if not strength_bits:
        strength_bits.append("極端な尖りよりも、複数項目を中位以上にまとめる総合力が強み")

    risk_bits = []
    if ranks["houjuu_rate"] >= total - 1:
        risk_bits.append("放銃率が相対的に高いので、親番・終盤の押し返し基準を一段絞る")
    if ranks["average_houjuu_point"] >= total - 1:
        risk_bits.append("放銃平均打点が重いので、高打点気配への撤退を早める")
    if ranks["hu_rate"] >= total - 1:
        risk_bits.append("和了率が伸びにくいので、序盤の孤立牌選択と鳴き判断で速度を補う")
    if ranks["top_keep_rate"] >= total - 1:
        risk_bits.append("トップキープ率が課題なので、トップ目では局消化と放銃回避を優先する")

    if not risk_bits:
        risk_bits.append("明確な穴は小さいので、現在の強みを保ちつつ局面別の押し引きを精密化する")

    top_count = sum(1 for rank in ranks.values() if rank == 1)
    score = format_cell_value("earned_score", row.get("earned_score", ""))
    avg_rank = row.get("average_rank", "")
    hu = row.get("hu_rate", "")
    deal_in = row.get("houjuu_rate", "")

    style = (
        f"{player}は、累計獲得スコア{score}、平均順位{avg_rank}の成績。"
        + "。".join(style_bits[:4])
        + f"。和了率{hu}、放銃率{deal_in}のバランスを見ると、"
        "ただ前に出るだけではなく、収支を残す局面選択ができているタイプ。"
    )
    strength = (
        f"項目別1位は{top_count}項目。"
        + "。".join(strength_bits[:4])
        + "。この強みがある半荘では、序盤から主導権を握るか、勝負所で一気に着順を押し上げられる。"
    )
    advice = (
        "改善点は、"
        + "。".join(risk_bits[:4])
        + "こと。特に自分の強い土俵に入っていない局では、打点固定・速度・撤退のどれを優先するかを早めに決めると成績が安定しやすい。"
    )
    return style, strength, advice


def render_player_panel(
    player: str,
    cumulative_context: dict[str, object],
    season_contexts: list[dict[str, object]],
    panel_key: str | None = None,
    title_label: str = "累計",
    use_manual_analysis: bool = True,
) -> str:
    panel_key = panel_key or f"player-{player}"
    cumulative_rows = list(cumulative_context.get("rows", []))
    cumulative_row = player_row_from(cumulative_context, player)
    if not cumulative_row:
        return (
            f"<section class=\"tab-panel\" id=\"panel-{esc(panel_key)}\" "
            f"data-panel=\"{esc(panel_key)}\"><p class=\"empty\">{esc(player)}の集計データがありません。</p></section>"
        )

    season_rows = player_season_rows(player, season_contexts)
    rank_rows = player_metric_rank_rows(player, cumulative_rows)
    style, strength, advice = player_analysis(player, cumulative_rows, use_manual=use_manual_analysis)

    return f"""
    <section class="tab-panel" id="panel-{esc(panel_key)}" data-panel="{esc(panel_key)}">
      <section class="summary" aria-label="{esc(player)} {esc(title_label)} 集計概要">
        <div><span>対戦数</span><strong>{number(cumulative_row.get("games", ""))}</strong></div>
        <div><span>獲得スコア</span><strong>{number(cumulative_row.get("earned_score", ""), 1)}</strong></div>
        <div><span>平均順位</span><strong>{esc(cumulative_row.get("average_rank", ""))}</strong></div>
        <div><span>役満回数</span><strong>{number(cumulative_row.get("yakuman_count", ""))}</strong></div>
      </section>

      <h2>{esc(player)} {esc(title_label)}成績</h2>
      {split_tables(
        [cumulative_row],
        [
          ("順位スタッツ", PLAYER_RANK_COLUMNS),
          ("和了・放銃スタッツ", PLAYER_WIN_COLUMNS),
        ],
      )}

      <h2>{esc(player)} リーチの質</h2>
      <div class="table-wrap">
        {table([cumulative_row], RIICHI_QUALITY_COLUMNS)}
      </div>

      <h2>{esc(player)} 鳴きの質</h2>
      <div class="table-wrap">
        {table([cumulative_row], CALL_QUALITY_COLUMNS)}
      </div>

      <h2>{esc(player)} 放銃の質</h2>
      <div class="table-wrap">
        {table([cumulative_row], DEAL_IN_QUALITY_COLUMNS)}
      </div>

      <h2>{esc(player)} シーズン別推移</h2>
      {split_tables(
        season_rows,
        [
          ("順位スタッツ", PLAYER_SEASON_RANK_COLUMNS),
          ("和了・放銃スタッツ", PLAYER_SEASON_WIN_COLUMNS),
        ],
      )}
      <div class="table-wrap">
        {table(season_rows, PLAYER_RIICHI_QUALITY_COLUMNS)}
      </div>
      <div class="table-wrap">
        {table(season_rows, PLAYER_CALL_QUALITY_COLUMNS)}
      </div>
      <div class="table-wrap">
        {table(season_rows, PLAYER_DEAL_IN_QUALITY_COLUMNS)}
      </div>

      <h2>{esc(player)} 項目別順位</h2>
      <div class="table-wrap">
        {player_rank_table(rank_rows)}
      </div>

      <h2>AI雀風分析</h2>
      <section class="analysis-grid">
        <article class="analysis-card">
          <h3>雀風</h3>
          <p>{esc(style)}</p>
        </article>
        <article class="analysis-card">
          <h3>強み</h3>
          <p>{esc(strength)}</p>
        </article>
        <article class="analysis-card">
          <h3>改善点</h3>
          <p>{esc(advice)}</p>
        </article>
      </section>
    </section>
    """


def render_stats_panel(context: dict[str, object]) -> str:
    rows = context["rows"]
    if not rows:
        return (
            f"<section class=\"tab-panel\" id=\"panel-{esc(context['key'])}\" "
            f"data-panel=\"{esc(context['key'])}\">"
            "<p class=\"empty\">集計できる牌譜がありません。</p>"
            "</section>"
        )

    yakuman_rows = context["yakuman_rows"]
    yakuman_detail_rows = context["yakuman_detail_rows"]
    correlation_rows = context["correlation_rows"]
    best_score = context["best_score"]
    best_top = context["best_top"]
    if context.get("is_cumulative"):
        team_block_title = "チーム優勝経験"
        team_block = team_champion_section(list(context.get("team_champion_rows", [])))
        rank_columns = CUMULATIVE_RANK_COLUMNS
        mvp_block = (
            "<h2>シーズンMVP経験</h2>"
            + season_mvp_section(list(context.get("season_mvp_rows", [])))
        )
    else:
        team_block_title = f"{context['label']} チーム成績"
        team_block = team_section(list(context.get("team_rows", [])))
        rank_columns = MAIN_RANK_COLUMNS
        mvp_block = ""

    return f"""
    <section class="tab-panel" id="panel-{esc(context['key'])}" data-panel="{esc(context['key'])}">
      <h2>{esc(context['label'])} ダイジェスト</h2>
      <section class="cards digest-cards">
        {digest_cards(rows)}
      </section>

      <section class="summary" aria-label="集計概要">
        <div><span>対象半荘</span><strong>{int(context['total_games']):,}</strong></div>
        <div><span>対象局数</span><strong>{int(context['total_rounds']):,}</strong></div>
        <div><span>獲得スコアトップ</span><strong>{esc(best_score["player"])}</strong></div>
        <div><span>役満合計</span><strong>{int(context['total_yakuman']):,}</strong></div>
      </section>

      <h2>{esc(context['label'])} 個人成績ランキング</h2>
      {split_tables(
        rows,
        [
          ("順位スタッツ", rank_columns),
          ("和了・放銃スタッツ", MAIN_WIN_COLUMNS),
        ],
        rank_by="earned_score",
        reverse=True,
      )}

      <h2>{esc(context['label'])} リーチの質</h2>
      <div class="table-wrap">
        {riichi_quality_table(rows)}
      </div>

      <h2>{esc(context['label'])} 鳴きの質</h2>
      <div class="table-wrap">
        {call_quality_table(rows)}
      </div>

      <h2>{esc(context['label'])} 放銃の質</h2>
      <div class="table-wrap">
        {deal_in_quality_table(rows)}
      </div>

      <h2>{esc(team_block_title)}</h2>
      {team_block}
      {mvp_block}

      <h2>詳細スタッツ</h2>
      {split_tables(
        rows,
        [
          ("順位スタッツ", DETAIL_RANK_COLUMNS),
          ("和了・放銃スタッツ", DETAIL_WIN_COLUMNS),
        ],
        rank_by="average_rank",
      )}

      <h2>許されない相関図</h2>
      <p class="subnote">矢印は「左のプレイヤーが右のプレイヤーへ、同卓時の最終持ち点差でネット献上」。ラベルは 献上点棒 / 直接対戦数。</p>
      {correlation_mermaid(correlation_rows)}
      <div class="table-wrap">
        {correlation_table(correlation_rows)}
      </div>

      <p class="generated-note">1位率トップ: {esc(best_top["player"])} ({esc(best_top["rank1_rate"])})</p>

      <div class="ranking-grid">
        <section class="ranking-panel">
          <h3>役満被害者ランキング</h3>
          <div class="table-wrap">
            {yakuman_victim_ranking(yakuman_detail_rows)}
          </div>
        </section>
        <section class="ranking-panel">
          <h3>役満加害者ランキング</h3>
          <div class="table-wrap">
            {yakuman_attacker_ranking(yakuman_detail_rows)}
          </div>
        </section>
      </div>

      <h2>役満内訳</h2>
      <section class="yakuman-grid">
        {yakuman_section(yakuman_rows, yakuman_detail_rows)}
      </section>
    </section>
    """


def display_season_label(
    season: int,
    latest_season: int,
    game_count: int,
    full_games: int = OLD_LEAGUE_FULL_GAMES,
    prefix: str = "シーズン",
) -> str:
    if season == latest_season and game_count < full_games:
        return f"{prefix}{season}（進行中）"
    return f"{prefix}{season}"


def build_season_contexts(
    season_to_uuids: dict[int, set[str]],
    key_prefix: str,
    label_prefix: str,
    full_games: int,
    teams_by_season: dict[int, dict[str, list[str]]] | None = None,
) -> list[dict[str, object]]:
    if not season_to_uuids:
        return []
    season_contexts = []
    latest_season = max(season_to_uuids)
    for season in sorted(season_to_uuids, reverse=True):
        label = display_season_label(
            season,
            latest_season,
            len(season_to_uuids[season]),
            full_games=full_games,
            prefix=label_prefix,
        )
        season_contexts.append(
            build_context(
                f"{key_prefix}-season-{season}",
                label,
                season_to_uuids[season],
                season=season,
                teams_by_season=teams_by_season,
            )
        )
    return season_contexts


def add_context_awards(
    context: dict[str, object],
    season_contexts: list[dict[str, object]],
) -> None:
    context["team_champion_rows"] = team_champion_rows(season_contexts)
    context["season_mvp_rows"] = season_mvp_rows(season_contexts)
    add_cumulative_awards(
        context,
        list(context["season_mvp_rows"]),
        list(context["team_champion_rows"]),
    )


def sorted_player_names(context: dict[str, object]) -> list[str]:
    return [
        row["player"]
        for row in sorted(
            list(context.get("rows", [])),
            key=lambda r: float(r.get("earned_score", 0) or 0),
            reverse=True,
        )
        if row.get("player")
    ]


def save_old_context_cache(
    old_context: dict[str, object],
    old_season_contexts: list[dict[str, object]],
) -> None:
    OLD_CONTEXT_CACHE.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "version": OLD_CONTEXT_CACHE_VERSION,
        "old_context": old_context,
        "old_season_contexts": old_season_contexts,
    }
    OLD_CONTEXT_CACHE.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def load_old_context_cache() -> tuple[dict[str, object], list[dict[str, object]]] | None:
    if not OLD_CONTEXT_CACHE.exists():
        return None
    try:
        payload = json.loads(OLD_CONTEXT_CACHE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if payload.get("version") != OLD_CONTEXT_CACHE_VERSION:
        return None
    old_context = payload.get("old_context")
    old_season_contexts = payload.get("old_season_contexts")
    if not isinstance(old_context, dict) or not isinstance(old_season_contexts, list):
        return None
    return old_context, old_season_contexts


def build_old_context_from_summary_csv() -> dict[str, object] | None:
    rows = read_csv(SUMMARY_CSV)
    if not rows:
        return None

    total_player_games = sum(parse_int(row.get("games", 0)) for row in rows)
    total_games = total_player_games // 3
    total_rounds = sum(parse_int(row.get("rounds", 0)) for row in rows) // 3
    total_yakuman = sum(parse_int(row.get("yakuman_count", 0)) for row in rows)
    best_score = max(rows, key=lambda row: parse_float(row.get("earned_score", 0)))
    best_top = max(rows, key=lambda row: pct_number(row.get("rank1_rate", "")))

    return {
        "key": "old-league",
        "label": "旧リーグ",
        "rows": rows,
        "yakuman_rows": read_csv(YAKUMAN_CSV),
        "yakuman_detail_rows": read_csv(YAKUMAN_DETAILS_CSV),
        "correlation_rows": [],
        "total_games": total_games,
        "total_rounds": total_rounds,
        "total_yakuman": total_yakuman,
        "best_score": best_score,
        "best_top": best_top,
        "team_rows": [],
        "team_champion_rows": [],
        "season_mvp_rows": [],
        "is_cumulative": True,
    }


def build_old_contexts(refresh_cache: bool = False) -> tuple[dict[str, object], list[dict[str, object]]]:
    cached = None if refresh_cache else load_old_context_cache()
    if cached is not None:
        print(f"use old league cache: {OLD_CONTEXT_CACHE}")
        return cached

    old_context = build_old_context_from_summary_csv()
    if old_context is not None and not refresh_cache:
        print("use old league summary csv")
        save_old_context_cache(old_context, [])
        return old_context, []

    print("build old league cache...")
    old_paifu_rows = read_season_paifu_rows()
    old_season_to_uuids = group_uuids_by_season(old_paifu_rows)
    old_uuids = set().union(*old_season_to_uuids.values()) if old_season_to_uuids else set()
    old_teams_by_season = read_team_members()
    old_season_contexts = build_season_contexts(
        old_season_to_uuids,
        "old",
        "旧シーズン",
        OLD_LEAGUE_FULL_GAMES,
        teams_by_season=old_teams_by_season,
    )
    old_context = build_context("old-league", "旧リーグ", old_uuids)
    add_context_awards(old_context, old_season_contexts)
    save_old_context_cache(old_context, old_season_contexts)
    print(f"saved old league cache: {OLD_CONTEXT_CACHE}")
    return old_context, old_season_contexts


def parse_float(value: object) -> float:
    try:
        return float(str(value).replace(",", "").replace("%", ""))
    except (TypeError, ValueError):
        return 0.0


def parse_int(value: object) -> int:
    return int(round(parse_float(value)))


def pct_count(row: dict[str, str], col: str, denominator: int) -> int:
    return int(round(pct_number(row.get(col, "")) * denominator / 100))


def fmt_pct_count(numerator: int, denominator: int) -> str:
    if denominator <= 0:
        return "0.00%"
    return f"{numerator / denominator * 100:.2f}%"


def weighted_average(total: float, denominator: int, digits: int = 1) -> str:
    if denominator <= 0:
        return "0"
    return str(round(total / denominator, digits))


def parse_quality_breakdown(value: str) -> Counter:
    counts = Counter()
    for part in (value or "").split("|"):
        if ":" not in part:
            continue
        key, raw_count = part.split(":", 1)
        try:
            counts[key] += int(raw_count)
        except ValueError:
            continue
    return counts


def format_quality_breakdown(counts: Counter) -> str:
    return "|".join(f"{key}:{count}" for key, count in counts.items() if count)


def top_category_from_rows(rows: list[dict[str, str]], count_col: str, label_col: str) -> str:
    weighted: Counter = Counter()
    for row in rows:
        label = row.get(label_col, "")
        if label:
            weighted[label] += max(1, parse_int(row.get(count_col, 0)))
    return weighted.most_common(1)[0][0] if weighted else ""


def combine_player_rows(contexts: list[dict[str, object]]) -> list[dict[str, str]]:
    rows_by_player: dict[str, list[dict[str, str]]] = defaultdict(list)
    for context in contexts:
        for row in list(context.get("rows", [])):
            player = row.get("player", "")
            if player:
                rows_by_player[player].append(dict(row))

    combined_rows = []
    for player, rows in rows_by_player.items():
        games = sum(parse_int(row.get("games", 0)) for row in rows)
        rounds = sum(parse_int(row.get("rounds", 0)) for row in rows)
        hu = sum(pct_count(row, "hu_rate", parse_int(row.get("rounds", 0))) for row in rows)
        called = sum(pct_count(row, "called_rate", parse_int(row.get("rounds", 0))) for row in rows)
        riichi = sum(parse_int(row.get("riichi", 0)) for row in rows)
        houjuu = sum(pct_count(row, "houjuu_rate", parse_int(row.get("rounds", 0))) for row in rows)
        tsumo_loss = sum(pct_count(row, "tsumo_loss_rate", parse_int(row.get("rounds", 0))) for row in rows)
        two_called = sum(pct_count(row, "two_called_rate", parse_int(row.get("rounds", 0))) for row in rows)
        deal_in_events = houjuu
        riichi_recommended = sum(pct_count(row, "riichi_recommended_rate", parse_int(row.get("riichi", 0))) for row in rows)

        rank_counts = {
            rank: sum(pct_count(row, f"rank{rank}_rate", parse_int(row.get("games", 0))) for row in rows)
            for rank in [1, 2, 3]
        }
        called_hu = sum(pct_count(row, "call_after_hu_rate", pct_count(row, "called_rate", parse_int(row.get("rounds", 0)))) for row in rows)
        called_houjuu_rounds = sum(pct_count(row, "call_after_houjuu_rate", pct_count(row, "called_rate", parse_int(row.get("rounds", 0)))) for row in rows)
        two_called_hu = sum(pct_count(row, "two_called_hu_rate", pct_count(row, "two_called_rate", parse_int(row.get("rounds", 0)))) for row in rows)
        two_called_houjuu = sum(pct_count(row, "two_called_after_houjuu_rate", pct_count(row, "two_called_rate", parse_int(row.get("rounds", 0)))) for row in rows)

        riichi_breakdown = Counter()
        call_breakdown = Counter()
        deal_breakdown = Counter()
        for row in rows:
            riichi_breakdown.update(parse_quality_breakdown(row.get("riichi_quality_breakdown", "")))
            call_breakdown.update(parse_quality_breakdown(row.get("call_quality_breakdown", "")))
            deal_breakdown.update(parse_quality_breakdown(row.get("deal_in_quality_breakdown", "")))

        combined_rows.append(
            {
                "player": player,
                "games": str(games),
                "earned_score": str(round(sum(parse_float(row.get("earned_score", 0)) for row in rows), 1)),
                "rank1_rate": fmt_pct_count(rank_counts[1], games),
                "rank2_rate": fmt_pct_count(rank_counts[2], games),
                "rank3_rate": fmt_pct_count(rank_counts[3], games),
                "last_avoid_rate": fmt_pct_count(rank_counts[1] + rank_counts[2], games),
                "average_rank": weighted_average(sum(parse_float(row.get("average_rank", 0)) * parse_int(row.get("games", 0)) for row in rows), games, 2),
                "rounds": str(rounds),
                "average_hu_point": weighted_average(sum(parse_float(row.get("average_hu_point", 0)) * pct_count(row, "hu_rate", parse_int(row.get("rounds", 0))) for row in rows), hu, 1),
                "average_called_hu_point": weighted_average(sum(parse_float(row.get("average_called_hu_point", 0)) * pct_count(row, "call_after_hu_rate", pct_count(row, "called_rate", parse_int(row.get("rounds", 0)))) for row in rows), called_hu, 1),
                "hu_rate": fmt_pct_count(hu, rounds),
                "open_tanyao_hu_rate": fmt_pct_count(sum(pct_count(row, "open_tanyao_hu_rate", pct_count(row, "hu_rate", parse_int(row.get("rounds", 0)))) for row in rows), hu),
                "chiitoi_hu_rate": fmt_pct_count(sum(pct_count(row, "chiitoi_hu_rate", pct_count(row, "hu_rate", parse_int(row.get("rounds", 0)))) for row in rows), hu),
                "honitsu_hu_rate": fmt_pct_count(sum(pct_count(row, "honitsu_hu_rate", pct_count(row, "hu_rate", parse_int(row.get("rounds", 0)))) for row in rows), hu),
                "chinitsu_hu_rate": fmt_pct_count(sum(pct_count(row, "chinitsu_hu_rate", pct_count(row, "hu_rate", parse_int(row.get("rounds", 0)))) for row in rows), hu),
                "tsumo_rate": fmt_pct_count(sum(pct_count(row, "tsumo_rate", pct_count(row, "hu_rate", parse_int(row.get("rounds", 0)))) for row in rows), hu),
                "tsumo_loss_rate": fmt_pct_count(tsumo_loss, rounds),
                "average_tsumo_loss_point": weighted_average(sum(parse_float(row.get("average_tsumo_loss_point", 0)) * pct_count(row, "tsumo_loss_rate", parse_int(row.get("rounds", 0))) for row in rows), tsumo_loss, 1),
                "houjuu_rate": fmt_pct_count(houjuu, rounds),
                "average_houjuu_point": weighted_average(sum(parse_float(row.get("average_houjuu_point", 0)) * pct_count(row, "houjuu_rate", parse_int(row.get("rounds", 0))) for row in rows), houjuu, 1),
                "noten_houjuu_rate": fmt_pct_count(sum(pct_count(row, "noten_houjuu_rate", pct_count(row, "houjuu_rate", parse_int(row.get("rounds", 0)))) for row in rows), deal_in_events),
                "two_shanten_houjuu_rate": fmt_pct_count(sum(pct_count(row, "two_shanten_houjuu_rate", pct_count(row, "houjuu_rate", parse_int(row.get("rounds", 0)))) for row in rows), deal_in_events),
                "riichi_after_houjuu_rate": fmt_pct_count(sum(pct_count(row, "riichi_after_houjuu_rate", pct_count(row, "houjuu_rate", parse_int(row.get("rounds", 0)))) for row in rows), deal_in_events),
                "vs_riichi_houjuu_rate": fmt_pct_count(sum(pct_count(row, "vs_riichi_houjuu_rate", pct_count(row, "houjuu_rate", parse_int(row.get("rounds", 0)))) for row in rows), deal_in_events),
                "vs_dama_houjuu_rate": fmt_pct_count(sum(pct_count(row, "vs_dama_houjuu_rate", pct_count(row, "houjuu_rate", parse_int(row.get("rounds", 0)))) for row in rows), deal_in_events),
                "vs_called_houjuu_rate": fmt_pct_count(sum(pct_count(row, "vs_called_houjuu_rate", pct_count(row, "houjuu_rate", parse_int(row.get("rounds", 0)))) for row in rows), deal_in_events),
                "vs_two_called_houjuu_rate": fmt_pct_count(sum(pct_count(row, "vs_two_called_houjuu_rate", pct_count(row, "houjuu_rate", parse_int(row.get("rounds", 0)))) for row in rows), deal_in_events),
                "vs_haneman_houjuu_rate": fmt_pct_count(sum(pct_count(row, "vs_haneman_houjuu_rate", pct_count(row, "houjuu_rate", parse_int(row.get("rounds", 0)))) for row in rows), deal_in_events),
                "late_noten_houjuu_share": fmt_pct_count(sum(pct_count(row, "late_noten_houjuu_share", pct_count(row, "houjuu_rate", parse_int(row.get("rounds", 0)))) for row in rows), deal_in_events),
                "deal_in_quality_score": weighted_average(sum(parse_float(row.get("deal_in_quality_score", 0)) * pct_count(row, "houjuu_rate", parse_int(row.get("rounds", 0))) for row in rows), deal_in_events, 2),
                "deal_in_quality_top_category": top_category_from_rows(rows, "games", "deal_in_quality_top_category"),
                "deal_in_quality_breakdown": format_quality_breakdown(deal_breakdown),
                "called_houjuu_rate": fmt_pct_count(sum(pct_count(row, "called_houjuu_rate", parse_int(row.get("rounds", 0))) for row in rows), rounds),
                "two_called_houjuu_rate": fmt_pct_count(sum(pct_count(row, "two_called_houjuu_rate", parse_int(row.get("rounds", 0))) for row in rows), rounds),
                "called_haneman_houjuu_rate": fmt_pct_count(sum(pct_count(row, "called_haneman_houjuu_rate", parse_int(row.get("rounds", 0))) for row in rows), rounds),
                "call_after_hu_rate": fmt_pct_count(called_hu, called),
                "call_after_houjuu_rate": fmt_pct_count(called_houjuu_rounds, called),
                "two_called_rate": fmt_pct_count(two_called, rounds),
                "two_called_hu_rate": fmt_pct_count(two_called_hu, two_called),
                "two_called_after_houjuu_rate": fmt_pct_count(two_called_houjuu, two_called),
                "average_first_call_turn": weighted_average(sum(parse_float(row.get("average_first_call_turn", 0)) * pct_count(row, "called_rate", parse_int(row.get("rounds", 0))) for row in rows), called, 1),
                "call_quality_score": weighted_average(sum(parse_float(row.get("call_quality_score", 0)) * pct_count(row, "called_rate", parse_int(row.get("rounds", 0))) for row in rows), called, 2),
                "call_quality_top_category": top_category_from_rows(rows, "games", "call_quality_top_category"),
                "call_quality_breakdown": format_quality_breakdown(call_breakdown),
                "top_keep_rate": weighted_average(sum(pct_number(row.get("top_keep_rate", "")) * parse_int(row.get("games", 0)) for row in rows), games, 2) + "%",
                "first_tenpai_rate": fmt_pct_count(sum(pct_count(row, "first_tenpai_rate", parse_int(row.get("rounds", 0))) for row in rows), rounds),
                "tenpai_keep_rate": weighted_average(sum(pct_number(row.get("tenpai_keep_rate", "")) * parse_int(row.get("rounds", 0)) for row in rows), rounds, 2) + "%",
                "top_stay_rate": fmt_pct_count(sum(pct_count(row, "top_stay_rate", parse_int(row.get("rounds", 0))) for row in rows), rounds),
                "second_stay_rate": fmt_pct_count(sum(pct_count(row, "second_stay_rate", parse_int(row.get("rounds", 0))) for row in rows), rounds),
                "last_stay_rate": fmt_pct_count(sum(pct_count(row, "last_stay_rate", parse_int(row.get("rounds", 0))) for row in rows), rounds),
                "late_noten_houjuu_rate": weighted_average(sum(pct_number(row.get("late_noten_houjuu_rate", "")) * parse_int(row.get("rounds", 0)) for row in rows), rounds, 2) + "%",
                "late_noten_fresh_discard_rate": weighted_average(sum(pct_number(row.get("late_noten_fresh_discard_rate", "")) * parse_int(row.get("rounds", 0)) for row in rows), rounds, 2) + "%",
                "winning_run_points": str(sum(parse_int(row.get("winning_run_points", 0)) for row in rows)),
                "average_opening_shanten": weighted_average(sum(parse_float(row.get("average_opening_shanten", 0)) * parse_int(row.get("rounds", 0)) for row in rows), rounds, 2),
                "average_opening_dora": weighted_average(sum(parse_float(row.get("average_opening_dora", 0)) * parse_int(row.get("rounds", 0)) for row in rows), rounds, 2),
                "called_rate": fmt_pct_count(called, rounds),
                "riichi": str(riichi),
                "riichi_rate": fmt_pct_count(riichi, rounds),
                "riichi_miss_rate": fmt_pct_count(sum(pct_count(row, "riichi_miss_rate", parse_int(row.get("riichi", 0))) for row in rows), riichi),
                "bad_shape_riichi_rate": fmt_pct_count(sum(pct_count(row, "bad_shape_riichi_rate", parse_int(row.get("riichi", 0))) for row in rows), riichi),
                "top_riichi_rate": fmt_pct_count(sum(pct_count(row, "top_riichi_rate", parse_int(row.get("riichi", 0))) for row in rows), riichi),
                "max_final_point": str(max((parse_int(row.get("max_final_point", 0)) for row in rows), default=0)),
                "min_final_point": str(min((parse_int(row.get("min_final_point", 0)) for row in rows), default=0)),
                "yakuman_count": str(sum(parse_int(row.get("yakuman_count", 0)) for row in rows)),
                "riichi_quality_score": weighted_average(sum(parse_float(row.get("riichi_quality_score", 0)) * parse_int(row.get("riichi", 0)) for row in rows), riichi, 2),
                "riichi_recommended_rate": fmt_pct_count(riichi_recommended, riichi),
                "riichi_not_recommended_rate": fmt_pct_count(max(riichi - riichi_recommended, 0), riichi),
                "riichi_quality_top_category": top_category_from_rows(rows, "riichi", "riichi_quality_top_category"),
                "riichi_quality_breakdown": format_quality_breakdown(riichi_breakdown),
            }
        )

    return sorted(combined_rows, key=lambda row: float(row.get("earned_score", 0) or 0), reverse=True)


def combine_named_count_rows(contexts: list[dict[str, object]], row_key: str, name_key: str) -> list[dict[str, str]]:
    grouped: Counter = Counter()
    for context in contexts:
        for row in list(context.get(row_key, [])):
            player = str(row.get("player", ""))
            name = str(row.get(name_key, ""))
            if player and name:
                grouped[(player, name)] += parse_int(row.get("count", 0))
    return [
        {"player": player, name_key: name, "count": str(count)}
        for (player, name), count in sorted(grouped.items())
    ]


def combine_correlation_rows(contexts: list[dict[str, object]]) -> list[dict[str, object]]:
    grouped: dict[tuple[str, str], dict[str, object]] = {}
    for context in contexts:
        for row in list(context.get("correlation_rows", [])):
            key = (str(row.get("giver", "")), str(row.get("receiver", "")))
            if not key[0] or not key[1]:
                continue
            current = grouped.setdefault(key, {"giver": key[0], "receiver": key[1], "amount": 0, "games": 0})
            current["amount"] = int(current["amount"]) + parse_int(row.get("amount", 0))
            current["games"] = int(current["games"]) + parse_int(row.get("games", 0))
    return sorted(grouped.values(), key=lambda row: int(row["amount"]), reverse=True)


def combine_contexts(key: str, label: str, contexts: list[dict[str, object]]) -> dict[str, object]:
    rows = combine_player_rows(contexts)
    if not rows:
        return build_context(key, label, set())
    total_player_games = sum(parse_int(row.get("games", 0)) for row in rows)
    total_rounds = sum(parse_int(row.get("rounds", 0)) for row in rows) // 3
    total_yakuman = sum(parse_int(row.get("yakuman_count", 0)) for row in rows)
    best_score = max(rows, key=lambda row: parse_float(row.get("earned_score", 0)))
    best_top = max(rows, key=lambda row: pct_number(row.get("rank1_rate", "")))
    return {
        "key": key,
        "label": label,
        "rows": rows,
        "yakuman_rows": combine_named_count_rows(contexts, "yakuman_rows", "yakuman_name"),
        "yakuman_detail_rows": [
            dict(row)
            for context in contexts
            for row in list(context.get("yakuman_detail_rows", []))
        ],
        "correlation_rows": combine_correlation_rows(contexts),
        "total_games": total_player_games // 3,
        "total_rounds": total_rounds,
        "total_yakuman": total_yakuman,
        "best_score": best_score,
        "best_top": best_top,
        "team_rows": [],
        "team_champion_rows": [],
        "season_mvp_rows": [],
        "is_cumulative": True,
    }


def main() -> None:
    refresh_old_cache = "--refresh-old-cache" in sys.argv
    old_context, old_season_contexts = build_old_contexts(refresh_cache=refresh_old_cache)

    new_paifu_rows = read_new_league_paifu_rows()
    if not old_context.get("rows") and not new_paifu_rows:
        raise SystemExit("牌譜ID CSV が見つからないか空です。先に牌譜IDを収集してください。")

    new_season_to_uuids = group_uuids_by_season(new_paifu_rows)
    new_uuids = set().union(*new_season_to_uuids.values()) if new_season_to_uuids else set()

    new_season_contexts = build_season_contexts(
        new_season_to_uuids,
        "new",
        "新シーズン",
        NEW_LEAGUE_FULL_GAMES,
    )

    new_context = build_context("new-league", "新リーグ", new_uuids)
    add_context_awards(new_context, new_season_contexts)
    lifetime_context = combine_contexts("lifetime", "通算", [old_context, new_context])
    add_context_awards(lifetime_context, new_season_contexts + old_season_contexts)

    contexts = [new_context] + new_season_contexts + [lifetime_context, old_context] + old_season_contexts
    new_player_names = sorted_player_names(new_context)
    lifetime_player_names = sorted_player_names(lifetime_context)

    season_tabs = "\n".join(
        f'<button class="tab-button{" active" if index == 0 else ""}" type="button" data-tab="{esc(context["key"])}">{esc(context["label"])}</button>'
        for index, context in enumerate(contexts)
    )
    new_player_tabs = "\n".join(
        f'<button class="tab-button player-tab" type="button" data-tab="new-player-{esc(player)}">{esc(player)}</button>'
        for player in new_player_names
    )
    lifetime_player_tabs = "\n".join(
        f'<button class="tab-button player-tab" type="button" data-tab="lifetime-player-{esc(player)}">{esc(player)}</button>'
        for player in lifetime_player_names
    )
    stats_panels = "\n".join(render_stats_panel(context) for context in contexts)
    new_player_panels = "\n".join(
        render_player_panel(
            player,
            new_context,
            new_season_contexts,
            panel_key=f"new-player-{player}",
            title_label="新リーグ",
            use_manual_analysis=False,
        )
        for player in new_player_names
    )
    lifetime_player_panels = "\n".join(
        render_player_panel(
            player,
            lifetime_context,
            new_season_contexts + old_season_contexts,
            panel_key=f"lifetime-player-{player}",
            title_label="通算",
            use_manual_analysis=False,
        )
        for player in lifetime_player_names
    )
    panels = stats_panels + "\n" + new_player_panels + "\n" + lifetime_player_panels

    html_text = f"""<!doctype html>
<html lang="ja">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>魚群リーグ</title>
  <script type="module">
    import mermaid from "https://cdn.jsdelivr.net/npm/mermaid@11/dist/mermaid.esm.min.mjs";
    // 図の描画は表示中のタブに限定する。startOnLoad: trueのままだと、
    // hidden(display:none)のパネル内の図を幅0のまま描画して潰れるうえ、
    // 初回表示で全タブ分の描画コストがかかる。タブ切替時はactivate()から呼ばれる。
    mermaid.initialize({{ startOnLoad: false, theme: "base", flowchart: {{ curve: "basis" }} }});
    window.renderMermaidIn = (root) => {{
      const nodes = Array.from((root || document).querySelectorAll(".mermaid:not([data-processed])"));
      if (nodes.length) mermaid.run({{ nodes }}).catch(() => {{}});
    }};
    window.renderMermaidIn(document.querySelector(".tab-panel:not([hidden])"));
  </script>
  <script>
    window.addEventListener("DOMContentLoaded", () => {{
      const buttons = Array.from(document.querySelectorAll("[data-tab]"));
      const panels = Array.from(document.querySelectorAll("[data-panel]"));

      function activate(key) {{
        buttons.forEach((button) => {{
          const active = button.dataset.tab === key;
          button.classList.toggle("active", active);
          button.setAttribute("aria-selected", active ? "true" : "false");
        }});
        panels.forEach((panel) => {{
          panel.hidden = panel.dataset.panel !== key;
        }});
        // 開いたタブの図をこのタイミングで初描画する（hiddenのまま描画すると潰れる）。
        // モジュール読込失敗時はrenderMermaidInが未定義なので何もしない（図は生テキスト表示）。
        const activePanel = panels.find((panel) => panel.dataset.panel === key);
        if (activePanel && window.renderMermaidIn) window.renderMermaidIn(activePanel);
      }}

      buttons.forEach((button) => {{
        button.addEventListener("click", () => activate(button.dataset.tab));
      }});

      const metricModal = document.querySelector("[data-metric-modal]");
      const metricTitle = metricModal ? metricModal.querySelector("#metric-modal-title") : null;
      const metricBody = metricModal ? metricModal.querySelector("[data-metric-body]") : null;

      function closeMetricModal() {{
        if (!metricModal) return;
        metricModal.hidden = true;
      }}

      document.querySelectorAll("[data-metric-title]").forEach((button) => {{
        button.addEventListener("click", () => {{
          if (!metricModal || !metricTitle || !metricBody) return;
          metricTitle.textContent = button.dataset.metricTitle || "項目説明";
          if (button.dataset.metricHtml) {{
            metricBody.innerHTML = button.dataset.metricHtml;
          }} else {{
            metricBody.textContent = button.dataset.metricBody || "";
          }}
          metricModal.hidden = false;
          const closeButton = metricModal.querySelector(".metric-modal-close");
          if (closeButton) closeButton.focus();
        }});
      }});

      document.querySelectorAll("[data-metric-close]").forEach((button) => {{
        button.addEventListener("click", closeMetricModal);
      }});

      document.addEventListener("keydown", (event) => {{
        if (event.key === "Escape") closeMetricModal();
      }});

      if (buttons[0]) activate(buttons[0].dataset.tab);
    }});
  </script>
  <style>
    :root {{
      color-scheme: light;
      --ink: #17202a;
      --muted: #687582;
      --line: #d8dee6;
      --fill: #f6f8fa;
      --panel: #ffffff;
      --accent: #0f766e;
      --accent-soft: #dff6f1;
      --gold: #9a6700;
      --danger: #b42318;
    }}
    * {{ box-sizing: border-box; }}
    body {{ margin: 0; color: var(--ink); background: #fff; font-family: system-ui, "Yu Gothic", "Meiryo", sans-serif; }}
    header {{ padding: 30px 32px 18px; border-bottom: 1px solid var(--line); background: linear-gradient(180deg, #fbfcfd, #fff); }}
    h1 {{ margin: 0 0 8px; font-size: 30px; letter-spacing: .02em; }}
    h2 {{ margin: 30px 0 12px; font-size: 20px; }}
    h3 {{ margin: 0; font-size: 16px; }}
    p {{ margin: 0; color: var(--muted); }}
    main {{ padding: 22px 32px 44px; }}
    .tabs {{ display: flex; flex-wrap: wrap; gap: 8px; margin: 0 0 20px; }}
    .tab-groups {{ display: grid; gap: 14px; margin: 0 0 20px; }}
    .tab-group h2 {{ margin: 0 0 8px; font-size: 15px; color: var(--muted); }}
    .tab-group .tabs {{ margin: 0; }}
    .tab-button {{ appearance: none; border: 1px solid var(--line); background: #fff; color: var(--ink); border-radius: 8px; padding: 8px 12px; font: inherit; font-weight: 700; cursor: pointer; }}
    .tab-button:hover {{ border-color: var(--accent); color: var(--accent); }}
    .tab-button.active {{ background: var(--accent); border-color: var(--accent); color: #fff; }}
    .player-tab {{ border-style: dashed; }}
    .tab-panel[hidden] {{ display: none; }}
    .summary {{ display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 10px; margin-bottom: 20px; }}
    .summary div {{ border: 1px solid var(--line); border-radius: 8px; padding: 12px; background: var(--fill); }}
    .summary span {{ display: block; color: var(--muted); font-size: 12px; }}
    .summary strong {{ display: block; margin-top: 4px; font-size: 20px; }}
    .section-band {{ padding: 2px 0 8px; }}
    .ranking-grid {{ display: grid; grid-template-columns: 1fr 1fr; gap: 12px; margin-top: 12px; }}
    .ranking-panel {{ min-width: 0; }}
    .ranking-panel h3 {{ margin: 0 0 8px; font-size: 16px; }}
    .analysis-grid {{ display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 12px; }}
    .analysis-card {{ border: 1px solid var(--line); border-radius: 8px; padding: 14px; background: var(--panel); }}
    .analysis-card h3 {{ margin-bottom: 8px; }}
    .analysis-card p {{ line-height: 1.8; color: var(--ink); }}
    .metric-best td {{ background: #fff7df; }}
    .metric-best td:first-child {{ color: var(--gold); }}
    .metric-best td:nth-child(3) {{ font-weight: 800; color: var(--gold); }}
    .metric-worst td {{ background: #f1f3f5; color: #6b7280; }}
    .metric-worst td:first-child {{ color: #4b5563; }}
    .metric-worst td:nth-child(3) {{ font-weight: 800; }}
    .cards {{ display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 12px; }}
    .player-card, .yakuman-card {{ border: 1px solid var(--line); border-radius: 8px; padding: 14px; background: var(--panel); }}
    .player-card-head {{ display: flex; justify-content: space-between; gap: 10px; align-items: baseline; margin-bottom: 12px; }}
    .player-card-head span {{ color: var(--accent); font-weight: 700; font-size: 13px; white-space: nowrap; }}
    .meter-row {{ position: relative; display: grid; grid-template-columns: 58px 54px 1fr; align-items: center; gap: 8px; margin: 8px 0; font-size: 12px; color: var(--muted); }}
    .meter-row b {{ color: var(--ink); text-align: right; }}
    .meter-row i {{ display: block; height: 8px; border-radius: 999px; background: linear-gradient(90deg, var(--accent) var(--w), var(--fill) var(--w)); border: 1px solid var(--line); }}
    .meter-row.danger i {{ background: linear-gradient(90deg, var(--danger) var(--w), var(--fill) var(--w)); }}
    .mini-stats {{ display: grid; grid-template-columns: 1fr 1fr; gap: 8px; margin-top: 12px; }}
    .mini-stats div {{ background: var(--fill); border-radius: 6px; padding: 8px; }}
    .mini-stats span {{ display: block; font-size: 11px; color: var(--muted); }}
    .mini-stats strong {{ font-size: 17px; }}
    .digest-cards {{ margin-bottom: 18px; }}
    .digest-metrics {{ display: grid; gap: 7px; }}
    .digest-metric {{ display: grid; grid-template-columns: minmax(86px, 1fr) auto auto; align-items: baseline; gap: 8px; padding: 7px 8px; border-radius: 6px; background: var(--fill); }}
    .digest-metric span {{ color: var(--muted); font-size: 12px; }}
    .digest-metric strong {{ font-size: 15px; }}
    .digest-metric em {{ font-style: normal; color: var(--accent); font-size: 12px; font-weight: 800; white-space: nowrap; }}
    .table-wrap {{ position: relative; max-width: 100%; overflow-x: auto; border: 1px solid var(--line); border-radius: 8px; -webkit-overflow-scrolling: touch; isolation: isolate; }}
    table {{ border-collapse: separate; border-spacing: 0; width: 100%; min-width: 920px; font-size: 14px; }}
    th, td {{ border-bottom: 1px solid var(--line); padding: 8px 9px; text-align: right; white-space: nowrap; background: #fff; }}
    th {{ background: var(--fill); font-weight: 700; color: #30363d; }}
    tr:last-child td {{ border-bottom: 0; }}
    td.name, th:nth-child(2), th.sticky-name {{ text-align: left; font-weight: 700; }}
    td.sticky-rank, th.sticky-rank {{ position: sticky; left: 0; z-index: 5; width: 44px; min-width: 44px; max-width: 44px; text-align: center; background: #fff; box-shadow: 1px 0 0 var(--line); background-clip: padding-box; }}
    td.sticky-name, th.sticky-name {{ position: sticky; left: 0; z-index: 4; min-width: 132px; max-width: 184px; background: #fff; box-shadow: 1px 0 0 var(--line), 8px 0 12px rgba(23, 32, 42, .05); background-clip: padding-box; }}
    tr > .sticky-rank + .sticky-name {{ left: 44px; }}
    th.sticky-rank, th.sticky-name {{ z-index: 6; background: var(--fill); }}
    .metric-best td.sticky-name {{ background: #fff7df; }}
    .metric-worst td.sticky-name {{ background: #f1f3f5; }}
    td.roles {{ text-align: left; white-space: normal; min-width: 240px; }}
    .metric-help {{ appearance: none; display: inline-flex; align-items: center; justify-content: flex-end; gap: 5px; border: 0; padding: 0; background: transparent; color: inherit; font: inherit; font-weight: 800; cursor: pointer; }}
    .metric-help:hover {{ color: var(--accent); }}
    .metric-help span {{ display: inline-grid; place-items: center; width: 16px; height: 16px; border-radius: 999px; background: var(--accent-soft); color: var(--accent); font-size: 11px; line-height: 1; }}
    .metric-value-help {{ appearance: none; border: 0; padding: 0; background: transparent; color: var(--accent); font: inherit; font-weight: 900; cursor: pointer; }}
    .metric-value-help:hover {{ text-decoration: underline; text-underline-offset: 3px; }}
    .metric-modal[hidden] {{ display: none; }}
    .metric-modal {{ position: fixed; inset: 0; z-index: 50; display: grid; place-items: center; padding: 18px; }}
    .metric-modal-backdrop {{ position: absolute; inset: 0; background: rgba(23, 32, 42, .38); }}
    .metric-modal-panel {{ position: relative; z-index: 1; width: min(760px, 100%); max-height: min(84vh, 720px); overflow: auto; border: 1px solid var(--line); border-radius: 8px; padding: 20px; background: #fff; box-shadow: 0 18px 50px rgba(23, 32, 42, .22); }}
    .metric-modal-panel h2 {{ margin: 0 0 10px; font-size: 18px; }}
    .metric-modal-body {{ color: var(--ink); line-height: 1.8; white-space: normal; }}
    .metric-modal-body p {{ margin: 0 0 12px; color: var(--ink); }}
    .metric-modal-body .table-wrap {{ margin-top: 10px; }}
    .metric-modal-body table {{ min-width: 560px; }}
    .metric-modal-close {{ appearance: none; margin-top: 18px; border: 1px solid var(--accent); border-radius: 8px; padding: 8px 14px; background: var(--accent); color: #fff; font: inherit; font-weight: 800; cursor: pointer; }}
    .metric-modal-close:hover {{ filter: brightness(.94); }}
    .yakuman-grid {{ display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 12px; }}
    .yakuman-card h3 {{ margin-bottom: 8px; }}
    .yakuman-card ul {{ list-style: none; padding: 0; margin: 0; display: grid; gap: 6px; }}
    .yakuman-card li {{ display: grid; gap: 7px; padding: 9px 10px; border-radius: 6px; background: var(--accent-soft); }}
    .yakuman-title, .victims div {{ display: flex; justify-content: space-between; gap: 10px; }}
    .yakuman-title strong, .victims strong {{ color: var(--gold); }}
    .victims {{ display: grid; gap: 4px; padding-top: 7px; border-top: 1px solid rgba(15, 118, 110, .18); }}
    .victims em {{ font-style: normal; color: var(--muted); font-size: 11px; }}
    .victims div {{ font-size: 12px; }}
    .mermaid {{ border: 1px solid var(--line); border-radius: 8px; padding: 14px; overflow: auto; background: #fff; margin: 8px 0 16px; }}
    .subnote {{ margin: -4px 0 12px; color: var(--muted); }}
    .split-tables {{ display: grid; gap: 14px; }}
    .stat-table-panel {{ min-width: 0; }}
    .stat-table-panel h3 {{ margin: 0 0 8px; color: var(--accent); font-size: 15px; }}
    .generated-note {{ margin-top: 18px; font-size: 12px; }}
    footer {{ padding: 18px 32px 30px; border-top: 1px solid var(--line); color: var(--muted); font-size: 12px; }}
    @media (max-width: 920px) {{
      header, main, footer {{ padding-left: 16px; padding-right: 16px; }}
      .summary {{ grid-template-columns: 1fr 1fr; }}
      .ranking-grid {{ grid-template-columns: 1fr; }}
      .analysis-grid {{ grid-template-columns: 1fr; }}
      .cards, .yakuman-grid {{ grid-template-columns: 1fr; }}
      .digest-metric {{ grid-template-columns: minmax(82px, 1fr) auto auto; }}
      td.sticky-name, th.sticky-name {{ width: 112px; min-width: 112px; max-width: 112px; overflow: hidden; text-overflow: ellipsis; }}
      h1 {{ font-size: 26px; }}
    }}
  </style>
</head>
<body>
  <header>
    <h1>魚群リーグ</h1>
  </header>
  <main>
    <section class="tab-groups" aria-label="ページ切り替え">
      <div class="tab-group">
        <h2>シーズンメニュー</h2>
        <nav class="tabs" aria-label="シーズンメニュー" role="tablist">
          {season_tabs}
        </nav>
      </div>
      <div class="tab-group">
        <h2>新リーグ個人データ</h2>
        <nav class="tabs" aria-label="新リーグ個人データ" role="tablist">
          {new_player_tabs}
        </nav>
      </div>
      <div class="tab-group">
        <h2>通算個人データ</h2>
        <nav class="tabs" aria-label="通算個人データ" role="tablist">
          {lifetime_player_tabs}
        </nav>
      </div>
    </section>
    {panels}
  </main>
  <div class="metric-modal" data-metric-modal hidden>
    <div class="metric-modal-backdrop" data-metric-close></div>
    <section class="metric-modal-panel" role="dialog" aria-modal="true" aria-labelledby="metric-modal-title">
      <h2 id="metric-modal-title">項目説明</h2>
      <div class="metric-modal-body" data-metric-body></div>
      <button class="metric-modal-close" type="button" data-metric-close>閉じる</button>
    </section>
  </div>
  <footer>
    Generated from collected Mahjong Soul records.
  </footer>
</body>
</html>
"""

    write_site_pages(html_text)


if __name__ == "__main__":
    main()
