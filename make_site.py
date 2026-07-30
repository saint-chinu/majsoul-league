from __future__ import annotations

import csv
import html
from collections import defaultdict
from itertools import combinations
from pathlib import Path
import re


SUMMARY_CSV = Path("summary.csv")
YAKUMAN_CSV = Path("yakuman_summary.csv")
YAKUMAN_DETAILS_CSV = Path("yakuman_details.csv")
PAIFU_CSV = Path("admin_paifu_ids.csv")
TEAM_CSV = Path("team_members.csv")
OUTPUT_HTML = Path("docs") / "index.html"
RAW_DIR = Path("records_raw")
SEASON_FILE_RE = re.compile(r"admin_paifu_ids_season(\d+)\.csv$")


LABELS = {
    "rank": "順位",
    "player": "プレイヤー",
    "games": "対戦数",
    "earned_score": "獲得スコア",
    "rank1_rate": "1位率",
    "rank2_rate": "2位率",
    "rank3_rate": "3位率",
    "last_avoid_rate": "ラス回避率",
    "average_rank": "平均順位",
    "rounds": "参加局数",
    "average_hu_point": "平均和了点",
    "hu_rate": "和了率",
    "tsumo_rate": "ツモ率",
    "houjuu_rate": "放銃率",
    "average_houjuu_point": "放銃平均打点",
    "top_keep_rate": "トップキープ率",
    "average_opening_shanten": "平均配牌シャンテン",
    "average_opening_dora": "平均配牌ドラ",
    "called_rate": "副露率",
    "riichi_rate": "立直率",
    "max_final_point": "最高終了時持ち点",
    "min_final_point": "最低終了時持ち点",
    "yakuman_count": "役満回数",
    "season": "シーズン",
    "metric": "項目",
    "value": "値",
    "rank_text": "順位",
    "direction": "評価",
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
    "houjuu_rate",
    "average_houjuu_point",
    "top_keep_rate",
    "tsumo_rate",
    "average_opening_shanten",
    "average_opening_dora",
    "called_rate",
    "riichi_rate",
    "yakuman_count",
]


DETAIL_COLUMNS = [
    "player",
    "rounds",
    "average_hu_point",
    "average_houjuu_point",
    "top_keep_rate",
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
    "houjuu_rate",
    "average_houjuu_point",
    "top_keep_rate",
    "tsumo_rate",
    "called_rate",
    "riichi_rate",
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
    "houjuu_rate",
    "average_houjuu_point",
    "top_keep_rate",
    "tsumo_rate",
    "called_rate",
    "riichi_rate",
    "yakuman_count",
]


PLAYER_RANK_METRICS = [
    ("earned_score", True, "高い方が上位"),
    ("average_rank", False, "低い方が上位"),
    ("rank1_rate", True, "高い方が上位"),
    ("last_avoid_rate", True, "高い方が上位"),
    ("hu_rate", True, "高い方が上位"),
    ("average_hu_point", True, "高い方が上位"),
    ("tsumo_rate", True, "高い方が上位"),
    ("houjuu_rate", False, "低い方が上位"),
    ("average_houjuu_point", False, "低い方が上位"),
    ("top_keep_rate", True, "高い方が上位"),
    ("called_rate", True, "高い順"),
    ("riichi_rate", True, "高い順"),
    ("yakuman_count", True, "高い方が上位"),
]


