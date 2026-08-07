# Switchyard for opencode + Fireworks

opencode のリクエストを NeMo Switchyard が自動で strong / weak tier に振り分け、品質を保ったままコストを下げるローカルルーターです。各自の端末で Docker コンテナとして常駐させます。

```
opencode → Switchyard (127.0.0.1:4100) → Fireworks AI
              └─ classifier（weak が兼任）が難易度を判定して振り分け
```

| route（opencode のモデル名） | 動作                                                                                            |
| ---------------------------- | ----------------------------------------------------------------------------------------------- |
| `auto`（既定）               | coding-agent 向け自動ルーティング。普段はこれだけで OK                                          |
| `strong-only`                | deepseek-v4-pro 固定（ルーティングを疑ったときの切り分け用）                                    |
| `weak-only`                  | deepseek-v4-flash-0731 固定                                                                     |
| `k3-only`                    | Kimi K3 固定（オプトイン。深いプランニング・設計相談向け。[コスト注意](#k3-only-の使いどころ)） |

設定は `route.yaml`（Switchyard の route-bundle 形式）1 枚です。

> 初めてセットアップする場合は、[docs/onboarding.md](docs/onboarding.md)（初回セットアップの一本道手順）から始めるのがおすすめです。

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

初回は Switchyard の Rust 拡張をビルドするため数分かかります。

colima 等の Docker Desktop 以外の環境では、`docker compose` サブコマンドが入っていないことがあります。その場合はスタンドアロン版 compose を導入します。

```bash
brew install docker-compose
```

導入後は、本 README 内の `docker compose ...` を **`docker-compose ...`** に読み替えて実行してください（例: `docker-compose up -d --build`。中身は同じ compose v2 なので動作は変わりません）。

`docker compose` のサブコマンド構文のまま使いたい場合のみ、`~/.docker/config.json` に次のキーを追加すると plugin として認識されます（既存の `auths` 等は残したままにします。パスは `brew --prefix` の出力に合わせてください。Apple Silicon は `/opt/homebrew`、Intel は `/usr/local`）。認識されない環境でも、スタンドアロン版の読み替えで問題ありません。

```json
"cliPluginsExtraDirs": ["/opt/homebrew/lib/docker/cli-plugins"]
```

compose を使わない場合は docker run でも起動できます（`route.yaml` はイメージに焼き込み済み。ただしログ永続化と healthcheck は compose 版のみ）。

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
# → auto / strong-only / weak-only / k3-only が並ぶ
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
- strict-privacy の環境変数側の設定（`OPENCODE_ENABLE_EXA=0` 等）はこのファイルには含まれません。シェル rc への設定は別途済ませてください

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
      "strong-only": { "name": "strong-only — deepseek-v4-pro pinned" },
      "weak-only": { "name": "weak-only — deepseek-v4-flash-0731 pinned" },
      "k3-only": { "name": "k3-only — kimi-k3 pinned (opt-in)" }
    }
  }
},
"model": "switchyard/auto",
"small_model": "switchyard/weak-only"
```

マージ時の注意点は次のとおりです。

- 既に `provider` キーがある場合は、その**中に** `switchyard` エントリだけを追加してください。`provider` ブロックごと貼り付けて置き換えると、既存のプロバイダ設定が消えます
- strict-privacy 系のキー（`share` / `autoupdate` / `tools` / `permission` 等）とは衝突しません。そのまま共存できます
- `model` / `small_model` を既に設定していて、いまの既定モデルを残したい場合は、この 2 行を取り込まず、使うときだけモデルピッカーから選択してください
- マージ後に opencode を再起動し、モデルピッカーに `Switchyard (Fireworks auto-routing)` のモデル群（`auto` / `strong-only` / `weak-only` / `k3-only`）が出ることを確認してください

### 運用のポイント

- モデル切替は opencode のモデルピッカー（`/models`）から選択します。プロバイダ `Switchyard (Fireworks auto-routing)` の下に 4 つのルートが並びます
- Switchyard を止めたいとき（障害切り分け等）は、opencode 側に Fireworks 直結のプロバイダ設定があれば、ピッカーから素の `fireworks-ai/...` モデルを選んで直結にフォールバックできます
- `small_model` はタイトル生成などの補助コール用です。`weak-only` 固定にしてあります（auto に流すと小物が strong に化けることがあるため）
- サブエージェントの扱い: 会話単位で classifier が個別に分類・ピン留めするため、軽いサブエージェントは自動で weak に落ちます。常に weak を強制したい場合は opencode の per-agent 設定（`"agent": {"<name>": {"model": "switchyard/weak-only"}}`）を使ってください

### k3-only の使いどころ

`k3-only` は **Kimi K3 を固定で使うオプトインのルート**です。`auto` の振り分け先には入っていません。

自動ルーティングに載せていない理由は 2 つあります。

1. **コスト差が大きい**。100 万トークンあたり K3 は $3.00 / $0.30 / $15.00（input / cached / output）、deepseek-v4-pro は $1.74 / $0.145 / $3.48 です。output の単価差は 4.3 倍ですが、K3 は思考も長いため、戦略・プランニング系の 6 問で測ったときの実コストは **約 7 倍**（レイテンシは約 2.5 倍）でした
2. **classifier がこの領域を拾えない**。`coding_agent` プリセットの判定材料はコード作業の特徴量（変更範囲・ツール呼び出し数・コードベース文脈の要否）で構成されているため、コードを触らない設計相談や戦略の壁打ちは「単純」と判定されがちです。しかも誤る側ほど確信度が高く出るため、`min_confidence` を上げても救えません

そのため、**深い設計相談・プランニングを始めるときに手動で選ぶ**運用を想定しています。コードを書くフェーズに戻ったら `auto` に戻してください。

#### 選び方

モデルピッカー（`/models`）では、プロバイダ `Switchyard (Fireworks auto-routing)` の下に次の表示で並びます。検索欄に `k3` と入力すると絞り込めます。

```
Switchyard (Fireworks auto-routing)
  auto        — Switchyard routing
  strong-only — deepseek-v4-pro pinned
  weak-only   — deepseek-v4-flash-0731 pinned
  k3-only     — kimi-k3 pinned (opt-in)
