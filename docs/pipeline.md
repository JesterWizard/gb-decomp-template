# Pipeline

```
baserom.gb[c] ──mgbdis──► src/bank_NNN.asm, game.asm, hardware.inc
      ▲                         │ rgbasm + rgblink + rgbfix
 baserom.sym                    ▼
 (generated from           <FILE_NAME>.gb[c]  ──► make compare (sha1 vs rom.sha1)
  analysis/*.json)               │ <FILE_NAME>.sym
      ▲                         ▼
 symbols.py ◄── you ◄── analyze.py ──► analysis/{functions,data,ram,banks,suspects}.json
                                         │
                                  document.py / tier.py / report_status.py
```

## Stage 1: mgbdis stage (src/ is generated)

mgbdis decodes everything linearly and cannot tell code from data. The result assembles to
the identical ROM but misreads tables, strings and pointer lists as instructions.
`analyze.py` flags the most reliable symptom as a **suspect**: instructions after an
unconditional `jp`/`jr`/`ret`/`reti` with no label in between (padding of `nop` / `rst $38`
is ignored). Fix loop:

1. `report_status.py` — list suspects (`analysis/suspects.json`: address, approx size).
2. Look at the bytes (`xxd -s 0x… -l 64 baserom.gbc`, the surrounding code, who points at
   it) and classify: `symbols.py block data|text|code|padding|image BB:AAAA LEN [--stride N]`.
3. `make disasm && make compare` — `baserom.sym` is regenerated and src/ re-disassembled.
4. Name functions and RAM as understanding grows (`symbols.py set` / `ram`). Because names
   are written into `baserom.sym`, they survive every re-disassembly.

An emulator trace (e.g. Beaten Dying Moon, Emulicious, BGB code/data logger) is the best
source of ground truth: import it with `symbols.py import-sym` or drop `.code` lines into
`baserom.extra.sym`.

## Stage 2: hand stage (src/ is the source)

`redisasm.py --freeze` writes `src/.frozen`. From then on:

- `symbols.py apply` renames labels and RAM operands in place (string/comment aware).
- `carve.py START END module.asm` splits ranges out of bank files into per-module files.
  Every SECTION keeps its fixed address, so the ROM cannot change; a changed ROM rolls the
  carve back automatically.
- Add comments, constants (`src/constants/*.inc`), macros. Replace `db`/`dw` runs with
  structured data (charmaps, `dw Label`, macros) once `make compare` stays green.
- Eventually replace fixed `SECTION ... [$addr]` placement with ordinary sections so code can
  move (the pokered end state). Do this only when most banks are carved; it is the point
  where `make compare` becomes a real check instead of a layout guarantee.

## Analysis DB

| File | Contents |
|---|---|
| `functions.json` | Entry label → address, size, callers, callees, tail-jumps, RAM reads/writes, bank-switch flag, indirect-jump flag |
| `data.json` | Labelled data blocks, size, which functions mention them |
| `ram.json` | Every WRAM/HRAM/SRAM/VRAM/IO address touched, with readers/writers and name |
| `banks.json` | Per-bank code / data / padding bytes and named share |
| `suspects.json` | Data-as-code candidates |

A function is a label that is a `call`/`rst` target, a vector (< $0150), or a symbols.json
entry of kind `function`. Labels in between belong to the preceding function. Addresses come
from the linker's `.sym`; sizes use an LR35902 instruction-length model that
`analyze.py --check` validates against it. It must report 0 disagreements; a non-zero count
is a bug in the model or an unusual directive/macro in the source (the label addresses are
authoritative), not a code/data signal.

## Known limits

- Cross-bank calls: mgbdis assumes a `call $4xxx` stays in the caller's bank. Real games
  switch banks first (`ld a, N / ld [$2000], a / call ...` or a `Bankswitch`/`farcall` helper).
  `functions.json` flags bank-switching functions; resolve targets by hand and
  name them with the right `BB:AAAA`.
- Indirect jumps (`jp hl`, jump tables) hide callees; they are flagged, not resolved.
- RAM references through registers (`ld hl, $c000` then `[hl+]`) are not tracked; use
  `symbols.py apply --immediates` for the start address, and read the code for the rest.
- Self-modifying code and code executed from RAM (HRAM DMA routines) are data to the tools.
