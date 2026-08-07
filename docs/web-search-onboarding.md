# web-search skill オンボーディング（15 分想定）

web-search skill（`plugin/team-ai-kb/skills/web-search/`）は、各自の `GEMINI_API_KEY` で
Gemini API（Google Search grounding）を直接呼びます。中間サーバはありません。

**必ず課金有効の GCP プロジェクトで発行したキーを使ってください。**
free tier（課金未設定）のキーは、Google の利用規約上、検索クエリがモデル学習に使われます。
課金有効プロジェクトのキーは paid tier 扱いとなり学習不使用（DPA 適用）です。
この手順で唯一外せないポイントがここです。

## 手順

1. **GCP プロジェクト作成**（1 分）
   - https://console.cloud.google.com/ → 新規プロジェクト（例: `websearch-<name>`）
   - 他用途と分けるため websearch 専用プロジェクトを推奨（Cloud Billing のレポートが
     そのまま検索コストのレポートになります）
2. **課金アカウントをリンク**（2 分・必須）
   - プロジェクト設定 → 請求先アカウントをリンク
   - 無料枠（月 5,000 クエリ）内なら請求は発生しません。リンクは「paid tier = 学習不使用」の条件です
3. **API キー発行**（2 分）
   - https://aistudio.google.com/ → API keys → 上で作ったプロジェクトを選んで発行
4. **キーを環境変数に配置**（2 分）
   - `~/.zshenv` 等に `export GEMINI_API_KEY=<キー>`（ファイルは chmod 600、キーはパスワードマネージャにも保管）
   - git 管理下のファイルには絶対に書かない
5. **動作確認**（1 分）
   - `uv run plugin/team-ai-kb/skills/web-search/scripts/search.py "DGX Spark のメモリ帯域は？"`
   - 回答 + `Sources:` + 統計行（`-- model=... executed_queries=... tokens=...`）が出れば OK
   - キー未設定・無効の場合はエラーメッセージが案内を出します

## 運用ルール

- 無料枠は**各自のプロジェクトごとに月 5,000 検索クエリ**。1 回の呼び出しで 1〜3 クエリ実行され、
  統計行の `executed_queries` が課金単位です（目安 = 1 日 10〜16 回で枠内）
- 超過は $14/1,000 クエリで各自のプロジェクトに課金。使用量は AI Studio / Cloud Billing で各自確認
- **機密語（顧客名・社内コードネーム・シークレット）をクエリに入れない**（SKILL.md のクエリ規律参照）
- モデル既定は `gemini-3.6-flash`。変更する場合は `WEB_SEARCH_MODEL` 環境変数で上書き
