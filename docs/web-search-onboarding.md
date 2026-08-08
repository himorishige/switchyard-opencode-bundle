# web-search skill onboarding

**English** | [日本語](web-search-onboarding.ja.md)

The web-search skill (`plugin/team-ai-kb/skills/web-search/`) calls a search backend directly with
your own API key. There is no intermediary server.
Two backends are supported — **Gemini (recommended) and OpenAI (alternative)** — and either one works
on its own. The skill picks whichever key you have configured (Gemini wins if both are set; override
with `WEB_SEARCH_PROVIDER=openai`).

## Choosing a backend

| Backend              | Condition for exclusion from training                                                           | Free tier                  | Cost beyond it     | Setup  |
| -------------------- | ----------------------------------------------------------------------------------------------- | -------------------------- | ------------------ | ------ |
| Gemini (recommended) | **The key must come from a billing-enabled GCP project** (free-tier keys are used for training) | 5,000 queries/month/person | $14 per 1k queries | 15 min |
| OpenAI (alternative) | Excluded by default on the API (no extra conditions)                                            | none                       | ≈$0.012 per search | 5 min  |

Gemini is recommended for everyday use because of the free tier. If you cannot get a billing-enabled
GCP project, use OpenAI.

## Using Gemini (15 minutes)

**You must use a key issued from a billing-enabled GCP project.**
Under Google's terms, queries made with a free-tier key (no billing configured) are used to train
models. A key from a billing-enabled project counts as paid tier and is excluded from training (the
DPA applies). This is the one point in this procedure you cannot skip.

1. **Create a GCP project** (1 min)
   - https://console.cloud.google.com/ → new project (for example `websearch-<name>`)
   - A dedicated websearch project is recommended so it stays separate from other work — your Cloud
     Billing report then doubles as your search cost report
2. **Link a billing account** (2 min, required)
   - Project settings → link a billing account
   - Nothing is charged while you stay inside the free tier (5,000 queries/month). The link is what
     makes the key paid tier, and therefore excluded from training
3. **Issue an API key** (2 min)
   - https://aistudio.google.com/ → API keys → select the project you just created
4. **Put the key in an environment variable** (2 min)
   - `export GEMINI_API_KEY=<key>` in `~/.zshenv` or similar (`chmod 600` the file, and keep the key
     in your password manager as well)
   - Never write it into a file under git
5. **Verify** (1 min)
   - `uv run plugin/team-ai-kb/skills/web-search/scripts/search.py "What is the memory bandwidth of DGX Spark?"`
   - You should get an answer, a `Sources:` list, and a stats line
     (`-- provider=gemini model=... executed_queries=... tokens=...`)
   - If the key is missing or invalid, the error message tells you what to do
   - The default model is `gemini-3.6-flash`; override it with the `WEB_SEARCH_MODEL` environment variable

## Using OpenAI (5 minutes)

Exclusion from training is the API default — your data is not used unless you explicitly opt in
(there is retention of up to 30 days for abuse monitoring). There is no free tier; each search costs
roughly $0.012 (the web search tool charge plus token usage) against your own account.

1. **Issue an API key** (2 min)
   - From https://platform.openai.com/api-keys (if keys are issued through an organization, follow
     your team's instructions)
2. **Put the key in an environment variable** (2 min)
   - `export OPENAI_API_KEY=<key>` in `~/.zshenv` or similar — same rules as Gemini: `chmod 600`,
     password manager, never under git
   - If `GEMINI_API_KEY` is also set, Gemini takes precedence. To use OpenAI, add
     `export WEB_SEARCH_PROVIDER=openai`
3. **Verify** (1 min)
   - Same command as Gemini. You are set if the stats line reads `-- provider=openai model=gpt-5-mini ...`
   - The default model is `gpt-5-mini`; override it with the `WEB_SEARCH_MODEL` environment variable

## Ground rules (both backends)

- **Keep confidential terms out of queries** — customer names, internal code names, secrets (see the
  query discipline in SKILL.md)
- Do not mechanically retry the same question with reworded queries (after two attempts, change the
  question or fetch the source directly)
- For topics the local knowledge base covers (team verification records, past articles), try rag-kb first
- Gemini's free tier is **5,000 executed search queries per month, per project**. One call runs 1–3
  queries, and the `executed_queries` value in the stats line is the billing unit (as a rule of thumb,
  10–16 calls a day stays inside the tier).
  Overage, and all OpenAI usage, is billed to your own account — check your usage on your own
  dashboards (AI Studio / Cloud Billing, OpenAI Usage)
