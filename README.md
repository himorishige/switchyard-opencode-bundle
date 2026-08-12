# Switchyard for opencode + Fireworks

**English** | [日本語](README.ja.md)

A local router that puts NeMo Switchyard between opencode and Fireworks AI, automatically dispatching each request to a strong or weak tier so you cut cost without giving up quality. It runs as a Docker container on your own machine.

```
opencode → Switchyard (127.0.0.1:4100) → Fireworks AI
              └─ a classifier (the weak model does double duty) rates difficulty and picks the tier
```

| Route (model name in opencode) | Behavior                                                                                                                  |
| ------------------------------ | ------------------------------------------------------------------------------------------------------------------------- |
| `auto` (default)               | Automatic routing tuned for coding agents. This is all you need day to day                                                |
| `auto-esc` (opt-in)            | Weak-first; a trajectory judge escalates to strong on real trouble. [Details](#evidence-based-escalation-auto-esc-opt-in) |
| `strong-only`                  | Pinned to kimi-k3 (useful when you suspect routing is the problem)                                                        |
| `weak-only`                    | Pinned to deepseek-v4-flash-0731                                                                                          |
| `k3-only`                      | Alias of `strong-only` (the old opt-in route from before K3 became strong). [Why](#the-strong-tier-and-kimi-k3)           |

Everything is configured in a single file, `routes.toml` (the config format of Switchyard's native Rust server).

**Attaching images**: use `strong-only` or `k3-only`. Both pin Kimi K3, which reads images, and both declare `modalities` in the opencode config so the attachment is actually sent — opencode silently drops an image for any model that does not declare it, and the model then replies that it cannot read images. `auto`, `auto-esc` and `weak-only` intentionally leave the declaration out, because the weak tier (deepseek-v4-flash-0731) rejects image input: on `auto`, session affinity can hand a screenshot to a session already pinned to weak, which fails with an upstream 400.

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

The first build installs Switchyard's native Rust server from crates.io and compiles it — about a minute and a half on an Apple Silicon Mac, longer on slower hardware. Later builds reuse the Docker layer cache and finish in seconds unless the pinned Switchyard version changed.

Outside Docker Desktop — on colima, for example — the `docker compose` subcommand may not be installed. In that case, install the standalone compose binary:

```bash
brew install docker-compose
```

After that, read every `docker compose ...` in this README as **`docker-compose ...`** (for example `docker-compose up -d --build`). It is the same compose v2 underneath, so behavior is identical.

Only if you want to keep the `docker compose` subcommand syntax, add the following key to `~/.docker/config.json` and it will be picked up as a plugin. Keep your existing keys (`auths` and friends) in place, and match the path to the output of `brew --prefix` — `/opt/homebrew` on Apple Silicon, `/usr/local` on Intel. If it still is not recognized, the standalone binary above works just as well.

```json
"cliPluginsExtraDirs": ["/opt/homebrew/lib/docker/cli-plugins"]
```

You can also start the container without compose. `routes.toml` is baked into the image; only log persistence and the healthcheck are compose-only.

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
# → auto / auto-esc / strong-only / weak-only / k3-only
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
- The environment-variable half of strict-privacy (`OPENCODE_ENABLE_EXA=0` and friends) is not part of this file. Set those in your shell startup file (`~/.zshrc` or similar) separately

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
      "auto-esc": { "name": "auto-esc — weak-first, escalates on trouble" },
      "strong-only": {
        "name": "strong-only — kimi-k3 pinned",
        "modalities": { "input": ["text", "image"], "output": ["text"] }
      },
      "weak-only": { "name": "weak-only — deepseek-v4-flash-0731 pinned" },
      "k3-only": {
        "name": "k3-only — kimi-k3 pinned (alias of strong-only)",
        "modalities": { "input": ["text", "image"], "output": ["text"] }
      }
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
- Restart opencode after merging, and confirm that the model picker lists `Switchyard (Fireworks auto-routing)` with its five routes (`auto`, `auto-esc`, `strong-only`, `weak-only`, `k3-only`)

### Day-to-day notes

- Switch routes from opencode's model picker (`/models`). The five routes appear under the provider `Switchyard (Fireworks auto-routing)`
- If you need to take Switchyard out of the loop (to isolate a problem, say), keep a direct Fireworks provider entry in your opencode config — then you can fall back by picking a plain `fireworks-ai/...` model from the picker
- `small_model` is used for auxiliary calls such as title generation. It is pinned to `weak-only`, because routing those through `auto` occasionally sends trivial work to the strong tier
- Subagents: the classifier rates and pins each conversation independently, so lightweight subagents drop to weak on their own. To force weak unconditionally, use opencode's per-agent setting (`"agent": {"<name>": {"model": "switchyard/weak-only"}}`)

### The strong tier and Kimi K3

On 2026-08-07 the strong tier of automatic routing moved from deepseek-v4-pro to **Kimi K3**, prioritizing response quality on deep design discussions and planning. `k3-only` is a leftover from when K3 was an opt-in route you selected manually; today it is an **alias** pointing at the same target as `strong-only`, kept so existing configs do not break.

The cost side is a trade. Per 1M tokens, K3 is $3.00 / $0.30 / $15.00 (input / cached / output) against $1.74 / $0.145 / $3.48 for the previous strong tier, deepseek-v4-pro. Applying those prices to the measured token distribution of real agent loops puts **the absolute cost per run at roughly 3× the previous figure** (3.0× for both `auto` and pinned strong). The savings _rate_ of `auto` — how much the weak tier saves you — barely moves, because routing works on the price ladder itself. Do not read `auto` as "the expensive tier gets diluted"; read it as **both the floor and the ceiling rising together**.

The dominant cost term shifts to output: about 68% of the total for K3 versus about 47% for deepseek-v4-pro. The more you have it write long design documents or large patches, the further above the estimate you land.

#### Agent-level pinning (plan mode, enabled by default)

The classifier estimates whether the weak tier can complete the task. Its capability rubric is written around coding work, so business and design discussions match none of its rules and fall through to a stricter routing threshold — in our calibration set that catches most deep discussions (12 of 13), but not all, and the verdict is still a judgment call made per conversation.

That is why `opencode.jsonc.example` enables per-agent pinning **by default** (the `agent` key sits at the top level, alongside `provider` and `model`; when merging into an existing config, add the individual entries inside it). Plan mode is where deep discussions live, and pinning it makes the behavior deterministic instead of probabilistic.

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
git pull && docker compose up -d --build
curl -s http://127.0.0.1:4100/health   # {"status":"ok"}
```

`--build` matters when a release changes the Dockerfile or the pinned Switchyard version (the 2026-08 native-server migration is one of those — coming from the old `route.yaml` setup, a rebuild is required; your routing log survives in the `switchyard-logs` volume). For releases that only touch `routes.toml`, `git pull && docker compose restart` is enough.

Route names do not change, so editing `opencode.json` is not required. Update it only if you want the model picker labels to match reality:

```json
"models": {
  "auto": { "name": "auto — Switchyard routing" },
  "auto-esc": { "name": "auto-esc — weak-first, escalates on trouble" },
  "strong-only": { "name": "strong-only — kimi-k3 pinned" },
  "weak-only": { "name": "weak-only — deepseek-v4-flash-0731 pinned" },
  "k3-only": { "name": "k3-only — kimi-k3 pinned (alias of strong-only)" }
}
```

Restart opencode after saving; config is read only at startup, so a long-running session will not pick it up. Note that opencode only knows the models listed here — deleting `k3-only` from `models` makes anything referencing it (an old plan pin, for instance) fail with `UnknownError`. Clean up the references first.

#### Reverting to the previous strong tier (deepseek-v4-pro)

If the new tier does not suit you, the strong target is defined once in `routes.toml`, so it is a one-line change followed by a restart. Both `auto` and `strong-only` (plus the `k3-only` alias) follow it.

```toml
[targets.strong]
id = "accounts/fireworks/models/deepseek-v4-pro"
```

### Evidence-based escalation (auto-esc, opt-in)

`auto-esc` inverts the routing philosophy of `auto`. Instead of predicting difficulty before each turn, every session **starts on the weak tier**, and a trajectory judge reads the session after each turn looking for a clear pattern of real trouble — the same error repeating with unrelated edits in between, claimed success contradicted by test output, drift away from the task. Two consecutive escalate verdicts latch the session to strong for good.

Measured behavior (2026-08-08): healthy friction (a failing test being worked on, sequential alternatives) never escalated; a genuinely stuck trajectory latched to strong on turn 2 and stayed there with zero further judge calls (p50 latency ~1s once latched).

Trade-offs to know before picking it:

- **Streaming is buffered until the latch.** The judge must read the weak tier's completed reply before it is released, so responses arrive all at once instead of token by token. Short and mid-length replies feel similar (the weak model's own thinking already delays first tokens); long generations will visibly pause, then appear in full
- The turn that confirms escalation pays both tiers (the weak attempt is discarded and the turn re-runs on strong)
- The latch is one-way per session — there is no de-escalation back to weak

Where it shines: cost-minimal experiments (weak share is structurally maximal), and **non-interactive workloads** — cron jobs, batch pipelines, agents nobody watches live — where buffered streaming costs nothing and evidence-based escalation is exactly the failure insurance you want. To try it, pick `auto-esc` in the model picker; it is registered in `opencode.jsonc.example`.

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

Add two blocks to your global config. No symlinks are needed: opencode resolves the directory at
startup, so skills added by a later release appear after a `git pull`.

```jsonc
// ~/.config/opencode/opencode.json
"skills": {
  "paths": ["/path/to/switchyard-opencode-bundle/plugin/team-ai-kb/skills"]
},
"mcp": {
  "nvidia-rag": {
    "type": "remote",
    "url": "http://<rag-service-host>:8091/mcp",
    "enabled": true
  }
}
```

opencode also auto-loads skills from `~/.claude/skills/`, `~/.agents/skills/`, and a project's
`.claude/skills/`. If you already keep these skills in one of those paths for another client, they
are picked up without the `skills` block above. `opencode debug skill` prints what is actually
loaded, with the path each one came from.

Earlier releases asked you to symlink each skill into `~/.config/opencode/skills/`. That still
works and coexists with the block above (the symlink wins, and it points at the same file), so
removing the old links is optional.

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

For opencode and Claude Code, `git pull` is enough: the config and the plugin directory both point at the bundle. Codex uses symlinks, which follow the pull just as well. When a release changes `mcp.json.example`, check whether your local `mcp.json` needs the same change.

## Operations

| Task                    | Command                                                                                                               |
| ----------------------- | --------------------------------------------------------------------------------------------------------------------- |
| Update (config + image) | `git pull && docker compose up -d --build`                                                                            |
| Config-only change      | edit `routes.toml`, then `docker compose restart` (compose bind-mounts it, so no rebuild)                             |
| Key rotation            | update `.env`, then `docker compose up -d --force-recreate` (`restart` reuses the env captured at container creation) |
| Health check            | `curl -s http://127.0.0.1:4100/health`                                                                                |
| Stop                    | `docker compose down`                                                                                                 |

For releases that only change `routes.toml` (retargeting a tier, say), `git pull && docker compose restart` is enough. No rebuild is needed unless the image changed.

For releases that **add** a route, also register the new route name under `provider.switchyard.models` in your global config (`~/.config/opencode/opencode.json`). Updating the router alone will not make it appear in the model picker — see [Updating an existing router](#updating-an-existing-router).

### Changing models

Each tier is a `[targets.<name>]` table in `routes.toml`, referenced by the routes. To switch strong from kimi-k3 to GLM-5.2, for example, edit one line:

```toml
[targets.strong]
id = "accounts/fireworks/models/glm-5p2"
```

A restart applies the change — no rebuild, thanks to the bind mount.

```bash
docker compose restart
curl -s http://127.0.0.1:4100/health
```

Things to keep in mind:

- Valid model IDs are listed in the [Fireworks serverless catalog](https://app.fireworks.ai/models?capability=serverless)
- opencode only sees route names (`auto`, `strong-only`, `weak-only`, `k3-only`), so retargeting a tier needs no change to `opencode.json`. Update the `name` fields under `models` only if you want the picker labels to match. Adding a brand-new route name does require registering it under `models`
- If you change the classifier target's model, send one request afterwards and check judge health (`curl -s http://127.0.0.1:4100/v1/stats` → `classifier`). The judge suppresses its reasoning through `extra_body`, and not every provider honors that knob; if a verdict ends up outside plain `content`, every judgment fails open to strong
- **Model-id collisions: one trap applies here, one only if you leave the released version.** The server dedupes targets by (llm_client, model id) and silently drops one of the duplicates — that is why the classifier target keeps its own `[llm_clients.fireworks_judge]` entry. That trap applies to every version, 0.2.0 included. The second one does not: builds from #268 onward resolve serving calls through a per-route map keyed by model id alone, so a classifier target sharing a model with a tier leaks its `extra_body` into that tier's user responses (measured 2026-08-08; re-measured 2026-08-11 with both builds side by side, released 0.2.0 is unaffected). **If you ever pin a main commit instead of a release, remove the classifier's `extra_body` first**

### Periodic review (collecting routing stats)

Weekly, or on whatever cadence you choose, run one command:

```bash
./scripts/stats-snapshot.sh
```

It saves an aggregate JSON plus the per-request log (JSONL) into `stats-out/`, stamped with the date and your username, and prints a per-route summary of request and token counts. Submit those two files however your project has arranged it (upload to a shared folder, for example).

To look at the raw surfaces yourself:

| Surface                 | Command                                                                 | Contents                                                                                         |
| ----------------------- | ----------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------ |
| Aggregate snapshot      | `curl -s http://127.0.0.1:4100/v1/stats \| python3 -m json.tool`        | Cumulative request/token counts per model and tier, plus judge health (**reset on restart**)     |
| Per-request log (JSONL) | `docker cp switchyard-opencode:/app/logs/routing.jsonl ./routing.jsonl` | One line per request (selected tier, model, tokens). Durable via the named volume                |
| Prometheus metrics      | `curl -s http://127.0.0.1:4100/metrics`                                 | Includes `switchyard_classifier_fail_open_total` — worth an occasional glance for judge failures |

One improvement over the previous setup: the classifier's own calls now appear in the JSONL with `tier="classifier"`, so the routing overhead cost — invisible before — shows up in the weekly summary as its own row.

**The source of truth for usage and cost** is per-model usage on the [Fireworks dashboard](https://app.fireworks.ai/). Since strong (kimi-k3) and weak (deepseek-v4-flash-0731) are different models, **per-model usage is exactly your tier distribution multiplied by cost** — that is what a savings report is built from. The stats above are for analyzing the routing breakdown.

## Experimental

- [`experimental/permission-judge/`](experimental/permission-judge/) — an opencode plugin that adds a Claude Code-style "smart auto mode": an LLM judge (via the router's weak tier) classifies permission requests and only safe ones are auto-approved. Ships in shadow mode (judge and log only, humans still decide) until calibration proves agreement
- [`experimental/qwen-mm-plugins/`](experimental/qwen-mm-plugins/) — lets the text-only weak tier answer questions about images, by routing [Qwen-MM-Plugins](https://github.com/QwenLM/Qwen-MM-Plugins) tools to a hosted vision model. The brain never receives an image, so the tier stays on the cheap text model. Images only — audio and local video need a self-hosted model

## Security notes

- The listener binds to **127.0.0.1 only**. Nothing is exposed to the LAN
- The native Rust server has **no request-collection mechanism** (the old Python CLI's Intake sink does not exist here). The only place request bodies go is the Fireworks endpoint you configured
- The routing log (`/app/logs/routing.jsonl`) stays inside a Docker named volume (`switchyard-logs`). It reaches the host only when you pull it out with `stats-snapshot.sh` or `docker cp`. It contains routing decisions and token counts, never prompt bodies
- Web-search safeguards (disabling exa.ai) are outside this router's scope. If you want to limit what leaves through web search, apply them on the opencode side first (see [Requirements](#requirements))
- Queries from the web-search skill go directly to the Gemini API (Google) under your own key. Their exclusion from training **requires a key issued from a billing-enabled GCP project** ([docs/web-search-onboarding.md](docs/web-search-onboarding.md)). The rule about keeping confidential terms out of queries is documented in SKILL.md
- The `nvidia-rag` MCP assumes you connect to the read-only public surface (5 tools: search, generate, and so on). Keeping the admin surface — which includes delete operations — off the private network is the RAG service's responsibility
- Footnote: if you really want to avoid a plaintext `.env`, you can start the container through 1Password CLI's `op run` with a secret reference. The benefit is limited, though, since Docker stores env vars in container metadata in plaintext anyway (visible via `docker inspect`). This bundle's standard is `.env` plus `chmod 600`

## Implementation notes (for maintainers)

- The router is the **standalone native Rust server** (`switchyard-server --config routes.toml`). We migrated off the Python route-bundle format (`type: deterministic`) after upstream #268 (2026-08-07) removed the legacy Python routing implementations; the previous rails (v2 profile config, then route-bundle) are both gone from main. The old `route.yaml` is preserved under `legacy-routebundle/` in the working repo for reference
- The image installs a **released version** from crates.io (`SWITCHYARD_VERSION` in the Dockerfile), not a git commit. Switchyard 0.2.0 (2026-08-10) was the first release to publish the Rust crates; before that, pinning a main-commit SHA was the only option. Two things to know before bumping: the release tag has **diverged from `main`** (main carries the next development cycle, so following it means running an unreleased server), and 0.2.0 was published from `d0b9d50b` — **57 minutes before #268 landed on main**. Version numbers do not tell you this: both binaries report `switchyard-server 0.2.0`. The TOML surface rejects unknown keys, so validate any bump with `switchyard-server --config routes.toml --dry-run` before shipping
- **Thinking suppression on the judge is back (2026-08-11).** `extra_body = { reasoning_effort = "none", temperature = 0 }` sits on the classifier target again. It was removed on 2026-08-08 because the model-id collision above leaked it into weak-tier user responses — a regression #268 introduced, which the released 0.2.0 predates. Measured over the same 87-judgment set with and without it: judge p50 2.2s vs 10.4s, p90 4.4s vs 44.5s. Agent-loop shapes route identically either way (30/30 weak); only open-ended sparring moves (9/13 vs 12/13 reaching strong), and a three-way blind comparison on that set found weak and strong answers equally usable. `base_threshold = 0.75` unchanged
- **Known upstream issues in 0.2.0** worth knowing for the weekly review: routing-tier attribution is missing from `/v1/stats` and `/metrics` for judge failures that fall back to the default target, escalation decisions, and `stage_router` fallbacks (upstream has a fix in flight). Buffered upstream work also continues after a client disconnects, so a cancelled request can still cost you
- The routing algorithm is `llm_classifier` in **capability mode**: the judge predicts `p_solve` (the probability the weak tier completes the task) and the route compares it against `base_threshold` (+ `threshold_step` per capability-boundary level). Our thresholds (0.75/0.1) were calibrated on 2026-08-08 against an 87-judgment set built from real agent transcripts; at the 0.5 default, deep design discussions leaked to weak (9/13 vs 12/13). Recalibrate by measuring your own p_solve distribution rather than nudging blind
- The judge reads only the **first and latest user message** of a conversation (plus nothing else, by default) — assistant/tool turns are invisible to it. This is why mid-session judgments are far more stable than the old feature-extraction rubric, and why prompt-side calibration matters less than threshold calibration here
- Verdicts that fail schema validation, or land outside plain assistant `content`, **fail open to strong** — watch `switchyard_classifier_fail_open_total` on `/metrics`
- Session affinity uses `session_affinity = true` with `message_hash_fallback = true`. opencode sends a session header the server understands; the message-hash fallback covers clients that do not. Assignments are process-local (they reset on restart) and capped upstream at 4096 sessions
- Runtime runs as uid 1000 (matching the first user of the old Python image), so the `switchyard-logs` named volume and its `routing.jsonl` history carry across the migration without a chown
- The `APT::Sandbox::User=root` in the Dockerfile works around a colima/lima quirk where the `_apt` sandbox user cannot read downloaded package lists (apt reports "invalid signature" while gpgv verifies fine). It is harmless on Docker Desktop and Linux
- Known upstream quirks worth remembering: `/v1/routing/stats` is now `/v1/stats`; the response headers are `x-model-router-selected-model` / `x-model-router-rationale`; the routing log keys sessions off `proxy_x_session_id`, which is a different header from the one affinity uses (upstream known issue #7)
