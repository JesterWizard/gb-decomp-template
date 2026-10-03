# GB / GBC asm conventions

These come from the pret disassembly projects (pokered, pokecrystal, and others) and the
RGBDS docs, not from experience on one game. Adopt them so the result looks like every other
good GB decomp and so tools/people can pick it up.

## Naming

- Functions and data in ROM: `PascalCase` (`ClearMem`, `PlayerStatsTable`). Local loop /
  branch labels: `.lowercase` under their function once you hand-edit (mgbdis emits
  global `jr_000_0165`; `symbols.py set ... --kind label` renames them).
- RAM: `w` WRAM (`wFrameCounter`), `h` HRAM (`hJoypad`), `s` SRAM (`sSaveSlot`), `v` VRAM
  (`vBGMap`), hardware registers `r` (`rLCDC`, already from `hardware.inc`).
- Constants `ALL_CAPS` (`MAX_PARTY_SIZE`), enumerations via `const` macros once you hand-edit.
- A prefix is a claim. Name what the code *does* (`CopyDataToVRAM`), not what you guess the
  game calls it, unless the game's own text proves it. `Call_BBB_AAAA` is the honest fallback.

## Reading code

- Banked call helpers (`Bankswitch`, `FarCall`, `rst $10` style) take the target bank in a
  register or inline `db` after the call. Treat the bytes after such a call as data, not code.
- `jp hl` after `add a / ld e,a / ld d,0 / add hl,de / ld a,[hl+] / ld h,[hl] / ld l,a` is a
  jump table: the table is `dw` entries right after the call or at the loaded address.
- `ld a, N / ld [$2000], a` (MBC1/3/5) or `$2100`/`$3000` (MBC5 low/high bit) switch ROM
  banks; `$4000-$5FFF` writes pick the RAM bank (or RTC register on MBC3); `$0000-$1FFF`
  enable external RAM.
- HRAM `$FF80-$FFFE` often holds a DMA routine copied at boot (code that runs from HRAM:
  mgbdis shows it as ROM data). OAM DMA source/dest is `rDMA`.
- VBlank-only VRAM access: look for waits on `rSTAT`/`rLY` or work queued for the VBlank
  handler. These patterns explain a lot of "why is there a flag variable".

## Data

- Pointer tables: `dw Label, Label, ...` (bank-relative); farptrs `db bank / dw addr`.
  Convert `db $xx, $yy` pairs to `dw Label` once you know the target; `make compare` proves it.
- Strings: define a `charmap` and write them as text. Terminators and control codes become
  named constants.
- Padding between functions is `$00` (nop) or `$FF` (rst $38); keep it as `ds N, $FF` or
  `.padding` blocks so the ROM stays identical and the analysis does not count it as code.

## Layout

- Keep the bank/addr placement fixed (`SECTION ..., ROMX[$4000], BANK[n]`) until the project
  is mostly carved, then move to relocatable sections plus `ds`/`align` only where the
  original has holes.
