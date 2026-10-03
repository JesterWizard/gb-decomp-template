#!/usr/bin/env python3
"""Regenerate src/ from baserom + baserom.sym with mgbdis.

The disassembler guesses where code ends and data begins, and gets it wrong in
both directions. Stage 1 of a decomp is therefore a loop:

    find suspects (analyze.py)  ->  symbols.py block/set  ->  make disasm  ->  make compare

Once the disassembly is accurate enough, freeze it (`redisasm.py --freeze`): src/
becomes the source of truth and is edited by hand (and by symbols.py apply /
carve.py) from then on. After that this tool refuses to overwrite it.

  python3 tools/decomp/redisasm.py [--force] [--no-compare]
  python3 tools/decomp/redisasm.py --freeze
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common  # noqa: E402
from common import ROOT, SRC, FROZEN  # noqa: E402

MGBDIS = ROOT / "tools" / "mgbdis" / "mgbdis.py"
OUT = ROOT / "build" / "disasm"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--force", action="store_true", help="overwrite even with uncommitted changes in src/")
    ap.add_argument("--no-compare", action="store_true")
    ap.add_argument("--freeze", action="store_true", help="mark src/ as hand-maintained and stop")
    args = ap.parse_args()

    if args.freeze:
        FROZEN.parent.mkdir(parents=True, exist_ok=True)
        FROZEN.write_text("src/ is hand-maintained; redisasm.py refuses to overwrite it.\n")
        print("frozen: src/.frozen written")
        return 0
    if FROZEN.exists():
        print("error: src/ is frozen (src/.frozen). Delete it to re-disassemble.", file=sys.stderr)
        return 1
    if not MGBDIS.is_file():
        print("error: tools/mgbdis missing; run `bash build_tools.sh`", file=sys.stderr)
        return 1
    if not args.force and (ROOT / ".git").exists():
        st = subprocess.run(["git", "status", "--porcelain", "--", "src"], cwd=ROOT, capture_output=True, text=True).stdout
        if any(l[:2] != "??" for l in st.splitlines()):
            print("error: src/ has uncommitted edits that a re-disassembly would overwrite; commit or use --force", file=sys.stderr)
            return 1

    rom = common.baserom()
    subprocess.run([sys.executable, str(ROOT / "tools/decomp/symbols.py"), "generate"], check=True)
    if OUT.exists():
        shutil.rmtree(OUT)
    env_path = f"{ROOT / 'tools' / 'rgbds'}"
    subprocess.run(
        [sys.executable, str(MGBDIS), str(rom), "--output-dir", str(OUT), "--overwrite"],
        check=True, cwd=ROOT, env={**__import__("os").environ, "PATH": env_path + ":" + __import__("os").environ["PATH"]},
    )
    SRC.mkdir(exist_ok=True)
    for old in SRC.glob("bank_*.asm"):
        old.unlink()
    for f in OUT.iterdir():
        if f.name in ("Makefile",):
            continue
        shutil.copy2(f, SRC / f.name)
    print(f"src/: {len(list(SRC.glob('bank_*.asm')))} bank file(s) written")
    if args.no_compare:
        return 0
    return common.run_make("compare")


if __name__ == "__main__":
    raise SystemExit(main())
