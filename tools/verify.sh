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
.venv/bin/python tools/build_cpu32.py build/gameplay32.nes -o build/cpu32.nes
.venv/bin/python tools/test_cpu32.py build/gameplay32.nes --candidate build/cpu32.nes
.venv/bin/python tools/build_teamtables32.py build/cpu32.nes -o build/teamtables32.nes
.venv/bin/python tools/test_teamtables32.py build/cpu32.nes --candidate build/teamtables32.nes

.venv/bin/python tools/build_roles32.py build/teamtables32.nes -o build/roles32.nes
.venv/bin/python tools/test_roles32.py build/teamtables32.nes --candidate build/roles32.nes

.venv/bin/python tools/build_results32.py build/roles32.nes -o build/results32.nes
.venv/bin/python tools/test_results32.py build/roles32.nes --candidate build/results32.nes

.venv/bin/python tools/build_control32.py build/results32.nes -o build/control32.nes
.venv/bin/python tools/test_control32.py build/results32.nes --candidate build/control32.nes

if [ "${1:-}" = "--with-soak" ]; then
  timeout 300 python3 tools/soak_bracket.py \
    --rom build/direct31.nes --matches 6 --winner score --mode speed --session verify-stock
  timeout 300 python3 tools/soak_bracket.py \
    --rom build/control32.nes --team 31 --matches 31 --winner live-score --require-complete --mode speed \
    --check-stack --session verify-gameplay
fi
