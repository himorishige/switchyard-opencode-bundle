[English](qwen-mm-plugins.md) | **日本語**

# weak tier の目（Qwen-MM-Plugins）

テキスト専用の weak tier に、ツールとして呼べる「目」を付ける。ツールを提供するのは
[Qwen-MM-Plugins](https://github.com/QwenLM/Qwen-MM-Plugins) で、ルーターが専用 route で
ホスト型の vision モデルを提供する。

**ステータス: 画像のみ。** ルーター側（`routes.toml`）は既定で配線済み。使うかどうかは
opencode 側のオプトインで、下の MCP ブロックをマージすると有効になる。音声・手元の動画
ファイル・`grounding` はホスト型では動かない（[制約](#制約)を参照）。

## なぜ

`deepseek-v4-flash-0731` は安くて速いが、画像入力をはっきり拒否する。

```
POST /v1/chat/completions  + image_url
→ 400 This model does not support image inputs
```

素直な解決は weak tier を vision 対応モデルに替えることだが、画像が関係しない大多数のターンまで
単価が上がる。この構成は逆で、モデルはテキスト専用のまま、画像はテキストを返すツールに任せる。

```
opencode
  ├─ 脳    → ルーター → auto / weak-only → deepseek-v4-flash-0731  （画像を一度も受け取らない）
  └─ MCP   → ルーター → qwen3.7-plus     → Fireworks qwen3p7-plus  （画像を見てテキストを返す）
```

脳に届くのは説明文であって画像ではないので、コンテキストは軽いままで、ルーティングの設定も変わらない。

## 速度とコスト

このリポジトリのルーター経由で実測（n=3）。どちらのタスクもスコアは満点。

| タスク                      | レイテンシ | completion tokens |
| --------------------------- | ---------- | ----------------- |
| 現場写真から保護具を列挙    | 1.61s      | 302               |
| グラフに印字された数値 4 つ | 0.76s      | 53                |

`qwen3p7-plus` は 100 万トークンあたり $0.4 / $1.6 / $0.08（入力 / 出力 / キャッシュ入力）。
スクリーンショットを撮って CSS のバグを特定・修正・再確認まで回した 1 セッションで、目が使ったのは
1,626 prompt + 752 completion トークン、**約 $0.002** だった。

メディア呼び出しも他のリクエストと同じく `routing.jsonl` に残り、`scripts/stats-snapshot.sh` と
`scripts/trial-report.py` はこれを独立した行（`pinned:qwen3p7-plus`）で集計する。週次レビューで
コストを分離できる。

## セットアップ

ルーター側は配線済み —— `routes.toml` に vision target と `qwen3.7-plus` route が定義されている。
確認は次のとおり。

```bash
curl -s http://127.0.0.1:4100/v1/models | grep qwen
# → "qwen3.7-plus"
```

既存のルーターを更新する場合は `git pull && docker compose restart` だけでよい（イメージは
変わらない）。以前 `experimental/qwen-mm-plugins/routes.snippet.toml` を `routes.toml` に追記して
オプトインしていた場合は、先にローカルの追記分を消してから pull する —— 同じブロックが本体に
入ったので、重複した TOML テーブルはパースに失敗する。

```bash
git checkout routes.toml && git pull
docker compose restart
```

残るのは opencode 側だけ。

1. この `mcp` ブロックを opencode の設定（グローバル `~/.config/opencode/opencode.json` か
   プロジェクトの設定）にマージする。他の設定は変えなくてよい。

   ```jsonc
   // commit は意図的にピンしている。upstream は 2026-08-11 に capability を再編した:
   // vision_chat / ocr / grounding は `core` の外へ移り、`omni-av` extra は消え、外部 API を
   // 呼ぶものはすべて `api` に集まった。@main を追うと、次の再編でツール一覧が黙って空になる。
   {
     "mcp": {
       "qwen-mm-plugins-api": {
         "type": "local",
         "command": [
           "uvx",
           "--from",
           "qwen-mm-plugins[api] @ git+https://github.com/QwenLM/Qwen-MM-Plugins.git@8d6ea5a1f658260743307c52c2024ec87599fa48",
           "qwen-mm-plugins-api",
         ],
         "environment": {
           // プラグインの宛先を DashScope ではなくルーターに向ける。routes.toml の route id は
           // プラグインが既定で要求するモデル名に一致させてある。
           "DASHSCOPE_BASE_URL": "http://127.0.0.1:4100/v1",
           // セルフホスト・プロキシ経由では認証は無視される。実キーはルーターが持つ。
           "DASHSCOPE_API_KEY": "EMPTY",
           // メディア呼び出しはチャットより遅い。既定の read timeout では足りない。
           "QWEN_MM_CHAT_TIMEOUT": "900",
         },
         "enabled": true,
       },
     },
   }
   ```

2. 画像について尋ねる。添付ではなく**パス**を渡す。

   ```
   ./screenshot.png のレイアウト崩れの原因を、利用可能なツールで調べて
   ```

`FIREWORKS_API_KEY` 以外のキーは要らない。目もルーターと同じキーで課金される。

### 添付について

`opencode.jsonc.example` のうち画像を読めないモデル（`auto` / `auto-esc` / `weak-only`、そして
strong tier の deepseek-v4-pro-0813 も画像入力を拒否するため `strong-only` も）には、
画像の `modalities` を**意図的に宣言していない**。宣言がなければ opencode が手元で添付を断るので、
400 になるモデルにリクエストが飛ばない。この構成ではそれが正しい設定になる —— 画像はファイルパスとして
ツールに渡り、脳への添付にはならないからだ。宣言があるのは `k3-only`（Kimi K3）だけなので、モデルに
画像を直接見せたいときはそちらを指定する。

## 制約

| 機能                             | 可否   | 補足                                                 |
| -------------------------------- | ------ | ---------------------------------------------------- |
| 画像への `vision_chat`           | ○      | 主経路                                               |
| `ocr`                            | ○      |                                                      |
| `grounding`（物体の座標）        | **×**  | プラグインが `enable_thinking` を送り 400            |
| 動画（手元のファイル）           | **×**  | serverless のモデルがメディアパートを受けない        |
| 音声                             | **×**  | 音声を受ける Fireworks serverless モデルがない       |
| `read_image` など native reading | 対象外 | 画像そのものを返すので、テキスト専用の脳では使えない |

`grounding` が落ちるのは、プラグインが DashScope / vLLM 固有のフィールドをハードコードしていて、
strict なエンドポイントがそれを弾くため。upstream に
[QwenLM/Qwen-MM-Plugins#12](https://github.com/QwenLM/Qwen-MM-Plugins/issues/12) として報告済み。
実際にはモデルが `vision_chat` に切り替えてタスクを完遂するので、無駄なコールが 1 回増えるだけで済む。
気になる場合は `AGENTS.md` に 1 行足して抑えられる。

**音声や手元の動画ファイルが必要な場合**は、それらを受け付けるモデル —— 実質的にはセルフホストの Omni
—— を目にする必要がある。route 定義の `target` を差し替えて再起動するだけで、他は変わらない。

## 元に戻す

opencode 設定から `mcp` のエントリを消す —— それだけで route は何もしなくなる。ルーターのモデル一覧
からも消したい場合は、`routes.toml` 末尾の 2 ブロック（`[targets.fw_qwen_vl]` と
`[routes.omni-vision]`）を削除して再起動する。バンドルの他の部分はこれらに依存していない。