MANUAL_PLAYER_ANALYSIS: dict[str, tuple[str, str, str]] = {
    "流れ者金融": (
        "リーグ全体で一人だけ別の収支帯にいる支配型。累計獲得スコア、平均順位、1位率、ラス回避率、トップキープ率がすべて高く、しかも和了率も高い。単に守って浮いているのではなく、局を取りに行く回数を確保しながら、放銃平均打点を最も軽い水準に抑えているのが異常に強い。副露率も高く、三麻でありがちな「門前で待っている間に相手へ先制される」展開を嫌い、自分から局速度を作っている。S3、S5、S8のように大きく勝つシーズンがありつつ、悪いシーズンでも崩れ切らないので、実力の下限が高いタイプ。",
        "最大の強みは、攻撃量と失点管理が同時に成立していること。高いトップ率を出す人は放銃やラス率も重くなりがちだが、流れ者金融はトップを取りに行く局と、半荘を壊さない局の切り替えがかなり早い。副露で先にテンパイを入れ、相手が押し返してきたら自分の手価値と着順状況で押し引きを変える。この判断の速さがトップキープ率と平均順位に出ている。S8の57.14%トップ率、50.00%トップキープ率はかなり象徴的で、リードした後の局消化も、さらに突き放す攻撃も両方できている。",
        "改善点は、強者ゆえの過剰参加をさらに削ること。現状でも圧倒的に勝っているが、S4のようにトップキープ率が落ちたシーズンを見ると、リード後に相手の勝負手とぶつかる局がまだ少しある。特に南場トップ目、親番を落とした後の2着目、役あり愚形テンパイの終盤押しは、期待値より着順固定の価値が高い場面がある。もう一段冷たくするなら、満貫未満の押し返し基準を局面別に細分化したい。今後の課題は強くなることより、勝っている半荘をどれだけ事故らせず閉じるか。",
    ),
    "ひなんじょ": (
        "門前リーチで主導権を取る圧力型。累計でプラスを残し、平均順位も上位、和了率も高い。立直率がリーグ内で最も高い水準で、手が入った時にダマや軽い仕掛けへ逃げず、リーチで打点とツモ抽選を取りに行く姿勢がはっきりしている。S4、S7、S9で大きく勝っており、好調期はトップ率とラス回避率が同時に上がる。反面、放銃率と放銃平均打点は軽くないので、攻撃が噛み合わないシーズンではS5やS8のように一気に沈む。強い時の破壊力と、負ける時の削られ方の差が大きいプレイヤー。",
        "強みは、相手に対応を強制できる先制リーチの質。高い立直率なのに和了率が落ちていないので、無理なリーチ連打ではなく、テンパイ速度と形の作り方が噛み合っている。ツモ率も高く、相手が降りても局収支を取り切れるのが大きい。S7はラス回避78.69%で、トップキープ率は低めでも全体収支を大きく伸ばしており、無理に全半荘をトップで締めるより、2着を拾いながら爆発半荘で稼ぐ設計が合っている。",
        "改善点は、リーチ後ではなくリーチ前の押し引き。リーチしてからはもう勝負なので、差が出るのは一向聴から危険牌を押すか、テンパイの質を待つかの判断。特に親の濃い副露、ドラが見えている終盤、他家リーチ後の追いつき一向聴では、刺さった時の平均失点が重い。攻撃力を削る必要はないが、リーチに行ける局と、門前で粘った結果ただ危険牌を切らされる局を分けたい。S9のようにトップ率を出せる力はあるので、大沈みシーズンを減らせば流れ者金融を追う最有力になる。",
    ),
    "鯛ofカルピス": (
        "自力決着力の高いツモ攻撃型。ツモ率がリーグトップで、和了率も高い。相手からロンを取るというより、テンパイを入れて自分で山から引き切る局が多く、守備的な相手にも点棒を動かせるのが大きな個性。S1、S3、S5、S9のようにプラスを作るシーズンでは、トップ率もラス回避も高く、半荘のどこかで大きい和了を引いて着順を押し上げている。一方、放銃率は最も重い水準で、S7、S8のように失点が先行すると、和了力があっても取り返し切れない展開になる。",
        "強みは、勝負手の決着率。和了率が高いだけなら軽い仕掛け型にも見えるが、ツモ率48%超という数字がかなり特徴的で、リーチでも副露でも最後に自分で引いてくる局が多い。親番や高打点手を持った時の期待値が高く、相手が全員受けに回っても局収支を取れる。S9で持ち直している点も良く、S8の大きなマイナスから攻撃の質を戻している。トップキープ率も悪くなく、先行できた時は押し切れる。",
        "改善点は、攻撃をやめるタイミングの明確化。和了力が高いので押したくなるのは自然だが、現状は放銃率が成績の天井を抑えている。特に他家親番の終盤、ドラポンや染め手気配、リーチ後の無筋連打に対して、自分の待ちが良くない時まで同じ温度で押すと失点期待値が跳ねる。ツモ力は武器なので丸くしすぎる必要はない。むしろ「この局は押し切る」と「ここは自分の局ではない」を早く決めることで、攻撃力を残したままマイナスシーズンの底を浅くできる。",
    ),
    "アリスkey": (
        "改善型のバランス派。累計スコアはまだマイナスだが、シーズン推移を見るとS5の大沈みからS6、S7で明確に立て直している。副露率が高く、手数で局へ参加するタイプだが、ただ鳴き散らかすだけではなく、S7では和了率30%超、放銃率13.29%、トップ率40.35%まで伸ばしている。ラス回避率も累計では悪くなく、沈みっぱなしになるタイプではない。課題は、安定している時でもトップキープ率がやや低く、リードを最後まで点数に変換し切れていないこと。",
        "強みは、修正力と速度参加。序盤から中盤にかけての悪い内容を引きずらず、後半シーズンで放銃率と平均順位を改善しているのは大きい。副露率が高いので、配牌が重い局でも完全に傍観者になりにくい。S2やS7のように噛み合うとしっかりプラスを作れるし、S8も大崩れせず踏みとどまっている。今のアリスkeyは、序盤の印象よりかなり現実的に戦えている。伸びしろは「守備を覚える」段階ではなく、「勝ち切る局を選ぶ」段階に移っている。",
        "改善点は、リード時と2着目の打ち方。ラス回避は悪くないのに累計スコアが伸び切らないのは、トップを取り切る局面で点棒を守りすぎるか、逆に安い仕掛けで局を流しすぎるかの揺れがある。トップ目では無理に打点を追わず現実的に局を進める、2着目では安い和了で満足せず親番や良形リーチで一度トップを取りに行く。この差をはっきりさせたい。S9は和了率は悪くないのにラス回避が落ちているので、最近は少し押し返しが強くなりすぎている可能性もある。",
    ),
    "29ちゃん": (
        "守備基盤の強いロースコア安定型。放銃率がリーグ最少で、放銃平均打点も軽い。三麻では一発の放銃で半荘が壊れるので、この失点管理はかなり価値がある。一方で和了率、立直率、平均和了点は控えめで、自分から局面を動かす回数は多くない。S4やS9のように攻撃が少し増えたシーズンは平均順位が良く、S5やS7のようにトップ率が落ちるとマイナスが大きくなる。つまり守備は本物だが、勝つ半荘を増やすには能動的な和了がもう少し必要。",
        "強みは、半荘を壊さないこと。相手の高打点気配に過剰に付き合わず、放銃を軽く済ませる力がある。ラス回避率も大崩れしておらず、S9では76.67%まで上がっていて復調が見える。役満回数も多く、守備一辺倒ではなく、チャンス手を大物に育てる爆発力も持っている。守備型なのに最大点が高いのは面白いところで、我慢している間に一撃で返すルートがある。",
        "改善点は、親番と南場ビハインド時の攻撃量。守備力があるぶん、序盤の良形や役牌対子、ドラ周辺をもう少し前向きに扱っても大事故にはなりにくい。特に親番での先制テンパイ、ラス目南場でのリーチ判断、2着目からトップを狙う局では、安牌を抱えすぎるより手牌効率を優先したい。守備を捨てる必要はないが、今の低放銃を維持したまま和了率を1〜2ポイント上げられると、平均順位はかなり改善する。",
    ),
    "葡萄海ぶどう": (
        "高打点志向のロマン砲型。平均和了点はトップ級で、リーチ率も高く、門前で高い手を作る意識がはっきりしている。和了した時の一撃は強く、相手からすると押し返しにくい打点レンジを持っている。ただし累計では大きなマイナスで、平均順位、ラス回避率、放銃率が苦しい。特にS9はトップ率18.64%、ラス回避47.46%、放銃率19.20%でかなり重く、高打点を狙う前に半荘が壊れる局が増えている。S5のように噛み合えばプラスを作れるので、方向性そのものではなく選択頻度が課題。",
        "強みは、局面を一発で変える打点構築力。細かい和了で刻むより、リーチや高打点手で着順をひっくり返す麻雀になっている。平均和了点が高いので、押す局の見返りは確かに大きい。これは丸く直しすぎると個性が消える。S5では和了率30.42%、放銃率15.56%、ラス回避70.69%まで整っていて、打点志向と失点管理が噛み合えばちゃんと勝てることも証明している。",
        "改善点は、勝負手ではない局の撤退を早くすること。高打点を作る価値がある局と、ただ遅く重いだけの局を分けたい。特に配牌で打点種が薄い局、親の仕掛けが速い局、南場で2着を守れば十分な局では、満貫ルートを無理に追わず、速度か守備へ寄せる方が良い。今の課題は攻撃力不足ではなく、攻撃に値しない局まで攻撃の温度が残ること。S9の数字を見る限り、まず放銃率を2ポイント下げるだけで、打点の強みが成績へ戻ってくる。",
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
    if col in {"average_opening_shanten", "average_opening_dora"}:
        return number(value, 2)
    if col in {"average_hu_point", "average_houjuu_point", "max_final_point", "min_final_point"}:
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

    head = "".join(f"<th>{esc(LABELS[c])}</th>" for c in (["rank"] + columns if rank_by else columns))
    body_rows = []
    for i, row in enumerate(ranked, 1):
        cells = []
        if rank_by:
            cells.append(f"<td>{i}</td>")
        for col in columns:
            value = row.get(col, "")
            cls = "name" if col == "player" else ""
            value = format_cell_value(col, value)
            cells.append(f"<td class=\"{cls}\">{value}</td>")
        body_rows.append("<tr>" + "".join(cells) + "</tr>")
    return f"<table><thead><tr>{head}</tr></thead><tbody>{''.join(body_rows)}</tbody></table>"


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
            f"<td>{i}</td>"
            f"<td class=\"name\">{esc(row['team'])}</td>"
            f"<td class=\"roles\">{esc(row['members'])}</td>"
            f"<td class=\"roles\">{esc(row['member_details'])}</td>"
            f"<td>{number(row['total_score'], 1)}</td>"
            f"<td>{number(row['total_games'])}</td>"
            "</tr>"
        )
    return (
        "<div class=\"table-wrap\">"
        "<table class=\"team-table\">"
        "<thead><tr><th>チーム順位</th><th>チーム</th><th>メンバー</th><th>単体成績</th><th>合計成績</th><th>合計対戦数</th></tr></thead>"
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
            f"<td>{i}</td>"
            f"<td class=\"name\">{esc(row['player'])}</td>"
            f"<td>{esc(row['wins'])}</td>"
            f"<td class=\"roles\">{esc(row['seasons'])}</td>"
            f"<td class=\"roles\">{esc(row['teams'])}</td>"
            "</tr>"
        )
    return (
        "<div class=\"table-wrap\">"
        "<table class=\"team-table\">"
        "<thead><tr><th>順位</th><th>プレイヤー</th><th>チーム優勝回数</th><th>優勝シーズン</th><th>優勝チーム</th></tr></thead>"
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
            f"<td>{i}</td>"
            f"<td class=\"name\">{esc(row['player'])}</td>"
            f"<td>{esc(row['wins'])}</td>"
            f"<td class=\"roles\">{esc(row['details'])}</td>"
            "</tr>"
        )
    return (
        "<div class=\"table-wrap\">"
        "<table class=\"team-table\">"
        "<thead><tr><th>順位</th><th>プレイヤー</th><th>MVP回数</th><th>内訳</th></tr></thead>"
        f"<tbody>{''.join(body)}</tbody></table>"
        "</div>"
    )


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
            f"<td>{i}</td>"
            f"<td class=\"name\">{esc(row['player'])}</td>"
            f"<td>{esc(row['count'])}</td>"
            f"<td class=\"roles\">{esc(row['roles'])}</td>"
            f"<td>{number(row['payment'])}</td>"
            "</tr>"
        )

    return (
        "<table class=\"yakuman-rank-table\">"
        f"<thead><tr><th>順位</th><th>プレイヤー</th><th>回数</th><th>役</th><th>{esc(payment_label)}</th></tr></thead>"
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
            f"<td>{i}</td>"
            f"<td class=\"name\">{esc(row['giver'])}</td>"
            f"<td class=\"name\">{esc(row['receiver'])}</td>"
            f"<td>{number(row['amount'])}</td>"
            f"<td>{esc(row['games'])}</td>"
            "</tr>"
        )

    return (
        "<table class=\"relation-table\">"
        "<thead><tr><th>順位</th><th>献上者</th><th>受取人</th><th>ネット献上点棒</th><th>直接対戦数</th></tr></thead>"
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


def read_season_paifu_rows() -> list[dict[str, str]]:
    rows_by_uuid: dict[str, dict[str, str]] = {}
    canonical_rows = read_csv(PAIFU_CSV)
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

    for path in sorted(Path(".").glob("admin_paifu_ids_season*.csv")):
        match = SEASON_FILE_RE.match(path.name)
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
            print(f"skip incomplete season {season}: {len(ready)}/{len(rows)} records ready")
            continue
        complete_rows.extend(rows)

    return sorted(complete_rows, key=lambda row: (int(row["season"]), row["uuid"]))


def aggregate_uuids(uuids: set[str]) -> tuple[list[dict[str, str]], list[dict[str, str]], list[dict[str, str]]]:
    try:
        from aggregate_league import PlayerStats, aggregate_game, average, percent
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
                "hu_rate": percent(player_stats.hu, player_stats.rounds),
                "tsumo_rate": percent(player_stats.tsumo, player_stats.hu),
                "houjuu_rate": percent(player_stats.houjuu, player_stats.rounds),
                "average_houjuu_point": str(average(player_stats.houjuu_point_sum, player_stats.houjuu, 1)),
                "top_keep_rate": percent(player_stats.top_keep_successes, player_stats.top_keep_chances),
                "average_opening_shanten": str(
                    average(player_stats.opening_shanten_sum, player_stats.opening_samples, 2)
                ),
                "average_opening_dora": str(
                    average(player_stats.opening_dora_sum, player_stats.opening_samples, 2)
                ),
                "called_rate": percent(player_stats.called, player_stats.rounds),
                "riichi_rate": percent(player_stats.riichi, player_stats.rounds),
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
    head = "".join(f"<th>{esc(LABELS[c])}</th>" for c in columns)
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
            f"<td class=\"name\">{esc(row['metric'])}</td>"
            f"<td>{row['value']}</td>"
            f"<td>{esc(row['rank_text'])}</td>"
            f"<td>{esc(row['direction'])}</td>"
            "</tr>"
        )
    return f"<table class=\"player-rank-table\"><thead><tr>{head}</tr></thead><tbody>{''.join(body)}</tbody></table>"


