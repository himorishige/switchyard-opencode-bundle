[English](README.md) | **日本語**

# permission-judge（実験用）

opencode に Claude Code 風の「賢い auto モード」を足すプラグイン。全許可（`opencode --auto`）でも毎回プロンプトでもなく、LLM judge が各 permission リクエストの安全性を都度判定し、安全なものだけ自動承認する。

**ステータス: 実験用。** 既定は `shadow` モード —— 判定とログ記録のみで、応答は一切送らない。較正で十分な一致率が確認できるまで、判断は人間に残る。

## 仕組み

```
permission.asked イベント
  → 決定論プリフィルタ（破壊的パターンは judge にすら回さず人間直行）
  → ルーターの weak-only route で LLM 判定（DeepSeek V4 Flash、約 1〜2 秒・ほぼ無料）
  → enforce モード時のみ: judge が allow なら SDK で "once" 応答
  → 全ステップを JSONL に記録（較正用）
```

設計メモ:

- プラグイン SDK には同期フック `permission.ask`（`output.status = allow/deny/ask` を直接書ける）が**型定義だけ存在するが、サーバーから一度も呼び出されない**（v1.18.15 と dev HEAD で確認）。そのため本プラグインは `permission.asked` **イベント** + SDK の permission 応答 API（`postSessionIdPermissionsPermissionId`）で動く
- judge に許したのは `allow` のみ。`reject` は意図的に人間に残す: 1 件の reject がセッション内の全保留リクエストを巻き込む仕様で、分類器に持たせるには影響が大きすぎる
- フェイルセーフ設計: プリフィルタ該当・judge エラー・タイムアウト・出力パース失敗はすべて人間のダイアログにフォールバック

## セットアップ

1. 本リポジトリの Switchyard ルーターを起動しておく（judge は `weak-only` route を呼ぶ。追加の API キー不要）
2. プラグインを opencode のグローバル plugins にコピー:

   ```bash
   cp permission-judge.js ~/.config/opencode/plugins/
   ```

3. opencode を再起動。判定は `~/.local/share/opencode/permission-judge.jsonl` に記録される

4. 較正結果が良ければ enforce を有効化し、bash が実際に ask を出すようにする:

   ```bash
   export OPENCODE_PERM_JUDGE_MODE=enforce
   ```

   ```jsonc
   // opencode.json — これが無いと bash は既定 allow で permission イベント自体が発生しない
   { "permission": { "bash": "ask" } }
   ```

## 設定（環境変数）

| 変数                             | 既定値                                           | 意味                                    |
| -------------------------------- | ------------------------------------------------ | --------------------------------------- |
| `OPENCODE_PERM_JUDGE_MODE`       | `shadow`                                         | `shadow`（ログのみ）/ `enforce` / `off` |
| `OPENCODE_PERM_JUDGE_LOG`        | `~/.local/share/opencode/permission-judge.jsonl` | JSONL ログのパス                        |
| `OPENCODE_PERM_JUDGE_URL`        | `http://127.0.0.1:4100/v1`                       | judge の接続先（ルーターの base URL）   |
| `OPENCODE_PERM_JUDGE_MODEL`      | `weak-only`                                      | 判定に使うルーターの route / モデル     |
| `OPENCODE_PERM_JUDGE_TYPES`      | `bash,webfetch`                                  | judge が処理する permission 種別        |
| `OPENCODE_PERM_JUDGE_TIMEOUT_MS` | `10000`                                          | 判定呼び出しのタイムアウト              |

## 較正プローブ

`probe_judge.py` はプラグインが使うものと同一の judge プロンプトに、ラベル付き 24 問（bash 安全 10・危険 10・webfetch 4）を流して一致率を計測する:

```bash
python3 probe_judge.py
```

初回実測: **23/24（96%）一致・レイテンシ中央値 ≈1.8 秒**。唯一の相違は `rm -rf node_modules && npm install` が `allow` 判定 —— ルーブリック上は妥当（可逆・workspace 内）で、ボーダーライン事例として記録。生データは `results-probe-20260808-205857.json`。

## 制限事項

- 非対話 `opencode run` は permission リクエスト発生の約 3ms 後に auto-reject するため、judge の回答が間に合わない。判定対象は対話 TUI セッションのみ
- enforce モードでは TUI のダイアログが judge のレイテンシ分（約 1〜2 秒）だけ一瞬開いてから閉じる
- 将来 opencode が本物の `permission.ask` フックを配線したら、そちらへ移行する（同期実行でダイアログの点滅も消える）
