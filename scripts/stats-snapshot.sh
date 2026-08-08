#!/usr/bin/env bash
# Routing-stats snapshot for the periodic cost-reduction review.
#
# Collects two files from the running switchyard-opencode container into
# ./stats-out/ and prints a per-route summary:
#   - stats-<user>-<stamp>.json    aggregate GET /v1/routing/stats
#   - routing-<user>-<stamp>.jsonl per-request log (tier, model, tokens;
#                                  no prompt bodies)
#
# Note: /v1/routing/stats counters reset on container restart; the JSONL
# lives in the switchyard-logs named volume and survives restarts and
# `up -d --force-recreate`, so the JSONL is the durable record.
set -euo pipefail

cd "$(dirname "$0")/.."
OUT_DIR="stats-out"
STAMP="$(date +%Y%m%d-%H%M%S)"
TAG="${USER:-unknown}"
mkdir -p "$OUT_DIR"

STATS_FILE="$OUT_DIR/stats-$TAG-$STAMP.json"
LOG_FILE="$OUT_DIR/routing-$TAG-$STAMP.jsonl"

curl -sf http://127.0.0.1:4100/v1/routing/stats > "$STATS_FILE"
docker cp -q switchyard-opencode:/app/logs/routing.jsonl "$LOG_FILE"

python3 - "$LOG_FILE" <<'PY'
import json
import sys
from collections import Counter

reqs, toks = Counter(), Counter()
for line in open(sys.argv[1]):
    r = json.loads(line)
    # Auto-routed lines carry tier=strong/weak; tier-pinned routes
    # (strong-only / weak-only) log an empty tier, so label by model.
    key = r.get("tier") or "pinned:" + r["model"].rsplit("/", 1)[-1]
    reqs[key] += 1
    toks[key] += r.get("total_tokens", 0)

total = sum(reqs.values())
if not total:
    print("routing.jsonl is empty — no requests logged yet")
    sys.exit(0)
print(f"{'route':<28}{'requests':>9}{'req%':>8}{'total_tokens':>14}")
for k in sorted(reqs, key=reqs.get, reverse=True):
    print(f"{k:<28}{reqs[k]:>9}{100 * reqs[k] / total:>7.1f}%{toks[k]:>14,}")
PY

echo
echo "Saved: $STATS_FILE"
echo "       $LOG_FILE"
echo "Next : submit both files as designated by your project (see README, \"Periodic review\")"
