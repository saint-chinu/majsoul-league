# Cloudflare 実機レビュー（2026-09-15）— 仕様確認とバグチェック

対象：**https://doppel-tag.doppel-tag.workers.dev/**（本日時点のデプロイ。`/assets/game-0KBW24ll.js` のビルド）

方法：

1. 配信されている JS バンドル（`simulation` / `game` / `escape-map` / `infection-meter` / `ceiling` / `equipment` / `renderer`）を整形して静的に読んだ
2. Node から WebSocket で実サーバーに接続し、**練習部屋・マルチ部屋を実際に立てて**配信フレームと挙動を計測した
3. ヘッドレス Chromium で実クライアントの起動を試みた（調査環境のプロキシ都合で資産の一部が読めず、
   画面の確認までは至っていない。HTML/CSS/JS の静的な読みで補った）

サーバー側（Worker / Durable Object）のソースは配信されないので、**サーバーの内部は外から観測できる範囲**で判断している。
「要コード確認」と書いた項目は、サーバーのソースで裏を取ってほしい。

関連：[CLOUDFLARE_SPEC.md](CLOUDFLARE_SPEC.md)（通信・運用の追補仕様）、[REVIEW_2026-09-14.md](REVIEW_2026-09-14.md)（仕様書レビュー）

---

## 0. 結論

**CLOUDFLARE_SPEC.md の P0（情報露出）は実装済み。公開してよい水準に達している部分と、まだの部分がはっきり分かれている。**

| CLOUDFLARE_SPEC の項目 | 状態 | 実測 |
|---|---|---|
| 4-2 `kind` / `copyId` を送らない | **済** | actor に `kind` `copyId` `targetId` `fallenOwnerId` なし。AI の内部状態なし |
| 4-3 段階 2（見えない actor を送らない） | **済**（想定以上） | 視界外の actor は**一切送られない**。自分だけのフレームが大半 |
| （追加）ID の匿名化 | **済** | actor / party の ID は**閲覧者ごとに別のハッシュ**。party と actor の ID 照合でドッペルを割り出せない |
| 3 節 帯域削減（差分・バイナリ） | **未** | JSON 全量 20Hz。1 フレーム **1.7〜3.1 KB**、中央値 2.97 KB ＝ **約 476 kbps／人** |
| 5 節 静的配信のキャッシュ | **未** | ハッシュ付き JS/CSS も `max-age=0, must-revalidate`。1.7 MB の PNG が 3 枚 |
| 1 節 DO の分割 | **未** | `/health` が `roomLimit: 4`。1 DO・4 部屋のまま |
| 10 節 Turnstile / 乱造対策 | **未** | `POST /api/room` が無認証・無制限（→ B-1） |
| 2-3 tick 計測 | 不明 | 配信間隔は中央値 50 ms、p95 56 ms、最大 185 ms（40 秒間の 1 部屋計測。詰まりは観測されず） |
| 8-2 テレメトリ | 不明 | クライアントからは送っていない |
| 9 節 明滅軽減・コンテンツ警告 | **未** | 設定画面にない |
| P2-11 音声の圧縮 | **済** | 効果音は `.ogg`（`curse.mp3` のみ mp3） |

サーバーの堅牢性は良い。**入力値の検証、メッセージのレート制限、不正 JSON、復帰キーの検証はすべて正しく動いた**（3 節）。

---

## 1. 実測で分かった通信仕様（現状の記録）

仕様書に無い「実装の事実」を残しておく。次の仕様書更新の材料。

### 1-1. HTTP

| エンドポイント | 挙動 |
|---|---|
| `GET /health` | `{"ok":true,"platform":"cloudflare","tickRate":20,"roomLimit":4}` |
| `POST /api/room` | `{"room":"3桁","ticket":"uuid"}`。**予約のみ**。上限到達で `{"error":"現在4部屋が使用中です…"}`。予約は WebSocket が来なくても**約 60 秒**枠を占有する（実測：4 件予約 → 64 秒後に 1 枠解放） |
| `GET /ws?room=NNN&guest=1` | WebSocket。HTTP/2 で来ると 426。予約直後は 101、予約が消えると 410「部屋が終了しました」、部屋自体が無いと 404 |
| 静的資産 | すべて `cache-control: public, max-age=0, must-revalidate`。JS/CSS/manifest は brotli、PNG は無圧縮 |

### 1-2. WebSocket メッセージ

