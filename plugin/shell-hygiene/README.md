# shell-hygiene (OpenCode 2 only)

An [OpenCode 2](https://opencode.ai/v2/docs) plugin that cleans up every shell
command before it is spawned: it removes credentials the agent's shell never
needs from the command environment, caps the per-command timeout, and logs
commands that run outside the project directory. It never blocks a command —
blocking is the job of the `permissions` rules and
[tirith-guard](../tirith-guard/). Think of it as the environment half of the
guard: even if a command slips through, `env | grep KEY` finds nothing worth
stealing.

Requires `opencode2` (the V2 beta). It uses the V2 `shell.create.before` hook,
which has no V1 equivalent.

---

### 日本語（Japanese）

OpenCode 2 の `shell.create.before` hook で、すべてのシェルコマンドを起動前に整えるプラグインです。
コマンドをブロックする役割ではなく（それは `permissions` ルールと tirith-guard の仕事）、
コマンドが動く**環境**を整えます。

1. **秘密情報のスクラブ**: シェルは OpenCode サーバーの環境変数をそのまま継承します。エージェントが
   読む必要のない API キーがそこにあると、`env | grep KEY` の一発で流出します。`scrub` の glob に一致する
   環境変数をコマンド環境から削除します
2. **タイムアウト上限**: モデルが長い timeout を要求しても `maxTimeoutMs` で頭打ちにします
3. **プロジェクト外 cwd の警告**: プロジェクトディレクトリ外で動くコマンドをサーバーログに残します
   （実行可否は permission ルールが決めます。これは可視化だけです）

hook は permission 判定より前に走るため、最終的に deny されるコマンドに対しても動きます（害はありません）。

## インストール

opencode2 の Global 設定（`~/.config/opencode/opencode.jsonc`）の `plugins` に、このリポジトリのクローンを
指す行を追加します。後続の plugin が整えた環境を見られるよう、**先頭**に置いてください。

```jsonc
"plugins": [
  "file:///絶対パス/switchyard-opencode-bundle/plugin/shell-hygiene/index.ts",
  "file:///絶対パス/switchyard-opencode-bundle/plugin/tirith-guard/v2.ts"
]
```

`file://` 指定の plugin は起動時に解決されるため、バンドルの `git pull` で更新が流れます。
動作確認で `opencode2 debug config` のように `--standalone` を付けられないコマンドを使うと background service が起動して残ります。その後の `--standalone` 実行がハングしたら `opencode2 service stop` で止めてください。

## 設定（plugin options）

```jsonc
"plugins": [
  {
    "package": "file:///絶対パス/switchyard-opencode-bundle/plugin/shell-hygiene/index.ts",
    "options": {
      "scrub": ["FIREWORKS_*", "*_PASSWORD"],
      "keep": ["BACKLOG_API_KEY"],
      "maxTimeoutMs": 300000,
      "warnExternalCwd": true,
      "verbose": false
    }
  }
]
```

| オプション | 既定 | 意味 |
| --- | --- | --- |
| `scrub` | 下記の既定リスト | 削除する環境変数名の glob（`*` / `?`、大文字小文字を区別しない）。指定すると既定リストを置き換える |
| `keep` | `[]` | glob に一致しても削除しない名前 |
| `maxTimeoutMs` | `600000` | コマンドごとの timeout 上限（ミリ秒）。これより短い要求はそのまま |
| `warnExternalCwd` | `true` | プロジェクト外 cwd のコマンドをログに残す |
| `verbose` | `false` | 削除した名前と timeout の変更をコマンドごとにログに残す |

既定の `scrub` リストは「エージェントのシェルが決して必要としない鍵」に絞っています。

```
FIREWORKS_*                     # 本物の Fireworks キーはルーターのコンテナにあり、シェルには不要
ANTHROPIC_API_KEY OPENROUTER_API_KEY DASHSCOPE_API_KEY HF_TOKEN HUGGINGFACE_HUB_TOKEN
AWS_SECRET_ACCESS_KEY AWS_SESSION_TOKEN
*_PASSWORD *_PASSWD *_PRIVATE_KEY *_SECRET_KEY *_CLIENT_SECRET
```

同梱 skill がシェル内で使う `GEMINI_API_KEY` / `OPENAI_API_KEY`（web-search）と `BACKLOG_API_KEY`（bee）は
意図的に**削除しません**。より厳しくしたい場合は `"scrub": ["*_API_KEY", "*_TOKEN", ...]` のように広げ、
必要なものを `keep` に列挙してください。

## 動作確認

opencode2 に次のように頼み、スクラブ対象が見えないことを確認します。

```
シェルで `echo ${FIREWORKS_API_KEY:-unset}` を実行して
```

`unset` と返れば動作しています（`--auto` なしでは permission の ask が出ます。`git status` のように
allow ルールに一致するコマンドで確かめても構いません）。
`verbose: true` にすると、削除した名前がサーバーログ（`opencode2 debug paths` の log ディレクトリ）に出ます。

## 制限

- 削除できるのはコマンド環境の変数だけです。ファイル（`~/.aws/credentials`、`.env`）は permission ルール
  （`read *.env` は既定で ask）で守ってください
- cwd の判定は `ctx.location.project.directory` 基準です。worktree 外の相対パスは permission 側の
  `external_directory` が担当します
- OpenCode 2 の plugin API は beta で、hook 名や event の形が変わる可能性があります

## ライセンス

Apache-2.0（バンドルと同じ）。
