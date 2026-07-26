from __future__ import annotations

import csv
import html
from collections import defaultdict
from pathlib import Path


SUMMARY_CSV = Path("summary.csv")
YAKUMAN_CSV = Path("yakuman_summary.csv")
OUTPUT_HTML = Path("docs") / "index.html"


LABELS = {
    "rank": "順位",
    "player": "プレイヤー",
    "games": "対戦数",
    "rank1_rate": "1位率",
    "rank2_rate": "2位率",
    "rank3_rate": "3位率",
    "average_rank": "平均順位",
    "rounds": "参加局数",
    "average_hu_point": "平均和了点",
    "hu_rate": "和了率",
    "tsumo_rate": "ツモ率",
    "houjuu_rate": "放銃率",
    "called_rate": "副露率",
    "riichi_rate": "立直率",
    "max_final_point": "最高終了時持ち点",
    "min_final_point": "最低終了時持ち点",
    "yakuman_count": "役満回数",
}


MAIN_COLUMNS = [
    "player",
    "games",
    "average_rank",
    "rank1_rate",
    "rank2_rate",
    "rank3_rate",
    "hu_rate",
    "tsumo_rate",
    "houjuu_rate",
    "called_rate",
    "riichi_rate",
    "yakuman_count",
]


DETAIL_COLUMNS = [
    "player",
    "rounds",
    "average_hu_point",
    "max_final_point",
    "min_final_point",
]


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


def table(rows: list[dict[str, str]], columns: list[str], rank_by: str | None = None) -> str:
    if rank_by:
        ranked = sorted(rows, key=lambda r: float(r.get(rank_by, "999") or 999))
    else:
        ranked = rows

    head = "".join(f"<th>{esc(LABELS[c])}</th>" for c in (["rank"] + columns if rank_by else columns))
    body_rows = []
    for i, row in enumerate(ranked, 1):
        cells = []
        if rank_by:
            cells.append(f"<td>{i}</td>")
        for col in columns:
            value = row.get(col, "")
            cls = "name" if col == "player" else ""
            if col in {"average_hu_point", "max_final_point", "min_final_point"}:
                value = number(value)
            cells.append(f"<td class=\"{cls}\">{esc(value)}</td>")
        body_rows.append("<tr>" + "".join(cells) + "</tr>")
    return f"<table><thead><tr>{head}</tr></thead><tbody>{''.join(body_rows)}</tbody></table>"


def rate_cards(rows: list[dict[str, str]]) -> str:
    cards = []
    for row in sorted(rows, key=lambda r: float(r.get("average_rank", "999") or 999)):
        name = row["player"]
        top = row.get("rank1_rate", "0%")
        hu = row.get("hu_rate", "0%")
        deal_in = row.get("houjuu_rate", "0%")
        yakuman = row.get("yakuman_count", "0")
        cards.append(
            f"""
            <article class="player-card">
              <div class="player-card-head">
                <h3>{esc(name)}</h3>
                <span>平均順位 {esc(row.get("average_rank", ""))}</span>
              </div>
              <div class="meter-row"><span>1位率</span><b>{esc(top)}</b><i style="--w:{pct_number(top)}%"></i></div>
              <div class="meter-row"><span>和了率</span><b>{esc(hu)}</b><i style="--w:{pct_number(hu)}%"></i></div>
              <div class="meter-row danger"><span>放銃率</span><b>{esc(deal_in)}</b><i style="--w:{pct_number(deal_in)}%"></i></div>
              <div class="mini-stats">
                <div><span>対戦数</span><strong>{esc(row.get("games", ""))}</strong></div>
                <div><span>役満</span><strong>{esc(yakuman)}</strong></div>
              </div>
            </article>
            """
        )
    return "\n".join(cards)


def yakuman_section(yakuman_rows: list[dict[str, str]]) -> str:
    grouped: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in yakuman_rows:
        grouped[row["player"]].append(row)

    if not yakuman_rows:
        return "<p class=\"empty\">役満記録なし</p>"

    blocks = []
    for player, rows in sorted(grouped.items()):
        items = "".join(
            f"<li><span>{esc(r['yakuman_name'])}</span><strong>{esc(r['count'])}</strong></li>"
            for r in sorted(rows, key=lambda r: (-int(r["count"]), r["yakuman_name"]))
        )
        blocks.append(f"<article class=\"yakuman-card\"><h3>{esc(player)}</h3><ul>{items}</ul></article>")
    return "\n".join(blocks)