クライアント → サーバー：`create`（ticket 必須、practice / partySize / aiCount / duration / name / pants）、`join`（guest 必須。無いと「保存データを読み込んでください」）、`roomSettings`、`start`、`restart`、`input`、`ping`、`leave`、`resume`、`puzzle`、`purify`。

サーバー → クライアント：`welcome`（`id` / `host` / `resumeKey` / `resumed`）、`snapshot`（20Hz、ロビー中は変化時のみ）、`profile`、`pong`、`error`。

### 1-3. snapshot の中身（20Hz で送られているもの）

```
room, phase, time, duration, talismansRequired(0), talismansCollected(0),
actors[], items[](脱出モードでは空), events[](直近), seed, practice,
escape{ missions{found,ladder,notes,pillars,objects,reportedComplete,hasCrowbar},
        progress{barricade,rubble,key,lock,drain,grate}, workers{}, walkSpeed(2.3),
        escaped, objective },
partySize, aiCount, party[]
```

**actor（自分）**：`id,name,pants,fish,x,z,yaw,hits,cursed,alive,battery,hydration,light,lookingBack,grabUntil,stunUntil,invulnerableUntil,state,lastSeq,skillLevel,skillReadyAt,discoveredItems,mirrorActive,survivalSeconds,matchXp,exposureNear,exposure,moveBoost,grabAvailable,grabAction,equipment`

**actor（他者。見えているときだけ）**：上記から個人フィールドを除いたもの＋`mirrorActive`。`state` は探索者もドッペルも `"exploring"` に正規化されていた。

**party**：`id,name,fish,pants,alive,hits,cursed,kind`（kind は `player`/`bot`。ドッペルは party に載らない）。`connected` は**無い**（→ B-6）。

**events**：`{id,type,text,actorId,targetId,at,cue?,call?{x,z},replaces?}`。ドッペルの偽の呼び声は `type:"shout", text:"声がする", call:{x,z}` で**発生座標そのものが乗る**（→ B-11）。

### 1-4. 実測した挙動

| 項目 | 結果 |
|---|---|
| 練習（`practice:true`） | `create` 直後に `phase:"playing"`。ロビーを経ない。`start` を送ると「探索はすでに始まっています」 |
| 出現 | 練習で 30 秒後に `spawn` イベント。人数 ≤4 で 1 体。実際に姿が見えるのは視界に入った時だけ |
| 名前 | 16 文字に切り詰め（`<script>` を含めても切り落とされる）。`pants` は `#rrggbb` 以外なら既定色 |
| `duration` 99999 | 1200 に丸め。`partySize` 9 → 6、`aiCount` 9 → 5 |
| 参加者の権限 | 非ホストの `roomSettings` / `start` はエラー。ホストの不正な人数もエラー |
| 探索中の `join` | 「この部屋はすでに探索中です」 |
| 入力の検証 | `NaN` / `1e308` / 文字列 / 巨大 `seq` はすべて無害。`seq` の巻き戻りも受け付けない |
| 不正なメッセージ | 未知 type「未対応の操作です」、非 JSON「通信データを読み取れませんでした」。切断されない |
| レート制限 | 2,000 通を一気に送ると **1008 "Too many messages"** で切断 |
| サーバー側ハートビート | クライアントが 30 秒無通信 → サーバーが **1000「接続が終了しました。」** で切断 |
| TCP 異常切断（close frame なし） | **30 秒保持**。その間に `resume` すれば同じキャラ・同じ host 権限で復帰（`resumed:true`） |
| close code 4000 / 1001 | 復帰可（クライアントの「Heartbeat timeout」経路とタブ遷移は復帰できる） |
| close code 1000 / 1005 | **即座に退室扱い**。復帰不可 |
| 復帰キー | 他人のキー・二重復帰・誤ったキーはすべて「復帰期限が切れたか、部屋が終了しています」 |
| ロビーの寿命 | ホストが接続していれば 4 分以上維持（それ以上は未計測） |

---

## 2. バグ・問題（重要度順）

形式：**問題／再現／影響／修正案**

### B-1 [High] `POST /api/room` が無認証・無制限で、4 回叩くだけで全体が満室になる

**再現**

```sh
for i in 1 2 3 4 5; do curl -sS -X POST https://doppel-tag.doppel-tag.workers.dev/api/room; echo; done
# 4 件目まで {"room":...}、5 件目から {"error":"現在4部屋が使用中です。少し待ってお試しください。"}
```

