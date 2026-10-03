# New game checklist

From an empty clone to a green, mostly-named project. The day-zero path
(init → mgbdis → `make compare OK` → analyze → name → block → carve) is exercised end to end
by `make selftest` on a synthetic ROM; it has not been run on a commercial game yet, so treat
the first real run as the real test and fix the template when something breaks.

## 0. Prerequisites

```bash
sudo apt install -y git python3 curl xz-utils rsync
cp /path/to/clean_dump.gb baserom.gb      # or baserom.gbc; gitignored, never commit it
```

## 1. Toolchain

```bash
bash build_tools.sh      # prebuilt RGBDS (Linux x86_64) + mgbdis; else install RGBDS >= 0.8 yourself
make selftest            # proves the toolchain and pipeline work before you touch the game
```

## 2. Day zero

```bash
./init_project.sh --name my_game --game-name "My Game"
```

Reads the header (title, CGB flag → `.gb`/`.gbc`, mapper, ROM/RAM size), writes `project.mk`
and `rom.sha1`, disassembles into `src/`, and runs `make compare` (must print
`my_game.gbc: OK`). Read the warnings it prints: a bad Nintendo logo or header checksum means a
bad dump or a deliberately odd header (then set `FIX_FLAGS :=` in `project.mk`).

Then:

```bash
make analyze && python3 tools/decomp/report_status.py
python3 tools/decomp/analyze.py --check     # must say 0 disagreements (validates the length model on this ROM)
```

## 3. Game-specific things to settle early

| Item | Notes |
|---|---|
| Mapper | MBC1/3/5 etc. Find the bank-switch routine(s) (`functions.json` → `bankswitch: true`), name them first; everything cross-bank depends on them. |
| Header fields | `project.mk` + the header lines in `src/bank_000.asm` are the ROM's; mgbdis reproduces them verbatim. |
| Hardware vs game RAM | `rLCDC`, `rIE` etc. are already named by `hardware.inc`. Start RAM naming with the HRAM and the most-touched WRAM addresses from `docs/ram-map.md`. |
| CGB-only features | Palette registers (`rBCPS/rBCPD/rOCPS/rOCPD`), VRAM bank (`rVBK`), WRAM bank (`rSVBK`), HDMA (`rHDMA*`), double speed (`rKEY1`): their users are the graphics/engine core; name them early. |
| Text encoding | Find the text printer, derive the charmap, then convert `db` strings to `charmap` text (`.text` blocks need `--character-map-path` when you re-disassemble). |
| Music engine | Often a self-contained bank; carve it as a module early. |
| Compression | Look for decompressor routines; their outputs explain many "data" blocks. |
| Compiled code | If most routines have C-like prologues (stack frames via `add sp`, `push bc/de/hl` patterns), the game used SDCC/GBDK — this template does not match C; see README "Not included". |

## 4. Session loop

See `CLAUDE.md`. Short form: `report_status.py` → `make compare` → fix suspects → name with
evidence → `symbols.py apply` → `make compare` → `make analyze document tier` →
`tools/notify_done.sh`.

## 5. Sharp edges

- `make tidy` removes `build/` and the ROM only. `analysis/` and `baserom.sym` are tracked.
- `redisasm.py` regenerates all of `src/`; it refuses with uncommitted edits unless `--force`,
  and always once `src/.frozen` exists. Freeze as soon as suspects are down to noise.
- `symbols.py apply` needs the auto labels to exist (`Call_000_0184`); after a `make disasm`
  they do. After freezing, it renames in place.
