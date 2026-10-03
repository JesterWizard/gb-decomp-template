#!/usr/bin/env python3
"""Day-zero setup for a fresh GB/GBC decomp from baserom.gb / baserom.gbc.

  python3 tools/decomp/init_project.py [--name my_game] [--game-name "My Game"]

Reads the cartridge header, writes project.mk and rom.sha1, disassembles the ROM
with mgbdis into src/, and leaves `make compare` green. Re-running overwrites
project.mk, rom.sha1 and (unless src/.frozen exists) src/.
"""

from __future__ import annotations

import argparse
import hashlib
import re
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common  # noqa: E402

MAPPERS = {
    0x00: "ROM ONLY", 0x01: "MBC1", 0x02: "MBC1+RAM", 0x03: "MBC1+RAM+BATTERY",
    0x05: "MBC2", 0x06: "MBC2+BATTERY", 0x08: "ROM+RAM", 0x09: "ROM+RAM+BATTERY",
    0x0B: "MMM01", 0x0C: "MMM01+RAM", 0x0D: "MMM01+RAM+BATTERY",
    0x0F: "MBC3+TIMER+BATTERY", 0x10: "MBC3+TIMER+RAM+BATTERY", 0x11: "MBC3",
    0x12: "MBC3+RAM", 0x13: "MBC3+RAM+BATTERY", 0x19: "MBC5", 0x1A: "MBC5+RAM",
    0x1B: "MBC5+RAM+BATTERY", 0x1C: "MBC5+RUMBLE", 0x1D: "MBC5+RUMBLE+RAM",
    0x1E: "MBC5+RUMBLE+RAM+BATTERY", 0x20: "MBC6", 0x22: "MBC7+SENSOR+RUMBLE+RAM+BATTERY",
    0xFC: "POCKET CAMERA", 0xFD: "BANDAI TAMA5", 0xFE: "HuC3", 0xFF: "HuC1+RAM+BATTERY",
}
RAM_SIZES = {0: "none", 1: "2 KiB", 2: "8 KiB", 3: "32 KiB (4x8)", 4: "128 KiB (16x8)", 5: "64 KiB (8x8)"}


def slug(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", s.lower()).strip("_") or "game"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--name", help="output file stem (default: slug of the header title)")
    ap.add_argument("--game-name", help="display name for reports")
    ap.add_argument("--skip-make", action="store_true", help="do not run `make compare`")
    args = ap.parse_args()

    rom = common.baserom()
    data = rom.read_bytes()
    if len(data) < 0x150:
        print("error: file too small for a Game Boy header", file=sys.stderr)
        return 1
    logo_ok = data[0x104:0x108] == bytes([0xCE, 0xED, 0x66, 0x66])
    chk = 0
    for b in data[0x134:0x14D]:
        chk = (chk - b - 1) & 0xFF
    cgb = data[0x143]
    title = data[0x134:0x143 if cgb in (0x80, 0xC0) else 0x144].split(b"\0")[0].decode("ascii", "replace").strip()
    ctype = data[0x147]
    banks = 2 << data[0x148] if data[0x148] <= 8 else None
    ext = "gbc" if cgb in (0x80, 0xC0) else "gb"
    name = args.name or slug(title)
    game = args.game_name or title.title() or name

    print(f"header: title={title!r} cgb={cgb:#04x} ({ext}) sgb={data[0x146]:#04x}")
    print(f"        mapper={MAPPERS.get(ctype, f'unknown {ctype:#04x}')} romsize={len(data):#x} "
          f"banks={banks} ram={RAM_SIZES.get(data[0x149], data[0x149])} dest={data[0x14A]:#04x} rev={data[0x14C]}")
    if not logo_ok:
        print("warning: Nintendo logo bytes do not match; is this a clean dump?", file=sys.stderr)
    if chk != data[0x14D]:
        print(f"warning: header checksum {data[0x14D]:#04x} != computed {chk:#04x}; "
              "set FIX_FLAGS := (empty) in project.mk if this is deliberate", file=sys.stderr)
    if banks and len(data) != banks * 0x4000:
        print(f"warning: file size {len(data):#x} != header bank count {banks} x 0x4000", file=sys.stderr)

    project = (common.ROOT / "project.mk").read_text()
    for k, v in (("FILE_NAME", name), ("GAME_NAME", game), ("EXT", ext)):
        line = f"{k:<10} := {v}"
        project = re.sub(rf"^{k}\s*:=.*$", lambda _m, line=line: line, project, flags=re.M)
    (common.ROOT / "project.mk").write_text(project)
    sha = hashlib.sha1(data).hexdigest()
    (common.ROOT / "rom.sha1").write_text(f"{sha}  {name}.{ext}\n")
    print(f"init: {name}.{ext} sha1={sha}")

    cmd = [sys.executable, "tools/decomp/symbols.py", "generate"]
    subprocess.run(cmd, cwd=common.ROOT, check=True)
    r = subprocess.run([sys.executable, "tools/decomp/redisasm.py", "--no-compare"], cwd=common.ROOT)
    if r.returncode:
        return r.returncode
    if args.skip_make:
        return 0
    return common.run_make("compare")


if __name__ == "__main__":
    raise SystemExit(main())
