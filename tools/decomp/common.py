"""Shared helpers: project settings, asm parsing, LR35902 instruction sizes."""

from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src"
ANALYSIS = ROOT / "analysis"
DOCS = ROOT / "docs"
FROZEN = SRC / ".frozen"

_LINE = re.compile(r"^([A-Z_]+)\s*:?=\s*(.*?)\s*$")


def load_project() -> dict[str, str]:
    out: dict[str, str] = {}
    for line in (ROOT / "project.mk").read_text().splitlines():
        m = _LINE.match(line)
        if m:
            out[m.group(1)] = m.group(2)
    return out


CFG = load_project()
FILE_NAME = CFG.get("FILE_NAME", "mygame")
GAME_NAME = CFG.get("GAME_NAME", FILE_NAME)
EXT = CFG.get("EXT", "gb")
ROM = ROOT / f"{FILE_NAME}.{EXT}"
SYMFILE = ROOT / f"{FILE_NAME}.sym"


def baserom() -> Path:
    for ext in ("gbc", "gb"):
        p = ROOT / f"baserom.{ext}"
        if p.is_file():
            return p
    sys.exit("error: baserom.gb / baserom.gbc not found in the repo root")


def tool(name: str) -> str:
    """Path to an RGBDS tool: tools/rgbds/<name> first, then PATH."""
    local = ROOT / "tools" / "rgbds" / name
    if local.is_file():
        return str(local)
    found = shutil.which(name)
    if not found:
        sys.exit(f"error: {name} not found; run `bash build_tools.sh` or install RGBDS >= 0.8")
    return found


def run_make(*targets: str) -> int:
    return subprocess.run(["make", "--no-print-directory", *targets], cwd=ROOT).returncode


# ---------------------------------------------------------------------------
# JSON helpers (stable, diff-friendly)
# ---------------------------------------------------------------------------

def load_json(path: Path, default):
    if path.is_file():
        return json.loads(path.read_text())
    return default


