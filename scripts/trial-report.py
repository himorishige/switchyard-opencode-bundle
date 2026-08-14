#!/usr/bin/env python3
"""Merge routing-log snapshots from multiple members into one usage report.

Inputs
  Any mix of files and directories (default: ./stats-out). Directories are
  searched recursively for *.jsonl. Files named
  routing-<user>-YYYYMMDD-HHMMSS.jsonl (what scripts/stats-snapshot.sh
  produces) are attributed to <user>; anything else is attributed to
  "unknown" unless --user overrides it.

Dedup
  Snapshot files are full copies of the container's routing.jsonl, so a
  member who submits weekly uploads the same early rows every time. Rows are
  deduped per user by exact line match before aggregation. Do NOT dedup
  across users: two routers legitimately produce independent rows.

Cost model
  Same as the measured Fireworks serverless rates used throughout this
  project (USD per 1M tokens, input / cached input / output):
    deepseek-v4-pro          1.74 / 0.145 / 3.48
    deepseek-v4-pro-0813     1.32 / 0.044 / 3.96
    deepseek-v4-flash(-0731) 0.14 / 0.028 / 0.28
    kimi-k3                  3.00 / 0.30  / 15.00
    minimax-m3               0.30 / 0.059 / 1.20
  Rows whose model has no known price keep their token counts in the tables
  but are EXCLUDED from cost and listed in a warning, so a silent
  under-count cannot hide in the totals.

The "strong-pinned" counterfactual
  What the same token volume would cost billed at the current strong tier's
  rates (deepseek-v4-pro-0813 since 2026-08-14; kimi-k3 before that), with
  classifier rows excluded (a pinned setup makes no routing calls). It is an
  approximation — a strong model would not generate the exact same tokens —
  but it is the same yardstick the project's published numbers use.

Usage
  scripts/trial-report.py                          # ./stats-out, all time
  scripts/trial-report.py --since 2026-09-01 --until 2026-09-30
  scripts/trial-report.py member-uploads/ --json   # machine-readable
"""

import argparse
import json
import re
import sys
from collections import defaultdict
from pathlib import Path

# (input, cached_input, output) USD per 1M tokens
PRICES = {
    "accounts/fireworks/models/deepseek-v4-pro": (1.74, 0.145, 3.48),
    "accounts/fireworks/models/deepseek-v4-pro-0813": (1.32, 0.044, 3.96),
    "accounts/fireworks/models/deepseek-v4-flash": (0.14, 0.028, 0.28),
    "accounts/fireworks/models/deepseek-v4-flash-0731": (0.14, 0.028, 0.28),
    "accounts/fireworks/models/kimi-k3": (3.00, 0.30, 15.00),
    "accounts/fireworks/models/minimax-m3": (0.30, 0.059, 1.20),
    "accounts/fireworks/models/qwen3p7-plus": (0.40, 0.08, 1.60),
}
STRONG_PRICE = PRICES["accounts/fireworks/models/deepseek-v4-pro-0813"]

SNAPSHOT_RE = re.compile(r"routing-(?P<user>.+)-\d{8}-\d{6}\.jsonl$")


def row_cost(row, price):
    p_in, p_cached, p_out = price
    cached = row.get("cached_tokens") or 0
    uncached = max((row.get("prompt_tokens") or 0) - cached, 0)
    out = row.get("completion_tokens") or 0
    return (uncached * p_in + cached * p_cached + out * p_out) / 1e6


def label_of(row):
    # Auto-routed rows carry tier=strong/weak, judge calls carry
    # tier=classifier, pinned routes log an empty tier -> label by model.
    return row.get("tier") or "pinned:" + row.get("model", "?").rsplit("/", 1)[-1]


