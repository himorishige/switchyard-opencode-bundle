[English](README.md) | **日本語**

# qwen-mm-plugins（実験用）

テキスト専用の weak tier に、ツールとして呼べる「目」を付ける。ツールを提供するのは
[Qwen-MM-Plugins](https://github.com/QwenLM/Qwen-MM-Plugins) で、ここではその宛先を、すでに動かしている
ルーター経由でホスト型の vision モデルに向ける。

**ステータス: 実験用。画像のみ。** 音声・手元の動画ファイル・`grounding` はホスト型では動かない
（[制約](#制約)を参照）。既定のセットアップには含まれないので、使わない人には影響しない。

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

メディア呼び出しも他のリクエストと同じく `routing.jsonl` に残り、`scripts/stats-snapshot.sh` は
これを独立した行（`pinned:qwen3p7-plus`）で集計する。週次レビューでコストを分離できる。

## セットアップ

1. [`routes.snippet.toml`](routes.snippet.toml) を `routes.toml` に追記し、検証してから再起動する。

   ```bash
   cat experimental/qwen-mm-plugins/routes.snippet.toml >> routes.toml
   docker compose run --rm switchyard --config /app/routes.toml --dry-run
   docker compose restart
   ```

   dry-run の一覧に、既存の route と並んで `qwen3.7-plus` が出れば成功。

2. [`opencode.mcp.example.jsonc`](opencode.mcp.example.jsonc) の `mcp` ブロックを opencode の設定に
   マージする。

3. 画像について尋ねる。添付ではなく**パス**を渡す。

   ```
   ./screenshot.png のレイアウト崩れの原因を、利用可能なツールで調べて
   ```

`FIREWORKS_API_KEY` 以外のキーは要らない。目もルーターと同じキーで課金される。

### 添付について

`opencode.jsonc.example` のうち weak tier が応答しうるモデル（`auto` / `auto-esc` / `weak-only`）には、
画像の `modalities` を**意図的に宣言していない**。宣言がなければ opencode が手元で添付を断るので、
400 になるモデルにリクエストが飛ばない。この構成ではそれが正しい設定になる —— 画像はファイルパスとして
ツールに渡り、脳への添付にはならないからだ。`strong-only` / `k3-only` には宣言があるので、モデルに
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
—— を目にする必要がある。route の `target` を差し替えて再起動するだけで、他は変わらない。

## 元に戻す

手順 1 で追記した 2 ブロックを `routes.toml` から削除して再起動し、`mcp` のエントリを消す。
バンドルの他の部分はこれらに依存していない。
