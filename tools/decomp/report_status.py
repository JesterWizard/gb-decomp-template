#!/usr/bin/env python3
"""One-screen progress report (refreshes the analysis DB first).

  python3 tools/decomp/report_status.py
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common  # noqa: E402
import tier  # noqa: E402


def main() -> int:
    if not common.ROM.is_file() or not common.SYMFILE.is_file():
        common.run_make("all")
    subprocess.run([sys.executable, str(Path(__file__).with_name("analyze.py"))], check=True, stdout=subprocess.DEVNULL)
    funcs = common.load_json(common.ANALYSIS / "functions.json", {})
    banks = common.load_json(common.ANALYSIS / "banks.json", {})
    susp = common.load_json(common.ANALYSIS / "suspects.json", [])
    sym = common.load_json(common.ANALYSIS / "symbols.json", {"symbols": {}, "ram": {}})
    tiers = tier.collect()
    counts = {t: sum(1 for v in tiers.values() if v == t) for t in tier.TIERS}
    code = sum(b["code_bytes"] for b in banks.values())
    data = sum(b["data_bytes"] for b in banks.values())
    pad = sum(b.get("padding_bytes", 0) for b in banks.values())
    print(f"=== {common.GAME_NAME} decomp ===")
    print(f"  ROM: {common.ROM.name}   sha1 check: run `make compare`")
    print(f"  Functions: {len(funcs)}   " + "  ".join(f"{t} {counts[t]}" for t in tier.TIERS))
    print(f"  Bytes: code {code}  data {data}  padding {pad}")
    print(f"  RAM symbols: {len(sym['ram'])}   named code symbols: {len(sym['symbols'])}")
    print(f"  Suspect data-as-code regions: {len(susp)}"
          + ("  <- fix these first (symbols.py block data ...; make disasm)" if susp and not common.FROZEN.exists() else ""))
    print(f"  src/ frozen: {'yes' if common.FROZEN.exists() else 'no (mgbdis stage)'}")
    print()
    print("  Bank   code   data    pad funcs named")
    for b in sorted(banks):
        d = banks[b]
        print(f"  {b:>4} {d['code_bytes']:>6} {d['data_bytes']:>6} {d.get('padding_bytes', 0):>6} {d['functions']:>5} {d['named_functions']:>5}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
