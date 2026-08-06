#!/usr/bin/env bash
# PostToolUse hook — runs after Claude edits a file.
#
# If the edited file was Python, lint and test the project. Exiting 2 sends
# stderr back to Claude as a blocking error, so a regression surfaces in the
# same turn it was introduced rather than several edits later.
#
# Deliberately uses the pinned .venv tools, not whatever is on PATH: CI pins
# ruff 0.15.9 and an unpinned linter is how this project broke CI once already.

set -uo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"

payload="$(cat)"

file="$(printf '%s' "$payload" | python3 -c '
import json, sys
try:
    print(json.load(sys.stdin).get("tool_input", {}).get("file_path", ""))
except Exception:
    print("")
' 2>/dev/null)"

# Only Python edits are worth a full lint+test cycle.
case "$file" in
    *.py) ;;
    *) exit 0 ;;
esac

cd "$PROJECT_DIR" || exit 0

# No venv means a fresh clone; stay quiet rather than failing confusingly.
[ -x .venv/bin/ruff ] || exit 0
[ -x .venv/bin/python ] || exit 0

if ! out="$(.venv/bin/ruff check . 2>&1)"; then
    {
        echo "BLOCKED: ruff failed after editing $file"
        echo
        echo "$out"
    } >&2
    exit 2
fi

if ! out="$(.venv/bin/python -m pytest tests/ -q 2>&1)"; then
    {
        echo "BLOCKED: pytest failed after editing $file"
        echo
        echo "$out"
        echo
        echo "Fix this before moving on. Do not report the work as done."
    } >&2
    exit 2
fi

exit 0