def player_analysis(player: str, cumulative_rows: list[dict[str, str]]) -> tuple[str, str, str]:
    if player in MANUAL_PLAYER_ANALYSIS:
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
) -> str:
    cumulative_rows = list(cumulative_context.get("rows", []))
    cumulative_row = player_row_from(cumulative_context, player)
    if not cumulative_row:
        return (
            f"<section class=\"tab-panel\" id=\"panel-player-{esc(player)}\" "
            f"data-panel=\"player-{esc(player)}\"><p class=\"empty\">{esc(player)}の集計データがありません。</p></section>"
        )

    season_rows = player_season_rows(player, season_contexts)
    rank_rows = player_metric_rank_rows(player, cumulative_rows)
    style, strength, advice = player_analysis(player, cumulative_rows)

    return f"""
    <section class="tab-panel" id="panel-player-{esc(player)}" data-panel="player-{esc(player)}">
      <section class="summary" aria-label="{esc(player)} 集計概要">
        <div><span>対戦数</span><strong>{number(cumulative_row.get("games", ""))}</strong></div>
        <div><span>獲得スコア</span><strong>{number(cumulative_row.get("earned_score", ""), 1)}</strong></div>
        <div><span>平均順位</span><strong>{esc(cumulative_row.get("average_rank", ""))}</strong></div>
        <div><span>役満回数</span><strong>{number(cumulative_row.get("yakuman_count", ""))}</strong></div>
      </section>

      <h2>{esc(player)} 累計成績</h2>
      <div class="table-wrap">
        {table([cumulative_row], PLAYER_MAIN_COLUMNS)}
      </div>

      <h2>{esc(player)} シーズン別推移</h2>
      <div class="table-wrap">
        {table(season_rows, PLAYER_SEASON_COLUMNS)}
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
    if context["key"] == "all":
        team_block_title = "チーム優勝経験"
        team_block = team_champion_section(list(context.get("team_champion_rows", [])))
        mvp_block = (
            "<h2>シーズンMVP経験</h2>"
            + season_mvp_section(list(context.get("season_mvp_rows", [])))
        )
    else:
        team_block_title = f"{context['label']} チーム成績"
        team_block = team_section(list(context.get("team_rows", [])))
        mvp_block = ""

    return f"""
    <section class="tab-panel" id="panel-{esc(context['key'])}" data-panel="{esc(context['key'])}">
      <section class="summary" aria-label="集計概要">
        <div><span>対象半荘</span><strong>{int(context['total_games']):,}</strong></div>
        <div><span>対象局数</span><strong>{int(context['total_rounds']):,}</strong></div>
        <div><span>獲得スコアトップ</span><strong>{esc(best_score["player"])}</strong></div>
        <div><span>役満合計</span><strong>{int(context['total_yakuman']):,}</strong></div>
      </section>

      <h2>{esc(context['label'])} 個人成績ランキング</h2>
      <div class="table-wrap">
        {table(rows, MAIN_COLUMNS, rank_by="earned_score", reverse=True)}
      </div>

      <h2>{esc(team_block_title)}</h2>
      {team_block}
      {mvp_block}

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

      <h2>個人成績ダイジェスト</h2>
      <section class="cards">
        {rate_cards(rows)}
      </section>

      <h2>詳細スタッツ</h2>
      <div class="table-wrap">
        {table(rows, DETAIL_COLUMNS, rank_by="average_rank")}
      </div>

      <h2>許されない相関図</h2>
      <p class="subnote">矢印は「左のプレイヤーが右のプレイヤーへ、同卓時の最終持ち点差でネット献上」。ラベルは 献上点棒 / 直接対戦数。</p>
      {correlation_mermaid(correlation_rows)}
      <div class="table-wrap">
        {correlation_table(correlation_rows)}
      </div>

      <h2>役満内訳</h2>
      <section class="yakuman-grid">
        {yakuman_section(yakuman_rows, yakuman_detail_rows)}
      </section>

      <p class="generated-note">1位率トップ: {esc(best_top["player"])} ({esc(best_top["rank1_rate"])})</p>
    </section>
    """


def display_season_label(season: int, latest_season: int, game_count: int) -> str:
    if season == latest_season and game_count < 120:
        return f"シーズン{season}（進行中）"
    return f"シーズン{season}"


def main() -> None:
    paifu_rows = read_season_paifu_rows()
    if not paifu_rows:
        raise SystemExit("admin_paifu_ids.csv が見つからないか空です。先に牌譜IDを収集してください。")

    season_to_uuids: dict[int, set[str]] = defaultdict(set)
    for row in paifu_rows:
        season = row.get("season", "")
        uuid = row.get("uuid", "")
        if season.isdigit() and uuid:
            season_to_uuids[int(season)].add(uuid)

    season_numbers = sorted(season_to_uuids)
    all_uuids = set().union(*season_to_uuids.values())
    teams_by_season = read_team_members()

    season_contexts = []
    latest_season = max(season_numbers)
    for season in sorted(season_numbers, reverse=True):
        label = display_season_label(season, latest_season, len(season_to_uuids[season]))
        season_contexts.append(
            build_context(
                f"season-{season}",
                label,
                season_to_uuids[season],
                season=season,
                teams_by_season=teams_by_season,
            )
        )

    cumulative_context = build_context("all", "累計", all_uuids)
    cumulative_context["team_champion_rows"] = team_champion_rows(season_contexts)
    cumulative_context["season_mvp_rows"] = season_mvp_rows(season_contexts)
    contexts = [cumulative_context] + season_contexts
    player_names = [
        row["player"]
        for row in sorted(
            list(cumulative_context.get("rows", [])),
            key=lambda r: float(r.get("earned_score", 0) or 0),
            reverse=True,
        )
        if row.get("player")
    ]

    season_tabs = "\n".join(
        f'<button class="tab-button{" active" if index == 0 else ""}" type="button" data-tab="{esc(context["key"])}">{esc(context["label"])}</button>'
        for index, context in enumerate(contexts)
    )
    player_tabs = "\n".join(
        f'<button class="tab-button player-tab" type="button" data-tab="player-{esc(player)}">{esc(player)}</button>'
        for player in player_names
    )
    stats_panels = "\n".join(render_stats_panel(context) for context in contexts)
    player_panels = "\n".join(
        render_player_panel(player, cumulative_context, season_contexts)
        for player in player_names
    )
    panels = stats_panels + "\n" + player_panels

    html_text = f"""<!doctype html>
