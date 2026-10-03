# GB / GBC disassembly-decomp template

A ready-to-run scaffold for turning a **Game Boy or Game Boy Color ROM** into a readable,
byte-identical RGBDS project, driven by an autonomous coding agent ([CLAUDE.md](CLAUDE.md))
or by hand. Companion to the GBA matching-decomp template; GB games are handwritten
assembly, so the product here is *understood assembly*, not matching C.

| Layer | Contents |
|---|---|
| Day zero | `./init_project.sh`: header → `project.mk` (`.gb`/`.gbc` from the CGB flag), `rom.sha1`, mgbdis disassembly, `make compare` |
| Stage 1 | `analyze.py` suspect detector for data decoded as code, `symbols.py block`, `make disasm` loop |
| Names | `symbols.py` (functions, RAM, blocks, with evidence), `apply` renames in place |
| Analysis DB | call graph, RAM readers/writers, bank-switch flags, per-bank code/data/padding |
| Structure | `carve.py` splits bank files into fixed-address module files with automatic rollback |
| Docs | `document.py`: `docs/banks.md`, `docs/ram-map.md`, per-function stubs |
| Verification | `make selftest` runs the whole pipeline on a synthetic ROM |

## Quick start

```bash
git clone <this repo> my_game_decomp && cd my_game_decomp
bash build_tools.sh            # RGBDS + mgbdis
make selftest                  # optional but cheap: proves the toolchain
cp /path/to/clean_dump.gbc baserom.gbc
./init_project.sh --name my_game --game-name "My Game"
python3 tools/decomp/report_status.py
```

Then follow [docs/new-game-checklist.md](docs/new-game-checklist.md) and
[docs/pipeline.md](docs/pipeline.md).

## Not included

- **C matching.** If your game was built with SDCC/GBDK, use the GBA template's matcher design
  as a starting point; the stub/manifest ideas carry over, the compiler wrapper does not.
- Mods, graphics extraction, music tooling.

## Status

Verified on a synthetic MBC1/CGB fixture (`tests/fixture`). Not yet run on a commercial ROM;
expect small portability bugs in the first real run. Tested with RGBDS 0.9.4 and mgbdis v3.0.