```

Kimi や Moonshot のプロバイダとしては出てきません。opencode から見た実体は、あくまで Switchyard のピン留めルートです。

CLI から 1 回だけ使う場合は `-m` で指定できます。

```bash
opencode run -m switchyard/k3-only "この設計の穴を洗い出して"
```

#### すでにルーターを使っている場合の追加手順

`k3-only` は後から追加されたルートです。以前のバージョンから使っている場合は、ルーターの更新に加えて **Global 設定への登録**が必要です。

```bash
git pull && docker compose restart
curl -s http://127.0.0.1:4100/v1/models | grep k3-only   # 出れば OK
```

続いて `~/.config/opencode/opencode.json` の `provider.switchyard.models` に 1 行足します。

```json
"models": {
  "auto": { "name": "auto — Switchyard routing" },
  "strong-only": { "name": "strong-only — deepseek-v4-pro pinned" },
  "weak-only": { "name": "weak-only — deepseek-v4-flash-0731 pinned" },
  "k3-only": { "name": "k3-only — kimi-k3 pinned (opt-in)" }
}
```

保存したら opencode を再起動します。設定は起動時にしか読み込まれないため、起動しっぱなしのセッションには反映されません。

opencode はここに書かれたモデルしか認識しないため、登録前に `switchyard/k3-only` を指定すると `UnknownError` になります。ルーター側の `/v1/models` に出ていても同じです。

#### plan モードだけ K3 に固定する

壁打ちのたびに切り替えるのが面倒な場合は、opencode の per-agent 設定で plan モードだけ K3 にできます。`~/.config/opencode/opencode.json` の**トップレベル**に `agent` キーを追加します（`provider` や `model` と同じ階層です。すでに `agent` キーがある場合は、その中に各エントリを足してください）。

```json
"agent": {
  "plan": { "model": "switchyard/k3-only" },
  "explore": { "model": "switchyard/weak-only" },
  "scout": { "model": "switchyard/weak-only" }
}
```

`explore` / `scout` にも明示指定しているのは、**opencode のサブエージェントが呼び出し元のモデルを継承する**ためです。指定を省くと、grep 結果を読むだけのサブエージェントにも $15/1M の output 単価が乗ります。

この設定を入れると、plan モードに切り替えたときだけ K3 になり、build モードに戻せば既定の `auto` に戻ります。モデルピッカー側の既定（`model`）を変える必要はありません。`opencode run --agent plan` でも同じ経路を通ります。

前提として `k3-only` の登録（前節）を先に済ませてください。未登録のままだと plan モードに入った時点でエラーになります。

## Agent Plugin（rag-kb / web-search）

`plugin/team-ai-kb/` は [Agent Plugins 標準](https://agent-plugins.org/)（v1.0.0）準拠のプラグインです。ルーターとは独立したオプションで、エージェント拡張 2 本 + MCP 定義を同梱しています。

| コンポーネント                              | 内容                                                                                      | 前提                                                                                        |
| ------------------------------------------- | ----------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------- |
| skill `rag-kb`                              | チーム共通ナレッジ検索（NVIDIA RAG Blueprint の MCP）の使い方ガイド                       | RAG サービスへのプライベート網到達 + 下記 MCP 登録                                          |
| skill `web-search`（+ `scripts/search.py`） | Gemini + Google Search grounding の web 検索。各自の API キーで直接呼ぶ（中間サーバなし） | `GEMINI_API_KEY`。発行手順 = [docs/web-search-onboarding.md](docs/web-search-onboarding.md) |
| `mcp.json`                                  | `nvidia-rag`（streamable HTTP）の MCP サーバ定義                                          | 下記の初期設定                                                                              |

### 初期設定（共通・初回のみ）

RAG の接続先はプライベート網内のアドレスのため、`.env` と同じ流儀で example からコピーして書き換えます（実ファイルは gitignore 済み）。

```bash
cp plugin/team-ai-kb/mcp.json.example plugin/team-ai-kb/mcp.json
# mcp.json の <rag-service-host> をサービス機のアドレスに書き換える
```

### opencode で使う

skills を発見パスへリンクし、MCP を Global 設定に 1 エントリ足します。

```bash
ln -s "$(pwd)/plugin/team-ai-kb/skills/rag-kb" ~/.config/opencode/skills/rag-kb
ln -s "$(pwd)/plugin/team-ai-kb/skills/web-search" ~/.config/opencode/skills/web-search
```

```jsonc
// ~/.config/opencode/opencode.json の "mcp" ブロックに追記
"nvidia-rag": {
  "type": "remote",
  "url": "http://<rag-service-host>:8091/mcp",
  "enabled": true
}
```

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

skills はシンボリックリンク経由なので `git pull` だけで反映されます。`mcp.json.example` が変わったリリースでは、手元の `mcp.json` への反映を確認してください。

## 運用

| 操作                   | コマンド                                                                                                   |
| ---------------------- | ---------------------------------------------------------------------------------------------------------- |
| 更新（設定・イメージ） | `git pull && docker compose up -d --build`                                                                 |
| 設定だけ変えたとき     | `route.yaml` 編集後 `docker compose restart`（compose が bind-mount しているため rebuild 不要）            |
| キーローテーション     | `.env` 更新後 `docker compose up -d --force-recreate`（`restart` はコンテナ作成時の env を再利用するため） |
| 死活確認               | `curl -s http://127.0.0.1:4100/health`                                                                     |
| 停止                   | `docker compose down`                                                                                      |