WebSocket を一度も繋がなくても、予約は**約 60 秒**枠を占有する（実測 64 秒で解放）。
つまり **1 分に 4 回の POST を続けるだけで、誰も部屋を作れなくなる。**
今回の調査中、私自身が予約だけを繰り返してしまい、実際に 2 分ほど満室にした。

**影響** 公開後、悪意がなくても（例：リロード連打、タブを複数開く）満室になりうる。
悪意があれば 1 行のスクリプトで恒久的に止められる。CLOUDFLARE_SPEC 10 節が
「確実な防御はアプリ側の上限だけ」と書いたその上限が、逆にこの穴になっている。

**修正案（効果順）**

1. **予約を枠に数えない。**枠は「`create` が成立した部屋」だけを数える。予約は 3 桁コードの衝突回避にだけ使う
2. 予約の TTL を **10 秒**に下げる（クライアントは予約直後に `create` するので十分）
3. `POST /api/room` に **Turnstile**（CLOUDFLARE_SPEC 10 節）か、最低でも **IP ごとのレート制限**（Cloudflare の WAF ルールで無料で設定できる）
4. 満室エラーに `retry-after` 相当の秒数を含め、クライアントが自動で再試行する

### B-2 [High・スマホ] 30 秒無通信の切断は「退室」扱いで、復帰できない

**再現**

1. 試合中に **ping と input を止める**（スマホでホーム画面に戻る、別アプリに切り替える、PC でタブを裏に回して数分放置、と同じ状態）
2. 約 30 秒後、サーバーが `1000「接続が終了しました。」` で切断する
3. すぐに `resume` を送っても「復帰期限が切れたか、部屋が終了しています」。party からも即座に消えている

一方、**回線が物理的に落ちた場合（close frame なし）は 30 秒保持され、復帰できる。**
つまり「電波が切れた人は戻れるが、通知を見ただけの人は戻れない」という逆転が起きている。

ブラウザは裏に回ったタブの `setInterval` を 1 分に 1 回まで間引く（Chrome の intensive throttling）。
2 秒間隔の ping は必ず止まる。**スマホ横持ち専用を掲げる本作では、これは日常的に起きる。**

**影響** 仲間の 1 人が「通知を見て戻ったら部屋から消えていた」。残った側はホストが消えた場合、`restart` 不能。

**修正案**

1. サーバー側のアイドル切断を「切断保持 30 秒」の**対象にする**（異常切断と同じ経路に流す）。最小の修正
2. 切断時のコードを 1000 ではなく **4001 など独自コード**にし、クライアントが「復帰を試みる切断」と判別できるようにする
3. クライアントは `visibilitychange` で復帰した瞬間に `resume` を送る（現行は onclose からのリトライ 25 秒に依存）
4. 仕様書に「バックグラウンド 30 秒で切断・30 秒保持・合計 60 秒以内なら復帰可」と明記する

### B-3 [Med] 帯域：JSON 全量を 20Hz、1 人あたり約 476 kbps（CLOUDFLARE_SPEC 3 節が未実施）

**実測** 練習部屋（4 人）で 40 秒間：1 フレーム 1,722〜3,055 バイト、中央値 2,973 バイト。
20Hz なので **59 KB/s ＝ 476 kbps（下り、1 人）**。CLOUDFLARE_SPEC 3-1 の試算（2〜4 KB）と一致。

内訳を見ると、**見えている actor が自分 1 人でも 1.7 KB** ある。`escape.missions` / `progress` / `workers` /
`party` / `events`（直近 24 件）が毎フレーム丸ごと入っているため。

**修正案** 3-2 の順序どおり。特に本作は段階 2 の可視性フィルタが既にあるので、
**「変化しないもの（escape・party・events）を毎フレーム送らない」だけで半分以下になる**。
events は `id` 付きなので、クライアントが最後に受けた `id` 以降だけ送ればよい。

### B-4 [Med] 静的資産：キャッシュ無効・無圧縮の PNG が合計 5 MB 超

| ファイル | サイズ | 問題 |
|---|---|---|
| `/title/reservoir-night.png` | **1.77 MB** | タイトル背景。初回表示を最も遅らせる |
| `/demo/repel-reactions.png` | **1.78 MB** | 撃退演出の顔 |
| `/app-icon-bream.png` | **1.67 MB** | 1254×1254 を `favicon` と `apple-touch-icon` に指定。**毎回の起動で読まれる** |

すべて `cache-control: public, max-age=0, must-revalidate`。ハッシュ付きの `/assets/*.js` も同じ。
CLOUDFLARE_SPEC 5 節の表が丸ごと未適用。