def collect_files(paths):
    files = []
    for p in (Path(p) for p in paths):
        if p.is_dir():
            files.extend(sorted(p.rglob("*.jsonl")))
        elif p.is_file():
            files.append(p)
        else:
            sys.exit(f"error: no such file or directory: {p}")
    return files


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument(
        "paths",
        nargs="*",
        default=None,
        help="jsonl files or directories (default: ./stats-out)",
    )
    ap.add_argument(
        "--since", help="inclusive date filter, YYYY-MM-DD (on the row's ts)"
    )
    ap.add_argument("--until", help="inclusive date filter, YYYY-MM-DD")
    ap.add_argument(
        "--user",
        help="attribute files without a routing-<user>-<stamp> name to this user",
    )
    ap.add_argument(
        "--json",
        action="store_true",
        help="emit the aggregate as JSON instead of tables",
    )
    args = ap.parse_args()

    files = collect_files(args.paths or ["stats-out"])
    if not files:
        sys.exit("error: no .jsonl files found")

    seen = defaultdict(set)  # user -> exact lines (dedup within a user)
    rows = defaultdict(list)  # user -> parsed rows
    file_count = defaultdict(int)
    for f in files:
        m = SNAPSHOT_RE.search(f.name)
        user = m["user"] if m else (args.user or "unknown")
        file_count[user] += 1
        for line in f.read_text().splitlines():
            line = line.strip()
            if not line or line in seen[user]:
                continue
            seen[user].add(line)
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            day = (row.get("ts") or "")[:10]
            if args.since and day < args.since:
                continue
            if args.until and day > args.until:
                continue
            rows[user].append(row)

    report = {"users": {}, "team": None, "unknown_models": {}}
    unknown = defaultdict(lambda: [0, 0])  # model -> [calls, tokens]

    def aggregate(row_list):
        agg = defaultdict(
            lambda: {
                "requests": 0,
                "prompt": 0,
                "cached": 0,
                "completion": 0,
                "cost": 0.0,
            }
        )
        counterfactual = 0.0
        for row in row_list:
            a = agg[label_of(row)]
            a["requests"] += 1
            a["prompt"] += row.get("prompt_tokens") or 0
            a["cached"] += row.get("cached_tokens") or 0
            a["completion"] += row.get("completion_tokens") or 0
            price = PRICES.get(row.get("model", ""))
            if price:
                a["cost"] += row_cost(row, price)
            if row.get("tier") != "classifier":
                counterfactual += row_cost(row, STRONG_PRICE)
        return agg, counterfactual

    team_rows = []
    for user_rows in rows.values():
        for row in user_rows:
            if row.get("model", "") not in PRICES:
                u = unknown[row.get("model", "?")]
                u[0] += 1
                u[1] += row.get("total_tokens") or 0
    for user in sorted(rows):
        agg, cf = aggregate(rows[user])
        total = {
            k: sum(a[k] for a in agg.values())
            for k in ("requests", "prompt", "cached", "completion", "cost")
        }
        report["users"][user] = {
            "files": file_count[user],
            "rows": len(rows[user]),
            "by_route": {k: dict(v) for k, v in agg.items()},
            "total": total,
            "cache_hit_rate": total["cached"] / total["prompt"]
            if total["prompt"]
            else None,
            "strong_pinned_counterfactual_usd": cf,
        }
        team_rows.extend(rows[user])

    team_agg, team_cf = aggregate(team_rows) if team_rows else ({}, 0.0)
    team_total = {
        k: sum(a[k] for a in team_agg.values())
        for k in ("requests", "prompt", "cached", "completion", "cost")
    }
    report["team"] = {
        "total": team_total,
        "by_route": {k: dict(v) for k, v in team_agg.items()},
        "cache_hit_rate": team_total["cached"] / team_total["prompt"]
        if team_total.get("prompt")
        else None,
        "strong_pinned_counterfactual_usd": team_cf,
        "saved_vs_strong_pinned": 1 - team_total["cost"] / team_cf if team_cf else None,
    }
    report["unknown_models"] = {
        m: {"calls": c, "total_tokens": t} for m, (c, t) in unknown.items()
    }

    if args.json:
        json.dump(report, sys.stdout, indent=2)
        print()
        return

    def table(agg, total, cache_hit):
        print(
            f"{'route/tier':<24}{'requests':>9}{'prompt':>12}{'cached':>12}{'completion':>12}{'cost':>10}"
        )
        for k in sorted(agg, key=lambda k: agg[k]["cost"], reverse=True):
            a = agg[k]
            print(
                f"{k:<24}{a['requests']:>9,}{a['prompt']:>12,}{a['cached']:>12,}{a['completion']:>12,}{a['cost']:>10.4f}"
            )
        print(
            f"{'total':<24}{total['requests']:>9,}{total['prompt']:>12,}{total['cached']:>12,}{total['completion']:>12,}{total['cost']:>10.4f}"
        )
        if cache_hit is not None:
            print(f"cache hit rate: {cache_hit:.1%} (cached / prompt tokens)")

    for user, u in report["users"].items():
        print(f"== {user} ({u['files']} files, {u['rows']:,} rows after dedup) ==")
        table(u["by_route"], u["total"], u["cache_hit_rate"])
        print()

    if len(report["users"]) > 1:
        print("== team total ==")
        table(report["team"]["by_route"], team_total, report["team"]["cache_hit_rate"])
        print()

    saved = report["team"]["saved_vs_strong_pinned"]
    if saved is not None:
        print(
            f"strong-pinned counterfactual: ${team_cf:.4f}   actual: ${team_total['cost']:.4f}"
            f"   saved: {saved:.1%}"
        )
        print(
            "(same token volume at deepseek-v4-pro-0813 rates, classifier calls excluded; approximation)"
        )

    for model, info in report["unknown_models"].items():
        print(
            f"WARNING: no price for {model} — {info['calls']} calls / {info['total_tokens']:,} tokens"
            " excluded from cost",
            file=sys.stderr,
        )


if __name__ == "__main__":
    main()