def save_json(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n")


# ---------------------------------------------------------------------------
# Addresses
# ---------------------------------------------------------------------------

def key(bank: int, addr: int) -> str:
    return f"{bank:02X}:{addr:04X}"


def parse_key(k: str) -> tuple[int, int]:
    b, a = k.split(":")
    return int(b, 16), int(a, 16)


#: mgbdis auto-label: Call_000_0184, Jump_000_0197, jr_000_0165, ...
AUTO_RE = re.compile(r"^([A-Za-z]+)_([0-9a-fA-F]{3})_([0-9a-fA-F]{4})$")
IDENT_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def auto_key(name: str) -> str | None:
    m = AUTO_RE.match(name)
    if not m:
        return None
    return key(int(m.group(2), 16), int(m.group(3), 16))


def parse_sym(path: Path = SYMFILE) -> dict[str, tuple[int, int]]:
    """rgblink `.sym`: name -> (bank, addr). Local `.labels` keep their full name."""
    out: dict[str, tuple[int, int]] = {}
    if not path.is_file():
        return out
    for line in path.read_text().splitlines():
        m = re.match(r"^([0-9A-Fa-f]{2,3}):([0-9A-Fa-f]{4})\s+(\S+)$", line)
        if m:
            out[m.group(3)] = (int(m.group(1), 16), int(m.group(2), 16))
    return out


def asm_files() -> list[Path]:
    return sorted(p for p in SRC.rglob("*.asm") if p.is_file())


# ---------------------------------------------------------------------------
# Asm line parsing
# ---------------------------------------------------------------------------

LABEL_RE = re.compile(r"^([A-Za-z_][A-Za-z0-9_]*)(::?)\s*(?:;.*)?$")
SECTION_RE = re.compile(r'^SECTION\s+"([^"]*)"\s*,\s*(ROM0|ROMX|WRAM0|WRAMX|HRAM|SRAM|VRAM|OAM)\s*(?:\[\s*\$?([0-9A-Fa-f]+)\s*\])?(?:\s*,\s*BANK\[\s*\$?([0-9A-Fa-f]+)\s*\])?', re.I)
DATA_DIRECTIVES = {"db", "dw", "dl", "ds", "incbin"}
UNCONDITIONAL_END = {"ret", "reti"}


def strip_comment(line: str) -> str:
    out = []
    inq = False
    for ch in line:
        if ch == '"':
            inq = not inq
        if ch == ";" and not inq:
            break
        out.append(ch)
    return "".join(out).rstrip()


def split_instr(line: str) -> tuple[str, str] | None:
    """Return (mnemonic, operands) for an indented instruction/directive line."""
    if not line[:1].isspace():
        return None
    body = strip_comment(line).strip()
    if not body:
        return None
    parts = body.split(None, 1)
    return parts[0].lower(), (parts[1].strip() if len(parts) > 1 else "")


def is_terminator(mn: str, ops: str) -> bool:
    """Unconditional control transfer: nothing falls through after it."""
    if mn in UNCONDITIONAL_END:
        return True
    if mn in ("jp", "jr"):
        return "," not in ops
    return False


_REG8 = {"a", "b", "c", "d", "e", "h", "l"}
_REG16 = {"bc", "de", "hl", "sp", "af"}
_CB = {"rlc", "rrc", "rl", "rr", "sla", "sra", "swap", "srl", "bit", "res", "set"}
_ALU = {"add", "adc", "sub", "sbc", "and", "xor", "or", "cp"}


def _split_commas(s: str) -> list[str]:
    parts, cur, depth, inq = [], [], 0, False
    for ch in s:
        if ch == '"':
            inq = not inq
        if not inq:
            if ch in "[(":
                depth += 1
            elif ch in "])":
                depth -= 1
            elif ch == "," and depth == 0:
                parts.append("".join(cur).strip())
                cur = []
                continue
        cur.append(ch)
    if cur:
        parts.append("".join(cur).strip())
    return parts


def _num(tok: str) -> int | None:
    tok = tok.strip()
    try:
        if tok.startswith("$"):
            return int(tok[1:], 16)
        if tok.startswith("%"):
            return int(tok[1:], 2)
        return int(tok, 0)
    except ValueError:
        return None


def _data_size(mn: str, ops: str) -> int | None:
    args = _split_commas(ops)
    if mn == "db":
        n = 0
        for a in args:
            if a.startswith('"') and a.endswith('"') and len(a) >= 2:
                n += len(a[1:-1].replace("\\\\", "\\").replace('\\"', '"'))
            else:
                n += 1
        return n
    if mn == "dw":
        return 2 * len(args)
    if mn == "dl":
        return 4 * len(args)
    if mn == "ds":
        v = _num(args[0]) if args else None
        return v
    return None


def instr_size(mn: str, ops: str) -> int | None:
    """Byte length of one LR35902 instruction or data directive (None = unknown)."""
    if mn in DATA_DIRECTIVES:
        return _data_size(mn, ops)
    args = _split_commas(ops)
    if mn == "stop":
        return 2
    if mn in _CB:
        return 2
    if mn == "jr":
        return 2
    if mn == "call":
        return 3
    if mn == "jp":
        return 1 if args and args[-1].lower() == "hl" else 3
    if mn == "ldh":
        return 1 if any("[c]" in a.lower() for a in args) else 2
    if mn in _ALU:
        if mn == "add" and args and args[0].lower() == "hl":
            return 1
        if mn == "add" and args and args[0].lower() == "sp":
            return 2
        last = args[-1].lower() if args else "a"
        return 1 if (last in _REG8 or last == "[hl]") else 2
    if mn == "ld":
        if len(args) != 2:
            return None
        dst, src = args[0].lower(), args[1].lower()
        if "[" in dst or "[" in src:
            mem = dst if "[" in dst else src
            inner = mem.strip("[]").strip()
            if inner in ("hl", "hl+", "hl-", "hli", "hld", "bc", "de", "c"):
                return 2 if (inner == "hl" and "[" in dst and src not in _REG8) else 1
            return 3
        if dst in _REG16:
            if src.replace(" ", "").startswith("sp+") or src.replace(" ", "").startswith("sp-"):
                return 2
            if src in _REG16:
                return 1
            return 3
        return 1 if src in _REG8 else 2
    # nop halt di ei daa cpl scf ccf rlca rrca rla rra ret reti push pop inc dec rst
    return 1
