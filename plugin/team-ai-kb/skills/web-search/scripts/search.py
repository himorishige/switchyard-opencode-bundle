#!/usr/bin/env python3
"""Grounded web search via Gemini API (Google Search grounding).

Usage: search.py "your question"
Env:   GEMINI_API_KEY   (required; key from a billing-enabled GCP project)
       WEB_SEARCH_MODEL (optional; default gemini-3.6-flash)

Stdlib only. Prints the grounded answer, sources, and a usage line.
"""

import json
import os
import sys
import urllib.error
import urllib.request

BASE = "https://generativelanguage.googleapis.com/v1beta"
DEFAULT_MODEL = "gemini-3.6-flash"


def fail(msg: str) -> None:
    print(msg, file=sys.stderr)
    sys.exit(1)


def main() -> None:
    query = " ".join(sys.argv[1:]).strip()
    if not query:
        fail('usage: search.py "your question"')

    key = os.environ.get("GEMINI_API_KEY", "").strip()
    if not key:
        fail(
            "GEMINI_API_KEY is not set.\n"
            "Use an API key from a BILLING-ENABLED GCP project (free-tier keys allow "
            "Google to train on your queries). See the team onboarding guide."
        )

    model = os.environ.get("WEB_SEARCH_MODEL", DEFAULT_MODEL)
    body = json.dumps(
        {
            "contents": [{"role": "user", "parts": [{"text": query}]}],
            "tools": [{"google_search": {}}],
        }
    ).encode()
    req = urllib.request.Request(
        f"{BASE}/models/{model}:generateContent",
        data=body,
        headers={"Content-Type": "application/json", "x-goog-api-key": key},
    )
    try:
        with urllib.request.urlopen(req, timeout=90) as res:
            data = json.loads(res.read())
    except urllib.error.HTTPError as e:
        detail = e.read().decode(errors="replace")[:400]
        fail(f"Gemini API error: HTTP {e.code}\n{detail}")
    except urllib.error.URLError as e:
        fail(f"network error: {e.reason}")

    cand = (data.get("candidates") or [{}])[0]
    parts = (cand.get("content") or {}).get("parts") or []
    answer = "".join(p.get("text", "") for p in parts).strip()
    print(answer if answer else "(no answer text returned)")

    gm = cand.get("groundingMetadata") or {}
    chunks = gm.get("groundingChunks") or []
    sources = [
        f"[{i + 1}] {c['web'].get('title', 'untitled')} - {c['web'].get('uri', '')}"
        for i, c in enumerate(chunks)
        if c.get("web", {}).get("uri")
    ]
    if sources:
        print("\nSources:")
        print("\n".join(sources))

    usage = data.get("usageMetadata") or {}
    print(
        f"\n-- model={model} executed_queries={len(gm.get('webSearchQueries') or [])} "
        f"tokens={usage.get('totalTokenCount', '?')}"
    )


if __name__ == "__main__":
    main()
