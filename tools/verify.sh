#!/usr/bin/env bash
# Stock regression gate for the 32-team ROM loop.
# Usage: ./tools/verify.sh [--with-soak]
set -euo pipefail
cd "$(dirname "$0")/.."

python3 tools/check_build.py build/direct31.nes
.venv/bin/python tools/test_bracket32.py
.venv/bin/python tools/test_roster32.py

if [ "${1:-}" = "--with-soak" ]; then
  timeout 300 python3 tools/soak_bracket.py \
    --rom build/direct31.nes --matches 6 --winner score --mode speed
fi
