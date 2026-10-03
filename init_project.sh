#!/usr/bin/env bash
# One-shot day-zero setup. See docs/new-game-checklist.md.
set -euo pipefail
cd "$(dirname "$0")"
exec python3 tools/decomp/init_project.py "$@"
