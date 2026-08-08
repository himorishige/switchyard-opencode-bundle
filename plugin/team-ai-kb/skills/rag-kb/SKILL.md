---
name: rag-kb
description: >
  Guide to searching the shared team knowledge base (NVIDIA RAG Blueprint) over MCP.
  Use when: you need something from internal knowledge, verification records or published
  articles / the user asks you to "check the knowledge base" or "search the RAG" /
  you need to confirm a number from a past experiment or article.
  Trigger keywords: knowledge base, RAG, rag-kb, internal docs, collection, search the knowledge,
  ナレッジ, RAG で検索, 社内ドキュメント, 記事を調べて, コレクション
---

# rag-kb — using the shared knowledge base

Access the team's RAG stack (NVIDIA RAG Blueprint) through the `nvidia-rag` MCP server.
Only five read-only tools are exposed: `search`, `generate`, `get_summary`,
`list_collections`, `get_documents`. Writes and deletes are not reachable from this surface
(administrators only).

## Which tool to use when

| Goal                                                     | Tool               | Notes                                                                   |
| -------------------------------------------------------- | ------------------ | ----------------------------------------------------------------------- |
| See the relevant chunks and judge for yourself (default) | `search`           | Light and fast. Start around `reranker_top_k: 4`                        |
| Get a written answer grounded in the knowledge base      | `generate`         | Runs the whole RAG pipeline (rewriter, rerank, generation). Slow, heavy |
| Find out which collections exist                         | `list_collections` | Check the catalog here first                                            |
| List the files inside a collection                       | `get_documents`    |                                                                         |

**Rule of thumb: reach for `search` first.** If you — the agent — are going to compose the final
answer anyway, reading chunks from `search` is faster than waiting on `generate`'s LLM, and it keeps
your context cleaner. Use `generate` only when the deliverable is the cited answer text itself.

## The usual shape

1. Confirm the collections with `list_collections` (names come from the catalog)
2. Pass the **question as-is** to `search` — do not decompose it into keywords. Embeddings work best
   on sentences, and a Japanese query retrieves English documents just fine; cross-language search
   works normally
3. Always specify `collection_names` explicitly (omitting it searches collections you did not intend)
4. Check `document_name` and `score` on the hits. If nothing scores above 0.5, judge it "no match"
   rather than forcing a citation
5. Cite the source (`document_name`) in your answer

## Manners and constraints

- Every search consumes one request against the shared embedding API (40 requests/minute, shared by
  the team). **Do not mechanically retry the same question with reworded queries** — after three
  attempts, change the question
- `[image content removed by MCP adapter]` in a response marks a table or page image that the adapter
  layer stripped. When you actually need the image, ask the same question in the web UI
- For the endpoint address, or who to contact when it misbehaves, see the "Agent Plugin" section of
  the distribution repository README

## Collection catalog (maintained by administrators)

| Collection               | Contents                                    | Updated   |
| ------------------------ | ------------------------------------------- | --------- |
| (example) devio-articles | Archive of the team's published articles    | Weekly    |
| (example) nvidia-docs    | Excerpts from NVIDIA official documentation | As needed |
