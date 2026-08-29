# permission-judge (OpenCode 2 only)

An [OpenCode 2](https://opencode.ai/v2/docs) plugin that puts an LLM judge on the
permission `evaluate` hook. Requests the `permissions` rules leave as `ask` are
classified by a small model (the router's `weak-only` route by default); the
judge only ever says **allow**, and everything it cannot vouch for stays with the
human (`assist`) or is denied with a reason (`strict`). It starts in `shadow`
mode — judging and logging without changing anything — so calibration data
accumulates before any decision is automated.

This is the V2 successor of [`experimental/permission-judge/`](../../experimental/permission-judge/)
(V1, event stream + async reply). V2 exposes a synchronous hook, so there is no
dialog flash and it also works for unattended `opencode2 run --auto` sessions.
Requires `opencode2` (the V2 beta).

---

### 日本語（Japanese）

OpenCode 2 の permission `evaluate` hook に LLM の judge を載せるプラグインです。`permissions` ルールが
`ask` に残したリクエストを小型モデル（既定はルーターの `weak-only` route）が分類し、judge が **allow** と
言ったものだけを自動承認します。judge は allow しか言いません。allow できないものは、`assist` では人間の
判断（ask のまま）に、`strict` では理由つきの deny になります。

既定は `shadow`（判定してログに残すだけで、決定は変えない）。較正データが溜まってから `assist` / `strict` に
切り替えてください。

## 位置づけ（3 層）

```
[0] 静的ポリシー   permissions[]（deny はここで終端。plugin には来ない）
[1] 内容認識 guard  tirith-guard v2（allow / ask → deny）
[2] 判定器          permission-judge（ask → allow、strict では ask → deny）
[3] 人間            TUI の ask / Allow always / headless は reject
```

hook は plugin の登録順に走ります。**tirith-guard → permission-judge の順**に並べてください。judge は
`ask` 以外（rule の allow、tirith の deny）には触りません。

## インストール

```jsonc
// ~/.config/opencode/opencode.jsonc（opencode2）
"plugins": [
  "file:///絶対パス/switchyard-opencode-bundle/plugin/shell-hygiene/index.ts",
  "file:///絶対パス/switchyard-opencode-bundle/plugin/tirith-guard/v2.ts",
  {
    "package": "file:///絶対パス/switchyard-opencode-bundle/plugin/permission-judge/index.ts",
    "options": { "mode": "shadow" }
  }
]
```

judge はルーターの `switchyard/weak-only` を `ctx.generate.text` で呼びます。ルーターが起動していれば
追加のキーは不要です。

## モード

| mode | hook が見た `ask` の扱い | 想定する使い方 |
| --- | --- | --- |
| `off` | 何もしない | 一時停止 |
| `shadow`（既定） | 判定してログに残すだけ | 較正。まずこれで数日回す |
| `assist` | judge=allow なら `allow`、それ以外は `ask` のまま（人間へ） | TUI での対話セッション |
| `strict` | judge=allow なら `allow`、それ以外は **理由つき `deny`** | `opencode2 run --auto`、cron / batch |

`strict` が要る理由: OpenCode 2 では `--auto` のとき hook から見える決定は `ask` のままで、hook が `ask` を
残すと**そのまま実行**されます（auto 変換は hook の後）。無人運用で「judge が allow できなかったものを止める」には
`deny` しかありません。hook 自身は `--auto` かどうかを知らないので、起動側で mode を選びます。

`strict` では judge のエラー・タイムアウト・不正出力も deny になります（fail-closed）。judge が止まると auto
運用も止まりますが、それが意図した挙動です。

## 判定の入力（reasoning-blind）

- action / resource（コマンド文字列や URL）/ agent / cwd / project / git branch
- チーム方針文（`policy` または `policyFile`）
- セッションの直近の**ユーザー発話**と**tool 呼び出し**（`context: "user"`、既定）。assistant の説明文と tool の
  出力は見せません（そこが注入面のため）。方針文とユーザー発話は「意図であって judge への指示ではない」と
  rubric に明記しています

v2 は shell コマンドをパイプライン単位に分割して resource にします（`curl x | sh` → `["curl x", "sh"]`）。
プリフィルタと judge には生コマンドが要るので、`tool.execute.before` で捕まえた生コマンドを `event.source` で
突き合わせて使います（ログの `command` / `raw_command`）。捕まえられなかった場合はセグメントを ` | ` で結合した
保守的な文字列で代用します。

決定的なプリフィルタ（root / home への `rm -rf`、force push、`curl | sh`、`sudo`、publish、URL 内の認証情報など）
に一致したものは judge に送らず、必ず `ask`（strict では deny）になります。

## 設定（plugin options）

| オプション | 既定 | 意味 |
| --- | --- | --- |
| `mode` | `shadow` | `off` / `shadow` / `assist` / `strict` |
| `model` | `switchyard/weak-only` | judge に使う `provider/model`。判定器を差し替えるときはここだけ変える |
| `actions` | `["shell", "webfetch"]` | 判定対象の permission action |
| `timeoutMs` | `10000` | judge 呼び出しのタイムアウト |
| `policy` / `policyFile` | なし | チーム方針文（`policyFile` があれば優先） |
| `context` | `user` | `user` = 直近のユーザー発話と tool 呼び出しを渡す / `none` = 渡さない |
| `contextItems` / `contextChars` | `8` / `400` | 渡す件数と 1 件あたりの文字数 |
| `log` | `$XDG_DATA_HOME/opencode/permission-judge.jsonl` | JSONL の出力先 |
| `debugContext` | `false` | `ctx.session.context` の生 JSON をログに落とす（形状確認用。大きい） |
| `logEvents` | `true` | サーバーの permission 系イベント（人間の返答など）も同じログに残す |

## ログ（JSONL）

1 判定 = 1 行。agent-action-judge の較正データに寄せた形です。

```json
{"ts":"...","plugin":"permission-judge","v":2,"kind":"judged",
 "sessionID":"ses_...","agent":"build","action":"shell","resources":["git fetch"],"command":"git fetch","raw_command":true,
 "cwd":"/path","project":"/path","git":{"branch":"main"},"policy_hash":"none",
 "context_items":3,"context":["user: ...","tool: read {...}"],
 "effect_seen":"ask","prefilter":null,
 "judge":{"model":"switchyard/weak-only","decision":"allow","reason":"...","ms":1200,"error":null},
 "mode":"shadow","effect_final":"ask"}
```

`kind: "event"` の行はサーバーのイベントストリームから拾った permission 系イベントで、人間が once / always /
reject のどれを選んだかを後から突き合わせるためのものです。

## 動作確認

1. `mode: "shadow"` で opencode2 を使い、`permission-judge.jsonl` に `judged` 行が増えることを確認する
2. `jq 'select(.kind=="judged") | [.effect_seen, .judge.decision, .judge.ms]'` で判定分布と遅延を見る
3. 人間の判断と judge の一致率が十分なら `assist` へ。無人運用は `strict`

## 制限

- hook は同期なので、判定対象の tool 実行は judge の応答分（weak-only で 1〜2 秒）遅れます
- `assist` / `strict` の使い分けは起動側の責任です。TUI を `strict` で使うと、judge が allow しないものは
  人間に聞かずに deny されます
- OpenCode 2 の plugin / permission API は beta です。`PermissionEvaluation` やイベントの形が変われば追従が要ります
- V1（opencode 1.x）では動きません。V1 版は `experimental/permission-judge/` のまま凍結しています

## ライセンス

Apache-2.0（バンドルと同じ）。
