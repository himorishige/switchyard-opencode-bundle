# Switchyard for opencode + Fireworks

**English** | [日本語](README.ja.md)

A local router that puts NeMo Switchyard between opencode and Fireworks AI, automatically dispatching each request to a strong or weak tier so you cut cost without giving up quality. It runs as a Docker container on your own machine.

```
opencode → Switchyard (127.0.0.1:4100) → Fireworks AI
              └─ a classifier (the weak model does double duty) rates difficulty and picks the tier
```

| Route (model name in opencode) | Behavior                                                                                                        |
| ------------------------------ | --------------------------------------------------------------------------------------------------------------- |
| `auto` (default)               | Automatic routing tuned for coding agents. This is all you need day to day                                      |
| `strong-only`                  | Pinned to kimi-k3 (useful when you suspect routing is the problem)                                              |
| `weak-only`                    | Pinned to deepseek-v4-flash-0731                                                                                |
| `k3-only`                      | Alias of `strong-only` (the old opt-in route from before K3 became strong). [Why](#the-strong-tier-and-kimi-k3) |

Everything is configured in a single file, `route.yaml` (Switchyard's route-bundle format).

> Setting this up for the first time? Start from [docs/onboarding.md](docs/onboarding.md), a single linear path through the whole setup.

## Requirements

- Docker (Docker Desktop, colima, etc.)
- A Fireworks API key ([create one here](https://app.fireworks.ai/settings/users/api-keys))
- opencode, already installed. If you want to limit what leaves your machine through web search, apply the [opencode-with-strict-privacy](https://github.com/cm-dyoshikawa/opencode-with-strict-privacy) settings first — disable exa.ai and disable sharing, at **Global scope**

## Setup

### 1. Clone the repository

```bash
git clone https://github.com/himorishige/switchyard-opencode-bundle.git
cd switchyard-opencode-bundle
```

### 2. Set your API key

```bash
cp .env.example .env
chmod 600 .env
```

Open `.env` and replace `FIREWORKS_API_KEY` with your own key.

### 3. Start the router

```bash
docker compose up -d --build
```

The first build takes a few minutes because Switchyard's Rust extension is compiled from source.

Outside Docker Desktop — on colima, for example — the `docker compose` subcommand may not be installed. In that case, install the standalone compose binary:

```bash
brew install docker-compose
```

After that, read every `docker compose ...` in this README as **`docker-compose ...`** (for example `docker-compose up -d --build`). It is the same compose v2 underneath, so behavior is identical.

Only if you want to keep the `docker compose` subcommand syntax, add the following key to `~/.docker/config.json` and it will be picked up as a plugin. Keep your existing keys (`auths` and friends) in place, and match the path to the output of `brew --prefix` — `/opt/homebrew` on Apple Silicon, `/usr/local` on Intel. If it still is not recognized, the standalone binary above works just as well.

```json
"cliPluginsExtraDirs": ["/opt/homebrew/lib/docker/cli-plugins"]
```

You can also start the container without compose. `route.yaml` is baked into the image; only log persistence and the healthcheck are compose-only.

```bash
docker build -t switchyard-opencode .
docker run -d --name switchyard-opencode --env-file .env \
  -p 127.0.0.1:4100:4100 --restart unless-stopped switchyard-opencode
```

### 4. Verify

```bash
curl -s http://127.0.0.1:4100/health
# → {"status":"ok"}

curl -s http://127.0.0.1:4100/v1/models | head
# → auto / strong-only / weak-only / k3-only
```

Once that works, move on to configuring opencode.

## Configuring opencode

Apply the contents of `opencode.jsonc.example` to your **Global config** (`~/.config/opencode/opencode.json`). opencode officially supports JSONC, so the comments can stay as they are. There are two ways to do this.

### A. Overwrite with the bundled config

`opencode.jsonc.example` is a **ready-to-use merge** of the recommended global settings from [opencode-with-strict-privacy](https://github.com/cm-dyoshikawa/opencode-with-strict-privacy) and the Switchyard connection settings. If you have no global config yet, or you are running the strict-privacy recommendations unmodified, copying the file is all it takes.

```bash
mkdir -p ~/.config/opencode
cp opencode.jsonc.example ~/.config/opencode/opencode.json
```

- If you use the `opencode.jsonc` filename instead, overwrite that file. Do not keep both `.json` and `.jsonc` — the precedence between them is not documented officially
- The environment-variable half of strict-privacy (`OPENCODE_ENABLE_EXA=0` and friends) is not part of this file. Set those in your shell rc separately

### B. Merge into an existing config

If you have your own settings — a theme, other providers — do not overwrite. Add these three top-level keys to your existing JSON instead.

```json
"provider": {
  "switchyard": {
    "npm": "@ai-sdk/openai-compatible",
    "name": "Switchyard (Fireworks auto-routing)",
    "options": {
      "baseURL": "http://127.0.0.1:4100/v1",
      "apiKey": "local-dummy"
    },
    "models": {
      "auto": { "name": "auto — Switchyard routing" },
      "strong-only": { "name": "strong-only — kimi-k3 pinned" },
      "weak-only": { "name": "weak-only — deepseek-v4-flash-0731 pinned" },
      "k3-only": { "name": "k3-only — kimi-k3 pinned (alias of strong-only)" }
    }
  }
},
"model": "switchyard/auto",
"small_model": "switchyard/weak-only",
"agent": {
  "plan": { "model": "switchyard/strong-only" },
  "explore": { "model": "switchyard/weak-only" },
  "scout": { "model": "switchyard/weak-only" }
}
```

A few things to watch out for when merging:

- If you already have a `provider` key, add only the `switchyard` entry **inside** it. Pasting the whole `provider` block over yours will wipe your existing providers
- The strict-privacy keys (`share`, `autoupdate`, `tools`, `permission`, …) do not conflict with any of this. They coexist as-is
- If you already set `model` / `small_model` and want to keep your current default, skip those two lines and pick the route from the model picker when you need it
- For the reasoning behind the `agent` block (plan wired straight to strong, explore / scout pinned to weak), see [Agent-level pinning](#agent-level-pinning-plan-mode-enabled-by-default)
- Restart opencode after merging, and confirm that the model picker lists `Switchyard (Fireworks auto-routing)` with its four routes (`auto`, `strong-only`, `weak-only`, `k3-only`)

### Day-to-day notes

- Switch routes from opencode's model picker (`/models`). The four routes appear under the provider `Switchyard (Fireworks auto-routing)`
- If you need to take Switchyard out of the loop (to isolate a problem, say), keep a direct Fireworks provider entry in your opencode config — then you can fall back by picking a plain `fireworks-ai/...` model from the picker
- `small_model` is used for auxiliary calls such as title generation. It is pinned to `weak-only`, because routing those through `auto` occasionally sends trivial work to the strong tier
- Subagents: the classifier rates and pins each conversation independently, so lightweight subagents drop to weak on their own. To force weak unconditionally, use opencode's per-agent setting (`"agent": {"<name>": {"model": "switchyard/weak-only"}}`)

### The strong tier and Kimi K3

On 2026-08-07 the strong tier of automatic routing moved from deepseek-v4-pro to **Kimi K3**, prioritizing response quality on deep design discussions and planning. `k3-only` is a leftover from when K3 was an opt-in route you selected manually; today it is an **alias** pointing at the same target as `strong-only`, kept so existing configs do not break.

The cost side is a trade. Per 1M tokens, K3 is $3.00 / $0.30 / $15.00 (input / cached / output) against $1.74 / $0.145 / $3.48 for the previous strong tier, deepseek-v4-pro. Applying those prices to the measured token distribution of real agent loops puts **the absolute cost per run at roughly 3× the previous figure** (3.0× for both `auto` and pinned strong). The savings _rate_ of `auto` — how much the weak tier saves you — barely moves, because routing works on the price ladder itself. Do not read `auto` as "the expensive tier gets diluted"; read it as **both the floor and the ceiling rising together**.

The dominant cost term shifts to output: about 68% of the total for K3 versus about 47% for deepseek-v4-pro. The more you have it write long design documents or large patches, the further above the estimate you land.

#### Agent-level pinning (plan mode, enabled by default)

The `coding_agent` preset decides using features of code work — how much changes, how many tool calls, whether codebase context is needed. Design discussions and strategy sessions that touch no code therefore tend to read as "simple". Worse, the misjudgments come back with _higher_ confidence than the correct ones, so raising `min_confidence` does not rescue them.

That is why `opencode.jsonc.example` enables per-agent pinning **by default** (the `agent` key sits at the top level, alongside `provider` and `model`; when merging into an existing config, add the individual entries inside it).

```json
"agent": {
  "plan": { "model": "switchyard/strong-only" },
  "explore": { "model": "switchyard/weak-only" },
  "scout": { "model": "switchyard/weak-only" }
}
```

`plan` is wired straight to strong (Kimi K3). Switching to plan mode bypasses the classifier and goes strong; switching back to build mode returns you to the default `auto` (`opencode run --agent plan` takes the same path). Pinning `explore` / `scout` to weak is the defense in the other direction: **opencode subagents inherit the model of whatever called them**, so leaving them unset means a subagent that only reads grep output still bills at the $15/1M output rate.

#### Updating an existing router

```bash
git pull && docker compose restart
curl -s http://127.0.0.1:4100/health   # {"status":"ok"}
```

Route names do not change, so editing `opencode.json` is not required. Update it only if you want the model picker labels to match reality:

```json
"models": {
  "auto": { "name": "auto — Switchyard routing" },
  "strong-only": { "name": "strong-only — kimi-k3 pinned" },
  "weak-only": { "name": "weak-only — deepseek-v4-flash-0731 pinned" },
  "k3-only": { "name": "k3-only — kimi-k3 pinned (alias of strong-only)" }
}
```

Restart opencode after saving; config is read only at startup, so a long-running session will not pick it up. Note that opencode only knows the models listed here — deleting `k3-only` from `models` makes anything referencing it (an old plan pin, for instance) fail with `UnknownError`. Clean up the references first.

#### Reverting to the previous strong tier (deepseek-v4-pro)

If the new tier does not suit you, revert these two places in `route.yaml` and restart.

```yaml
# 1. under routes.auto
strong:
  model: accounts/fireworks/models/deepseek-v4-pro

# 2. under routes.strong-only
strong-only:
  type: model
  target: accounts/fireworks/models/deepseek-v4-pro
```

## Agent Plugin (rag-kb / web-search)

`plugin/team-ai-kb/` is a plugin conforming to the [Agent Plugins standard](https://agent-plugins.org/) (v1.0.0). It is optional and independent of the router, bundling two agent skills plus an MCP definition.

| Component                                  | What it is                                                                                                  | Requires                                                                                |
| ------------------------------------------ | ----------------------------------------------------------------------------------------------------------- | --------------------------------------------------------------------------------------- |
| skill `rag-kb`                             | A guide to searching the shared knowledge base (NVIDIA RAG Blueprint) over MCP                              | Private-network reach to the RAG service, plus the MCP registration below               |
| skill `web-search` (+ `scripts/search.py`) | Web search via Gemini + Google Search grounding, called directly with your own key (no intermediary server) | `GEMINI_API_KEY`. Setup: [docs/web-search-onboarding.md](docs/web-search-onboarding.md) |
| `mcp.json`                                 | MCP server definition for `nvidia-rag` (streamable HTTP)                                                    | The first-time setup below                                                              |

### First-time setup (all clients)

The RAG endpoint lives on a private network, so it follows the same convention as `.env`: copy the example and edit it (the real file is gitignored).

```bash
cp plugin/team-ai-kb/mcp.json.example plugin/team-ai-kb/mcp.json
# replace <rag-service-host> in mcp.json with the address of the service host
```

### With opencode

Link the skills into the discovery path and add one MCP entry to your global config.

```bash
ln -s "$(pwd)/plugin/team-ai-kb/skills/rag-kb" ~/.config/opencode/skills/rag-kb
ln -s "$(pwd)/plugin/team-ai-kb/skills/web-search" ~/.config/opencode/skills/web-search
```

```jsonc
// add to the "mcp" block of ~/.config/opencode/opencode.json
"nvidia-rag": {
  "type": "remote",
  "url": "http://<rag-service-host>:8091/mcp",
  "enabled": true
}
```

### With Claude Code

The plugin format is read as-is (the `.mcp.json` shim for MCP is already bundled). One startup flag:

```bash
claude --plugin-dir /path/to/switchyard-opencode-bundle/plugin/team-ai-kb
# put it in a shell alias if you use it regularly
```

### With Codex CLI

```bash
ln -s "$(pwd)/plugin/team-ai-kb/skills/rag-kb" ~/.codex/skills/rag-kb
ln -s "$(pwd)/plugin/team-ai-kb/skills/web-search" ~/.codex/skills/web-search
codex mcp add nvidia-rag --url "http://<rag-service-host>:8091/mcp"
```

For non-interactive runs (`codex exec`), add one line to `[mcp_servers.nvidia-rag]` in `~/.codex/config.toml`: `default_tools_approval_mode = "approve"`. Codex gates MCP tool calls through an approval path separate from the `approval_policy` used for shell commands, and without this they are cancelled immediately in non-interactive mode. Grant it only to read-only servers.

### Updating

The skills are symlinked, so `git pull` is enough. When a release changes `mcp.json.example`, check whether your local `mcp.json` needs the same change.

## Operations

| Task                    | Command                                                                                                               |
| ----------------------- | --------------------------------------------------------------------------------------------------------------------- |
| Update (config + image) | `git pull && docker compose up -d --build`                                                                            |
| Config-only change      | edit `route.yaml`, then `docker compose restart` (compose bind-mounts it, so no rebuild)                              |
| Key rotation            | update `.env`, then `docker compose up -d --force-recreate` (`restart` reuses the env captured at container creation) |
| Health check            | `curl -s http://127.0.0.1:4100/health`                                                                                |
| Stop                    | `docker compose down`                                                                                                 |

For releases that only change `route.yaml` (retargeting a tier, say), `git pull && docker compose restart` is enough. No rebuild is needed unless the image changed.

For releases that **add** a route, also register the new route name under `provider.switchyard.models` in your global config (`~/.config/opencode/opencode.json`). Updating the router alone will not make it appear in the model picker — see [Updating an existing router](#updating-an-existing-router).

### Changing models

Each tier's target is set by a model line in `route.yaml`. To switch strong from kimi-k3 to GLM-5.2, for example, edit two places.

The first is under `routes.auto` (where automatic routing sends strong traffic):

```yaml
strong:
  model: accounts/fireworks/models/glm-5p2
```

The second is under `routes.strong-only` (change the pinned route to match):

```yaml
strong-only:
  type: model
  target: accounts/fireworks/models/glm-5p2
```

A restart applies the change — no rebuild, thanks to the bind mount.

```bash
docker compose restart
curl -s http://127.0.0.1:4100/health
```

Things to keep in mind:

- Valid model IDs are listed in the [Fireworks serverless catalog](https://app.fireworks.ai/models?capability=serverless)
- opencode only sees route names (`auto`, `strong-only`, `weak-only`, `k3-only`), so retargeting a tier needs no change to `opencode.json`. Update the `name` fields under `models` only if you want the picker labels to match. Adding a brand-new route name does require registering it under `models`
- If you change `classifier.model`, send one request afterwards to confirm it still works. The reasoning suppression baked into the image (`reasoning_effort: "none"`) was verified against deepseek-v4-flash-0731; other models may reject it
- Do not remove `defaults.extra_body: {}` — it prevents an HTTP 400 when a deepseek-v4 target is in play, and it is harmless with other models

### Periodic review (collecting routing stats)

Weekly, or on whatever cadence you choose, run one command:

```bash
./scripts/stats-snapshot.sh
```

It saves an aggregate JSON plus the per-request log (JSONL) into `stats-out/`, stamped with the date and your username, and prints a per-route summary of request and token counts. Submit those two files however your project has arranged it (upload to a shared folder, for example).

To look at the raw surfaces yourself:

| Surface                 | Command                                                                  | Contents                                                                              |
| ----------------------- | ------------------------------------------------------------------------ | ------------------------------------------------------------------------------------- |
| Aggregate snapshot      | `curl -s http://127.0.0.1:4100/v1/routing/stats \| python3 -m json.tool` | Cumulative request and token counts per model (**reset when the container restarts**) |
| Per-request log (JSONL) | `docker cp switchyard-opencode:/app/logs/routing.jsonl ./routing.jsonl`  | One line per request (selected tier, model, tokens). Durable via the named volume     |

**The source of truth for usage and cost** is per-model usage on the [Fireworks dashboard](https://app.fireworks.ai/). Since strong (kimi-k3) and weak (deepseek-v4-flash-0731) are different models, **per-model usage is exactly your tier distribution multiplied by cost** — that is what a savings report is built from. The stats above are for analyzing the routing breakdown.

## Security notes

- The listener binds to **127.0.0.1 only**. Nothing is exposed to the LAN
- Switchyard's Intake sink (its request-collection mechanism) stays **disabled** — `--intake-enabled` is never passed. The only place request bodies go is the Fireworks endpoint you configured
- The routing log (`/app/logs/routing.jsonl`) stays inside a Docker named volume (`switchyard-logs`). It reaches the host only when you pull it out with `stats-snapshot.sh` or `docker cp`. It contains routing decisions and token counts, never prompt bodies
- Web-search safeguards (disabling exa.ai) are outside this router's scope. If you want to limit what leaves through web search, apply them on the opencode side first (see [Requirements](#requirements))
- Queries from the web-search skill go directly to the Gemini API (Google) under your own key. Their exclusion from training **requires a key issued from a billing-enabled GCP project** ([docs/web-search-onboarding.md](docs/web-search-onboarding.md)). The rule about keeping confidential terms out of queries is documented in SKILL.md
- The `nvidia-rag` MCP assumes you connect to the read-only public surface (5 tools: search, generate, and so on). Keeping the admin surface — which includes delete operations — off the private network is the RAG service's responsibility
- Footnote: if you really want to avoid a plaintext `.env`, you can start the container through 1Password CLI's `op run` with a secret reference. The benefit is limited, though, since Docker stores env vars in container metadata in plaintext anyway (visible via `docker inspect`). This bundle's standard is `.env` plus `chmod 600`

## Implementation notes (for maintainers)

- `route.yaml` uses Switchyard's **route-bundle format** (`switchyard --routing-profiles route.yaml serve`). We migrated off the older v2 profile config (`serve --config` plus a `serve.py` adapter) because upstream PR #119 plans to remove it
- The image pins a git main commit SHA (`SWITCHYARD_SHA` in the Dockerfile). PyPI v0.1.0 is not used because it predates the streaming usage fix (PR #64)
- Classifier reasoning suppression is implemented as a sed patch against `request_processor.py`, replacing the vLLM vocabulary `chat_template_kwargs` with the Fireworks-compatible `reasoning_effort: "none"`. Measured 2026-07-23: 18/18 identical decisions, 2.7–4.2× faster. It exists because the deterministic type has no `disable_reasoning` knob; "provider coverage for suppression vocabulary" is on our list of upstream issue candidates
- The weak tier moved to deepseek-v4-flash-0731 on 2026-08-03 (the official release replacing the preview). Same price, substantially better agentic benchmarks, and the suppression knob works on it as a classifier too (measured: `reasoning_effort: "none"` accepted, completion pinned at 61 tokens, empty `reasoning_content`; without the knob it emits 431 tokens and ~1.5k characters of reasoning). The 0731 model card documents `reasoning_effort` as low/high/max only, but `"none"` is accepted in practice. `thinking: {"type": "disabled"}` was confirmed to give the same result
- The model ID in the Dockerfile's patch-verification assert feeds `model_accepts_reasoning_hint()`, which keys off provider tags — it is independent of the version number of whatever model a tier points at. Retargeting a tier therefore never requires touching the Dockerfile, and users can update without a rebuild
- Caution: bumping to a SHA that includes upstream PR #123 (which adds fireworks to the deny list) flips auto-detect to False and stops the injection entirely — safe, but reasoning comes back and things slow down. Re-check this patch whenever you bump the SHA
- `session_affinity: true` with `affinity_warmup_turns: 2` is enabled by default (measured 2026-07-23: classifier calls −56%, classifier prompt tokens −55%, zero tier switches after pinning). The known trade-off is that tool-planning escalation stops applying once pinned. Fail-open decisions are never pinned, so a low-confidence call cannot get frozen in
- Upstream's profile-level `subagent_target` (#112) is not used: it is components-v2 only and relies on header detection that opencode never triggers. Per-agent settings in opencode cover the subagent case
- The compose setup was verified on real hardware under colima with the compose plugin installed via brew (2026-07-23): build → healthy → end-to-end request → JSONL written to the `switchyard-logs` volume → logs surviving `--force-recreate`. All passed
- `defaults.extra_body: {}` in `route.yaml` is load-bearing: it suppresses the vLLM hint injection in `apply_deepseek_overrides()`. It becomes unnecessary once we bump to a SHA that includes upstream PR #122
