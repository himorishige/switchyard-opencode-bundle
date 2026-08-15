# Pi オンボーディング — 2 つ目のクライアント（任意、15〜20 分）

## 概要

[Pi](https://pi.dev/)（[earendil-works/pi](https://github.com/earendil-works/pi)、MIT）は最小構成のコーディングエージェントハーネスです。システムプロンプトは約 430 トークン、コアツールは 4 つだけで、残りは extension と package で足す設計です。このガイドでは、opencode で使っているのと同じ Switchyard ルーターに Pi を接続します。ルーティング・コスト記録・team-ai-kb スキルは両クライアントで共通のままです。

このバンドルの主クライアントは引き続き opencode です。Pi も入れておく理由は次のとおりです。

- headless の画像入力が動きます: `pi -p @screenshot.png "..."`（opencode の `run -f` は現在画像添付でハングします）
- `--mode json` がトークン使用量つきの機械可読イベントストリームを出すため、スクリプトや他エージェントからの委譲に向きます
- MCP サーバへは単一の遅延プロキシツール（約 200 トークン）で到達するため、weak tier でもコンテキストが膨れません
- サブスクリプション認証（`/login`）: ChatGPT Plus/Pro（Codex）・Claude・Copilot などをルーターと並用できます

注意: Pi には**組み込みの permission 確認がありません**（設計思想としての YOLO）。実行ユーザーの全権限で動くため、信頼できる作業ディレクトリで使ってください。ガードレールが欲しい場合は `@gotgenes/pi-permission-system` を追加します（手順 5）。

## 1. Pi のインストール

```bash
npm install -g --ignore-scripts @earendil-works/pi-coding-agent
# または: bun add -g @earendil-works/pi-coding-agent
pi --version
```

## 2. ルーターへの接続

ルーターが起動済みであることが前提です（メイン README 参照）。モデル定義をコピーします。

```bash
mkdir -p ~/.pi/agent
cp pi-models.json.example ~/.pi/agent/models.json
```

ルーターが `127.0.0.1:4100` 以外にある場合は `baseUrl` を書き換えてください。

## 3. settings（既定モデル + チームスキル）

```bash
cp pi-settings.json.example ~/.pi/agent/settings.json
```

`~/.pi/agent/settings.json` を開き、`<bundle-repo>` をこのリポジトリのクローンの絶対パスに置き換えます。これでチームスキル（`rag-kb` / `web-search`）が Pi でも使えるようになります。スキルは Agent Skills 標準のため、opencode と Pi で同じファイルを共用します。`web-search` スキルは web-search オンボーディングで設定済みの `GEMINI_API_KEY` / `OPENAI_API_KEY` 環境変数をそのまま使います。

既に自分の `settings.json` がある場合は、上書きせず `skills` エントリだけマージしてください。

## 4. 動作確認

```bash
pi                       # TUI。フッターに "(switchyard) auto" が出ます
pi --list-models switchyard
pi -p "このリポジトリを 2 文で説明して"            # headless
pi -p @screenshot.png "この画像に何が写っている？"  # 画像つき headless（k3-only か qwen3.7-plus で）
```

TUI 内では `/model` または `Ctrl+P` で route を切り替えます（日常は `auto`、難しいタスクは `strong-only` / `k3-only`）。`/skill:web-search` と `/skill:rag-kb` でチームスキルを直接呼べます。

## 5. 追加パッケージ（任意）

```bash
pi install npm:pi-mcp-adapter          # MCP 対応（単一の遅延プロキシツール）
pi install npm:pi-subagents            # scout / reviewer / worker への委譲
pi install npm:@gotgenes/pi-permission-system   # allow/ask/deny のガードレールが欲しい場合
```

MCP は、既にあれば標準の `.mcp.json` をそのまま読みます。チームの RAG サービスに繋ぐ場合は `~/.pi/agent/mcp.json` に追記します。

```json
{
  "mcpServers": {
    "nvidia-rag": { "url": "http://<rag-service-host>:8091/mcp" }
  }
}
```

`pi-permission-system` を入れる場合の注意: インストールすると**全プロジェクトに適用**されます。`~/.pi/agent/extensions/pi-permission-system/config.json` に許可ベースの既定（`"*": "allow"` + 必要な deny / ask ルール）を必ず作ってください。これが無いと headless 実行が全ツールで fail-closed になります。

## 6. サブスクリプションモデルの並用（任意）

TUI の `/login` から ChatGPT Plus/Pro（Codex）・Claude・Copilot のサブスクリプション認証を追加できます。追加したモデルは `/model` で Switchyard route と並んで表示されます。ただしサブスクリプション利用はルーター台帳の外になるため、日常作業を route 側で行うことでチームのコスト集計の意味が保たれます。

## 7. 検証チェックリスト

- [ ] `pi --list-models switchyard` で 6 route が表示される
- [ ] TUI フッターに `(switchyard) auto` が出てプロンプトに応答する
- [ ] `pi -p "1+1?"` が headless で動く
- [ ] `/skill:` の補完に `rag-kb` と `web-search` が出る
- [ ] （任意）pi-mcp-adapter 導入後、`mcp` ツールで `nvidia-rag` に到達できる
