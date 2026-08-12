# Team onboarding (one linear path, 45–60 minutes)

**English** | [日本語](onboarding.ja.md)

This is the path a new team member follows to get everything in place, from starting the router to
running a web search. The details of each step live in the [README](../README.md) and the other
documents; what this page adds is the order, and the points people miss.
Most of the elapsed time is waiting — for the image build and for GCP.

## Overview

| #   | Step                                         | Where                                                  | Time      |
| --- | -------------------------------------------- | ------------------------------------------------------ | --------- |
| 1   | Start the router                             | README, "Setup"                                        | 15–20 min |
| 2   | opencode global config                       | README, "Configuring opencode"                         | 5 min     |
| 3   | Shell environment variables (strict-privacy) | This document                                          | 3 min     |
| 4   | Place a global AGENTS.md                     | This document                                          | 2 min     |
| 5   | Agent Plugin (team-ai-kb)                    | README, "Agent Plugin"                                 | 5 min     |
| 6   | Web search key                               | [web-search-onboarding.md](./web-search-onboarding.md) | 5–15 min  |
| 7   | Verification checklist                       | This document                                          | 5 min     |
| –   | (Optional) An eye for the weak tier (images) | [qwen-mm-plugins.md](./qwen-mm-plugins.md)             | 5 min     |

Steps 3 and 4 are independent of the router, so the image build in step 1 is a good time to do them.

## 1. Start the router

Follow steps 1–4 of "Setup" in the README. Three things matter:

- Put `FIREWORKS_API_KEY` in `.env` (outside git, `chmod 600`; follow your team's instructions for
  obtaining the key)
- `docker compose up -d --build` (the first build takes a while)
- `curl -s http://127.0.0.1:4100/health` returning `{"status":"ok"}` means you are done

## 2. opencode global config

Set up `~/.config/opencode/opencode.json` using either path A (overwrite with the bundled config) or
path B (merge into your existing config) from "Configuring opencode" in the README.

- It must go in the **global scope** (`~/.config/opencode/`). A project-level opencode.json overrides
  the global one, which is how privacy settings quietly go missing
- Do not keep both `.json` and `.jsonc` — pick one

## 3. Shell environment variables (strict-privacy)

Step 2 covers only the config-file half of strict-privacy. The environment-variable half goes into
your own shell startup file (`~/.zshrc`, or `~/.bashrc` for bash).

```sh
# environment variables recommended by opencode-with-strict-privacy
export OPENCODE_ENABLE_EXA=0             # disable Exa search
export OPENCODE_EXPERIMENTAL=0           # disable experimental features wholesale
export OPENCODE_EXPERIMENTAL_EXA=0       # legacy Exa flag
export OPENCODE_AUTO_SHARE=0             # disable automatic sharing
export OPENCODE_DISABLE_LSP_DOWNLOAD=1   # optional: stop automatic LSP downloads
export OPENCODE_DISABLE_MODELS_FETCH=1   # optional: stop model catalog fetches
```

Source: [opencode-with-strict-privacy](https://github.com/cm-dyoshikawa/opencode-with-strict-privacy),
which explains these together with the config-file side.

Run `source ~/.zshrc` afterwards, or open a new terminal.

## 4. Place a global AGENTS.md (easy to miss, and important)

When a global `~/.config/opencode/AGENTS.md` **does not exist, opencode falls back to reading
`~/.claude/CLAUDE.md` as its global rules** — this is documented behavior. If you also use Claude Code,
that means your personal settings and notes get sent along with every request.

The fix is simply to place a global AGENTS.md, which stops the fallback.

```sh
mkdir -p ~/.config/opencode
cat > ~/.config/opencode/AGENTS.md <<'EOF'
# Global rules

- Never put customer names, internal project names, or unreleased code names into web search queries
- Reply in the same language the user writes in
EOF
```

- If you already maintain your own AGENTS.md, you are fine — the fallback only fires when the file is absent
- The content can be minimal. The first line is the team's recommended query discipline
- The second line is worth keeping even if you write your own file. Open-weight models do not always
  follow the language of the question: with no system prompt at all, the weak tier answered 6 of 15
  Japanese prompts in Chinese. The failure is easy to miss because the answer itself is usually fine —
  it is just in the wrong language
- **Write this file in the language you ask questions in.** The file's own language anchors the reply
  more strongly than the instruction does. On those same 15 Japanese prompts: an English file with the
  language line still left 2 misses, while a Japanese file with the line written in Japanese left 0.
  An English file without the line left 4

## 5. Agent Plugin (team-ai-kb)

Complete ["First-time setup (all clients)"](../README.md#first-time-setup-all-clients) under
["Agent Plugin (rag-kb / web-search)"](../README.md#agent-plugin-rag-kb--web-search) in the README,
then continue to the section for your client ([opencode](../README.md#with-opencode) /
[Claude Code](../README.md#with-claude-code) / [Codex CLI](../README.md#with-codex-cli)).

- For the endpoint address you fill in after copying `mcp.json.example` to `mcp.json` during the
  first-time setup, follow your team's instructions

## 6. Web search key

Follow [web-search-onboarding.md](./web-search-onboarding.md).
Either backend works on its own: **Gemini (recommended, has a free tier, 15 min) or OpenAI
(alternative, 5 min)**. Do not skip the part about exclusion from training — for Gemini, the key
**must be issued from a billing-enabled GCP project** (free-tier keys are used for training); for
OpenAI, the API excludes your data from training by default.

## 7. Verification checklist

| Check                 | Command                                           | Expected                                                           |
| --------------------- | ------------------------------------------------- | ------------------------------------------------------------------ |
| Router                | `curl -s http://127.0.0.1:4100/health`            | `{"status":"ok"}`                                                  |
| Route list            | `curl -s http://127.0.0.1:4100/v1/models`         | auto / auto-esc / strong-only / weak-only / k3-only / qwen3.7-plus |
| opencode              | `opencode run -m switchyard/auto "hello"`         | a response comes back                                              |
| AGENTS.md             | `ls ~/.config/opencode/AGENTS.md`                 | the file exists                                                    |
| Environment variables | `env \| grep OPENCODE_`                           | the values from step 3                                             |
| Web search            | the verification step in web-search-onboarding.md | an answer, `Sources:`, and a stats line                            |

- After a long idle period the first call can take tens of seconds because of a cold start (a few
  seconds from the second call onward). Adding `--max-time` to your connectivity checks makes it
  easier to tell the two apart
