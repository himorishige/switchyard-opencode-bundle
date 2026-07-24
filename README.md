# Switchyard for opencode + Fireworks

opencode のリクエストを NeMo Switchyard が自動で strong / weak tier に振り分け、品質を保ったままコストを下げるローカルルーターです。各自の端末で Docker コンテナとして常駐させます。

```
opencode → Switchyard (127.0.0.1:4100) → Fireworks AI
              └─ classifier（weak が兼任）が難易度を判定して振り分け
```

| route（opencode のモデル名） | 動作                                                         |
| ---------------------------- | ------------------------------------------------------------ |
| `auto`（既定）               | coding-agent 向け自動ルーティング。普段はこれだけで OK       |
| `strong-only`                | deepseek-v4-pro 固定（ルーティングを疑ったときの切り分け用） |
| `weak-only`                  | deepseek-v4-flash 固定                                       |

設定は `route.yaml`（Switchyard の route-bundle 形式）1 枚です。

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
# → auto / strong-only / weak-only が並ぶ
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
      "weak-only": { "name": "weak-only — deepseek-v4-flash pinned" }
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
- マージ後に opencode を再起動し、モデルピッカーに `Switchyard (Fireworks auto-routing)` のモデル群（`auto` / `strong-only` / `weak-only`）が出ることを確認してください

### 運用のポイント

- モデル切替は opencode のモデルピッカーから `auto` / `strong-only` / `weak-only` を選択
- Switchyard を止めたいとき（障害切り分け等）は、opencode 側に Fireworks 直結のプロバイダ設定があれば、ピッカーから素の `fireworks-ai/...` モデルを選んで直結にフォールバックできます
- `small_model` はタイトル生成などの補助コール用です。`weak-only` 固定にしてあります（auto に流すと小物が strong に化けることがあるため）
- サブエージェントの扱い: 会話単位で classifier が個別に分類・ピン留めするため、軽いサブエージェントは自動で weak に落ちます。常に weak を強制したい場合は opencode の per-agent 設定（`"agent": {"<name>": {"model": "switchyard/weak-only"}}`）を使ってください

## 運用

| 操作                   | コマンド                                                                                                   |
| ---------------------- | ---------------------------------------------------------------------------------------------------------- |
| 更新（設定・イメージ） | `git pull && docker compose up -d --build`                                                                 |
| 設定だけ変えたとき     | `route.yaml` 編集後 `docker compose restart`（compose が bind-mount しているため rebuild 不要）            |
| キーローテーション     | `.env` 更新後 `docker compose up -d --force-recreate`（`restart` はコンテナ作成時の env を再利用するため） |
| 死活確認               | `curl -s http://127.0.0.1:4100/health`                                                                     |
| 停止                   | `docker compose down`                                                                                      |

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
- opencode 側は route 名（`auto` / `strong-only` / `weak-only`）しか見ていないため、`opencode.json` の変更は不要です。モデルピッカーの表示名も実態に合わせたい場合は、`opencode.json` の `models` 配下の `name` を書き換えてください
- `classifier.model` を変更した場合は、変更後に 1 リクエスト流して動作確認してください。イメージに組み込んである思考抑制（`reasoning_effort: "none"`）は deepseek-v4-flash で受理を実測確認したもので、モデルによっては拒否される可能性があります
- `defaults.extra_body: {}` は消さないでください（deepseek-v4 系ターゲット使用時の HTTP 400 回避。他モデルの場合も残して無害です）

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

**使用量・コストの正**: [Fireworks ダッシュボード](https://app.fireworks.ai/)のモデル別使用量を見てください。strong（deepseek-v4-pro）と weak（deepseek-v4-flash）は別モデルなので、**モデル別使用量がそのまま tier 分布 × コスト**です。これが削減効果レポートの材料になります。上の stats はルーティング内訳の分析用です。

## セキュリティノート

- リスナーは **127.0.0.1 バインドのみ**。LAN には公開されません
- Switchyard の Intake sink（リクエスト収集機構）は**無効**のままです（`--intake-enabled` を付けていません）。リクエスト本文が出ていく先は設定した Fireworks エンドポイントだけです
- ルーティングログ（`/app/logs/routing.jsonl`）は Docker named volume（`switchyard-logs`）内に留まり、ホスト側には `stats-snapshot.sh` / `docker cp` で取り出したときだけ出ます。中身はルーティング判定とトークン数のみで、プロンプト本文は含まれません
- web 検索の安全策（exa.ai 無効化・webseek 代替）は本ルーターの管轄外です。web 検索経由の情報送信を絞りたい場合は、opencode 側で先に適用してください（「前提」参照）
- 脚注: 平文 `.env` をどうしても避けたい場合は 1Password CLI の `op run` + secret reference でも起動できますが、Docker はコンテナ metadata に env を平文保存するため（`docker inspect` で見えます）利得は限定的です。本バンドルの標準は `.env` + `chmod 600` です

## 実装メモ（メンテナ向け）

- `route.yaml` は Switchyard の **route-bundle 形式**（`switchyard --routing-profiles route.yaml serve`）。旧 v2 profile config（`serve --config` + `serve.py` アダプタ）は上流 PR #119 で撤去予定のため移行済み
- イメージは git main の commit SHA ピン（Dockerfile の `SWITCHYARD_SHA`）。PyPI v0.1.0 は streaming usage 修正（PR #64）未収載のため使わない
- classifier の思考抑制は `request_processor.py` への sed パッチで実現（vLLM 語彙 `chat_template_kwargs` → Fireworks 互換の `reasoning_effort: "none"` に置換。2026-07-23 実測: 判定 18/18 一致・2.7〜4.2 倍高速）。deterministic 型に `disable_reasoning` ノブが無いための措置で、上流には「抑制語彙のプロバイダ対応」を issue 候補として持つ
- 注意: 上流 PR #123（fireworks を deny リストに追加）がマージされた SHA に上げると auto-detect が False になり注入自体が止まる（安全だが思考が復活して低速化）。SHA を上げる際は本パッチとの整合を再確認すること
- `session_affinity: true` + `affinity_warmup_turns: 2` を既定化（2026-07-23 実測: classifier 呼び出し −56%・classifier prompt tokens −55%・ピン後の切替ゼロ）。ピン後は tool-planning エスカレーションも効かなくなる点は既知のトレードオフ（fail-open 判定はピンされないため、低確信のまま固定されることはない）
- 上流の profile-level `subagent_target`（#112）は components-v2 専用 + ヘッダー検知（opencode は非発火）のため不採用。サブエージェント対応は opencode 側設定で足りる
- compose 構成は colima 環境（compose plugin は brew 導入）で実機検証済み（2026-07-23）: build → healthy → E2E 疎通 → `switchyard-logs` volume への JSONL 書き込み → `--force-recreate` 後のログ残存、全 PASS
- `route.yaml` の `defaults.extra_body: {}` は load-bearing（`apply_deepseek_overrides()` の vLLM ヒント注入を抑止。上流 PR #122 マージ後の SHA に上げたら不要になる）
