---
name: web-search
description: >
  Gemini（Google Search grounding）または OpenAI（web search）による web 検索。出典つきの回答を返す。
  Use when: 最新情報・公開情報を web で調べたい / 「web で検索して」「ググって」と言われた /
  ローカルナレッジ（rag-kb）にない一般知識・最新リリース・価格・仕様を確認したい。
  Trigger keywords: web検索, 検索して, ググって, 調べて, web search, 最新情報, リリース情報
---

# web-search — grounded web 検索（Gemini / OpenAI）

各自の API キーで検索バックエンド（Gemini または OpenAI）を直接呼ぶ。
中間サーバなし。クエリは自分の端末から選んだバックエンド 1 社にのみ送信される。

## 実行方法

この skill の `scripts/search.py` を質問文つきで実行します（stdlib のみ、依存なし）。

```bash
uv run <この skill のディレクトリ>/scripts/search.py "質問文"
# uv がなければ python3 でも可
```

出力 = grounded な回答本文 + `Sources:`（出典 URL）+ 使用統計 1 行
（`-- provider=... model=... executed_queries=... tokens=...`）。

## 前提（初回のみ）

- 環境変数のキーが **どちらか一方** 必要。バックエンドはキーから自動判別される
  （両方ある場合は Gemini 優先。`WEB_SEARCH_PROVIDER=gemini|openai` で明示切替）
  - `GEMINI_API_KEY`（推奨・無料枠あり）: **必ず課金有効の GCP プロジェクトで発行したキー**を使う
    （free tier キーはクエリが Google の学習に使われる）
  - `OPENAI_API_KEY`（代替・無料枠なし）: API 既定で学習不使用。追加条件なし
  - 手順 = 配布リポジトリの `docs/web-search-onboarding.md`
- モデル既定は Gemini = `gemini-3.6-flash` / OpenAI = `gpt-5-mini`。
  `WEB_SEARCH_MODEL` 環境変数で上書き可

## クエリ規律（必須）

- **機密語をクエリに入れない**（顧客名・社内コードネーム・未公開の内部情報・シークレット類）。
  一般語に言い換えてから検索する
- 質問は文のまま渡してよい（キーワード分解より文の方が grounding が効く）
- 回答には `Sources:` の出典を添えて引用する。出典が空の回答は「未確認情報」として扱う

## コストマナー

- Gemini の課金は「実行された検索クエリごと」で、1 回の呼び出しで 1〜3 クエリ走る
  （出力の統計行で見える）。無料枠は各自の GCP プロジェクトごとに月 5,000 クエリ。
  OpenAI は無料枠なしの従量（≈$0.012/検索）
- **同じ質問の言い換えリトライを機械的に繰り返さない**（2 回試して駄目なら質問を変えるか、
  ソースを直接 fetch する）
- ローカルナレッジで足りる話題（チームの検証記録・過去記事）は rag-kb を先に使う
