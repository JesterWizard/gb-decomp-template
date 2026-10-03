#!/usr/bin/env python3
"""Build the analysis DB from src/*.asm and the linker .sym.

  python3 tools/decomp/analyze.py [--check]

Writes analysis/:
  functions.json  entry label -> bank, addr, size, kind, callers, callees, tail jumps,
                  ram/hram/sram refs, bank-switch flag, indirect jumps
  data.json       labelled data blocks (tables, strings) with size and referrers
  ram.json        every WRAM/HRAM/SRAM/VRAM address touched: readers, writers, symbol
  banks.json      per-bank bytes of code/data, entries, named share
  suspects.json   probable data decoded as code (stage-1 work list)

A "function" is a label that is a call/rst target, an interrupt/entry vector, or a
symbols.json entry of kind `function`. Other labels are internal to the function
that precedes them. Run `make` first: addresses come from the linker's .sym.
`--check` additionally verifies the instruction-length model against the .sym
(it must agree on every label; any mismatch means data was decoded as code
or the model has a bug).
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common  # noqa: E402
from common import ANALYSIS  # noqa: E402

VECTOR_MAX = 0x150
BANKSWITCH_RE = re.compile(r"^\[\s*\$([0-3][0-9A-Fa-f]{3})\s*\]$")
ADDR_RE = re.compile(r"\[\s*\$([0-9A-Fa-f]{4})\s*\]")
LDH_RE = re.compile(r"\[\s*\$?([0-9A-Fa-f]{2,4})\s*\]")
REGION = [(0x8000, 0x9FFF, "vram"), (0xA000, 0xBFFF, "sram"), (0xC000, 0xDFFF, "wram"),
          (0xE000, 0xFDFF, "echo"), (0xFE00, 0xFE9F, "oam"), (0xFF00, 0xFF7F, "io"), (0xFF80, 0xFFFE, "hram")]


def region(addr: int) -> str | None:
    for lo, hi, name in REGION:
        if lo <= addr <= hi:
            return name
    return None


def ram_names() -> dict[int, str]:
    d = common.load_json(ANALYSIS / "symbols.json", {"ram": {}})
    return {int(k, 16): v["name"] for k, v in d.get("ram", {}).items()}


class Label:
    def __init__(self, name, exported, path, line):
        self.name, self.exported, self.path, self.line = name, exported, path, line
        self.items: list[tuple[int, str, str]] = []  # (lineno, mnemonic, operands)
        self.addr: int | None = None
        self.bank: int | None = None


def parse_files(sym: dict[str, tuple[int, int]]) -> list[Label]:
    labels: list[Label] = []
    for f in common.asm_files():
        cur: Label | None = None
        for i, line in enumerate(f.read_text().splitlines(), 1):
            if common.SECTION_RE.match(line.strip()):
                cur = None
                continue
            m = common.LABEL_RE.match(line)
            if m:
                cur = Label(m.group(1), m.group(2) == "::", f, i)
                if cur.name in sym:
                    cur.bank, cur.addr = sym[cur.name]
                else:
                    k = common.auto_key(cur.name)
                    if k:
                        cur.bank, cur.addr = common.parse_key(k)
                labels.append(cur)
                continue
            ins = common.split_instr(line)
            if ins and cur is not None:
                cur.items.append((i, ins[0], ins[1]))
    return labels


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--check", action="store_true")
    args = ap.parse_args()

    sym = common.parse_sym()
    if not sym:
        print("error: no .sym file; run `make` first", file=sys.stderr)
        return 1
    labels = parse_files(sym)
    by_name = {l.name: l for l in labels}
    symbols = common.load_json(ANALYSIS / "symbols.json", {"symbols": {}})["symbols"]
    named_funcs = {s["name"] for s in symbols.values() if s["kind"] == "function"}
    rnames = ram_names()

    # --- entries ---------------------------------------------------------
    call_targets: set[str] = set()
    for l in labels:
        for _ln, mn, ops in l.items:
            if mn == "call":
                call_targets.add(ops.split(",")[-1].strip())
            elif mn == "rst":
                addr = common._num(ops)
                for n, (b, a) in sym.items():
                    if b == 0 and a == addr:
                        call_targets.add(n)
    entries = [l for l in labels if l.name in call_targets or l.name in named_funcs
               or (l.addr is not None and l.addr < VECTOR_MAX and not l.name.startswith("Header"))]
    entry_names = {l.name for l in entries}

    # --- instruction-length model check -----------------------------------
    mismatches = 0
    suspects = []
    for idx, l in enumerate(labels):
        if l.addr is None:
            continue
        pc = l.addr
        dead_start = None
        dead_real = False
        terminated = False
        for ln, mn, ops in l.items:
            sz = common.instr_size(mn, ops)
            if terminated and mn not in common.DATA_DIRECTIVES and dead_start is None:
                dead_start = (ln, pc)
            if dead_start is not None and not (mn == "nop" or (mn == "rst" and ops.strip().lower() == "$38")):
                dead_real = True  # more than 0x00 / 0xFF padding
            if sz is None:
                break
            pc += sz
            terminated = common.is_terminator(mn, ops)
        else:
            nxt = labels[idx + 1] if idx + 1 < len(labels) else None
            if nxt and nxt.addr is not None and nxt.path == l.path and pc != nxt.addr:
                mismatches += 1
                if args.check:
                    print(f"length mismatch: {l.name} model ends ${pc:04X}, next label {nxt.name} at ${nxt.addr:04X}", file=sys.stderr)
        if dead_start and dead_real:
            ln, addr = dead_start
            end = pc
            suspects.append({"after": l.name, "key": common.key(l.bank or 0, addr), "line": ln, "file": str(l.path.relative_to(common.ROOT)),
                             "approx_size": end - addr,
                             "reason": "code after an unconditional jump/ret with no label (unreachable unless entered by an unlabelled indirect jump) - probably data"})
    if args.check:
        print(f"check: {mismatches} label(s) disagree with the instruction-length model")

    # --- functions ---------------------------------------------------------
    owner: dict[str, str] = {}
    cur_entry = None
    for l in labels:
        if l.name in entry_names:
            cur_entry = l.name
        if cur_entry:
            owner[l.name] = cur_entry
    functions: dict[str, dict] = {}
    ram: dict[int, dict] = {}
    datas: dict[str, dict] = {}
    for l in labels:
        if l.name in entry_names:
            functions[l.name] = {"name": l.name, "key": common.key(l.bank, l.addr) if l.addr is not None else None,
                                 "file": str(l.path.relative_to(common.ROOT)), "line": l.line, "size": None,
                                 "callers": [], "callees": [], "tailjumps": [], "reads": [], "writes": [],
                                 "bankswitch": False, "indirect": False, "labels": []}
    for l in labels:
        fn = owner.get(l.name)
        if not fn:
            continue
        f = functions[fn]
        if l.name != fn:
            f["labels"].append(l.name)
        for _ln, mn, ops in l.items:
            args_ = common._split_commas(ops)
            if mn == "call" or mn == "rst":
                tgt = args_[-1]
                if mn == "rst":
                    v = common._num(tgt)
                    tgt = next((n for n, (b, a) in sym.items() if b == 0 and a == v), tgt)
                if tgt in functions and tgt not in f["callees"]:
                    f["callees"].append(tgt)
                    functions[tgt]["callers"].append(fn) if fn not in functions[tgt]["callers"] else None
                elif tgt.lower() == "hl":
                    f["indirect"] = True
            elif mn in ("jp", "jr"):
                tgt = args_[-1]
                if tgt.lower() == "hl":
                    f["indirect"] = True
                elif tgt in entry_names and tgt != fn and tgt not in f["tailjumps"]:
                    f["tailjumps"].append(tgt)
            if mn == "ld" and len(args_) == 2:
                for side, dst in ((args_[0], True), (args_[1], False)):
                    mm = ADDR_RE.search(side)
                    if not mm:
                        continue
                    addr = int(mm.group(1), 16)
                    if dst and addr <= 0x7FFF and BANKSWITCH_RE.match(side.strip()):
                        f["bankswitch"] = True
                        continue
                    if region(addr):
                        r = ram.setdefault(addr, {"readers": set(), "writers": set()})
                        r["writers" if dst else "readers"].add(fn)
                        lst = f["writes" if dst else "reads"]
                        k2 = f"{addr:04X}"
                        if k2 not in lst:
                            lst.append(k2)
            elif mn == "ldh" and len(args_) == 2:
                for side, dst in ((args_[0], True), (args_[1], False)):
                    if "[" in side and "[c]" not in side.lower():
                        v = common._num(side.strip("[] "))
                        if v is None:
                            continue
                        addr = 0xFF00 + v if v < 0x100 else v
                        if region(addr) in ("hram", "io"):
                            r = ram.setdefault(addr, {"readers": set(), "writers": set()})
                            r["writers" if dst else "readers"].add(fn)
                            lst = f["writes" if dst else "reads"]
                            k2 = f"{addr:04X}"
                            if k2 not in lst:
                                lst.append(k2)
    # sizes: distance to the next entry (else the next label of any kind) in the same bank
    all_addrs = sorted(sym.values())
    for name, f in functions.items():
        if not f["key"]:
            continue
        b, a = common.parse_key(f["key"])
        entry_addrs = sorted(sym[n][1] for n in entry_names if n in sym and sym[n][0] == b and sym[n][1] > a)
        any_addrs = [ad for (bb, ad) in all_addrs if bb == b and ad > a]
        end = entry_addrs[0] if entry_addrs else (min(any_addrs) if any_addrs else None)
        f["size"] = (end - a) if end else None
    # data blocks: labels with only data directives
    for l in labels:
        if l.name in entry_names or not l.items:
            continue
        if all(mn in common.DATA_DIRECTIVES for _ln, mn, _o in l.items) and l.addr is not None:
            datas[l.name] = {"name": l.name, "key": common.key(l.bank, l.addr), "file": str(l.path.relative_to(common.ROOT)), "line": l.line,
                             "bytes": sum(common.instr_size(mn, o) or 0 for _ln, mn, o in l.items)}
    # which functions mention data labels
    for l in labels:
        fn = owner.get(l.name)
        for _ln, mn, ops in l.items:
            for d in datas:
                if d in ops and fn:
                    datas[d].setdefault("referrers", [])
                    if fn not in datas[d]["referrers"]:
                        datas[d]["referrers"].append(fn)

    ram_out = {f"{a:04X}": {"region": region(a), "name": rnames.get(a), "readers": sorted(v["readers"]), "writers": sorted(v["writers"])}
               for a, v in sorted(ram.items())}
    # banks
    banks: dict[str, dict] = {}
    for l in labels:
        if l.bank is None:
            continue
        b = banks.setdefault(f"{l.bank:02X}", {"code_bytes": 0, "data_bytes": 0, "padding_bytes": 0, "functions": 0, "named_functions": 0})
        only_data = bool(l.items) and all(mn in common.DATA_DIRECTIVES for _ln, mn, _o in l.items)
        terminated = False
        for _ln, mn, ops in l.items:
            sz = common.instr_size(mn, ops) or 0
            if only_data:
                b["data_bytes"] += sz
            elif terminated and (mn == "nop" or (mn == "rst" and ops.strip().lower() == "$38")):
                b["padding_bytes"] += sz
            else:
                b["code_bytes"] += sz
            if mn not in common.DATA_DIRECTIVES:
                terminated = common.is_terminator(mn, ops) or (terminated and mn in ("nop", "rst"))
    for f in functions.values():
        if f["key"]:
            b = banks.setdefault(f["key"][:2], {"code_bytes": 0, "data_bytes": 0, "padding_bytes": 0, "functions": 0, "named_functions": 0})
            b["functions"] += 1
            if not common.AUTO_RE.match(f["name"]) and not f["name"].startswith(("RST_", "Boot")) and not f["name"].endswith("Interrupt"):
                b["named_functions"] += 1

    ANALYSIS.mkdir(exist_ok=True)
    common.save_json(ANALYSIS / "functions.json", functions)
    common.save_json(ANALYSIS / "data.json", datas)
    common.save_json(ANALYSIS / "ram.json", ram_out)
    common.save_json(ANALYSIS / "banks.json", banks)
    common.save_json(ANALYSIS / "suspects.json", suspects)
    print(f"analyze: {len(functions)} functions, {len(datas)} data blocks, {len(ram_out)} RAM addresses, "
          f"{len(suspects)} suspect data-as-code region(s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
