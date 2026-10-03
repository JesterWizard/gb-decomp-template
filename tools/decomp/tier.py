#!/usr/bin/env python3
"""Lifecycle tiers for every function in analysis/functions.json.

  UNKNOWN     still has the disassembler's auto name (Call_000_0184, ...)
  NAMED       has a symbols.json entry with confidence + evidence
  DOCUMENTED  docs/functions/<name>.md exists and no longer contains TODO

  python3 tools/decomp/tier.py [--json]
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common  # noqa: E402

TIERS = ("UNKNOWN", "NAMED", "DOCUMENTED")
VECTOR_PREFIXES = ("RST_", "Boot")


def collect() -> dict[str, str]:
    funcs = common.load_json(common.ANALYSIS / "functions.json", {})
    if not funcs:
        sys.exit("error: no analysis/functions.json; run `make analyze`")
    named = {s["name"] for s in common.load_json(common.ANALYSIS / "symbols.json", {"symbols": {}})["symbols"].values()}
    out = {}
    for name, f in funcs.items():
        key = f.get("key") or "00:FFFF"
        if common.parse_key(key)[1] < 0x150 and name not in named:
            continue  # hardware vectors / entry point: not part of the naming work
        doc = common.DOCS / "functions" / f"{name}.md"
        if doc.is_file() and "TODO" not in doc.read_text():
            out[name] = "DOCUMENTED"
        elif name in named or name.startswith(VECTOR_PREFIXES) or name.endswith("Interrupt"):
            out[name] = "NAMED"
        else:
            out[name] = "UNKNOWN"
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()
    tiers = collect()
    counts = {t: sum(1 for v in tiers.values() if v == t) for t in TIERS}
    if args.json:
        print(json.dumps({"counts": counts, "functions": tiers}, indent=2))
    else:
        total = len(tiers) or 1
        print("  ".join(f"{t} {counts[t]}" for t in TIERS) + f"   ({100 * (total - counts['UNKNOWN']) // total}% named)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
