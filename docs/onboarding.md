# チームオンボーディング（初回セットアップの一本道、45〜60 分想定）

新しくチーム環境に参加するメンバーが、ルーター起動から web 検索まで一通り揃えるための手順です。
各ステップの詳細は README と各ドキュメントにあり、ここでは順番と漏れやすいポイントだけをまとめます。
所要時間の大半はイメージビルドと GCP まわりの待ち時間です。

## 全体像

| #   | ステップ                         | 参照先                                                 | 目安      |
| --- | -------------------------------- | ------------------------------------------------------ | --------- |
| 1   | ルーター起動                     | README「セットアップ」                                 | 15〜20 分 |
| 2   | opencode Global 設定             | README「opencode 側の設定」                            | 5 分      |
| 3   | シェル環境変数（strict-privacy） | 本ドキュメント                                         | 3 分      |
| 4   | Global AGENTS.md 配置            | 本ドキュメント                                         | 2 分      |
| 5   | Agent Plugin（team-ai-kb）導入   | README「Agent Plugin」                                 | 5 分      |
| 6   | web 検索キー                     | [web-search-onboarding.md](./web-search-onboarding.md) | 15 分     |
| 7   | 動作確認チェックリスト           | 本ドキュメント                                         | 5 分      |

手順 3・4 はルーターと独立しているので、手順 1 のビルド待ちの間に済ませるのがおすすめです。

## 1. ルーター起動

README「セットアップ」1〜4 のとおりです。要点は次の 3 つです。

- `FIREWORKS_API_KEY` を `.env` に配置します（git 管理外・`chmod 600`。キーの発行・取得はチームの案内に従ってください）
- `docker compose up -d --build`（初回はビルドに時間がかかります）
- `curl -s http://127.0.0.1:4100/health` が `{"status":"ok"}` を返せば OK

## 2. opencode Global 設定

README「opencode 側の設定」の A（そのまま上書き）/ B（既存カスタム設定へマージ）どちらかで
`~/.config/opencode/opencode.json` を設定します。

- 必ず **Global スコープ**（`~/.config/opencode/`）に置きます。プロジェクト側の opencode.json は
  Global を上書きするため、プライバシー設定が抜け落ちる原因になります
- `.json` と `.jsonc` を両方置かないでください（どちらか一方のみ）

## 3. シェル環境変数（strict-privacy）

設定ファイル（手順 2）に含まれるのは config 側だけです。環境変数側の無効化フラグは
各自のシェル rc（`~/.zshrc` 等）に設定します。

```sh
# opencode-with-strict-privacy 推奨の環境変数
export OPENCODE_ENABLE_EXA=0             # Exa 検索を無効化
export OPENCODE_EXPERIMENTAL=0           # 実験機能を一括無効化
export OPENCODE_EXPERIMENTAL_EXA=0       # 旧 Exa フラグ（レガシー）
export OPENCODE_AUTO_SHARE=0             # 自動共有を無効化
export OPENCODE_DISABLE_LSP_DOWNLOAD=1   # 任意: LSP 自動ダウンロード停止
export OPENCODE_DISABLE_MODELS_FETCH=1   # 任意: モデルカタログ取得停止
```

出典: [opencode-with-strict-privacy](https://github.com/cm-dyoshikawa/opencode-with-strict-privacy/blob/main/README.ja.md)（設定ファイル側とあわせた全体像の説明があります）

設定後は `source ~/.zshrc`、または新しいターミナルで反映してください。

## 4. Global AGENTS.md を置く（見落としやすい・重要）

opencode は Global の `~/.config/opencode/AGENTS.md` が**存在しない場合、`~/.claude/CLAUDE.md` を
互換フォールバックとしてグローバルルールに読み込みます**（公式仕様）。Claude Code を併用している人は、
個人設定・メモの内容がそのまま全リクエストと一緒に送信されることになります。

対処は Global AGENTS.md を置いてフォールバックを止めるだけです。

```sh
mkdir -p ~/.config/opencode
cat > ~/.config/opencode/AGENTS.md <<'EOF'
# Global rules

- web 検索クエリには顧客名・社内プロジェクト名・未公開のコード名を含めない
EOF
```

- すでに自分の AGENTS.md を運用している場合はそのままで問題ありません（フォールバックは「無い場合」だけ発動します）
- 内容は最小で構いません。上の 1 行はチーム推奨のクエリ規律です

## 5. Agent Plugin（team-ai-kb）

README「Agent Plugin（rag-kb / web-search）」の「初期設定（共通・初回のみ）」を済ませてから、
使っているクライアント（opencode / Claude Code / Codex CLI）の節に進んでください。

- `mcp.json.example → mcp.json` のコピー後に書き換える接続先アドレスは、チームの案内を参照してください

## 6. web 検索キー

[web-search-onboarding.md](./web-search-onboarding.md)（15 分）に従ってください。
**課金有効の GCP プロジェクトで発行したキーを使う**点だけは飛ばさずに読んでください（学習不使用の条件です）。

## 7. 動作確認チェックリスト

| 確認       | コマンド                                       | 期待する結果                             |
| ---------- | ---------------------------------------------- | ---------------------------------------- |
| ルーター   | `curl -s http://127.0.0.1:4100/health`         | `{"status":"ok"}`                        |
| ルート一覧 | `curl -s http://127.0.0.1:4100/v1/models`      | auto / strong-only / weak-only / k3-only |
| opencode   | `opencode run -m switchyard/auto "こんにちは"` | 応答が返る                               |
| AGENTS.md  | `ls ~/.config/opencode/AGENTS.md`              | ファイルが存在する                       |
| 環境変数   | `env \| grep OPENCODE_`                        | 手順 3 の値が並ぶ                        |
| web 検索   | web-search-onboarding.md の手順 5              | 回答 + `Sources:` + 統計行               |

- 長時間アイドル後の初回コールはコールドスタートで数十秒かかることがあります（2 回目からは数秒）。
  疎通確認のコマンドには `--max-time` を付けると原因の切り分けが楽になります
