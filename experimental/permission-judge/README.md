**English** | [日本語](README.ja.md)

# permission-judge (experimental)

An opencode plugin that adds a Claude Code-style "smart auto mode": instead of
approving every permission request blindly (`opencode --auto`) or asking every
time, an LLM judge classifies each request and only safe ones are auto-approved.

**Status: experimental.** Default mode is `shadow` — the plugin judges and logs
everything but never replies. Humans keep deciding until calibration says the
judge agrees often enough.

## How it works

```
permission.asked event
  → deterministic pre-filter (catastrophic patterns go straight to the human)
  → LLM judge via the router's weak-only route (DeepSeek V4 Flash, ~1-2 s, ~$0)
  → enforce mode only: SDK reply "once" when the judge says allow
  → every step logged to JSONL for calibration
```

Design notes:

- The plugin SDK declares a synchronous `permission.ask` hook
  (`output.status = allow/deny/ask`), but the server never triggers it
  (verified on v1.18.15 and dev HEAD). This plugin therefore works through the
  `permission.asked` **event** plus the SDK permission-reply API
  (`postSessionIdPermissionsPermissionId`).
- The judge may only say `allow`. `reject` is left to humans on purpose:
  rejecting one request rejects all pending requests in the session, which is
  too much blast radius for a classifier.
- Fail-safe by construction: pre-filter hits, judge errors, timeouts, and
  malformed judge output all fall through to the human dialog.

## Setup

1. Start the Switchyard router from this repository (the judge calls the
   `weak-only` route; no extra API key is needed).
2. Copy the plugin into your global opencode plugins:

   ```bash
   cp permission-judge.js ~/.config/opencode/plugins/
   ```

3. Restart opencode. Judgments appear in
   `~/.local/share/opencode/permission-judge.jsonl`.

4. When calibration looks good, enable enforcement and make bash actually ask:

   ```bash
   export OPENCODE_PERM_JUDGE_MODE=enforce
   ```

   ```jsonc
   // opencode.json — without this, bash defaults to "allow" and no
   // permission events fire at all
   { "permission": { "bash": "ask" } }
   ```

## Configuration (environment variables)

| Variable                         | Default                                          | Meaning                                 |
| -------------------------------- | ------------------------------------------------ | --------------------------------------- |
| `OPENCODE_PERM_JUDGE_MODE`       | `shadow`                                         | `shadow` (log only) / `enforce` / `off` |
| `OPENCODE_PERM_JUDGE_LOG`        | `~/.local/share/opencode/permission-judge.jsonl` | JSONL log path                          |
| `OPENCODE_PERM_JUDGE_URL`        | `http://127.0.0.1:4100/v1`                       | Judge endpoint (the router's base URL)  |
| `OPENCODE_PERM_JUDGE_MODEL`      | `weak-only`                                      | Router route/model used for judging     |
| `OPENCODE_PERM_JUDGE_TYPES`      | `bash,webfetch`                                  | Permission types the judge handles      |
| `OPENCODE_PERM_JUDGE_TIMEOUT_MS` | `10000`                                          | Judge call timeout                      |

## Calibration probe

`probe_judge.py` replays 24 labeled requests (bash safe×10 / dangerous×10,
webfetch×4) through the exact judge prompt the plugin uses:

```bash
python3 probe_judge.py
```

First run: **23/24 (96%) agreement**, median latency ≈1.8 s. The single
disagreement was `rm -rf node_modules && npm install` judged as `allow` —
defensible under the rubric (reversible, workspace-scoped) and recorded as a
borderline case. Raw data: `results-probe-20260808-205857.json`.

## Limitations

- Non-interactive `opencode run` auto-rejects permission requests ~3 ms after
  they are raised, long before the judge answers. Judging targets interactive
  TUI sessions only.
- In enforce mode the TUI dialog flashes open for the judge's latency (~1-2 s)
  before auto-closing on allow.
- If opencode ever wires up the real `permission.ask` hook, this plugin should
  migrate to it (synchronous, no dialog flash).
