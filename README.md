# Switchyard for opencode + Fireworks（チーム配布バンドル）

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
- Fireworks 試用 Org の個人 API キー（[発行ページ](https://app.fireworks.ai/settings/users/api-keys)。1Password に保管）
- opencode セットアップ済み（[opencode-with-strict-privacy](https://github.com/cm-dyoshikawa/opencode-with-strict-privacy) の MUST 項目——exa.ai 無効化・share 無効化を **Global スコープ**で——を先に済ませること）

## セットアップ

```bash
# 1. このリポジトリを clone してリポジトリ直下へ
git clone https://github.com/himorishige/switchyard-opencode-bundle.git
cd switchyard-opencode-bundle

# 2. API キーを配置（1Password から手動コピー）
cp .env.example .env
chmod 600 .env
# .env を編集して FIREWORKS_API_KEY を実キーに置き換える

# 3. 起動
docker compose up -d --build
# colima 等で `docker compose` が無い場合は plugin を導入（macmini で検証済み）:
#   brew install docker-compose
#   ~/.docker/config.json に "cliPluginsExtraDirs": ["/opt/homebrew/lib/docker/cli-plugins"] を追加
# それも避けたい場合の docker run 代替（route.yaml はイメージに焼き込み済み。
# ただしログ永続化と healthcheck は compose 版のみ）:
#   docker build -t switchyard-opencode . && \
#   docker run -d --name switchyard-opencode --env-file .env \
#     -p 127.0.0.1:4100:4100 --restart unless-stopped switchyard-opencode

# 4. 動作確認
curl -s http://127.0.0.1:4100/health          # {"status":"ok"}
curl -s http://127.0.0.1:4100/v1/models | head  # auto / strong-only / weak-only が並ぶ
```

## opencode 側の設定

`opencode.json.example` の `provider.switchyard` ブロックを **Global 設定**（`~/.config/opencode/opencode.json`）にマージしてください。既定モデルが `switchyard/auto` になります。

- モデル切替は opencode のモデルピッカーから `auto` / `strong-only` / `weak-only` を選択
- Switchyard を止めたいとき（障害切り分け等）は、ピッカーから素の `fireworks-ai/...` モデルを選べば直結にフォールバックできます（AIXC ガイドの標準セットアップ）
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

### 週次レビュー（ルーティング実績の回収）

毎週金曜（目安）に各自 1 コマンド:

```bash
./scripts/stats-snapshot.sh
```

`stats-out/` に集計 JSON + per-request ログ（JSONL）が日付・ユーザー名つきで保存され、route 別のリクエスト数・トークン数サマリーが表示されます。出力 2 ファイルを [AIXC 成果報告フォルダ](https://drive.google.com/drive/u/0/folders/0AMlGENSwjZu5Uk9PVA)へアップロードしてください。

手動で見たいときの生アクセス:

| 取得面                    | コマンド                                                                 | 内容                                                                          |
| ------------------------- | ------------------------------------------------------------------------ | ----------------------------------------------------------------------------- |
| 集計スナップショット      | `curl -s http://127.0.0.1:4100/v1/routing/stats \| python3 -m json.tool` | モデル別リクエスト数・トークン数の累計（**コンテナ再起動でリセット**）        |
| per-request ログ（JSONL） | `docker cp switchyard-opencode:/app/logs/routing.jsonl ./routing.jsonl`  | 1 リクエスト 1 行（選択 tier・モデル・トークン。named volume 永続で耐久記録） |

**使用量・コストの正**: [Fireworks ダッシュボード](https://app.fireworks.ai/)のモデル別使用量を見てください。strong（deepseek-v4-pro）と weak（deepseek-v4-flash）は別モデルなので、**モデル別使用量がそのまま tier 分布 × コスト**です。これが削減費用レポート（AIXC 成果報告）の材料になります。上の stats はルーティング内訳の分析用です。

## セキュリティノート

- リスナーは **127.0.0.1 バインドのみ**。LAN には公開されません
- Switchyard の Intake sink（リクエスト収集機構）は**無効**のままです（`--intake-enabled` を付けていません）。リクエスト本文が出ていく先は設定した Fireworks エンドポイントだけです
- ルーティングログ（`/app/logs/routing.jsonl`）は Docker named volume（`switchyard-logs`）内に留まり、ホスト側には `stats-snapshot.sh` / `docker cp` で取り出したときだけ出ます。中身はルーティング判定とトークン数のみで、プロンプト本文は含まれません
- web 検索の安全策（exa.ai 無効化・webseek 代替）は本ルーターの管轄外です。strict-privacy の MUST 項目を必ず先に適用してください
- 脚注: 平文 `.env` をどうしても避けたい場合は 1Password CLI の `op run` + secret reference でも起動できますが、Docker はコンテナ metadata に env を平文保存するため（`docker inspect` で見えます）利得は限定的です。チーム標準は `.env` + `chmod 600` です

## 実装メモ（メンテナ向け）

- `route.yaml` は Switchyard の **route-bundle 形式**（`switchyard --routing-profiles route.yaml serve`）。旧 v2 profile config（`serve --config` + `serve.py` アダプタ）は上流 PR #119 で撤去予定のため移行済み。旧ファイルは `legacy-v2config/` に退避
- イメージは git main の commit SHA ピン（Dockerfile の `SWITCHYARD_SHA`）。PyPI v0.1.0 は streaming usage 修正（PR #64）未収載のため使わない
- classifier の思考抑制は `request_processor.py` への sed パッチで実現（vLLM 語彙 `chat_template_kwargs` → Fireworks 互換の `reasoning_effort: "none"` に置換。2026-07-23 実測: 判定 18/18 一致・2.7〜4.2 倍高速）。deterministic 型に `disable_reasoning` ノブが無いための措置で、上流には「抑制語彙のプロバイダ対応」を issue 候補として持つ
- 注意: 上流 PR #123（fireworks を deny リストに追加）がマージされた SHA に上げると auto-detect が False になり注入自体が止まる（安全だが思考が復活して低速化）。SHA を上げる際は本パッチとの整合を再確認すること
- `session_affinity: true` + `affinity_warmup_turns: 2` を既定化（2026-07-23 実測: classifier 呼び出し −56%・classifier prompt tokens −55%・ピン後の切替ゼロ）。ピン後は tool-planning エスカレーションも効かなくなる点は既知のトレードオフ（fail-open 判定はピンされないため、低確信のまま固定されることはない）
- 上流の profile-level `subagent_target`（#112）は components-v2 専用 + ヘッダー検知（opencode は非発火）のため不採用。サブエージェント対応は opencode 側設定で足りる
- compose 構成は 2026-07-23 に colima（macmini、compose plugin は brew 導入）で実機検証済み: build → healthy → E2E 疎通 → `switchyard-logs` volume への JSONL 書き込み → `--force-recreate` 後のログ残存、全 PASS
- `route.yaml` の `defaults.extra_body: {}` は load-bearing（`apply_deepseek_overrides()` の vLLM ヒント注入を抑止。上流 PR #122 マージ後の SHA に上げたら不要になる）
