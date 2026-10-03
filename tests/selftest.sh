#!/usr/bin/env bash
# End-to-end smoke test on a synthetic ROM: init -> compare -> analyze -> name -> block
# -> redisasm -> carve. Runs in a temp copy so the working tree is untouched.
# Needs tools/rgbds + tools/mgbdis (bash build_tools.sh).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
cd "$ROOT"
rsync -a --exclude .git --exclude build ./ "$TMP/"
cd "$TMP"
export PATH="$TMP/tools/rgbds:$PATH"
command -v rgbasm >/dev/null || { echo "selftest: rgbasm missing (bash build_tools.sh)"; exit 1; }

echo "== build fixture ROM"
( cd tests/fixture && rgbasm -o /tmp/fixture.$$.o fixture.asm && rgblink -o "$TMP/baserom.gbc" /tmp/fixture.$$.o \
  && rgbfix -v -c -m MBC1 -t FIXTURE -p 0xFF "$TMP/baserom.gbc" && rm -f /tmp/fixture.$$.o )

echo "== init + compare"
./init_project.sh --name fixture --game-name Fixture
make compare | tail -1

echo "== analyze"
python3 tools/decomp/analyze.py --check
python3 tools/decomp/analyze.py
python3 - <<'PY'
import json
s = json.load(open("analysis/suspects.json"))
assert s, "expected the string/pointer table after reti to be flagged"
print("suspects:", [(x["key"], x["approx_size"]) for x in s])
f = json.load(open("analysis/functions.json"))
assert "Call_000_0184" in f and f["Call_000_0184"]["callers"], f.keys()
PY

echo "== blocks: mark the pointer table + string as data, re-disassemble"
python3 tools/decomp/symbols.py block data 00:01a1 12
python3 tools/decomp/symbols.py generate
python3 tools/decomp/redisasm.py --force
python3 tools/decomp/analyze.py
python3 - <<'PY'
import json
assert not json.load(open("analysis/suspects.json")), "suspect should be gone after .data block"
PY

echo "== names + RAM, apply"
python3 tools/decomp/symbols.py set 00:0184 ClearMem --confidence high --evidence "zeroes BC bytes starting at HL"
python3 tools/decomp/symbols.py ram C000 wFrameCounter --evidence "inc'd every frame in the VBlank handler"
python3 tools/decomp/symbols.py ram FF80 hScratch --evidence "written by AddScore"
python3 tools/decomp/symbols.py apply
grep -q "ClearMem" src/bank_000.asm && grep -q "wFrameCounter" src/bank_000.asm && grep -q "hScratch" src/bank_000.asm
make compare | tail -1

echo "== redisasm picks the names up natively"
python3 tools/decomp/redisasm.py --force --no-compare
grep -q "^ClearMem" src/bank_000.asm
python3 tools/decomp/symbols.py apply
make compare | tail -1

echo "== docs + tier + status"
make analyze >/dev/null
python3 tools/decomp/document.py
python3 tools/decomp/tier.py
python3 tools/decomp/report_status.py | head -8

echo "== freeze + carve"
python3 tools/decomp/redisasm.py --freeze
python3 tools/decomp/carve.py ClearMem Call_000_018c engine/memory.asm
make compare | tail -1
test -f src/engine/memory.asm

echo "selftest OK"