<html lang="ja">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>魚群リーグ</title>
  <script type="module">
    import mermaid from "https://cdn.jsdelivr.net/npm/mermaid@11/dist/mermaid.esm.min.mjs";
    mermaid.initialize({{ startOnLoad: true, theme: "base", flowchart: {{ curve: "basis" }} }});
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
      }}

      buttons.forEach((button) => {{
        button.addEventListener("click", () => activate(button.dataset.tab));
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
    .table-wrap {{ overflow-x: auto; border: 1px solid var(--line); border-radius: 8px; }}
    table {{ border-collapse: collapse; width: 100%; min-width: 920px; font-size: 14px; }}
    th, td {{ border-bottom: 1px solid var(--line); padding: 8px 9px; text-align: right; white-space: nowrap; }}
    th {{ background: var(--fill); font-weight: 700; color: #30363d; }}
    tr:last-child td {{ border-bottom: 0; }}
    td.name, th:nth-child(2) {{ text-align: left; font-weight: 700; }}
    td.roles {{ text-align: left; white-space: normal; min-width: 240px; }}
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
    .generated-note {{ margin-top: 18px; font-size: 12px; }}
    footer {{ padding: 18px 32px 30px; border-top: 1px solid var(--line); color: var(--muted); font-size: 12px; }}
    @media (max-width: 920px) {{
      header, main, footer {{ padding-left: 16px; padding-right: 16px; }}
      .summary {{ grid-template-columns: 1fr 1fr; }}
      .ranking-grid {{ grid-template-columns: 1fr; }}
      .analysis-grid {{ grid-template-columns: 1fr; }}
      .cards, .yakuman-grid {{ grid-template-columns: 1fr; }}
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
        <h2>プレイヤー別データ</h2>
        <nav class="tabs" aria-label="プレイヤー別データ" role="tablist">
          {player_tabs}
        </nav>
      </div>
    </section>
    {panels}
  </main>
  <footer>
    Generated from collected Mahjong Soul records.
  </footer>
</body>
</html>
"""

    OUTPUT_HTML.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_HTML.write_text(html_text, encoding="utf-8")
    print(f"saved: {OUTPUT_HTML}")


if __name__ == "__main__":
    main()
