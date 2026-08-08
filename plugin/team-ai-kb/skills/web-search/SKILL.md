---
name: web-search
description: >
  Grounded web search through Gemini (Google Search grounding) or OpenAI (web search).
  Returns an answer with its sources.
  Use when: you need current or public information from the web / the user asks you to
  "search the web" or "google it" / you need general knowledge, a recent release, a price
  or a spec that the local knowledge base (rag-kb) does not cover.
  Trigger keywords: web search, search the web, google it, look it up, latest, release info,
  web検索, 検索して, ググって, 調べて, 最新情報, リリース情報
---

# web-search — grounded web search (Gemini / OpenAI)

Calls a search backend (Gemini or OpenAI) directly with the user's own API key.
No intermediary server: the query goes from this machine to exactly one backend provider.

## How to run it

Run this skill's `scripts/search.py` with the question as its argument (stdlib only, no dependencies).

```bash
uv run <this skill's directory>/scripts/search.py "your question"
# python3 works too if uv is unavailable
```

Output = the grounded answer, then `Sources:` (source URLs), then one line of usage stats
(`-- provider=... model=... executed_queries=... tokens=...`).

## Prerequisites (once)

- **One** of these API keys must be in the environment. The backend is selected from whichever key
  is present (Gemini wins if both are; override with `WEB_SEARCH_PROVIDER=gemini|openai`)
  - `GEMINI_API_KEY` (recommended, has a free tier): the key **must be issued from a
    billing-enabled GCP project** — queries made with a free-tier key are used to train Google's models
  - `OPENAI_API_KEY` (alternative, no free tier): excluded from training by default on the API, no
    extra conditions
  - Setup instructions: `docs/web-search-onboarding.md` in the distribution repository
- Default models are `gemini-3.6-flash` for Gemini and `gpt-5-mini` for OpenAI.
  Override with the `WEB_SEARCH_MODEL` environment variable

## Query discipline (required)

- **Never put confidential terms in a query** — customer names, internal code names, unreleased
  internal information, secrets. Rephrase into general terms before searching
- Pass the question as a sentence (grounding works better on sentences than on decomposed keywords)
- Cite the `Sources:` entries when you use the answer. Treat an answer with no sources as unverified

## Cost manners

- Gemini bills **per executed search query**, and one call runs 1–3 of them (visible in the stats
  line). The free tier is 5,000 queries per month per GCP project.
  OpenAI has no free tier and costs roughly $0.012 per search
- **Do not mechanically retry the same question with reworded queries.** After two attempts, change
  the question or fetch the source directly
- For topics the local knowledge base covers (team verification records, past articles), use rag-kb first
