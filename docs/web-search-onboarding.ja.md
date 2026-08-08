# web-search skill オンボーディング

[English](web-search-onboarding.md) | **日本語**

web-search skill（`plugin/team-ai-kb/skills/web-search/`）は、各自の API キーで
検索バックエンドを直接呼びます。中間サーバはありません。
バックエンドは **Gemini（推奨）/ OpenAI（代替）** の 2 つで、どちらか一方だけで動きます。
設定済みのキーの環境変数から自動判別されます（両方ある場合は Gemini 優先。
`WEB_SEARCH_PROVIDER=openai` で明示切替）。

## バックエンドの選び方

| バックエンド   | 学習不使用の条件                                                              | 無料枠             | 超過時の目安  | 所要  |
| -------------- | ----------------------------------------------------------------------------- | ------------------ | ------------- | ----- |
| Gemini（推奨） | **課金有効の GCP プロジェクトのキーであること**（free tier は学習利用される） | 月 5,000 クエリ/人 | $14/1k クエリ | 15 分 |
| OpenAI（代替） | API 既定で学習不使用（追加条件なし）                                          | なし               | ≈$0.012/検索  | 5 分  |

普段使いは無料枠のある Gemini を推奨します。課金有効の GCP プロジェクトが用意できない場合は
OpenAI を使ってください。

## Gemini で使う（15 分）

**必ず課金有効の GCP プロジェクトで発行したキーを使ってください。**
free tier（課金未設定）のキーは、Google の利用規約上、検索クエリがモデル学習に使われます。
課金有効プロジェクトのキーは paid tier 扱いとなり学習不使用（DPA 適用）です。
この手順で唯一外せないポイントがここです。

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
   - 回答 + `Sources:` + 統計行（`-- provider=gemini model=... executed_queries=... tokens=...`）が出れば OK
   - キー未設定・無効の場合はエラーメッセージが案内を出します
   - モデル既定は `gemini-3.6-flash`。変更する場合は `WEB_SEARCH_MODEL` 環境変数で上書き

## OpenAI で使う（5 分）

学習不使用は API の既定です（明示的にオプトインしない限り学習に使われません。
不正利用監視のための最大 30 日保持はあります）。無料枠はなく、1 検索 ≈$0.012
（web search ツール課金 + トークン実費）が各自のアカウントに課金されます。

1. **API キー発行**（2 分）
   - https://platform.openai.com/api-keys から発行（Organization 経由で払い出す場合はチームの案内に従ってください）
2. **キーを環境変数に配置**（2 分）
   - `~/.zshenv` 等に `export OPENAI_API_KEY=<キー>`（chmod 600・パスワードマネージャ保管・git 管理下に書かない、は Gemini と同じです）
   - `GEMINI_API_KEY` も設定している場合は Gemini が優先されます。OpenAI を使うときは
     `export WEB_SEARCH_PROVIDER=openai` を追加してください
3. **動作確認**（1 分）
   - コマンドは Gemini と同じです。統計行が `-- provider=openai model=gpt-5-mini ...` になっていれば OK
   - モデル既定は `gpt-5-mini`。変更する場合は `WEB_SEARCH_MODEL` 環境変数で上書き

## 運用ルール（両バックエンド共通）

- **機密語（顧客名・社内コードネーム・シークレット）をクエリに入れない**（SKILL.md のクエリ規律参照）
- 同じ質問の言い換えリトライを機械的に繰り返さない（2 回試して駄目なら質問を変えるか、ソースを直接 fetch する）
- ローカルナレッジで足りる話題（チームの検証記録・過去記事）は rag-kb を先に使う
- Gemini の無料枠は**各自のプロジェクトごとに月 5,000 検索クエリ**。1 回の呼び出しで 1〜3 クエリ実行され、
  統計行の `executed_queries` が課金単位です（目安 = 1 日 10〜16 回で枠内）。
  超過分と OpenAI の利用分は各自のアカウントに課金されるので、使用量は各自のダッシュボード
  （AI Studio / Cloud Billing、OpenAI Usage）で確認してください
