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

.venv/bin/python tools/test_password32.py build/results32.nes
.venv/bin/python tools/build_passwordrom32.py build/control32.nes -o build/password32.nes
.venv/bin/python tools/test_passwordrom32.py build/control32.nes --candidate build/password32.nes

.venv/bin/python tools/build_teamnames32.py build/password32.nes -o build/teamnames32.nes
.venv/bin/python tools/test_teamnames32.py build/password32.nes --candidate build/teamnames32.nes

.venv/bin/python tools/build_visualtables32.py build/teamnames32.nes -o build/visualtables32.nes
.venv/bin/python tools/test_visualtables32.py build/teamnames32.nes --candidate build/visualtables32.nes

.venv/bin/python tools/build_menuart32.py build/visualtables32.nes -o build/menuart32.nes
.venv/bin/python tools/test_menuart32.py build/visualtables32.nes --candidate build/menuart32.nes

.venv/bin/python tools/build_draw32.py build/menuart32.nes -o build/draw32.nes
.venv/bin/python tools/test_draw32.py build/menuart32.nes --candidate build/draw32.nes
.venv/bin/python tools/build_pick32.py build/draw32.nes -o build/pick32.nes
.venv/bin/python tools/test_pick32.py build/draw32.nes --candidate build/pick32.nes
.venv/bin/python tools/title32_convert.py --rom build/pick32.nes --check
.venv/bin/python tools/build_title32.py build/pick32.nes -o build/title32.nes
.venv/bin/python tools/test_title32.py build/pick32.nes --candidate build/title32.nes

.venv/bin/python tools/modeart32_convert.py --rom build/title32.nes --check
.venv/bin/python tools/build_modeart32.py build/title32.nes -o build/modeart32.nes
.venv/bin/python tools/test_modeart32.py build/title32.nes --candidate build/modeart32.nes

.venv/bin/python tools/scoreart32_convert.py --rom build/modeart32.nes --check
.venv/bin/python tools/build_scoreart32.py build/modeart32.nes -o build/scoreart32.nes
.venv/bin/python tools/test_scoreart32.py build/modeart32.nes --candidate build/scoreart32.nes
.venv/bin/python tools/test_scoreart32_probe.py

.venv/bin/python -B tools/stockart32_convert.py --rom build/scoreart32.nes --font-rom build/modeart32.nes --pxl build/vendor/claude-pxl
.venv/bin/python -B tools/build_stockart32.py build/scoreart32.nes -o build/stockart32.nes
.venv/bin/python -B tools/test_stockart32.py --pxl build/vendor/claude-pxl --candidate build/stockart32.nes
.venv/bin/python -B tools/test_stockart32_probe.py

.venv/bin/python -B tools/analysisart32_convert.py --rom build/stockart32.nes --pxl build/vendor/claude-pxl
.venv/bin/python -B tools/build_analysisart32.py build/stockart32.nes -o build/analysisart32.nes
.venv/bin/python -B tools/test_analysisart32.py build/stockart32.nes --candidate build/analysisart32.nes --pxl build/vendor/claude-pxl
.venv/bin/python -B tools/test_analysisart32_probe.py
.venv/bin/python -B tools/test_soak_lineup.py

if [ "${1:-}" = "--with-soak" ]; then
  timeout 300 python3 tools/soak_bracket.py \
    --rom build/direct31.nes --matches 6 --winner score --mode speed --session verify-stock
  timeout 300 python3 tools/soak_bracket.py \
    --rom build/analysisart32.nes --team 31 --matches 31 --winner live-score --require-complete --mode speed \
    --check-stack --session verify-gameplay
fi