`route.yaml` だけが変わったリリース（tier の向き先変更など）では `git pull && docker compose restart` で足ります。イメージが変わっていなければ rebuild は不要です。

route が**追加**されたリリースでは、それに加えて Global 設定（`~/.config/opencode/opencode.json`）の `provider.switchyard.models` にも同じ route 名を登録してください。ルーター側を更新しただけではモデルピッカーに出てきません（手順は「[すでにルーターを使っている場合の追加手順](#すでにルーターを使っている場合の追加手順)」）。

### モデルを変更するには

tier の向き先は `route.yaml` の model 行で決まります。例として strong を deepseek-v4-pro から GLM-5.2 に切り替える場合、次の 2 箇所を書き換えます。

1 箇所目は `routes.auto` 配下です（自動ルーティングの振り分け先）。

```yaml
strong:
  model: accounts/fireworks/models/glm-5p2
```

2 箇所目は `routes.strong-only` 配下です（ピン留めルートも合わせて変更します）。

```yaml
strong-only:
  type: model
  target: accounts/fireworks/models/glm-5p2
```

編集後は restart だけで反映されます（bind-mount のため rebuild 不要）。

```bash
docker compose restart
curl -s http://127.0.0.1:4100/health
```

注意点は次のとおりです。

- 使えるモデル ID は [Fireworks serverless カタログ](https://app.fireworks.ai/models?capability=serverless)で確認できます
- opencode 側は route 名（`auto` / `strong-only` / `weak-only` / `k3-only`）しか見ていないため、向き先を変えるだけなら `opencode.json` の変更は不要です。モデルピッカーの表示名も実態に合わせたい場合は、`opencode.json` の `models` 配下の `name` を書き換えてください。route 名そのものを増やした場合は `models` への登録が別途必要です
- `classifier.model` を変更した場合は、変更後に 1 リクエスト流して動作確認してください。イメージに組み込んである思考抑制（`reasoning_effort: "none"`）は deepseek-v4-flash-0731 で受理を実測確認したもので、モデルによっては拒否される可能性があります
- `defaults.extra_body: {}` は消さないでください（deepseek-v4 系ターゲット使用時の HTTP 400 回避。他モデルの場合も残して無害です）

### strong を K3 に差し替えるには

`k3-only` を都度選ぶのではなく、自動ルーティングの strong 側を丸ごと Kimi K3 にすることもできます。上と同じ 2 箇所を書き換えるだけです。

```yaml
# 1. routes.auto 配下
strong:
  model: accounts/fireworks/models/kimi-k3

# 2. routes.strong-only 配下
strong-only:
  type: model
  target: accounts/fireworks/models/kimi-k3
```

コスト影響を先に把握しておいてください。エージェントループの実測トークン分布に単価を当てた試算では、**1 run あたりの絶対額が約 3 倍**になります（strong 固定・auto ともに 3.0 倍）。weak との併用による削減率自体は −40% → −39% とほぼ変わらないため、「auto にすれば K3 の高単価が薄まる」という効果は期待できません。薄まるのではなく、**下限も上限も一緒に持ち上がる**と考えてください。

また、コストの支配項が output に移ります（K3 は総額の約 68% が output、deepseek-v4-pro は約 47%）。長文の設計文書や大きなパッチを吐かせる使い方をするほど、試算より上振れします。

まずは `k3-only` を手動で使って費用対効果を確かめ、それから差し替えを検討するのが安全です。

### 定期レビュー（ルーティング実績の回収）

週次など定期のタイミングで 1 コマンド:

```bash
./scripts/stats-snapshot.sh
```

`stats-out/` に集計 JSON + per-request ログ（JSONL）が日付・ユーザー名つきで保存され、route 別のリクエスト数・トークン数サマリーが表示されます。出力 2 ファイルは、プロジェクトで指定された方法（共有フォルダへのアップロード等）で収集してください。

手動で見たいときの生アクセス:

| 取得面                    | コマンド                                                                 | 内容                                                                          |
| ------------------------- | ------------------------------------------------------------------------ | ----------------------------------------------------------------------------- |
| 集計スナップショット      | `curl -s http://127.0.0.1:4100/v1/routing/stats \| python3 -m json.tool` | モデル別リクエスト数・トークン数の累計（**コンテナ再起動でリセット**）        |
| per-request ログ（JSONL） | `docker cp switchyard-opencode:/app/logs/routing.jsonl ./routing.jsonl`  | 1 リクエスト 1 行（選択 tier・モデル・トークン。named volume 永続で耐久記録） |

**使用量・コストの正**: [Fireworks ダッシュボード](https://app.fireworks.ai/)のモデル別使用量を見てください。strong（deepseek-v4-pro）と weak（deepseek-v4-flash-0731）は別モデルなので、**モデル別使用量がそのまま tier 分布 × コスト**です。これが削減効果レポートの材料になります。上の stats はルーティング内訳の分析用です。

## セキュリティノート

- リスナーは **127.0.0.1 バインドのみ**。LAN には公開されません
- Switchyard の Intake sink（リクエスト収集機構）は**無効**のままです（`--intake-enabled` を付けていません）。リクエスト本文が出ていく先は設定した Fireworks エンドポイントだけです
- ルーティングログ（`/app/logs/routing.jsonl`）は Docker named volume（`switchyard-logs`）内に留まり、ホスト側には `stats-snapshot.sh` / `docker cp` で取り出したときだけ出ます。中身はルーティング判定とトークン数のみで、プロンプト本文は含まれません
- web 検索の安全策（exa.ai 無効化）は本ルーターの管轄外です。web 検索経由の情報送信を絞りたい場合は、opencode 側で先に適用してください（「前提」参照）
- web-search skill のクエリは、各自のキーで Gemini API（Google）に直接送信されます。学習不使用は**課金有効 GCP プロジェクトのキーであることが条件**です（[docs/web-search-onboarding.md](docs/web-search-onboarding.md)）。機密語をクエリに入れない規律は SKILL.md に記載しています
- `nvidia-rag` MCP は読み取り専用の公開面（search / generate 等 5 tools）への接続を前提としています。削除系 tools を含む管理面をプライベート網に公開しない構成は、RAG サービス側の責務です
- 脚注: 平文 `.env` をどうしても避けたい場合は 1Password CLI の `op run` + secret reference でも起動できますが、Docker はコンテナ metadata に env を平文保存するため（`docker inspect` で見えます）利得は限定的です。本バンドルの標準は `.env` + `chmod 600` です

## 実装メモ（メンテナ向け）

- `route.yaml` は Switchyard の **route-bundle 形式**（`switchyard --routing-profiles route.yaml serve`）。旧 v2 profile config（`serve --config` + `serve.py` アダプタ）は上流 PR #119 で撤去予定のため移行済み
- イメージは git main の commit SHA ピン（Dockerfile の `SWITCHYARD_SHA`）。PyPI v0.1.0 は streaming usage 修正（PR #64）未収載のため使わない
- classifier の思考抑制は `request_processor.py` への sed パッチで実現（vLLM 語彙 `chat_template_kwargs` → Fireworks 互換の `reasoning_effort: "none"` に置換。2026-07-23 実測: 判定 18/18 一致・2.7〜4.2 倍高速）。deterministic 型に `disable_reasoning` ノブが無いための措置で、上流には「抑制語彙のプロバイダ対応」を issue 候補として持つ
- weak tier は 2026-08-03 に deepseek-v4-flash-0731（preview 版を置き換える公式リリース）へ更新。同一価格で agentic 系ベンチが大きく伸びており、classifier としても抑制ノブが効く（実測: `reasoning_effort: "none"` 受理・completion 61 tokens 固定・reasoning_content 空。ノブ無しでは 431 tokens / 1.5k 字の思考が出る）。0731 のモデルカードは `reasoning_effort` を low/high/max としか書いていないが、`"none"` は実測で受理される。代替ノブとして `thinking: {"type": "disabled"}` も同じ結果になることを確認済み
- Dockerfile のパッチ検証 assert が参照するモデル ID は `model_accepts_reasoning_hint()`（プロバイダタグ判定）の入力であり、tier に指定した実モデルの版番号とは独立。tier を差し替えても Dockerfile を触る必要はなく、利用者側の更新も rebuild なしで済む
- 注意: 上流 PR #123（fireworks を deny リストに追加）がマージされた SHA に上げると auto-detect が False になり注入自体が止まる（安全だが思考が復活して低速化）。SHA を上げる際は本パッチとの整合を再確認すること
- `session_affinity: true` + `affinity_warmup_turns: 2` を既定化（2026-07-23 実測: classifier 呼び出し −56%・classifier prompt tokens −55%・ピン後の切替ゼロ）。ピン後は tool-planning エスカレーションも効かなくなる点は既知のトレードオフ（fail-open 判定はピンされないため、低確信のまま固定されることはない）
- 上流の profile-level `subagent_target`（#112）は components-v2 専用 + ヘッダー検知（opencode は非発火）のため不採用。サブエージェント対応は opencode 側設定で足りる
- compose 構成は colima 環境（compose plugin は brew 導入）で実機検証済み（2026-07-23）: build → healthy → E2E 疎通 → `switchyard-logs` volume への JSONL 書き込み → `--force-recreate` 後のログ残存、全 PASS
- `route.yaml` の `defaults.extra_body: {}` は load-bearing（`apply_deepseek_overrides()` の vLLM ヒント注入を抑止。上流 PR #122 マージ後の SHA に上げたら不要になる）
