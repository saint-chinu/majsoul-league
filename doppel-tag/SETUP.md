# 環境構築の手順

段階 1（ローカル・1 人・ブラウザ）を始めるための環境。
**所要 30 分〜1 時間、費用 0 円。**

Windows 想定で書く（macOS / Linux は各項の末尾に補足）。

---

## 0. 先に決めておくこと：作業フォルダの場所

**重要な落とし穴が 2 つある。**

- **パスに日本語やスペースを含めない。**一部のツールが誤動作する
- **OneDrive / Dropbox の配下に置かない。**`node_modules` は数万ファイルになるため、
  同期ソフトが暴走してマシンが重くなる

**推奨：`C:\dev\` のような短くて英数字だけのフォルダを作り、その下で作業する。**

```
C:\dev\doppel\
```

（macOS なら `~/dev/doppel`）

---

## 1. Node.js

**入手：** <https://nodejs.org/> から **LTS 版**のインストーラ（Windows は `.msi`）。
オプションは全部既定のままで良い。

**確認：** インストール後、**ターミナルを開き直してから**（開いたままだとパスが通らない）

```
node -v
npm -v
```

`v20` 以上の数字が出れば成功。

> macOS：公式インストーラ、または `brew install node`

---

## 2. Git

**入手：** <https://git-scm.com/> から Git for Windows。
オプションは既定のままで良い（Git Credential Manager が同梱される。これが後で効く）。

**確認と初期設定：**

```
git --version

git config --global user.name "あなたの名前"
git config --global user.email "あなたのメールアドレス"
git config --global init.defaultBranch main
```

> macOS：`brew install git`（標準の Xcode 版でも可）

---

## 3. VS Code

**入手：** <https://code.visualstudio.com/>

**拡張機能は、最小構成なら何も要らない**（TypeScript の補完は最初から動く）。
入れるなら：

| 拡張 | 用途 |
| --- | --- |
| Japanese Language Pack | UI の日本語化。好みで |
| Prettier | コードの自動整形。あると楽 |

**便利な設定**（`Ctrl + ,` で設定を開き検索）：
`Format On Save` を有効にすると、保存時に自動で整形される。

---

## 4. Google Chrome

**入手：** <https://www.google.com/chrome/>

**理由：** WebGL まわりの開発者ツールが最も充実している。
`F12` → Performance タブと Rendering タブを後でよく使う。

---

## 5. GitHub アカウントとリポジトリ

1. <https://github.com/> でアカウント作成（無料）
2. 右上の **＋ → New repository**
3. 名前：`doppel`（何でも良い）
4. **Private** を選ぶ（後で公開に変えられる）
5. **README も .gitignore も追加しない**（空のまま作る。手元から push するため）

**認証について：** Windows なら Git for Windows 同梱の Credential Manager が働くので、
初回の `git push` のときにブラウザが開いてログインするだけで済む。
SSH 鍵の設定は不要。

---

## 6. プロジェクトを作る

ターミナル（Windows Terminal か PowerShell）で：

```
cd C:\dev
npm create vite@latest doppel -- --template vanilla-ts
cd doppel
npm install
npm install three
npm install -D @types/three
npm run dev
```

ターミナルに `Local: http://localhost:5173/` のような表示が出るので、
そのアドレスをブラウザで開く。Vite の初期画面が出れば成功。

**止めるときは `Ctrl + C`。**

---

## 7. GitHub に繋ぐ

`npm run dev` を止めてから、同じフォルダで：

```
git init
git add -A
git commit -m "init"
git branch -M main
git remote add origin https://github.com/<あなたのユーザー名>/doppel.git
git push -u origin main
```

初回はブラウザが開いて GitHub のログインを求められる。それで通る。

> Vite のテンプレートが `.gitignore` を用意してくれているので、
> `node_modules` は自動的に除外される。手を加えなくて良い。

---

## 8. 完了チェックリスト

全部 ✓ になったら環境構築は終わり。

- [ ] `node -v` でバージョンが表示される
- [ ] `git --version` でバージョンが表示される
- [ ] `npm run dev` でブラウザに画面が出る
- [ ] `src/main.ts` を適当に編集して保存すると、**ブラウザが自動で更新される**
- [ ] `git push` が成功し、GitHub のページにファイルが見える

**4 番目（ホットリロード）が特に重要。**
保存した瞬間に画面が変わる状態になっていると、
段階 1 の本体である「数値をいじって試す」作業が一気に速くなる。

---

## 9. 今は入れなくていいもの

| もの | いつ必要になるか |
| --- | --- |
| **Blender** | 段階 3。スプライトを 3D から書き出すとき |
| Audacity | 音の加工をするとき |
| Node のサーバ関連ライブラリ | 段階 2。ネットワーク対応のとき |
| 物理エンジン、パスファインディングのライブラリ | **入れない**（GETTING_STARTED.md 5-2） |
| Docker、DB、ホスティング、ドメイン | 段階 2 以降 |

---

## 10. 用意する素材（最小限）

| 素材 | どうするか |
| --- | --- |
| キャラのスプライト | **不要。**コードで単色のマテリアルを 4 色作れば足りる。
絵にするなら「前」「後」「左」「右」と書いた PNG 4 枚で十分 |
| ダンジョン | **不要。**テキストの升目から箱を並べる |
| 足音・呼吸音 | <https://freesound.org/> で拾う。段階 1 の後半であると体験が変わる |

---

## 11. PC の要件

| 項目 | 目安 |
| --- | --- |
| メモリ | 8GB で動く。16GB あると快適 |
| ストレージ | 空き 10GB もあれば十分（`node_modules` が数百 MB） |
| GPU | 内蔵グラフィックスでも動く。本作は描画が軽い |
| OS | Windows / macOS / Linux どれでも可 |

**ゲームが動く程度の PC なら問題なし。**

---

## 12. ここまで終わったら

GETTING_STARTED.md 6 章の実装順に進む。

最初にやるのは「テキストの升目から 3D の壁を生成する」ところ。
そこまで動けば、あとは積み上げるだけになる。
