#!/usr/bin/env python3
"""Grounded web search with a pluggable backend (Gemini / OpenAI).

Usage: search.py "your question"
Env:   WEB_SEARCH_PROVIDER (optional; "gemini" or "openai". Default: auto-detect
                            from which API key is set, Gemini first)
       GEMINI_API_KEY   (gemini backend; key from a BILLING-ENABLED GCP project)
       OPENAI_API_KEY   (openai backend; API data is not used for training by default)
       WEB_SEARCH_MODEL (optional; default gemini-3.6-flash / gpt-5-mini)

Stdlib only. Prints the grounded answer, sources, and a usage line.
Output contract (both backends): answer text, then "Sources:" numbered list,
then one stat line "-- provider=... model=... executed_queries=... tokens=...".
"""

import json
import os
import sys
import urllib.error
import urllib.request

GEMINI_BASE = "https://generativelanguage.googleapis.com/v1beta"
GEMINI_DEFAULT_MODEL = "gemini-3.6-flash"
OPENAI_BASE = "https://api.openai.com/v1"
OPENAI_DEFAULT_MODEL = "gpt-5-mini"


def fail(msg: str) -> None:
    print(msg, file=sys.stderr)
    sys.exit(1)


def post_json(url: str, body: dict, headers: dict, label: str, timeout: int) -> dict:
    req = urllib.request.Request(
        url,
        data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json", **headers},
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as res:
            return json.loads(res.read())
    except urllib.error.HTTPError as e:
        detail = e.read().decode(errors="replace")[:400]
        fail(f"{label} API error: HTTP {e.code}\n{detail}")
    except urllib.error.URLError as e:
        fail(f"network error: {e.reason}")
    raise AssertionError("unreachable")


def search_gemini(query: str, key: str) -> tuple[str, list[str], int, object, str]:
    model = os.environ.get("WEB_SEARCH_MODEL", GEMINI_DEFAULT_MODEL)
    data = post_json(
        f"{GEMINI_BASE}/models/{model}:generateContent",
        {
            "contents": [{"role": "user", "parts": [{"text": query}]}],
            "tools": [{"google_search": {}}],
        },
        {"x-goog-api-key": key},
        "Gemini",
        timeout=90,
    )
    cand = (data.get("candidates") or [{}])[0]
    parts = (cand.get("content") or {}).get("parts") or []
    answer = "".join(p.get("text", "") for p in parts).strip()

    gm = cand.get("groundingMetadata") or {}
    sources = [
        f"{c['web'].get('title', 'untitled')} - {c['web'].get('uri', '')}"
        for c in gm.get("groundingChunks") or []
        if c.get("web", {}).get("uri")
    ]
    executed = len(gm.get("webSearchQueries") or [])
    tokens = (data.get("usageMetadata") or {}).get("totalTokenCount", "?")
    return answer, sources, executed, tokens, model


def search_openai(query: str, key: str) -> tuple[str, list[str], int, object, str]:
    model = os.environ.get("WEB_SEARCH_MODEL", OPENAI_DEFAULT_MODEL)
    data = post_json(
        f"{OPENAI_BASE}/responses",
        {
            "model": model,
            "input": query,
            "tools": [{"type": "web_search"}],
        },
        {"Authorization": f"Bearer {key}"},
        "OpenAI",
        timeout=120,
    )
    answer_parts: list[str] = []
    sources: list[str] = []
    seen_urls: set[str] = set()
    executed = 0
    for item in data.get("output") or []:
        if item.get("type") == "web_search_call":
            executed += 1
        if item.get("type") != "message":
            continue
        for content in item.get("content") or []:
            if content.get("type") != "output_text":
                continue
            answer_parts.append(content.get("text", ""))
            for ann in content.get("annotations") or []:
                url = ann.get("url", "")
                if ann.get("type") == "url_citation" and url and url not in seen_urls:
                    seen_urls.add(url)
                    sources.append(f"{ann.get('title') or 'untitled'} - {url}")
    tokens = (data.get("usage") or {}).get("total_tokens", "?")
    return "".join(answer_parts).strip(), sources, executed, tokens, model


BACKENDS = {
    "gemini": ("GEMINI_API_KEY", search_gemini),
    "openai": ("OPENAI_API_KEY", search_openai),
}

KEY_GUIDANCE = {
    "GEMINI_API_KEY": (
        "GEMINI_API_KEY is not set.\n"
        "Use an API key from a BILLING-ENABLED GCP project (free-tier keys allow "
        "Google to train on your queries). See the team onboarding guide."
    ),
    "OPENAI_API_KEY": (
        "OPENAI_API_KEY is not set. Issue a key per the team onboarding guide "
        "(OpenAI API data is not used for training by default)."
    ),
}


def main() -> None:
    query = " ".join(sys.argv[1:]).strip()
    if not query:
        fail('usage: search.py "your question"')

    provider = os.environ.get("WEB_SEARCH_PROVIDER", "").strip().lower()
    if provider and provider not in BACKENDS:
        fail(f"unknown WEB_SEARCH_PROVIDER: {provider} (use 'gemini' or 'openai')")
    if not provider:
        provider = next(
            (
                name
                for name, (env, _) in BACKENDS.items()
                if os.environ.get(env, "").strip()
            ),
            "",
        )
        if not provider:
            fail(
                "No API key found. Set GEMINI_API_KEY (billing-enabled GCP project) or "
                "OPENAI_API_KEY, then retry. Backend is auto-detected from the key "
                "(override with WEB_SEARCH_PROVIDER=gemini|openai). "
                "See the team onboarding guide."
            )

    env_name, backend = BACKENDS[provider]
    key = os.environ.get(env_name, "").strip()
    if not key:
        fail(KEY_GUIDANCE[env_name])

    answer, sources, executed, tokens, model = backend(query, key)
    print(answer if answer else "(no answer text returned)")
    if sources:
        print("\nSources:")
        print("\n".join(f"[{i + 1}] {s}" for i, s in enumerate(sources)))
    print(
        f"\n-- provider={provider} model={model} executed_queries={executed} tokens={tokens}"
    )


if __name__ == "__main__":
    main()
