#!/usr/bin/env bash
# PreToolUse hook — runs before Claude executes a Bash command, and can block it.
#
# Two guards, both chosen because the condition is mechanically checkable and the
# answer is always no. Judgment calls belong in CLAUDE.md, not here.
#
#   1. No commits directly to main.
#   2. No force-pushes. This repo is public and has merged PRs, so rewriting
#      history invalidates commit hashes other people may already have.
#
# Errs toward over-blocking: a false positive costs one clarifying message, a
# false negative costs a rewritten public history.

set -uo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"

payload="$(cat)"

cmd="$(printf '%s' "$payload" | python3 -c '
import json, sys
try:
    print(json.load(sys.stdin).get("tool_input", {}).get("command", ""))
except Exception:
    print("")
' 2>/dev/null)"

[ -n "$cmd" ] || exit 0

cd "$PROJECT_DIR" || exit 0

# --- Guard 1: no commit while HEAD is main ---
if printf '%s' "$cmd" | grep -qE '\bgit\b.*\bcommit\b'; then
    branch="$(git rev-parse --abbrev-ref HEAD 2>/dev/null || echo "")"
    if [ "$branch" = "main" ]; then
        {
            echo "BLOCKED: refusing to commit directly to main."
            echo
            echo "CLAUDE.md requires one concern per branch. Create one first:"
            echo "  git checkout -b fix/<what>     # behavior change"
            echo "  git checkout -b feat/<what>    # new capability"
            echo "  git checkout -b chore/<what>   # tooling"
        } >&2
        exit 2
    fi
fi

# --- Guard 2: no force-push ---
if printf '%s' "$cmd" | grep -qE '\bgit\b.*\bpush\b' \
   && printf '%s' "$cmd" | grep -qE '(--force([^-]|$)|--force-with-lease|[[:space:]]-f([[:space:]]|$))'; then
    {
        echo "BLOCKED: refusing to force-push."
        echo
        echo "This repo is public and has merged PRs; rewriting history changes"
        echo "commit hashes others may already have. If a history rewrite is"
        echo "genuinely intended, Pranav should run it manually."
    } >&2
    exit 2
fi

exit 0