def main() -> None:
    rows = read_csv(SUMMARY_CSV)
    yakuman_rows = read_csv(YAKUMAN_CSV)
    if not rows:
        raise SystemExit("summary.csv が見つからないか空です。先に python aggregate_league.py を実行してください。")

    total_player_games = sum(int(r["games"]) for r in rows)
    total_games = total_player_games // 3
    total_rounds = sum(int(r["rounds"]) for r in rows) // 3
    total_yakuman = sum(int(r.get("yakuman_count", 0)) for r in rows)
    best_avg = min(rows, key=lambda r: float(r["average_rank"]))
    best_top = max(rows, key=lambda r: pct_number(r["rank1_rate"]))

    html_text = f"""<!doctype html>
<html lang="ja">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>雀魂リーグスタッツ</title>
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
    .summary {{ display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 10px; margin-bottom: 20px; }}
    .summary div {{ border: 1px solid var(--line); border-radius: 8px; padding: 12px; background: var(--fill); }}
    .summary span {{ display: block; color: var(--muted); font-size: 12px; }}
    .summary strong {{ display: block; margin-top: 4px; font-size: 20px; }}
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
    .table-wrap {{ overflow-x: auto; border: 1px solid var(--line); border-radius: 8px; }}
    table {{ border-collapse: collapse; width: 100%; min-width: 920px; font-size: 14px; }}
    th, td {{ border-bottom: 1px solid var(--line); padding: 8px 9px; text-align: right; white-space: nowrap; }}
    th {{ background: var(--fill); font-weight: 700; color: #30363d; }}
    tr:last-child td {{ border-bottom: 0; }}
    td.name, th:nth-child(2) {{ text-align: left; font-weight: 700; }}
    .yakuman-grid {{ display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 12px; }}
    .yakuman-card h3 {{ margin-bottom: 8px; }}
    .yakuman-card ul {{ list-style: none; padding: 0; margin: 0; display: grid; gap: 6px; }}
    .yakuman-card li {{ display: flex; justify-content: space-between; gap: 10px; padding: 7px 8px; border-radius: 6px; background: var(--accent-soft); }}
    .yakuman-card strong {{ color: var(--gold); }}
    footer {{ padding: 18px 32px 30px; border-top: 1px solid var(--line); color: var(--muted); font-size: 12px; }}
    @media (max-width: 920px) {{
      header, main, footer {{ padding-left: 16px; padding-right: 16px; }}
      .summary {{ grid-template-columns: 1fr 1fr; }}
      .cards, .yakuman-grid {{ grid-template-columns: 1fr; }}
      h1 {{ font-size: 26px; }}
    }}
  </style>
</head>
<body>
  <header>
    <h1>雀魂リーグスタッツ</h1>
    <p>大会「テスト」シーズン1集計。順位率、平均和了点、和了率、ツモ率、放銃率、副露率、立直率、役満内訳。</p>
  </header>
  <main>
    <section class="summary" aria-label="集計概要">
      <div><span>対象半荘</span><strong>{total_games:,}</strong></div>
      <div><span>対象局数</span><strong>{total_rounds:,}</strong></div>
      <div><span>平均順位トップ</span><strong>{esc(best_avg["player"])}</strong></div>
      <div><span>役満合計</span><strong>{total_yakuman:,}</strong></div>
    </section>

    <h2>個人成績ダイジェスト</h2>
    <section class="cards">
      {rate_cards(rows)}
    </section>

    <h2>個人成績ランキング</h2>
    <div class="table-wrap">
      {table(rows, MAIN_COLUMNS, rank_by="average_rank")}
    </div>

    <h2>詳細スタッツ</h2>
    <div class="table-wrap">
      {table(rows, DETAIL_COLUMNS, rank_by="average_rank")}
    </div>

    <h2>役満内訳</h2>
    <section class="yakuman-grid">
      {yakuman_section(yakuman_rows)}
    </section>
  </main>
  <footer>
    Generated from summary.csv and yakuman_summary.csv. 1位率トップ: {esc(best_top["player"])} ({esc(best_top["rank1_rate"])})
  </footer>
</body>
</html>
"""

    OUTPUT_HTML.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_HTML.write_text(html_text, encoding="utf-8")
    print(f"saved: {OUTPUT_HTML}")


if __name__ == "__main__":
    main()