（ヘッドレス Chromium での読み込み計測は、調査環境のプロキシで一部資産が `ERR_TOO_MANY_RETRIES` になり
再現性が取れなかったため、数値は載せない。上のサイズは `curl` で確認したもの。
実端末での初回読み込み計測は CLOUDFLARE_SPEC 11 節のとおり別途行うこと。）

**修正案**

1. `public/_headers`（Workers Static Assets が読む）で `/assets/*` を `max-age=31536000, immutable` に
2. 画像を **WebP / AVIF** に（1.7 MB → 100〜200 KB 程度）。favicon 用に **192px / 512px** の小さい版を別に作る
3. `/demo/` `/title/` `/audio/` `/animation/` の資産にも内容ハッシュを付けて immutable にする

### B-5 [Med・UX] 通知の最短表示が 7 秒に固定され、2 秒の警報が遅延・消失する

`game.js` の通知関数 `A(t, e, n)` の冒頭：

```js
n = Math.max(n, 7e3);        // すべての通知を最低 7 秒に引き上げる
if (B && n > 3e3) {          // 表示中なら待ち行列へ（最大 3 件、あふれたら捨てる）
```

`n` が常に 7,000 以上になるため、`n <= 3e3` の「即時差し替え」分岐が**到達不能**。
2 秒指定の「○○の警報！ 矢印の方向に仲間がいる」、2.5 秒の「お守り」「鉄パイプで反撃」、
2 秒の「通信が復旧した」が、直前の 7 秒通知（出現・変身・撃退）の後ろに並ぶ。
待ち行列が 3 件を超えると**捨てられる**。

**影響** 時間制の警報（2 秒の方向表示）が、表示された時には終わっている。

**修正案** `Math.max` を外し、短い通知（≤3 秒）は現行の設計どおり**割り込み表示**にする。
あるいは `alarm` / `counter` / `charm` は `A()` を通さず専用の小さな表示にする（矢印自体は別要素で出ているので、文言だけの問題）。

### B-6 [Low] HUD の文言・表示が現行ルールとずれている

| 箇所 | 現状 | 問題 |
|---|---|---|
| `#talisman-count` の初期値 | 「協力脱出 / 15 分」 | 選べるのは 20 分／30 分。最初のフレームまでこの文字が見える |
| `punch` イベントの通知 | 「殴られた！ 水分 −20％」 | 水分は無効化されている（`hydration` は常に 100） |
| チーム欄「接続待ち」 | `p.connected === false` で表示 | party に `connected` が無いので**一度も表示されない**。切断保持中の仲間が分からない（B-2 と併せて） |
| 手引き | 「掴み演出の後、ドッペルは 5 秒停止」 | 共有シミュレーションでは演出終了と同時に解放（`t.stunUntil = i.sceneUntil`）。5 秒停止は鉄パイプの反撃だけ。要コード確認（サーバー側で延長している可能性） |

### B-7 [Low] 練習モードの `start` がエラーを返す

練習は `create` で即開始するが、クライアントは `y.send({type:"start"})` を送る経路が残っており、
サーバーが「探索はすでに始まっています」を返す。画面には出ないが、エラーログを汚す。
`practice` のときは `start` を送らない、またはサーバーが黙って無視する。

### B-8 [Low] ホストは総人数に満たなくても開始できる

`partySize:6, aiCount:0` で人間 3 人のとき、UI は「探索を始める」を無効化するが、
サーバーは `start` を受け付けて 3 人で開始した。最低 3 人という下限だけが効いている。
仕様として「揃わなくても 3 人以上なら開始可」にするなら UI と手引きをそれに合わせる。逆なら サーバーで拒否する。

### B-9 [Low・要コード確認] tick の経過時間が 100 ms で切り捨てられ、詰まった分だけ試合が延びる

共有シミュレーション `tick(e)` の冒頭：`e = Math.min(e, 0.1); this.time += e;`。
サーバーが同じコードなら、DO が 1 tick に 300 ms 詰まったとき、ゲーム内時間は 100 ms しか進まない。
制限時間 20 分が実時間ではわずかに延びる（公平性には影響しないが「時間切れ」の再現性が落ちる）。
CLOUDFLARE_SPEC 2-3 の tick 計測と併せて、`time` と `Date.now()` の差を記録しておくとよい。

### B-10 [Info] 公開要件の未実装

