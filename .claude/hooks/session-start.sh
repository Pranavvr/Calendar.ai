#!/usr/bin/env bash
# SessionStart hook — stdout is added to Claude's context at session start.
#
# Exists because this project has repeatedly bitten on stale assumptions: a
# branch sitting 8 commits ahead of main unnoticed, and infrastructure assumed
# live when it was torn down. Both are cheap to just state up front.

set -uo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$PROJECT_DIR" || exit 0

echo "=== cal.ai session context ==="

branch="$(git rev-parse --abbrev-ref HEAD 2>/dev/null || echo "unknown")"
echo "branch: $branch"

if [ "$branch" != "main" ] && [ "$branch" != "unknown" ]; then
    if counts="$(git rev-list --left-right --count main..."$branch" 2>/dev/null)"; then
        behind="$(printf '%s' "$counts" | awk '{print $1}')"
        ahead="$(printf '%s' "$counts" | awk '{print $2}')"
        echo "vs main: $ahead ahead, $behind behind"
    fi
fi

dirty="$(git status --porcelain 2>/dev/null | wc -l | tr -d ' ')"
echo "uncommitted changes: $dirty"

# Terraform state is the fastest way to know whether AWS is costing money.
state="terraform/terraform.tfstate"
if [ -f "$state" ]; then
    n="$(python3 -c '
import json, sys
try:
    print(len(json.load(open("'"$state"'")).get("resources", [])))
except Exception:
    print("unknown")
' 2>/dev/null)"
    if [ "$n" = "0" ]; then
        echo "aws: torn down (0 resources in local state) — nothing is billing"
    else
        echo "aws: $n resources in local state — MAY BE BILLING"
    fi
fi

echo "==============================="
