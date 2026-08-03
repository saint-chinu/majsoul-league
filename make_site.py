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
    "houjuu_rate": "放銃率",
    "average_houjuu_point": "放銃平均打点",
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
    "late_noten_fresh_discard_rate": "後半非聴生牌率",
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
    "open_tanyao_hu_rate": "和了のうち、喰いタンだった割合。",
    "chiitoi_hu_rate": "和了のうち、七対子だった割合。",
    "honitsu_hu_rate": "和了のうち、ホンイツだった割合。",
    "chinitsu_hu_rate": "和了のうち、チンイツだった割合。",
    "average_opening_shanten": "配牌から北を抜き切って1枚打牌した時点の平均シャンテン数。",
    "average_opening_dora": "配牌時の平均ドラ枚数。北抜きと赤ドラも含む。",
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
    ("houjuu_rate", False, "低い方が上位"),
    ("average_houjuu_point", False, "低い方が上位"),
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


RIICHI_QUALITY_COLUMNS = [
    "player",
    "riichi",
    "riichi_quality_score",
    "riichi_recommended_rate",
    "riichi_not_recommended_rate",
    "riichi_quality_top_category",
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


PLAYER_RIICHI_QUALITY_COLUMNS = [
    "player",
    "season",
    "riichi",
    "riichi_quality_score",
    "riichi_recommended_rate",
    "riichi_not_recommended_rate",
    "riichi_quality_top_category",
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
        "累計トップの支配型。獲得スコア4,834.3、平均順位1.83、1位率42.33%、ラス回避率74.49%が抜けており、単にトップが多いだけでなく、負け半荘の底も浅い。和了率32.56%、副露率35.55%、先制テンパイ率35.33%、テンパイ維持率21.63%と、配牌から終局までずっと局へ関与し続ける数字になっている。特にテンパイ維持率が高いので、一度前に出た後に受けへ回されにくく、相手に先に選択を迫る局が多い。トップ滞在率46.22%も高く、半荘のかなり長い時間を勝っている側で進めている。",
        "強みは、速度を作った後の失点管理。これだけ副露・押し返しの量があるのに放銃率15.02%、放銃平均8,835.6点で済んでいるのはかなり強い。リーチの質もおすすめ寄り84.75%、非推奨15.25%、平均スコア2.94で、雑に曲げているというより、相手に圧をかける局と鳴いて流す局の使い分けができている。トップ目リーチ率42.52%は攻撃的だが、トップキープ率36.32%がリーグ最高なので、追加点を取りに行く判断が結果にもつながっている。守るトップではなく、相手の逆転手を成立前に潰すトップ。",
        "改善点は、勝っている半荘の終盤をさらに冷たく閉じること。現状でも十分勝てているが、トップ目リーチ率が高いぶん、南場トップ目の中打点愚形や、親が残っていない場面の追撃は少しだけ削る余地がある。テンパイ維持率が高い人ほど「まだ押せる局」が多く見えるので、オーラス前後は局収支より着順価値を一段重く見たい。攻撃力を増やす必要はほぼない。今後の伸びしろは、勝ち半荘をさらに事故らせず、2着で十分な局をきっちり2着で閉める精度にある。",
    ),
    "ひなんじょ": (
        "門前圧力型。立直率31.48%、和了率30.95%、先制テンパイ率33.20%、テンパイ維持率20.82%で、自分から先にテンパイを入れてリーチで場を縛る局が多い。平均順位1.98、獲得スコア983.7、1位率35.88%と攻撃の成果はきちんと出ている。トップ滞在率41.29%も高く、勝負どころでトップ目に立つ力がある一方、ラス滞在率29.44%はまだ少し残っており、攻撃の裏目がそのまま沈み半荘になることもある。",
        "強みは、リーチを軸にした局支配。リーチ率が高いのに和了率も高く、テンパイ維持率も20%を超えているため、待っているだけの門前派ではなく、押し返しまで含めて戦える。平均和了点10,618.8点も高く、ただ速いだけでなく収入も十分。トップ目リーチ率37.72%は攻めすぎというほどではなく、勝負手ならリード後も加点に行ける。リーチの質は平均スコア2.71、おすすめ寄り79.26%で、数を打ちながら最低限の質も保てている。",
        "改善点は、テンパイ前後の危険牌処理。放銃率16.88%、放銃平均9,519.6点は重めで、良いテンパイを作るまでの道中で失点が膨らんでいる可能性が高い。リーチ本数を単純に減らすより、一向聴で親の濃い仕掛けに押す局、ドラが見えていない終盤、2着目でトップが遠い局の押しを少し削る方が効く。ひなんじょは攻撃の軸がはっきりしているので、課題はアクセルではなくブレーキの場所。沈む半荘の放銃を1回減らせれば、トップ争い側にかなり寄る。",
    ),
    "鯛ofカルピス": (
        "自力決着型。先制テンパイ率36.50%、テンパイ維持率22.73%がどちらもリーグ最高で、誰よりも早くテンパイし、その状態を長く保てている。和了率31.77%、ツモ率48.43%も高く、相手の放銃待ちではなく、自分で山から引いて点棒を動かす力が強い。平均順位1.99、獲得スコア619.7で総合もプラス。立直率24.01%は控えめなので、テンパイ量の多さはリーチ乱発ではなく、ダマ・副露・押し返しを含めた手牌進行の速さから来ている。",
        "強みは、テンパイに入ってから局を離さないこと。テンパイ維持率が高い人は、押し返されても完全撤退に回りにくく、流局まで相手にプレッシャーを残せる。リーチの質も平均スコア2.96、おすすめ寄り81.63%でかなり良く、曲げる局は比較的選べている。鳴き手平均打点8,737.7点もあり、副露が単なる消化ではなく、速度と打点を両立した参加になっている。トップ滞在率41.14%、トップキープ率30.51%なので、先行した時に押し切る力もある。",
        "改善点は、防御面の温度管理。放銃率18.15%はリーグで最も高く、テンパイ維持率の高さがそのまま押しすぎにもつながっている。鯛ofカルピスは自分が和了れる局が多いぶん、終盤の愚形・安手・残りツモが少ないテンパイでも粘りたくなるはず。そこを親リーチ、ドラ周辺、明らかな高打点副露に対して一段だけ冷やしたい。攻撃を弱める必要はないが、非テンパイや価値の低いテンパイでの放銃を減らせば、最高クラスの先制力がそのまま順位に変わる。",
    ),
    "アリスkey": (
        "速度参加型の改善勢。累計スコアは-998.3だが、ラス回避率67.88%、放銃率15.39%は悪くなく、沈む半荘を投げるタイプではない。副露率32.40%、先制テンパイ率32.74%、テンパイ維持率20.31%で、重い配牌でも局へ関与する力は十分ある。シーズンを重ねるほど内容が良くなっている時期があり、後半にかけて平均順位や放銃面が整ってきているのはかなり大きい。数字だけ見るとマイナスだが、序盤の負債を後半の修正力で返しに行っているプレイヤー。",
        "強みは、局参加の柔軟さと修正速度。鳴きで速度を作れるし、立直率27.13%もあるので門前勝負も捨てていない。テンパイ維持率20.31%は中位以上で、テンパイ後に簡単に受けへ回らない粘りもある。ラス滞在率28.73%は低めで、ずっと苦しい位置にいる時間はそこまで多くない。ただしトップキープ率23.98%が低く、トップ滞在率39.84%のわりに勝ち切りへ変換しきれていない。強くなってきている分、次の課題は「参加できる」から「勝ち切れる」への移行。",
        "改善点は、トップ目と2着目での局面価値の整理。リーチの非推奨率22.56%、愚形リーチ率32.52%はやや高めで、押す局の中にまだ余計な勝負が混ざっている。トップ目では安い愚形リーチや遠い仕掛けを少し抑え、2着目や親番ビハインドでは逆に良形・高打点ルートを逃さない。後半シーズンで改善が見えているので、方向性は合っている。あとは勝っている半荘を失点でこぼさず、2着で耐える局とトップを奪う局をもう少しはっきり分けると、累計スコアが一気に戻る。",
    ),
    "29ちゃん": (
        "守備基盤型。放銃率14.61%はリーグ最少級で、放銃平均9,090.1点も軽め。三麻でこの失点管理はかなり価値がある。一方で和了率26.81%、副露率27.16%、立直率23.10%、先制テンパイ率30.55%、テンパイ維持率18.31%はいずれも控えめで、局を先に取りに行く量は少ない。平均和了点10,447.4点と役満回数を見ると打点ポテンシャルは高いが、通常局でテンパイを長く維持する時間が短く、和了まで届く回数が不足している。",
        "強みは、半荘を壊さない我慢と一撃の両立。低放銃の人は打点も低くなりがちだが、29ちゃんは平均和了点が高く、役満も多いので、守るだけのプレイヤーではない。リーチの質は平均スコア3.02、おすすめ寄り82.20%でかなり良く、曲げるリーチ自体は丁寧。だからこそ、課題はリーチの質ではなく量と到達回数にある。トップ滞在率37.05%、トップキープ率29.78%なので、先行できれば大きく崩れにくいが、先行する局数が足りず、守備力をスコアに変えきれていない。",
        "改善点は、親番と南場ビハインド時の攻撃量。テンパイ維持率18.31%は低めなので、序盤の良形・役牌対子・ドラ周辺はもう少し前向きに残してよい。特に親番で先制できる一向聴、ラス目南場で打点がある手、2着目からトップを狙える局では、安牌を抱えすぎず手牌効率を優先したい。守備力があるので、少し攻撃を増やしても大事故にはなりにくい。和了率を1から2ポイント上げられれば、低放銃という長所がそのまま累計スコアに変わる。",
    ),
    "葡萄海ぶどう": (
        "高打点志向のロマン砲型。平均和了点10,578.2点、ツモ率46.06%、リーチ率29.95%で、和了した時の破壊力は十分ある。一方で和了率26.45%、ラス回避率59.76%、ラス滞在率32.98%が苦しく、負けている時間が長い。先制テンパイ率30.69%、テンパイ維持率19.30%も下位寄りで、高い手を作る意識に対して、テンパイまでの速度とテンパイ後の継続時間が少し足りていない。最大点は作れるが、最低点が深くなりやすいタイプ。",
        "強みは、打点ルートを見つけた時の押し切り力。七対子、ホンイツ、リーチ高打点のルートを選べるので、細かい和了で刻むより一度の大物手で着順を変える麻雀になっている。平均和了点はリーグ上位で、鳴き手平均打点9,184.2点も高く、副露しても安く流すだけではない。トップ目リーチ率36.15%もあり、リード後に追加点を取りに行く意思はある。噛み合うシーズンでは一気にプラスを作れるので、個性そのものを消す必要はない。",
        "改善点は、勝負手ではない局の撤退速度と、重い手を追う基準。リーチの非推奨率25.84%が高めで、和了率が低いわりに放銃率17.29%が重い。打点種が薄い配牌、親の仕掛けが速い局、南場で2着を守れば十分な局では、満貫ルートを無理に追わず速度か守備に寄せたい。テンパイ維持率19.30%を見ると、押し返す局そのものはあるが、良いテンパイで押せている回数が足りない。放銃率を2ポイント下げつつ、先制テンパイ率を少し上げるのが一番効く。",
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
    if col == "riichi_quality_score":
        return number(value, 2)
    if col in {"average_opening_shanten", "average_opening_dora"}:
        return number(value, 2)
    if col in {
        "average_hu_point",
        "average_houjuu_point",
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
    if col != "riichi_quality_score":
        return ""
    description = METRIC_DESCRIPTIONS.get(col, "")
    table_html = riichi_quality_definition_table()
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
        from aggregate_league import (
            PlayerStats,
            aggregate_game,
            average,
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
                "houjuu_rate": percent(player_stats.houjuu, player_stats.rounds),
                "average_houjuu_point": str(average(player_stats.houjuu_point_sum, player_stats.houjuu, 1)),
                "called_houjuu_rate": percent(player_stats.called_houjuu, player_stats.rounds),
                "two_called_houjuu_rate": percent(player_stats.two_called_houjuu, player_stats.rounds),
                "called_haneman_houjuu_rate": percent(
                    player_stats.called_haneman_houjuu,
                    player_stats.rounds,
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
    add_cumulative_awards(
        cumulative_context,
        list(cumulative_context["season_mvp_rows"]),
        list(cumulative_context["team_champion_rows"]),
    )
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
        <h2>プレイヤー別データ</h2>
        <nav class="tabs" aria-label="プレイヤー別データ" role="tablist">
          {player_tabs}
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

    OUTPUT_HTML.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_HTML.write_text(html_text, encoding="utf-8")
    print(f"saved: {OUTPUT_HTML}")


if __name__ == "__main__":
    main()