明滅軽減設定、起動時のコンテンツ警告、プライバシー・利用規約の表記、テレメトリ送信。
CLOUDFLARE_SPEC 8〜9 節、REVIEW P2-13／P2-14 のとおり。ゲスト専用（アカウント無し）になったので
プライバシー面の負担は軽くなっている。

### B-11 [Info] 偽の呼び声イベントは発生座標をそのまま送っている

`events[].call = {x, z}`。画面には矢印しか出ないが、通信上は座標が乗る。
CLOUDFLARE_SPEC 4-3 の「音イベントは正体を含まない」は守れている（誰が鳴らしたかは無い）が、
**方向だけでよいなら、閲覧者からの角度と階の差に変換して送る**方が思想に一致する。
被害は小さい（呼び声の座標が分かっても正体は分からない）ので優先度は低い。

### B-12 [Info] クライアントの手鏡ボタンについて（誤検出の記録）

調査中に `#mirror-toggle{display:none!important}` を見つけて「スマホで鏡が開けない」と判断しかけたが、
正しくは `.mirror-mode #hud #mirror-toggle{…}` で**鏡モード中だけ隠す**規則だった。問題なし。
同種の CSS を読むときは `grep -o` の切り出しに注意。

---

## 3. 正しく動いていたこと（回帰の基準として残す）

- `kind` / `copyId` / `targetId` / AI 状態を配信しない。ID は閲覧者ごとにハッシュ化。**開発者ツールで WebSocket を眺めてもドッペルは分からない**（CLOUDFLARE_SPEC 11 節の受け入れシナリオを満たす）
- 視界外の actor を送らない（段階 2）。ポップインの緩和は補間バッファ 12 フレームで対処されている
- 入力値のクランプ（`NaN` / 無限大 / 文字列 / 巨大 `seq`）
- メッセージのレート制限（1008）、不正 JSON・未知 type はエラー応答のみで切断しない
- 復帰キーの検証（他人・二重・誤り）
- 異常切断の 30 秒保持と復帰（同じ ID、host 権限も維持）
- サーバー側ハートビート（30 秒）— ただし B-2
- 名前・ズボン・人数・時間の検証と丸め
- 効果音の ogg 化（P2-11 済）

---

## 4. 仕様書と実装の差分（ドキュメント側を更新すべきもの）

| 項目 | 仕様書 | 実装 |
|---|---|---|
| 試合時間 | 6 分（FUN_CORE / ESCAPE）、12 分（SPEC） | **20 分／30 分** |
| 目標 | お札 → 鍵 2〜3 個＋出口 15 秒（ESCAPE 3 章） | **梯子で階段修復 → バールで柱 3 本（30 秒）→ 暗号錠（メモ 3 枚、A〜I）→ 地下鍵扉 → 地上**。脱出は個人単位 |
| 歩行速度 | 1.6 m/s（LOCOMOTION） | **2.3 m/s（点灯）／1.61 m/s（消灯）** |
| 伝染 | 累積 60 秒・回復 0.1/秒・半径 5 m（ESCAPE 1-2） | **20 秒・離れると 2/秒で減少・半径 5 m**。二次呪いは 30 秒で自然回復。「予算」ではなく「近づきすぎ警告」の設計になっている |
| 呪われた人は出口を通れない（ESCAPE 1-6） | あり | 手引きでは「二次呪い中も脱出できる」。直接の呪いは要コード確認 |
| 掴みクールダウン | 60 秒（SPEC）、8 秒（FUN_CORE 核モード） | **30 秒** |
| 手鏡の身体回転 | ±135°（CONTROLS_FIX） | **±60°**（傾き ±45° は一致） |
| 手鏡 | 壁の鏡に置換（FUN_CORE 5-4） | **手持ちのまま**。3 系統の UI（傾き・身体回転・しまう） |
| 天井落下中の本人の反撃（REVIEW P1-10 修正案 B） | 提案 | **実装済**（`canGrab` の例外分岐） |
| 掴みボタンの根拠をサーバーが配信（REVIEW P1-8） | 提案 | **実装済**（`grabAvailable` / `grabAction`） |
| 不成立の掴みでクールダウンを消費しない（P1-8） | 要コード確認 | **消費しない**（`resolveGrabs` で不成立時は `continue`） |
| コピー元が呪われているときの撃退（P1-6 案 A） | 提案 | **実装済**（`r = (i.targetId === i.copyId …) && h.cursed` で 50 秒退場） |
| 水分・電池・装備・スキル | 仕様書に記述 | **無効化**（`hydration`/`battery` を毎 tick 100 に固定、装備欄は CSS で非表示） |
| 魚の種類 | 9 種の候補 | **6 種**（フグ・シュモクザメ・チョウチンアンコウ・マグロ・マンボウ・クロダイ） |

