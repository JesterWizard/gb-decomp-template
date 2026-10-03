#!/usr/bin/env python3
"""Move a range of a bank file into its own module file, byte-identical.

mgbdis writes one SECTION per bank. Real projects (pokered style) keep code in
per-module files. Because every SECTION here has a fixed address, a range can be cut
out and pinned in place without changing a single byte of the ROM:

  carve.py START_LABEL END_LABEL engine/memory.asm [--name "Memory"]
  carve.py START_LABEL --size 0x40 engine/memory.asm

The range is [START, END): END is the first label NOT moved. The new file is
INCLUDEd from src/game.asm; the rest of the bank file continues in a fresh
fixed-address SECTION. `make compare` runs afterwards and the carve is rolled back
if the ROM changed.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common  # noqa: E402
from common import SRC  # noqa: E402


def section_header(name: str, bank: int, addr: int) -> str:
    if addr < 0x4000:
        return f'SECTION "{name}", ROM0[${addr:04X}]'
    return f'SECTION "{name}", ROMX[${addr:04X}], BANK[${bank:X}]'


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("start")
    ap.add_argument("end", nargs="?", help="first label NOT moved (omit with --size)")
    ap.add_argument("dest", help="new file, relative to src/ (e.g. engine/memory.asm)")
    ap.add_argument("--size", type=lambda x: int(x, 0))
    ap.add_argument("--name", help="SECTION name (default: derived from dest)")
    args = ap.parse_args()
    if args.end is not None and Path(args.end).suffix == ".asm" and args.size is None:
        # carve.py START --size N dest  written as: carve.py START dest --size N
        args.dest, args.end = args.end, None

    if common.run_make("all") != 0:
        return 1
    sym = common.parse_sym()
    if args.start not in sym:
        print(f"error: {args.start} not in {common.SYMFILE.name}", file=sys.stderr)
        return 1
    bank, addr = sym[args.start]
    if args.end:
        if args.end not in sym:
            print(f"error: {args.end} not in the .sym", file=sys.stderr)
            return 1
        ebank, eaddr = sym[args.end]
        if ebank != bank or eaddr <= addr:
            print("error: END must be a later label in the same bank", file=sys.stderr)
            return 1
    elif args.size:
        eaddr = addr + args.size
    else:
        print("error: give END_LABEL or --size", file=sys.stderr)
        return 1

    # locate start label and the end boundary in one file
    target = None
    for f in common.asm_files():
        lines = f.read_text().splitlines()
        for i, line in enumerate(lines):
            m = common.LABEL_RE.match(line)
            if m and m.group(1) == args.start:
                target = (f, lines, i)
                break
        if target:
            break
    if not target:
        print(f"error: label {args.start} not found in src/", file=sys.stderr)
        return 1
    f, lines, s = target
    e = None
    for j in range(s + 1, len(lines)):
        if common.SECTION_RE.match(lines[j].strip()):
            print("error: range crosses a SECTION boundary", file=sys.stderr)
            return 1
        m = common.LABEL_RE.match(lines[j])
        if m and m.group(1) in sym and sym[m.group(1)] == (bank, eaddr):
            e = j
            break
    if e is None:
        print(f"error: no label at ${eaddr:04X} in {f.name} after {args.start}; pass an END label or a --size that lands on one", file=sys.stderr)
        return 1

    dest = SRC / args.dest
    if dest.exists():
        print(f"error: {dest} exists", file=sys.stderr)
        return 1
    name = args.name or Path(args.dest).with_suffix("").as_posix().replace("/", " ").title()
    game = SRC / "game.asm"
    backup = {f: f.read_text(), game: game.read_text()}

    # trim blank lines at the cut edges but keep content intact
    body = lines[s:e]
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(f"; {name}\n{section_header(name, bank, addr)}\n\n" + "\n".join(body).rstrip("\n") + "\n")
    cont = section_header(f"{f.stem} ${eaddr:04X}", bank, eaddr)
    new_lines = lines[:s] + [cont, ""] + lines[e:]
    f.write_text("\n".join(new_lines) + "\n")
    gtxt = game.read_text()
    if not gtxt.endswith("\n"):
        gtxt += "\n"
    game.write_text(gtxt + f'INCLUDE "{args.dest}"\n')

    r = common.run_make("compare")
    if r != 0:
        for p, txt in backup.items():
            p.write_text(txt)
        dest.unlink()
        common.run_make("all")
        print("error: ROM changed; carve rolled back", file=sys.stderr)
        return 1
    print(f"carved {args.start}..${eaddr:04X} -> src/{args.dest} (ROM unchanged)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
