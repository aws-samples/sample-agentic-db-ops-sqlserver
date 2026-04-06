#!/bin/bash
# cleanup.sh - Remove all deployed agents and shared memory
set -e
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$SCRIPT_DIR/../.."
source "$ROOT_DIR/.env"
source "$ROOT_DIR/.venv/bin/activate"

echo "╔══════════════════════════════════════════════════════════════╗"
echo "║     🧹 Autonomous DBOps — Cleanup                            ║"
echo "╚══════════════════════════════════════════════════════════════╝"
echo ""

python3 "$ROOT_DIR/scripts/cleanup_agents.py"