---

## 5. 手鏡の現状（コードから読み取れる挙動）

アイデア出しの土台として、実装済みの手鏡の仕様をここに固定する。

| 項目 | 実装 |
|---|---|
| 開閉 | `H`（スマホは左の「手鏡」ボタン）。**静止中のみ**開ける（移動入力があると `mirror` パルスを捨てる）。停止中・飲水中は不可 |
| 開いた瞬間 | ライト消灯、`mirrorBaseYaw` を記録、傾き 0 |
| 鏡の傾き | ±45°（`Z`/`V`、`X` で後ろ）。視線方向は `yaw + π + 2×傾き`：傾き 45° で**真横**を映す |
| 身体の回転 | `A`/`D` で 90°/秒、基準から **±60°** |
| 鏡の位置 | 傾きに応じて体の斜め後ろ〜横へオフセット（壁の中なら自分の位置に戻す） |
| 顔の変貌が見える条件 | 相手が **2.8 m 以内**、相手がこちらを向いている（cos > 0.35 ≒ 前方 69°）、遮蔽なし。判定はサーバー（`mirrorRevealed` を付与） |
| 鏡越しの「目撃」 | `mirrorSees`：鏡の位置から **14 m・半角 40°**。掴み演出後のドッペルの逃走判定（`witnessedGrabRange` 8 m）に**鏡使用者も数えられる** |
| AI から見た鏡使用者 | `sees()` が **false**（鏡使用中は「見ている」扱いにならない）。したがってドッペルは鏡使用者の視線で退かない。天井落下の対象にもならない |
| 出現位置の計算 | `observerEyes` には鏡使用者も含まれる（鏡越しに見える場所には出現しない） |
| 音 | `mirror-open` / `mirror-close` / `mirror-turn`（回転時 250 ms 間隔） |
| 演出 | 鏡モード中は HUD の上下・チーム欄・掴みボタンを隠す |

**REVIEW P2-15 の懸念（2.8 m は短い、無防備）は、そのまま残っている。**
加えて「AI が鏡使用者を無視して接近する」ことは仕様書に書かれていない。
意図的なら「鏡は無防備」の一部として明記、意図的でないなら `shouldRetreat` に鏡越し視線を足す。

手鏡を活かす案は [MIRROR_IDEAS.md](MIRROR_IDEAS.md) にまとめた。

---

## 6. 受け入れ確認への追加（CLOUDFLARE_SPEC 11 節へ）

| シナリオ | 期待する結果 |
|---|---|
| `POST /api/room` を 10 回連続 | 満室にならない（予約は枠に数えない）／IP レート制限に当たる |
| 試合中にタブを 40 秒裏に回して戻る | 同じキャラで復帰できる。party から消えない |
| 回線切断 40 秒後に戻る | 上と同じ結果（切断の種類で差が出ない） |
| 6 人接続時の下り帯域 | 1 人 150 kbps 以下（B-3 対策後の目標） |
| 2 回目の起動 | JS/CSS/PNG/audio が再取得されない（`immutable`） |
| 警報装置の通知 | 発生から 0.5 秒以内に表示される |

---

## 7. 調査で使った手順（再現用）

```sh
# 予約だけで満室になることの確認（注意：本当に 60 秒間、他の人が部屋を作れなくなる）
for i in 1 2 3 4 5; do curl -sS -X POST https://doppel-tag.doppel-tag.workers.dev/api/room; echo; done

# 静的資産のヘッダ
curl -sS -o /dev/null -w "%{http_code} %{size_download}B cc=%header{cache-control}\n" \
  https://doppel-tag.doppel-tag.workers.dev/app-icon-bream.png

# WebSocket（Node 22 の組み込み WebSocket で可）
#   1. POST /api/room で room/ticket を得る
#   2. wss://…/ws?room=NNN&guest=1 に接続
#   3. {"type":"create","room":NNN,"ticket":…,"practice":true,"name":"x","pants":"#617a68","guest":true,"duration":1200,"partySize":3,"aiCount":2}
#   4. 50ms ごとに {"type":"input","input":{forward:1,…,seq:n}}、2 秒ごとに {"type":"ping","at":Date.now()}
#   5. 受信した snapshot の actors のキーを確認する
```
