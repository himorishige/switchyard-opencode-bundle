**English** | [日本語](README.ja.md)

# qwen-mm-plugins (experimental)

Let the text-only weak tier answer questions about images, by giving it an "eye" it can call
as a tool. [Qwen-MM-Plugins](https://github.com/QwenLM/Qwen-MM-Plugins) provides the tools;
this directory wires them to a hosted vision model through the router you already run.

**Status: experimental. Images only.** Audio, local video files, and the `grounding` tool do
not work through a hosted endpoint — see [Limits](#limits). Not part of the default setup;
adding it changes nothing for anyone who does not opt in.

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
`scripts/stats-snapshot.sh` reports them on their own line (`pinned:qwen3p7-plus`), so the
cost stays separable in the weekly review.

## Setup

1. Append [`routes.snippet.toml`](routes.snippet.toml) to your `routes.toml`, then validate
   and restart:

   ```bash
   cat experimental/qwen-mm-plugins/routes.snippet.toml >> routes.toml
   docker compose run --rm switchyard --config /app/routes.toml --dry-run
   docker compose restart
   ```

   The dry-run should list `qwen3.7-plus` alongside your existing routes.

2. Merge the `mcp` block from
   [`opencode.mcp.example.jsonc`](opencode.mcp.example.jsonc) into your opencode config.

3. Ask for something in an image, giving a **path** rather than attaching it:

   ```
   ./screenshot.png のレイアウト崩れの原因を、利用可能なツールで調べて
   ```

No API key beyond `FIREWORKS_API_KEY` is needed — the eye is billed through the same key as
the rest of the router.

### A note on attachments

The models in `opencode.jsonc.example` that can be served by the weak tier (`auto`,
`auto-esc`, `weak-only`) deliberately do **not** declare image `modalities`, so opencode
refuses image attachments locally instead of sending them to a model that would 400. That is
the correct setting for this design: images travel as file paths to the tools, not as
attachments to the brain. `strong-only` / `k3-only` do declare them, so pin one of those if
you want to show a picture to the model directly.

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
in practice a self-hosted Omni model. Swap `target` in the route snippet and restart; nothing
else changes.

## Rollback

Delete the two blocks added in step 1 from `routes.toml`, restart, and remove the `mcp` entry.
Nothing else in the bundle depends on them.
