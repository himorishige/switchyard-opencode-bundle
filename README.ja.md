# Switchyard for opencode + Fireworks

[English](README.md) | **日本語**

opencode のリクエストを NeMo Switchyard が自動で strong / weak tier に振り分け、品質を保ったままコストを下げるローカルルーターです。各自の端末で Docker コンテナとして常駐させます。

```
opencode → Switchyard (127.0.0.1:4100) → Fireworks AI
              └─ classifier（weak が兼任）が難易度を判定して振り分け
```

| route（opencode のモデル名） | 動作                                                                                                                      |
| ---------------------------- | ------------------------------------------------------------------------------------------------------------------------- |
| `auto`（既定）               | coding-agent 向け自動ルーティング。普段はこれだけで OK                                                                    |
| `auto-esc`（オプトイン）     | weak 先行。軌跡 judge が本物のトラブルを検知したら strong へ昇格。[詳細](#証拠ベースのエスカレーションauto-escオプトイン) |
| `strong-only`                | kimi-k3 固定（ルーティングを疑ったときの切り分け用）                                                                      |
| `weak-only`                  | deepseek-v4-flash-0731 固定                                                                                               |
| `k3-only`                    | `strong-only` の別名（strong=K3 切替以前のオプトインルート。[経緯](#strong-tier-と-kimi-k3)）                             |

設定は `routes.toml`（Switchyard ネイティブ Rust サーバーの設定形式）1 枚です。

**画像を添付するとき**は `strong-only` または `k3-only` を使ってください。どちらも画像を読める Kimi K3 を固定しており、opencode 設定側で `modalities` を宣言しているので添付が実際に送信されます。宣言のないモデルでは opencode が画像を黙って落とし、モデルが「画像を読めません」と答えます。`auto` / `auto-esc` / `weak-only` はあえて宣言していません。weak tier（deepseek-v4-flash-0731）が画像入力を拒否するためで、`auto` ではセッションアフィニティによって weak に固定済みのセッションへスクリーンショットが渡り、上流から 400 が返ります。

> 初めてセットアップする場合は、[docs/onboarding.ja.md](docs/onboarding.ja.md)（初回セットアップの一本道手順）から始めるのがおすすめです。

## 前提

- Docker（Docker Desktop / colima 等）
- Fireworks の API キー（[発行ページ](https://app.fireworks.ai/settings/users/api-keys)）
- opencode セットアップ済み（web 検索経由の情報送信を絞りたい場合は [opencode-with-strict-privacy](https://github.com/cm-dyoshikawa/opencode-with-strict-privacy/blob/main/README.ja.md) の設定——exa.ai 無効化・share 無効化を **Global スコープ**で——を先に済ませておくことを推奨）

## セットアップ

### 1. リポジトリを取得

```bash
git clone https://github.com/himorishige/switchyard-opencode-bundle.git
cd switchyard-opencode-bundle
```

### 2. API キーを配置

```bash
cp .env.example .env
chmod 600 .env
```

`.env` を開き、`FIREWORKS_API_KEY` を自分のキーに置き換えます。

### 3. ルーターを起動

```bash
docker compose up -d --build
```

初回は Switchyard のネイティブ Rust サーバーを crates.io から取得してビルドします。Apple Silicon Mac で 1 分半ほど、遅いマシンではもう少しかかります。2 回目以降は Docker レイヤーキャッシュが効くため、ピン留めバージョンが変わらない限り数十秒で終わります。

colima 等の Docker Desktop 以外の環境では、`docker compose` サブコマンドが入っていないことがあります。その場合はスタンドアロン版 compose を導入します。

```bash
brew install docker-compose
```

導入後は、本 README 内の `docker compose ...` を **`docker-compose ...`** に読み替えて実行してください（例: `docker-compose up -d --build`。中身は同じ compose v2 なので動作は変わりません）。

`docker compose` のサブコマンド構文のまま使いたい場合のみ、`~/.docker/config.json` に次のキーを追加すると plugin として認識されます（既存の `auths` 等は残したままにします。パスは `brew --prefix` の出力に合わせてください。Apple Silicon は `/opt/homebrew`、Intel は `/usr/local`）。認識されない環境でも、スタンドアロン版の読み替えで問題ありません。

```json
"cliPluginsExtraDirs": ["/opt/homebrew/lib/docker/cli-plugins"]
```

compose を使わない場合は docker run でも起動できます（`routes.toml` はイメージに焼き込み済み。ただしログ永続化と healthcheck は compose 版のみ）。

```bash
docker build -t switchyard-opencode .
docker run -d --name switchyard-opencode --env-file .env \
  -p 127.0.0.1:4100:4100 --restart unless-stopped switchyard-opencode
```

### 4. 動作確認

```bash
curl -s http://127.0.0.1:4100/health
# → {"status":"ok"}

curl -s http://127.0.0.1:4100/v1/models | head
# → auto / auto-esc / strong-only / weak-only / k3-only / qwen3.7-plus が並ぶ
```

起動できたら、次の「opencode 側の設定」へ進みます。

## opencode 側の設定

`opencode.jsonc.example` の内容を **Global 設定**（`~/.config/opencode/opencode.json`）に反映します。opencode は JSONC（コメント付き JSON）を正式サポートしているので、コメントはそのままで有効です。反映方法は 2 通りあります。

### A. そのまま上書きする（新規、または strict-privacy 推奨構成のみで運用中）

`opencode.jsonc.example` は、[opencode-with-strict-privacy](https://github.com/cm-dyoshikawa/opencode-with-strict-privacy/blob/main/README.ja.md) の推奨グローバル設定と Switchyard の接続設定を**マージ済みの完成形**です。Global 設定が未作成、または strict-privacy の推奨構成のままなら、コピーするだけで完了します。

```bash
mkdir -p ~/.config/opencode
cp opencode.jsonc.example ~/.config/opencode/opencode.json
```

- `opencode.jsonc` のファイル名で運用している場合は、そのファイルに上書きしてください（`.json` と `.jsonc` を両方置いたときの優先順位は公式に明記されていないため、二重に置かないこと）
- strict-privacy の環境変数側の設定（`OPENCODE_ENABLE_EXA=0` 等）はこのファイルには含まれません。シェルの設定ファイル（`~/.zshrc` など）への設定は別途済ませてください

### B. 既存のカスタム設定にマージする

theme や他プロバイダなど独自の設定を足している場合は、上書きせず次の 3 つのトップレベルキーを既存の JSON に追記します。

```json
"provider": {
  "switchyard": {
    "npm": "@ai-sdk/openai-compatible",
    "name": "Switchyard (Fireworks auto-routing)",
    "options": {
      "baseURL": "http://127.0.0.1:4100/v1",
      "apiKey": "local-dummy"
    },
    "models": {
      "auto": { "name": "auto — Switchyard routing" },
      "auto-esc": { "name": "auto-esc — weak-first, escalates on trouble" },
      "strong-only": {
        "name": "strong-only — kimi-k3 pinned",
        "modalities": { "input": ["text", "image"], "output": ["text"] }
      },
      "weak-only": { "name": "weak-only — deepseek-v4-flash-0731 pinned" },
      "k3-only": {
        "name": "k3-only — kimi-k3 pinned (alias of strong-only)",
        "modalities": { "input": ["text", "image"], "output": ["text"] }
      }
    }
  }
},
"model": "switchyard/auto",
"small_model": "switchyard/weak-only",
"agent": {
  "plan": { "model": "switchyard/strong-only" },
  "explore": { "model": "switchyard/weak-only" },
  "scout": { "model": "switchyard/weak-only" }
}
```

マージ時の注意点は次のとおりです。

- 既に `provider` キーがある場合は、その**中に** `switchyard` エントリだけを追加してください。`provider` ブロックごと貼り付けて置き換えると、既存のプロバイダ設定が消えます
- strict-privacy 系のキー（`share` / `autoupdate` / `tools` / `permission` 等）とは衝突しません。そのまま共存できます
- `model` / `small_model` を既に設定していて、いまの既定モデルを残したい場合は、この 2 行を取り込まず、使うときだけモデルピッカーから選択してください
- `agent` ブロックの意図（plan の strong 直結、explore / scout の weak 固定）は「[classifier に任せない領域](#classifier-に任せない領域plan-モードの固定既定有効)」を参照してください
- マージ後に opencode を再起動し、モデルピッカーに `Switchyard (Fireworks auto-routing)` のモデル群（`auto` / `auto-esc` / `strong-only` / `weak-only` / `k3-only`）が出ることを確認してください

### 運用のポイント

- モデル切替は opencode のモデルピッカー（`/models`）から選択します。プロバイダ `Switchyard (Fireworks auto-routing)` の下に 5 つのルートが並びます
- Switchyard を止めたいとき（障害切り分け等）は、opencode 側に Fireworks 直結のプロバイダ設定があれば、ピッカーから素の `fireworks-ai/...` モデルを選んで直結にフォールバックできます
- `small_model` はタイトル生成などの補助コール用です。`weak-only` 固定にしてあります（auto に流すと小物が strong に化けることがあるため）
- サブエージェントの扱い: 会話単位で classifier が個別に分類・ピン留めするため、軽いサブエージェントは自動で weak に落ちます。常に weak を強制したい場合は opencode の per-agent 設定（`"agent": {"<name>": {"model": "switchyard/weak-only"}}`）を使ってください

### strong tier と Kimi K3

2026-08-07 に、自動ルーティングの strong tier を deepseek-v4-pro から **Kimi K3** に切り替えました。深い設計相談・プランニングでの応答品質を優先した変更です。`k3-only` はそれ以前に K3 を手動で使うためのオプトインルートだった名残で、現在は `strong-only` と同じ接続先を指す**別名**です（旧設定の参照を壊さないために残しています）。

コスト面はトレードです。100 万トークンあたり K3 は $3.00 / $0.30 / $15.00（input / cached / output）、旧 strong の deepseek-v4-pro は $1.74 / $0.145 / $3.48。エージェントループの実測トークン分布に単価を当てた試算では **1 run あたりの絶対額が約 3 倍**になります（strong 固定・auto ともに 3.0 倍）。一方で `auto` の削減率（weak 併用による節約幅）はほぼ変わりません。ルーティングは単価の梯子に働くためです。「auto にすれば高単価が薄まる」のではなく、**下限も上限も一緒に持ち上がる**と考えてください。

コストの支配項は output に移ります（K3 は総額の約 68% が output、deepseek-v4-pro は約 47%）。長文の設計文書や大きなパッチを吐かせる使い方をするほど、試算より上振れします。

#### classifier に任せない領域（plan モードの固定、既定有効）

classifier は「weak tier がタスクを完遂できる確率」を推定します。その判定基準（capability ルール）はコード作業を想定して書かれているため、ビジネスや設計の議論はどのルールにも当てはまらず、より厳しいルーティング閾値に落ちる設計です。較正セットの実測では深い議論の大半（13 問中 12 問）を拾えましたが全部ではなく、判定は会話ごとの確率的な見立てであることに変わりありません。

そこで `opencode.jsonc.example` では、agent 単位の固定を**既定で有効**にしています（`provider` や `model` と同じトップレベルの `agent` キー。既存のカスタム設定にマージする場合は、その中に各エントリを足してください）。深い議論の主戦場である plan モードを固定すれば、この領域の挙動は確率ではなく決定論になります。

```json
"agent": {
  "plan": { "model": "switchyard/strong-only" },
  "explore": { "model": "switchyard/weak-only" },
  "scout": { "model": "switchyard/weak-only" }
}
```

plan は strong（Kimi K3）直結です。plan モードに切り替えたときだけ classifier を通さず strong になり、build モードに戻せば既定の `auto` に戻ります（`opencode run --agent plan` でも同じ経路）。`explore` / `scout` の weak 明示は逆方向の防御で、**opencode のサブエージェントは呼び出し元のモデルを継承する**ため、指定を省くと grep 結果を読むだけのサブエージェントにも $15/1M の output 単価が乗ります。

#### すでにルーターを使っている場合の更新手順

```bash
git pull && docker compose up -d --build
curl -s http://127.0.0.1:4100/health   # {"status":"ok"}
```

`--build` が必要なのは Dockerfile やピン留めバージョンが変わるリリースの場合です（2026-08 のネイティブサーバー移行がまさにそれで、旧 `route.yaml` 構成からの更新は rebuild 必須。routing ログは `switchyard-logs` volume に保全されます）。`routes.toml` だけのリリースなら `git pull && docker compose restart` で足ります。

route 名は変わらないため、`opencode.json` の変更は必須ではありません。モデルピッカーの表示名を実態に合わせたい場合だけ、`provider.switchyard.models` の `name` を更新してください。

```json
"models": {
  "auto": { "name": "auto — Switchyard routing" },
  "auto-esc": { "name": "auto-esc — weak-first, escalates on trouble" },
  "strong-only": { "name": "strong-only — kimi-k3 pinned" },
  "weak-only": { "name": "weak-only — deepseek-v4-flash-0731 pinned" },
  "k3-only": { "name": "k3-only — kimi-k3 pinned (alias of strong-only)" }
}
```

保存したら opencode を再起動します。設定は起動時にしか読み込まれないため、起動しっぱなしのセッションには反映されません。なお opencode はここに書かれたモデルしか認識しないため、`models` から `k3-only` を消すと、それを参照する設定（旧 plan 固定など）が `UnknownError` になります。消す場合は参照側を先に整理してください。

#### 切替前の挙動（strong = deepseek-v4-pro）に戻すには

体感が合わない場合は、`routes.toml` の 1 行を戻して restart してください。strong target の定義は 1 箇所だけで、`auto` と `strong-only`（および別名 `k3-only`）がそこを参照しています。

```toml
[targets.strong]
id = "accounts/fireworks/models/deepseek-v4-pro"
```

### 証拠ベースのエスカレーション（auto-esc、オプトイン）

`auto-esc` は `auto` と逆の思想のルーティングです。ターンごとに難易度を予測するのではなく、すべてのセッションを **weak tier で開始**し、軌跡 judge が毎ターンのやり取りを読んで「本物のトラブルの明確なパターン」——同一エラーの反復（間に無関係な編集を挟む）、テスト出力と矛盾する完了宣言、タスクからの逸脱——を検知します。escalate 判定が 2 連続でセッションは strong にラッチされます。

実測（2026-08-08）: 健全な摩擦（修正中のテスト失敗、逐次的な代替案の試行）では一度も昇格せず、本当に詰んだ軌跡は 2 ターン目で strong にラッチ。ラッチ後は judge 呼び出しゼロで p50 約 1 秒でした。

選ぶ前に知っておくトレードオフ:

- **ラッチ前はストリーミングがバッファされます。** judge が weak の完成した返答を読んでから返すため、応答はトークン逐次ではなく一括で届きます。短〜中程度の応答は体感差が小さい（weak の思考時間がもともと先行するため）ですが、長い生成は「止まってから全文出る」見え方になります
- エスカレーション確定ターンは両 tier に課金されます（weak の返答を破棄して strong で撮り直すため）
- ラッチはセッション内で片道です（weak への降格はありません）

向いている場面: コスト最小の実験（weak 比率が構造的に最大）と、**非対話ワークロード**——cron ジョブ・バッチ・画面を見ていないエージェント——です。バッファリングの影響がなく、証拠ベースの昇格がそのまま失敗保険として効きます。試すにはモデルピッカーで `auto-esc` を選ぶだけです（`opencode.jsonc.example` に登録済み）。

### weak tier の目（Qwen-MM-Plugins）

weak tier はテキスト専用です——`deepseek-v4-flash-0731` は画像入力を拒否します。tier ごと vision 対応モデルに替えるのではなく、ルーターが [Qwen-MM-Plugins](https://github.com/QwenLM/Qwen-MM-Plugins) のツール向けに専用の vision route（`qwen3.7-plus`）を提供します。ツールが画像を vision モデルに見せ、脳にはテキストの説明が渡るので、脳は画像を一度も受け取らず安いモデルのままです。route は `routes.toml` に同梱済みで、opencode 側にプラグインの MCP エントリを足すまでは何もしません。セットアップ・コスト・制約（画像のみ）は [docs/qwen-mm-plugins.ja.md](docs/qwen-mm-plugins.ja.md) を参照してください。

## Agent Plugin（rag-kb / web-search）

`plugin/team-ai-kb/` は [Agent Plugins 標準](https://agent-plugins.org/)（v1.0.0）準拠のプラグインです。ルーターとは独立したオプションで、エージェント拡張 2 本 + MCP 定義を同梱しています。

| コンポーネント                              | 内容                                                                                                                  | 前提                                                                                                                      |
| ------------------------------------------- | --------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------- |
| skill `rag-kb`                              | チーム共通ナレッジ検索（NVIDIA RAG Blueprint の MCP）の使い方ガイド                                                   | RAG サービスへのプライベート網到達 + 下記 MCP 登録                                                                        |
| skill `web-search`（+ `scripts/search.py`） | Gemini / OpenAI 両対応の web 検索。設定済みのキーからバックエンドを自動選択し、各自のキーで直接呼ぶ（中間サーバなし） | `GEMINI_API_KEY` または `OPENAI_API_KEY`。発行手順 = [docs/web-search-onboarding.ja.md](docs/web-search-onboarding.ja.md) |
| `mcp.json`                                  | `nvidia-rag`（streamable HTTP）の MCP サーバ定義                                                                      | 下記の初期設定                                                                                                            |

### 初期設定（共通・初回のみ）

RAG の接続先はプライベート網内のアドレスのため、`.env` と同じ流儀で example からコピーして書き換えます（実ファイルは gitignore 済み）。

```bash
cp plugin/team-ai-kb/mcp.json.example plugin/team-ai-kb/mcp.json
# mcp.json の <rag-service-host> をサービス機のアドレスに書き換える
```

### opencode で使う

Global 設定に 2 ブロック追記します。symlink は不要です。opencode が起動時にディレクトリを解決するため、リリースで skill が増えても `git pull` だけで反映されます。

```jsonc
// ~/.config/opencode/opencode.json
"skills": {
  "paths": ["/path/to/switchyard-opencode-bundle/plugin/team-ai-kb/skills"]
},
"mcp": {
  "nvidia-rag": {
    "type": "remote",
    "url": "http://<rag-service-host>:8091/mcp",
    "enabled": true
  }
}
```

opencode は `~/.claude/skills/` / `~/.agents/skills/` / プロジェクトの `.claude/skills/` からも skills を自動で読み込みます。他のクライアント向けにこれらのパスへ置いてある場合は、上の `skills` ブロックがなくても認識されます。実際に読み込まれた一覧と読み込み元は `opencode debug skill` で確認できます。

以前のリリースでは `~/.config/opencode/skills/` への symlink を案内していました。そちらも引き続き動作し、上のブロックと並存しても壊れません（symlink 側が採用されますが、指し先は同じファイルです）。古いリンクの削除は任意です。

### Claude Code で使う

プラグイン形式をそのまま読めます（MCP 用の `.mcp.json` シムは同梱済み）。起動フラグ 1 つです。

```bash
claude --plugin-dir /path/to/switchyard-opencode-bundle/plugin/team-ai-kb
# 常用する場合は shell alias に含める
```

### Codex CLI で使う

```bash
ln -s "$(pwd)/plugin/team-ai-kb/skills/rag-kb" ~/.codex/skills/rag-kb
ln -s "$(pwd)/plugin/team-ai-kb/skills/web-search" ~/.codex/skills/web-search
codex mcp add nvidia-rag --url "http://<rag-service-host>:8091/mcp"
```

非対話実行（`codex exec`）で MCP を使う場合は、`~/.codex/config.toml` の `[mcp_servers.nvidia-rag]` に `default_tools_approval_mode = "approve"` を 1 行追加してください。Codex の MCP ツールコールはシェルコマンドの `approval_policy` と別系統の承認を通るため、非対話ではこの指定がないと即時キャンセルされます（読み取り専用サーバに限って許可する運用です）。

### 更新

opencode と Claude Code は設定・プラグインディレクトリがバンドルを直接指しているため `git pull` だけで反映されます。Codex の symlink も同様に追随します。`mcp.json.example` が変わったリリースでは、手元の `mcp.json` への反映を確認してください。

## 運用

| 操作                   | コマンド                                                                                                   |
| ---------------------- | ---------------------------------------------------------------------------------------------------------- |
| 更新（設定・イメージ） | `git pull && docker compose up -d --build`                                                                 |
| 設定だけ変えたとき     | `routes.toml` 編集後 `docker compose restart`（compose が bind-mount しているため rebuild 不要）           |
| キーローテーション     | `.env` 更新後 `docker compose up -d --force-recreate`（`restart` はコンテナ作成時の env を再利用するため） |
| 死活確認               | `curl -s http://127.0.0.1:4100/health`                                                                     |
| 停止                   | `docker compose down`                                                                                      |

`routes.toml` だけが変わったリリース（tier の向き先変更など）では `git pull && docker compose restart` で足ります。イメージが変わっていなければ rebuild は不要です。

route が**追加**されたリリースでは、それに加えて Global 設定（`~/.config/opencode/opencode.json`）の `provider.switchyard.models` にも同じ route 名を登録してください。ルーター側を更新しただけではモデルピッカーに出てきません（手順は「[すでにルーターを使っている場合の更新手順](#すでにルーターを使っている場合の更新手順)」）。

### モデルを変更するには

tier の実体は `routes.toml` の `[targets.<name>]` テーブルで、各 route はそこを参照しています。例として strong を kimi-k3 から GLM-5.2 に切り替える場合、書き換えるのは 1 行です。

```toml
[targets.strong]
id = "accounts/fireworks/models/glm-5p2"
```

編集後は restart だけで反映されます（bind-mount のため rebuild 不要）。

```bash
docker compose restart
curl -s http://127.0.0.1:4100/health
```

注意点は次のとおりです。

- 使えるモデル ID は [Fireworks serverless カタログ](https://app.fireworks.ai/models?capability=serverless)で確認できます
- opencode 側は route 名（`auto` / `strong-only` / `weak-only` / `k3-only`）しか見ていないため、向き先を変えるだけなら `opencode.json` の変更は不要です。モデルピッカーの表示名も実態に合わせたい場合は、`opencode.json` の `models` 配下の `name` を書き換えてください。route 名そのものを増やした場合は `models` への登録が別途必要です
- classifier target のモデルを変更した場合は、変更後に 1 リクエスト流して judge の健全性を確認してください（`curl -s http://127.0.0.1:4100/v1/stats` → `classifier`）。judge は `extra_body` で思考を抑制していますが、このノブを解釈しないプロバイダもあります。judge の回答が素の `content` の外（reasoning 領域）に出るようになると、全判定が fail-open で strong に倒れます
- **モデル ID 衝突の罠——1 つはこの構成にも効き、もう 1 つはリリース版を離れた場合だけ効きます。** サーバーは (llm_client, model id) の組で target を重複排除し、重複した片方を黙って落とします——classifier target が専用の `[llm_clients.fireworks_judge]` を使っているのはこのためで、これは 0.2.0 を含む全バージョンに当てはまります。もう 1 つは違います。**#268 以降のビルド**では、サービング呼び出しが route ごとのモデル ID のみをキーとするマップで解決されるため、tier と同一モデルの classifier target に置いた `extra_body` が、その tier のユーザー応答にも適用されます（2026-08-08 実測。2026-08-11 に両ビルドを並べて再測し、リリース版 0.2.0 では起きないことを確認）。**リリース版ではなく main の commit をピンする場合は、先に classifier の `extra_body` を外してください**

### 定期レビュー（ルーティング実績の回収）

週次など定期のタイミングで 1 コマンド:

```bash
./scripts/stats-snapshot.sh
```

`stats-out/` に集計 JSON + per-request ログ（JSONL）が日付・ユーザー名つきで保存され、route 別のリクエスト数・トークン数サマリーが表示されます。出力 2 ファイルは、プロジェクトで指定された方法（共有フォルダへのアップロード等）で収集してください。

複数メンバーから集めたスナップショットを 1 つの利用レポート（ユーザー別・チーム合算のトークン / コスト表、キャッシュヒット率、strong 固定換算との比較）に束ねるには次を実行します。

```bash
./scripts/trial-report.py member-uploads/                 # ファイル・ディレクトリ混在可
./scripts/trial-report.py --since 2026-09-01 --until 2026-09-30
```

ファイル名はスナップショットスクリプトの `routing-<user>-<stamp>.jsonl` のままで、ユーザー帰属は自動です。同一ユーザーの重複スナップショットは行単位で除去されます。単価未登録のモデルはコストから除外したうえで警告を表示します（黙って過小計上しません）。

手動で見たいときの生アクセス:

| 取得面                    | コマンド                                                                | 内容                                                                                       |
| ------------------------- | ----------------------------------------------------------------------- | ------------------------------------------------------------------------------------------ |
| 集計スナップショット      | `curl -s http://127.0.0.1:4100/v1/stats \| python3 -m json.tool`        | モデル別・tier 別のリクエスト数・トークン数の累計 + judge 健全性（**再起動でリセット**）   |
| per-request ログ（JSONL） | `docker cp switchyard-opencode:/app/logs/routing.jsonl ./routing.jsonl` | 1 リクエスト 1 行（選択 tier・モデル・トークン。named volume 永続で耐久記録）              |
| Prometheus メトリクス     | `curl -s http://127.0.0.1:4100/metrics`                                 | `switchyard_classifier_fail_open_total` を含む——judge 故障の検知面としてたまに見る価値あり |

旧構成からの改善が 1 点: classifier 自身のコールが JSONL に `tier="classifier"` で記録されるようになり、これまで不可視だったルーティング判定のコストが週次サマリーに独立行で出ます。

**使用量・コストの正**: [Fireworks ダッシュボード](https://app.fireworks.ai/)のモデル別使用量を見てください。strong（kimi-k3）と weak（deepseek-v4-flash-0731）は別モデルなので、**モデル別使用量がそのまま tier 分布 × コスト**です。これが削減効果レポートの材料になります。目（[qwen3p7-plus](docs/qwen-mm-plugins.ja.md)）のメディア呼び出しも、ダッシュボードでは独立したモデル行、ローカル集計では `pinned:qwen3p7-plus` の独立行になるため、tier 分布と混ざりません。上の stats はルーティング内訳の分析用です。

## 実験用

- [`experimental/permission-judge/`](experimental/permission-judge/) — Claude Code 風の「賢い auto モード」を足す opencode プラグイン。LLM judge（ルーターの weak tier 経由）が permission リクエストの安全性を都度判定し、安全なものだけ自動承認する。較正で一致率が裏づけされるまでは shadow モード（判定・ログのみ、判断は人間）で出荷

## セキュリティノート

- リスナーは **127.0.0.1 バインドのみ**。LAN には公開されません
- ネイティブ Rust サーバーには**リクエスト収集機構がありません**（旧 Python CLI の Intake sink はこのサーバーに存在しません）。リクエスト本文が出ていく先は設定した Fireworks エンドポイントだけです
- ルーティングログ（`/app/logs/routing.jsonl`）は Docker named volume（`switchyard-logs`）内に留まり、ホスト側には `stats-snapshot.sh` / `docker cp` で取り出したときだけ出ます。中身はルーティング判定とトークン数のみで、プロンプト本文は含まれません
- web 検索の安全策（exa.ai 無効化）は本ルーターの管轄外です。web 検索経由の情報送信を絞りたい場合は、opencode 側で先に適用してください（「前提」参照）
- web-search skill のクエリは、各自のキーで検索バックエンド（Gemini API または OpenAI API）に直接送信されます。学習不使用の条件はバックエンドで異なります——Gemini は**課金有効 GCP プロジェクトのキーであることが条件**（free tier のキーは学習に利用されます）、OpenAI は API 既定で学習不使用です（[docs/web-search-onboarding.ja.md](docs/web-search-onboarding.ja.md)）。機密語をクエリに入れない規律は SKILL.md に記載しています
- `nvidia-rag` MCP は読み取り専用の公開面（search / generate 等 5 tools）への接続を前提としています。削除系 tools を含む管理面をプライベート網に公開しない構成は、RAG サービス側の責務です
- 脚注: 平文 `.env` をどうしても避けたい場合は 1Password CLI の `op run` + secret reference でも起動できますが、Docker はコンテナ metadata に env を平文保存するため（`docker inspect` で見えます）利得は限定的です。本バンドルの標準は `.env` + `chmod 600` です

## 実装メモ（メンテナ向け）

- ルーターは **standalone のネイティブ Rust サーバー**（`switchyard-server --config routes.toml`）。上流 #268（2026-08-07）が Python のルーティング実装を削除したため、route-bundle 形式（`type: deterministic`）から移行した。これまでのレール（v2 profile config → route-bundle）はどちらも main から消えている。旧 `route.yaml` は作業リポジトリの `legacy-routebundle/` に参照用として保存
- イメージは crates.io の**リリース版**を入れる（Dockerfile の `SWITCHYARD_VERSION`）。git commit ピンではない。Rust crates が publish されたのは Switchyard 0.2.0（2026-08-10）が最初で、それ以前は main の commit SHA ピンが唯一の選択肢だった。バージョンを上げる前に知っておくべきことが 2 つ。①**リリースタグは `main` から分岐している**（main は次の開発サイクルなので、追従すると未リリース版を動かすことになる）②0.2.0 は `d0b9d50b` から publish されており、**#268 が main に入る 57 分前**の状態。バージョン番号では判別できない（どちらのバイナリも `switchyard-server 0.2.0` と名乗る）。TOML は未知キーを拒否するので、バージョンを上げる際は必ず `switchyard-server --config routes.toml --dry-run` で検証してから配布する
- **judge の思考抑制を復活（2026-08-11）。** classifier target に `extra_body = { reasoning_effort = "none", temperature = 0 }` を戻した。2026-08-08 に外したのは、上記のモデル ID 衝突で weak tier のユーザー応答へ漏れていたためだが、これは #268 が持ち込んだ回帰で、リリース版 0.2.0 はその手前にある。同一の 87 判定セットで有無を比較すると、judge の p50 は 2.2s vs 10.4s、p90 は 4.4s vs 44.5s。エージェントループ形状の行き先はどちらでも同一（30/30 weak）で、動くのは壁打ちだけ（strong 到達 9/13 vs 12/13）。その壁打ちセットは 3 者盲検で weak と strong の回答が同等に使えると判定されている。`base_threshold = 0.75` は据え置き
- **0.2.0 の既知の上流問題**のうち週次レビューに効くもの: judge 失敗時の既定 target フォールバック・escalation の判断・`stage_router` のフォールバックについて、`/v1/stats` と `/metrics` に routing tier が記録されない（上流に修正 PR が出ている）。またクライアント切断後もバッファ済みの上流処理は続くため、キャンセルしたリクエストにも課金が発生しうる
- ルーティングは `llm_classifier` の **capability モード**: judge が `p_solve`（weak tier がタスクを完遂する確率）を推定し、`base_threshold`（+ capability boundary 段階ごとの `threshold_step`）と比較する。現行の閾値（0.75/0.1）は 2026-08-08 に実エージェント transcript 由来の 87 判定セットで較正したもの（既定 0.5 では深い設計議論が weak に漏れる: 9/13 → 0.75 で 12/13）。調整する場合は勘で動かさず、自分の p_solve 分布を測ってから
- judge が読むのは会話の **最初と最新の user メッセージだけ**（既定では assistant / tool ターンは不可視）。旧特徴量抽出 rubric よりセッション中盤の判定が安定しているのはこのためで、較正の主役はプロンプトではなく閾値になる
- schema 検証に失敗した判定や、素の `content` の外に出た回答は **strong に fail-open** する。`/metrics` の `switchyard_classifier_fail_open_total` を監視面に
- session affinity は `session_affinity = true` + `message_hash_fallback = true`。opencode はサーバーが解釈するセッションヘッダを送るが、送らないクライアントは最初の user メッセージのハッシュでカバーされる。割り当てはプロセスローカル（再起動でリセット）、上流実装で 4096 セッション上限
- ランタイムは uid 1000 で実行（旧 Python イメージの最初のユーザーと一致）。`switchyard-logs` named volume の `routing.jsonl` 履歴は chown なしで移行をまたいで引き継がれる
- Dockerfile の `APT::Sandbox::User=root` は colima/lima の既知の癖（`_apt` サンドボックスユーザーが DL 済みパッケージリストを読めず、gpgv 手動検証は通るのに apt が「invalid signature」を報告する）への回避策。Docker Desktop / Linux では無害
- 覚えておく価値のある上流の変更点: `/v1/routing/stats` は `/v1/stats` に変更 / レスポンスヘッダは `x-model-router-selected-model` と `x-model-router-rationale` / routing ログのセッションキーは affinity が見るヘッダと別系統（上流 known issue #7）
