#!/usr/bin/env bash
# Thin shell entry point for the tracked clean-room integration harness.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
exec python3 "$SCRIPT_DIR/clean_test.py" "$@"
