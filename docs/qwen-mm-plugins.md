**English** | [日本語](qwen-mm-plugins.ja.md)

# An eye for the weak tier (Qwen-MM-Plugins)

Let the text-only weak tier answer questions about images, by giving it an "eye" it can call
as a tool. [Qwen-MM-Plugins](https://github.com/QwenLM/Qwen-MM-Plugins) provides the tools;
the router serves them a hosted vision model on a dedicated route.

**Status: images only.** The router side (`routes.toml`) ships by default; using it is
opt-in on the opencode side — merge the MCP block below. Audio, local video files, and the
`grounding` tool do not work through a hosted endpoint — see [Limits](#limits).

## Why

`deepseek-v4-flash-0731` is cheap and fast but rejects image input outright:

```
POST /v1/chat/completions  + image_url
→ 400 This model does not support image inputs
```

The usual fix is to move the weak tier to a vision-capable model, which costs more on every
turn — including the vast majority that never involve an image. This does the opposite: the
model stays text-only, and images are handled by a tool that returns text.

```
opencode
  ├─ brain   → router → auto / weak-only → deepseek-v4-flash-0731   (never sees an image)
  └─ MCP     → router → qwen3.7-plus     → Fireworks qwen3p7-plus   (sees the image, returns text)
```

The brain receives a description, not an image, so the context stays small and nothing about
the routing setup changes.

## What it costs

Measured on this repository's router, `n=3`, both tasks scored 1.0 (perfect):

| task                        | latency | completion tokens |
| --------------------------- | ------- | ----------------- |
| list PPE in a site photo    | 1.61s   | 302               |
| read 4 printed chart values | 0.76s   | 53                |

`qwen3p7-plus` is $0.4 / $1.6 / $0.08 per 1M (input / output / cached input). One end-to-end
session that took a screenshot, diagnosed a CSS bug, fixed it and verified the fix used
1,626 prompt + 752 completion tokens on the eye — about **$0.002**.

Media calls appear in `routing.jsonl` like any other request, and
`scripts/stats-snapshot.sh` and `scripts/trial-report.py` report them on their own line
(`pinned:qwen3p7-plus`), so the cost stays separable in the weekly review.

## Setup

The router side is already wired — `routes.toml` defines the vision target and the
`qwen3.7-plus` route. Verify:

```bash
curl -s http://127.0.0.1:4100/v1/models | grep qwen
# → "qwen3.7-plus"
```

If you are updating an existing router, `git pull && docker compose restart` is enough (the
image is unchanged). If you had opted in earlier by appending
`experimental/qwen-mm-plugins/routes.snippet.toml` to your `routes.toml`, drop that local
copy first — the same blocks are now committed, and duplicate TOML tables fail to parse:

```bash
git checkout routes.toml && git pull
docker compose restart
```

What remains is the opencode side:

1. Merge this `mcp` block into your opencode config (global
   `~/.config/opencode/opencode.json` or a project-level one). Nothing else in your config
   needs to change.

   ```jsonc
   // The commit is pinned on purpose. Upstream reorganised the capabilities on 2026-08-11:
   // vision_chat / ocr / grounding moved out of `core`, the `omni-av` extra was removed, and
   // everything that calls an external API now lives in `api`. Tracking @main means the next
   // reshuffle silently empties your toolset.
   {
     "mcp": {
       "qwen-mm-plugins-api": {
         "type": "local",
         "command": [
           "uvx",
           "--from",
           "qwen-mm-plugins[api] @ git+https://github.com/QwenLM/Qwen-MM-Plugins.git@8d6ea5a1f658260743307c52c2024ec87599fa48",
           "qwen-mm-plugins-api",
         ],
         "environment": {
           // Point the plugin at the router, not at DashScope. The route id in
           // routes.toml matches the model name the plugin asks for by default.
           "DASHSCOPE_BASE_URL": "http://127.0.0.1:4100/v1",
           // Self-hosted and proxied endpoints ignore auth; the router holds the real key.
           "DASHSCOPE_API_KEY": "EMPTY",
           // Media calls are slower than chat. The default read timeout is too tight.
           "QWEN_MM_CHAT_TIMEOUT": "900",
         },
         "enabled": true,
       },
     },
   }
   ```

2. Ask for something in an image, giving a **path** rather than attaching it:

   ```
   ./screenshot.png のレイアウト崩れの原因を、利用可能なツールで調べて
   ```

No API key beyond `FIREWORKS_API_KEY` is needed — the eye is billed through the same key as
the rest of the router.

### A note on attachments

The models in `opencode.jsonc.example` that cannot read images (`auto`, `auto-esc`,
`weak-only`, and `strong-only` — the strong tier, deepseek-v4-pro-0813, rejects image
input too) deliberately do **not** declare image `modalities`, so opencode refuses image
attachments locally instead of sending them to a model that would 400. That is the correct
setting for this design: images travel as file paths to the tools, not as attachments to
the brain. `k3-only` (Kimi K3) is the one route that declares them, so pin it if you want
to show a picture to the model directly.

## Limits

| capability                            | works?         | note                                                     |
| ------------------------------------- | -------------- | -------------------------------------------------------- |
| `vision_chat` on an image             | yes            | the main path                                            |
| `ocr`                                 | yes            |                                                          |
| `grounding` (object coordinates)      | **no**         | plugin sends `enable_thinking`, Fireworks 400s           |
| video (local file)                    | **no**         | serverless models reject media parts                     |
| audio                                 | **no**         | no Fireworks serverless model accepts audio              |
| `read_image` and other native reading | not applicable | returns the image itself; a text-only brain can't use it |

`grounding` fails because the plugin hardcodes a DashScope/vLLM-specific request field that
strict endpoints reject. Reported upstream as
[QwenLM/Qwen-MM-Plugins#12](https://github.com/QwenLM/Qwen-MM-Plugins/issues/12). In practice
the model falls back to `vision_chat` and still completes the task; the wasted call is the
only cost. Add a line to your `AGENTS.md` if you would rather it not try.

**If you need audio or local video files**, the eye has to be a model that accepts them —
in practice a self-hosted Omni model. Swap `target` in the route definition and restart;
nothing else changes.

## Rollback

Remove the `mcp` entry from your opencode config — without it the route is inert. If you
also want the route out of the router's model list, delete the two blocks
(`[targets.fw_qwen_vl]` and `[routes.omni-vision]`) at the end of `routes.toml` and restart.
Nothing else in the bundle depends on them.
