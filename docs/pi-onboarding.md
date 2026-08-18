# Pi onboarding — an optional second client (15–20 minutes)

## Overview

[Pi](https://pi.dev/) ([earendil-works/pi](https://github.com/earendil-works/pi), MIT) is a minimal
coding-agent harness: a ~430-token system prompt, four core tools, and everything else added
through extensions and packages. This guide connects Pi to the same Switchyard router you already
use with opencode, so routing, cost tracking, and the team-ai-kb skills stay identical across both
clients.

opencode remains the primary client of this bundle. Reasons to also set up Pi:

- Headless image input works: `pi -p @screenshot.png "..."` (opencode `run -f` currently hangs on
  image attachments)
- `--mode json` emits a machine-readable event stream with token usage, which is convenient for
  scripting and delegation from other agents
- MCP servers are reached through a single lazy proxy tool (~200 tokens) instead of full tool-schema
  injection, which keeps the context small on the weak tier
- Subscription auth (`/login`): ChatGPT Plus/Pro (Codex), Claude, Copilot and others can be used
  side by side with the router

Note: Pi has **no built-in permission prompts** (YOLO by design). It runs with your user's full
permissions. Use it in trusted working directories; optionally add
`@gotgenes/pi-permission-system` (see step 5).

## 1. Install Pi

```bash
npm install -g --ignore-scripts @earendil-works/pi-coding-agent
# or: bun add -g @earendil-works/pi-coding-agent
pi --version
```

## 2. Connect Pi to the router

The router must already be running (see the main README). Copy the model definitions:

```bash
mkdir -p ~/.pi/agent
cp pi-models.json.example ~/.pi/agent/models.json
```

If your router is not on `127.0.0.1:4100`, edit `baseUrl` accordingly.

## 3. Settings (default model + team skills)

```bash
cp pi-settings.json.example ~/.pi/agent/settings.json
```

Then open `~/.pi/agent/settings.json` and replace `<bundle-repo>` with the absolute path of your
clone of this repository. This makes the team skills (`rag-kb`, `web-search`, `using-bee`) available in Pi —
they are standard Agent Skills, so the same files serve both opencode and Pi. The `web-search`
skill uses the same `GEMINI_API_KEY` / `OPENAI_API_KEY` environment variables you already set up
in the web-search onboarding. The `using-bee` skill uses your local `bee` CLI authentication.

If you already have your own `settings.json`, merge the `skills` entry instead of overwriting.

## 4. Try it

```bash
pi                       # TUI; footer shows "(switchyard) auto"
pi --list-models switchyard
pi -p "explain this repo in two sentences"       # headless
pi -p @screenshot.png "what is in this image?"   # headless with an image (k3-only or qwen3.7-plus)
```

Inside the TUI: `/model` or `Ctrl+P` switches routes (`auto` for daily work, `strong-only` /
`k3-only` for hard tasks), `/skill:web-search`, `/skill:rag-kb`, and `/skill:using-bee` invoke the team skills.

## 5. Optional packages

```bash
pi install npm:pi-mcp-adapter          # MCP support (single lazy proxy tool)
pi install npm:pi-subagents            # scout / reviewer / worker delegation
pi install npm:@gotgenes/pi-permission-system   # allow/ask/deny rules if you want guardrails
```

For MCP, Pi reads the standard `.mcp.json` files you may already have. To reach the team RAG
service and the Qwen-MM-Plugins vision tools (same pinned revision and router-backed
configuration as the opencode setup — see `docs/qwen-mm-plugins.md`), add to
`~/.pi/agent/mcp.json`:

```json
{
  "mcpServers": {
    "nvidia-rag": { "url": "http://<rag-service-host>:8091/mcp" },
    "qwen-mm-plugins": {
      "command": "uvx",
      "args": [
        "--from",
        "qwen-mm-plugins[api] @ git+https://github.com/QwenLM/Qwen-MM-Plugins.git@8d6ea5a1f658260743307c52c2024ec87599fa48",
        "qwen-mm-plugins-api"
      ],
      "env": {
        "DASHSCOPE_BASE_URL": "http://127.0.0.1:4100/v1",
        "DASHSCOPE_API_KEY": "EMPTY",
        "QWEN_MM_CHAT_TIMEOUT": "900"
      }
    }
  }
}
```

Servers connect lazily, and the first `qwen-mm-plugins` start (a `uvx` stdio process) can exceed
the connect window. If a call reports "configured but not connected", ask the agent to run
`mcp({ "connect": "qwen-mm-plugins" })` once, or use `/mcp reconnect qwen-mm-plugins` in the TUI;
subsequent calls use the cached tool metadata.

If you install `pi-permission-system`, note that it applies to **all** projects once installed:
create `~/.pi/agent/extensions/pi-permission-system/config.json` with a permissive default
(`"*": "allow"` plus the deny/ask rules you want), otherwise headless runs fail closed on every
tool call.

## 6. Optional: subscription models side by side

`/login` in the TUI lets you add ChatGPT Plus/Pro (Codex), Claude, or Copilot subscription auth.
These models then appear in `/model` next to the Switchyard routes. Keep in mind that subscription
usage bypasses the router ledger, so day-to-day work on the router routes keeps the team cost
numbers meaningful.

## 7. Verification checklist

- [ ] `pi --list-models switchyard` shows 6 routes
- [ ] TUI footer shows `(switchyard) auto` and answers a prompt
- [ ] `pi -p "1+1?"` works headless
- [ ] `/skill:` autocomplete lists `rag-kb`, `web-search`, and `using-bee`
- [ ] (optional) `mcp` tool reaches `nvidia-rag` after installing pi-mcp-adapter
- [ ] (optional) `mcp({ "connect": "qwen-mm-plugins" })` connects and `vision_chat` answers about a local image
