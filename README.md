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
| `strong-only`                  | Pinned to deepseek-v4-pro-0813 (useful when you suspect routing is the problem)                                           |
| `weak-only`                    | Pinned to deepseek-v4-flash-0731                                                                                          |
| `k3-only`                      | Pinned to Kimi K3 — the plan agent's seat and the image-attachment lane. [Why](#the-strong-tier-and-kimi-k3)              |

Everything is configured in a single file, `routes.toml` (the config format of Switchyard's native Rust server).

**Attaching images**: use `k3-only`. It pins Kimi K3, which reads images, and it is the only route that declares `modalities` in the opencode config so the attachment is actually sent — opencode silently drops an image for any model that does not declare it, and the model then replies that it cannot read images. The strong tier (deepseek-v4-pro-0813) does not accept image input, so `strong-only` leaves the declaration out too; `auto`, `auto-esc` and `weak-only` do the same because the weak tier (deepseek-v4-flash-0731) rejects image input: on `auto`, session affinity can hand a screenshot to a session already pinned to weak, which fails with an upstream 400.

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
# → auto / auto-esc / strong-only / weak-only / k3-only / qwen3.7-plus
```

Once that works, move on to configuring opencode.

## Configuring opencode

Apply the contents of `opencode.jsonc.example` to your **Global config** (`~/.config/opencode/opencode.json`). opencode officially supports JSONC, so the comments can stay as they are. There are two ways to do this.

> **OpenCode 2 (opencode2, beta):** this file works unchanged on OpenCode 2 — it reads the V1 keys from the same
> location and normalizes them in memory. Every route now declares `tool_call` / `modalities` explicitly, because
> OpenCode 2 assumes tools + text + **image** input for an undeclared custom model (screenshots would reach the
> text-only tiers and fail with a 400). The native V2 shape is in `opencode.v2.jsonc.example`, and tirith-guard has a
> V2 build (`plugin/tirith-guard/v2.ts`). The trial targets opencode 1.x; V2 support is best-effort while its config
> and plugin APIs are beta.

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
      "strong-only": { "name": "strong-only — deepseek-v4-pro-0813 pinned" },
      "weak-only": { "name": "weak-only — deepseek-v4-flash-0731 pinned" },
      "k3-only": {
        "name": "k3-only — kimi-k3 pinned (plan/vision)",
        "modalities": { "input": ["text", "image"], "output": ["text"] }
      }
    }
  }
},
"model": "switchyard/auto",
"small_model": "switchyard/weak-only",
"agent": {
  "plan": { "model": "switchyard/k3-only" },
  "explore": { "model": "switchyard/weak-only" },
  "scout": { "model": "switchyard/weak-only" }
}
```

A few things to watch out for when merging:

- If you already have a `provider` key, add only the `switchyard` entry **inside** it. Pasting the whole `provider` block over yours will wipe your existing providers
- The strict-privacy keys (`share`, `autoupdate`, `tools`, `permission`, …) do not conflict with any of this. They coexist as-is
- If you already set `model` / `small_model` and want to keep your current default, skip those two lines and pick the route from the model picker when you need it
- For the reasoning behind the `agent` block (plan wired straight to Kimi K3 via `k3-only`, explore / scout pinned to weak), see [Agent-level pinning](#agent-level-pinning-plan-mode-enabled-by-default)
- Restart opencode after merging, and confirm that the model picker lists `Switchyard (Fireworks auto-routing)` with its five routes (`auto`, `auto-esc`, `strong-only`, `weak-only`, `k3-only`)

### Day-to-day notes

- Switch routes from opencode's model picker (`/models`). The five routes appear under the provider `Switchyard (Fireworks auto-routing)`
- If you need to take Switchyard out of the loop (to isolate a problem, say), keep a direct Fireworks provider entry in your opencode config — then you can fall back by picking a plain `fireworks-ai/...` model from the picker
- `small_model` is used for auxiliary calls such as title generation. It is pinned to `weak-only`, because routing those through `auto` occasionally sends trivial work to the strong tier
- Subagents: the classifier rates and pins each conversation independently, so lightweight subagents drop to weak on their own. To force weak unconditionally, use opencode's per-agent setting (`"agent": {"<name>": {"model": "switchyard/weak-only"}}`)

### The strong tier and Kimi K3

The strong tier has moved twice. On 2026-08-07 it went from deepseek-v4-pro to **Kimi K3**, prioritizing response quality on deep design discussions and planning. On 2026-08-14 it moved again, to **deepseek-v4-pro-0813** — the dated successor of the original pro tier — after a four-axis measurement pass confirmed it qualifies: tool calling works streamed and non-streamed with reasoning cleanly separated into `reasoning_content`, zero language drift on 15 Japanese consultations, blind sparring answers rated sufficient 12/13 by a third-party judge (K3: 11/13), 11/14 cumulative on the discriminative LiveCodeBench set (K3 rerun: 10/14), and lower latency throughout.

K3 did not leave. Deep design discussions are exactly where it earned its seat, so `k3-only` — formerly an alias of `strong-only` — is now its **own route pinned to Kimi K3**: the plan agent points there by default, and it is the manual lane for image attachments (K3 reads images; the strong tier does not).

The cost side moves the opposite way from the last switch. Per 1M tokens, deepseek-v4-pro-0813 is $1.32 / $0.044 / $3.96 (input / cached / output) against K3's $3.00 / $0.30 / $15.00. Replaying the measured token ledger of real usage prices the strong seat at **roughly a third to a quarter of the K3 figure** ($24.43 → $5.98–7.23 on the reference ledger). The savings _rate_ of `auto` barely moves, because routing works on the price ladder itself — this time read it as **both the floor and the ceiling coming down together**. Output remains the dominant cost term: about 62% of the total for pro-0813, versus about 68% for K3.

#### Agent-level pinning (plan mode, enabled by default)

The classifier estimates whether the weak tier can complete the task. Its capability rubric is written around coding work, so business and design discussions match none of its rules and fall through to a stricter routing threshold — in our calibration set that catches most deep discussions (12 of 13), but not all, and the verdict is still a judgment call made per conversation.

That is why `opencode.jsonc.example` enables per-agent pinning **by default** (the `agent` key sits at the top level, alongside `provider` and `model`; when merging into an existing config, add the individual entries inside it). Plan mode is where deep discussions live, and pinning it makes the behavior deterministic instead of probabilistic.

```json
"agent": {
  "plan": { "model": "switchyard/k3-only" },
  "explore": { "model": "switchyard/weak-only" },
  "scout": { "model": "switchyard/weak-only" }
}
```

`plan` is wired straight to Kimi K3 (`k3-only`) — design conversations stay on K3 even though the strong tier moved to deepseek-v4-pro-0813. Switching to plan mode bypasses the classifier and goes to K3; switching back to build mode returns you to the default `auto` (`opencode run --agent plan` takes the same path). Pinning `explore` / `scout` to weak is the defense in the other direction: **opencode subagents inherit the model of whatever called them**, so leaving them unset means a subagent that only reads grep output still bills at K3's $15/1M output rate.

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
  "strong-only": { "name": "strong-only — deepseek-v4-pro-0813 pinned" },
  "weak-only": { "name": "weak-only — deepseek-v4-flash-0731 pinned" },
  "k3-only": { "name": "k3-only — kimi-k3 pinned (plan/vision)" }
}
```

Restart opencode after saving; config is read only at startup, so a long-running session will not pick it up. Note that opencode only knows the models listed here — deleting `k3-only` from `models` makes anything referencing it (an old plan pin, for instance) fail with `UnknownError`. Clean up the references first.

#### Reverting to the previous strong tier (kimi-k3)

If the new tier does not suit you, the strong target is defined once in `routes.toml`, so it is a one-line change followed by a restart. `auto`, `auto-esc` and `strong-only` all follow it (`k3-only` has its own target and is unaffected).

```toml
[targets.strong]
id = "accounts/fireworks/models/kimi-k3"
```

### Evidence-based escalation (auto-esc, opt-in)

`auto-esc` inverts the routing philosophy of `auto`. Instead of predicting difficulty before each turn, every session **starts on the weak tier**, and a trajectory judge reads the session after each turn looking for a clear pattern of real trouble — the same error repeating with unrelated edits in between, claimed success contradicted by test output, drift away from the task. Two consecutive escalate verdicts latch the session to strong for good.

Measured behavior (2026-08-08): healthy friction (a failing test being worked on, sequential alternatives) never escalated; a genuinely stuck trajectory latched to strong on turn 2 and stayed there with zero further judge calls (p50 latency ~1s once latched).

Trade-offs to know before picking it:

- **Streaming is buffered until the latch.** The judge must read the weak tier's completed reply before it is released, so responses arrive all at once instead of token by token. Short and mid-length replies feel similar (the weak model's own thinking already delays first tokens); long generations will visibly pause, then appear in full
- The turn that confirms escalation pays both tiers (the weak attempt is discarded and the turn re-runs on strong)
- The latch is one-way per session — there is no de-escalation back to weak

Where it shines: cost-minimal experiments (weak share is structurally maximal), and **non-interactive workloads** — cron jobs, batch pipelines, agents nobody watches live — where buffered streaming costs nothing and evidence-based escalation is exactly the failure insurance you want. To try it, pick `auto-esc` in the model picker; it is registered in `opencode.jsonc.example`.

### An eye for the weak tier (Qwen-MM-Plugins)

The weak tier is text-only — `deepseek-v4-flash-0731` rejects image input outright. Rather than moving the tier to a costlier vision model, the router serves a dedicated vision route (`qwen3.7-plus`) for [Qwen-MM-Plugins](https://github.com/QwenLM/Qwen-MM-Plugins) tools: they show the image to the vision model and hand the brain a text description, so the brain never sees an image and stays on the cheap model. The route ships in `routes.toml` and is inert until you add the plugin's MCP entry to opencode. Setup, costs, and limits (images only): [docs/qwen-mm-plugins.md](docs/qwen-mm-plugins.md).

## Agent Plugin (rag-kb / web-search / using-bee)

`plugin/team-ai-kb/` is a plugin conforming to the [Agent Plugins standard](https://agent-plugins.org/) (v1.0.0). It is optional and independent of the router, bundling three agent skills plus an MCP definition.

| Component                                  | What it is                                                                                                                                    | Requires                                                                                                    |
| ------------------------------------------ | --------------------------------------------------------------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------- |
| skill `rag-kb`                             | A guide to searching the shared knowledge base (NVIDIA RAG Blueprint) over MCP                                                                | Private-network reach to the RAG service, plus the MCP registration below                                   |
| skill `web-search` (+ `scripts/search.py`) | Web search backed by Gemini or OpenAI, auto-selected from whichever key is set and called directly with your own key (no intermediary server) | `GEMINI_API_KEY` or `OPENAI_API_KEY`. Setup: [docs/web-search-onboarding.md](docs/web-search-onboarding.md) |
| skill `using-bee`                          | Backlog operations through the local `bee` CLI: issues, PRs, projects, wikis, documents, and notifications                                    | `bee` installed and authenticated. Setup: [docs/backlog-bee-onboarding.md](docs/backlog-bee-onboarding.md)  |
| `mcp.json`                                 | MCP server definition for `nvidia-rag` (streamable HTTP)                                                                                      | The RAG first-time setup below                                                                              |

### First-time setup (RAG only)

The RAG endpoint lives on a private network, so it follows the same convention as `.env`: copy the example and edit it (the real file is gitignored). Backlog / bee setup is per-user and documented separately in [docs/backlog-bee-onboarding.md](docs/backlog-bee-onboarding.md).

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
ln -s "$(pwd)/plugin/team-ai-kb/skills/using-bee" ~/.codex/skills/using-bee
codex mcp add nvidia-rag --url "http://<rag-service-host>:8091/mcp"
```

For non-interactive runs (`codex exec`), add one line to `[mcp_servers.nvidia-rag]` in `~/.codex/config.toml`: `default_tools_approval_mode = "approve"`. Codex gates MCP tool calls through an approval path separate from the `approval_policy` used for shell commands, and without this they are cancelled immediately in non-interactive mode. Grant it only to read-only servers.

### Updating

For opencode and Claude Code, `git pull` is enough: the config and the plugin directory both point at the bundle. Codex uses symlinks, which follow the pull just as well; add a symlink for `using-bee` if your local setup predates this release. When a release changes `mcp.json.example`, check whether your local `mcp.json` needs the same change.

## tirith-guard (optional, recommended for opencode)

[`plugin/tirith-guard/`](plugin/tirith-guard/) is an opencode plugin that guards every `bash` tool
call with [Tirith](https://tirith.sh) before it runs. While `--auto` mode and the static
`permission.bash` deny rules handle deterministically-bad commands, Tirith covers what a static deny
list cannot: homograph/homoglyph URLs (`gіthub.com` with a Cyrillic `і`), pipe-to-shell, ANSI
injection, credential leaks, and data exfiltration — 200+ rules, fully offline, sub-millisecond. It
is fail-open by default, so it never blocks when tirith is not installed.

Setup (macOS):

```sh
brew install sheeki03/tap/tirith
# then add to ~/.config/opencode/opencode.json:
#   "plugin": ["file:///abs/path/to/switchyard-opencode-bundle/plugin/tirith-guard/index.ts"]
```

OpenCode 2 (opencode2, beta) cannot load V1 plugins — use the V2 build `plugin/tirith-guard/v2.ts` with the `plugins`
key instead (see `opencode.v2.jsonc.example`).

Full install, tuning (env vars), and a verification checklist: [`plugin/tirith-guard/README.md`](plugin/tirith-guard/README.md).

## shell-hygiene (OpenCode 2 only)

[`plugin/shell-hygiene/`](plugin/shell-hygiene/) is the environment half of the guard for OpenCode 2. It hooks
`shell.create.before` and, for every shell command, removes credentials the agent's shell never needs from the command
environment (`FIREWORKS_*`, cloud session tokens, `*_PASSWORD`, `*_PRIVATE_KEY`, ...), caps the per-command timeout,
and logs commands that run outside the project. It never blocks anything — that is what the `permissions` rules and
tirith-guard do — but it makes `env | grep KEY` come back empty. Keys the shipped skills need (`GEMINI_API_KEY`,
`OPENAI_API_KEY`, `BACKLOG_API_KEY`) are left alone.

```jsonc
// ~/.config/opencode/opencode.jsonc (opencode2) — load it first so later plugins see the cleaned environment
"plugins": [
  "file:///abs/path/to/switchyard-opencode-bundle/plugin/shell-hygiene/index.ts",
  "file:///abs/path/to/switchyard-opencode-bundle/plugin/tirith-guard/v2.ts"
]
```

Options (`scrub` / `keep` / `maxTimeoutMs` / `warnExternalCwd` / `verbose`) and verification:
[`plugin/shell-hygiene/README.md`](plugin/shell-hygiene/README.md).

The V2 policy pack in `opencode.v2.jsonc.example` also allows the bundle's read-only MCP tools (`nvidia_rag_*`,
`qwen_mm_plugins_api_*`), denies Code Mode (`execute`), and removes `shell` from the `explore` / `general` subagents —
a denied action disappears from the model's tool list, so the subagent never even sees it.

## permission-judge (OpenCode 2 only, shadow by default)

[`plugin/permission-judge/`](plugin/permission-judge/) puts an LLM judge on OpenCode 2's permission `evaluate`
hook. Requests the `permissions` rules leave as `ask` are classified by the router's `weak-only` route; the judge only
ever says **allow**. `shadow` (default) judges and logs without changing anything, `assist` auto-approves what the
judge allows and leaves the rest to the human, and `strict` denies the rest with a reason — for `opencode2 run --auto`,
where an `ask` that reaches the runtime is executed, not asked. Input is reasoning-blind (action, resource, agent,
cwd, git branch, team policy, recent user prompts and tool calls; never the assistant's own text or tool outputs).
Every judgement is appended to `$XDG_DATA_HOME/opencode/permission-judge.jsonl` for calibration. Load it after
tirith-guard. This is the V2 successor of `experimental/permission-judge/` (V1, event stream + async reply), which
stays frozen. Details and the log schema: [`plugin/permission-judge/README.md`](plugin/permission-judge/README.md).

## Pi (optional second client)

[Pi](https://pi.dev/) is a minimal coding-agent harness that connects to the same router with a
single JSON file, and reuses the team skills (`rag-kb` / `web-search` / `using-bee`) as-is because they are
standard Agent Skills. Compared to opencode it adds working headless image input
(`pi -p @img "..."`), a machine-readable `--mode json` event stream, and subscription auth
(`/login` for ChatGPT Plus/Pro (Codex), Claude, Copilot). opencode remains the primary client.

Setup: copy `pi-models.json.example` and `pi-settings.json.example`, then follow
[docs/pi-onboarding.md](docs/pi-onboarding.md) (15–20 minutes).

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

Each tier is a `[targets.<name>]` table in `routes.toml`, referenced by the routes. To switch strong from deepseek-v4-pro-0813 to GLM-5.2, for example, edit one line:

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

### Patched build: judge text projection (temporary)

Switchyard 0.2.0 hands the capability judge the conversation exactly as the
client sent it. When a request carries an image (`image_url` part), a
text-only judge answers HTTP 400, the router treats that as an unavailable
judge and falls open to the strong tier - on every attached request, silently
(only `switchyard_classifier_fail_open_total{reason="upstream_non_5xx"}`
moves). Reported upstream as
[NVIDIA-NeMo/Switchyard#598](https://github.com/NVIDIA-NeMo/Switchyard/issues/598).

Until a release carries the fix, this bundle can build 0.2.0 plus the patch
from the fork branch `fix/judge-text-projection-0.2.0`: the judge sees a
`[image attachment]` placeholder instead of the image, judges the text, and
the request forwarded to the selected tier is untouched. Same config surface
as 0.2.0, so `routes.toml` does not change.

```bash
# build locally from the fork branch (10-20 min)
docker compose build --build-arg SWITCHYARD_SOURCE=git
docker compose up -d --force-recreate

# or pull the prebuilt image (linux/arm64 + linux/amd64)
#   ghcr.io/himorishige/switchyard-server:0.2.0-judge-text-projection
# and point the `image:` of the switchyard service at it.
```

To roll back, rebuild without the build arg (crates.io 0.2.0) or point
`image:` back. Check `GET /metrics`: the `upstream_non_5xx` fail-open counter
should stop increasing on attached requests, and the routing log should show
a classifier row for them. Note that with the bundled classifier
(`deepseek-v4-flash-0731`) attached requests are still judged from the text
alone; how often they land on the weak tier depends on the judge and the
threshold, not on this patch.

### Periodic review (collecting routing stats)

Weekly, or on whatever cadence you choose, run one command:

```bash
./scripts/stats-snapshot.sh
```

It saves an aggregate JSON plus the per-request log (JSONL) into `stats-out/`, stamped with the date and your username, and prints a per-route summary of request and token counts. Submit those two files however your project has arranged it (upload to a shared folder, for example).

To merge snapshots collected from several members into one usage report — per-user and team-wide token/cost tables, cache-hit rate, and a strong-pinned counterfactual — run:

```bash
./scripts/trial-report.py member-uploads/                 # any mix of files and directories
./scripts/trial-report.py --since 2026-09-01 --until 2026-09-30
```

Files keep their `routing-<user>-<stamp>.jsonl` names from the snapshot script, so attribution is automatic, and overlapping snapshots from the same user are deduped line by line. Models without a known price are excluded from cost and reported loudly instead of silently under-counting.

To look at the raw surfaces yourself:

| Surface                 | Command                                                                 | Contents                                                                                         |
| ----------------------- | ----------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------ |
| Aggregate snapshot      | `curl -s http://127.0.0.1:4100/v1/stats \| python3 -m json.tool`        | Cumulative request/token counts per model and tier, plus judge health (**reset on restart**)     |
| Per-request log (JSONL) | `docker cp switchyard-opencode:/app/logs/routing.jsonl ./routing.jsonl` | One line per request (selected tier, model, tokens). Durable via the named volume                |
| Prometheus metrics      | `curl -s http://127.0.0.1:4100/metrics`                                 | Includes `switchyard_classifier_fail_open_total` — worth an occasional glance for judge failures |

One improvement over the previous setup: the classifier's own calls now appear in the JSONL with `tier="classifier"`, so the routing overhead cost — invisible before — shows up in the weekly summary as its own row.

**The source of truth for usage and cost** is per-model usage on the [Fireworks dashboard](https://app.fireworks.ai/). Since strong (deepseek-v4-pro-0813) and weak (deepseek-v4-flash-0731) are different models, **per-model usage is exactly your tier distribution multiplied by cost** — that is what a savings report is built from. Kimi K3 (`k3-only` — plan mode and image attachments) and media calls to the eye ([qwen3p7-plus](docs/qwen-mm-plugins.md)) each get their own model row on the dashboard and their own `pinned:kimi-k3` / `pinned:qwen3p7-plus` rows in the local summaries, so they never blur the tier split. The stats above are for analyzing the routing breakdown.

## Experimental

- [`experimental/permission-judge/`](experimental/permission-judge/) — an opencode plugin that adds a Claude Code-style "smart auto mode": an LLM judge (via the router's weak tier) classifies permission requests and only safe ones are auto-approved. Ships in shadow mode (judge and log only, humans still decide) until calibration proves agreement

## Security notes

- The listener binds to **127.0.0.1 only**. Nothing is exposed to the LAN
- The native Rust server has **no request-collection mechanism** (the old Python CLI's Intake sink does not exist here). The only place request bodies go is the Fireworks endpoint you configured
- The routing log (`/app/logs/routing.jsonl`) stays inside a Docker named volume (`switchyard-logs`). It reaches the host only when you pull it out with `stats-snapshot.sh` or `docker cp`. It contains routing decisions and token counts, never prompt bodies
- Web-search safeguards (disabling exa.ai) are outside this router's scope. If you want to limit what leaves through web search, apply them on the opencode side first (see [Requirements](#requirements))
- Queries from the web-search skill go directly to the search backend (the Gemini API or the OpenAI API) under your own key. The conditions for exclusion from training differ per backend — Gemini **requires a key issued from a billing-enabled GCP project** (free-tier keys are used for training), while the OpenAI API excludes your data from training by default ([docs/web-search-onboarding.md](docs/web-search-onboarding.md)). The rule about keeping confidential terms out of queries is documented in SKILL.md
- The `nvidia-rag` MCP assumes you connect to the read-only public surface (5 tools: search, generate, and so on). Keeping the admin surface — which includes delete operations — off the private network is the RAG service's responsibility
- Footnote: if you really want to avoid a plaintext `.env`, you can start the container through 1Password CLI's `op run` with a secret reference. The benefit is limited, though, since Docker stores env vars in container metadata in plaintext anyway (visible via `docker inspect`). This bundle's standard is `.env` plus `chmod 600`
