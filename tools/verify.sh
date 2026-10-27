#!/usr/bin/env bash
# Stock regression gate for the 32-team ROM loop.
# Usage: ./tools/verify.sh [--with-soak]
set -euo pipefail
cd "$(dirname "$0")/.."

python3 tools/check_build.py build/direct31.nes
.venv/bin/python tools/test_assembler.py
.venv/bin/python tools/test_bracket32.py
.venv/bin/python tools/test_roster32.py
.venv/bin/python tools/build_gameplay32.py build/direct31.nes -o build/gameplay32.nes
.venv/bin/python tools/test_gameplay32.py build/direct31.nes

if [ "${1:-}" = "--with-soak" ]; then
  timeout 300 python3 tools/soak_bracket.py \
    --rom build/direct31.nes --matches 6 --winner score --mode speed --session verify-stock
  timeout 300 python3 tools/soak_bracket.py \
    --rom build/gameplay32.nes --matches 31 --winner score --mode speed \
    --check-stack --session verify-gameplay
fi
