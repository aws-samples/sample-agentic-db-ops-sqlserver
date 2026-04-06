#!/bin/bash
# Thin wrapper — the actual deploy script is at the repo root.
# Usage: cd to repo root and run ./deploy.sh
set -e
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$SCRIPT_DIR/../.."

echo "Delegating to repo root deploy script..."
exec "$ROOT_DIR/deploy.sh"
