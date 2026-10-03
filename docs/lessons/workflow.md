# Workflow lessons

Carried over from the GBA matching-decomp project (agbcc), keeping only what is
architecture-independent, plus the GB-specific loop.

## General

- **Root-cause, don't chase.** When `make compare` fails after an edit, `cmp -l a.gbc b.gbc | head`
  tells you the first differing offset. Map it to a label (`<FILE_NAME>.sym`), bisect by
  reverting half the edit. Never retry variations hoping one works.
- **Names are claims.** Evidence first: the caller that proves it, the register contract,
  the RAM it touches. Prefer an honest `Call_BBB_AAAA` to a wrong name that misfiles code in
  `docs/`.
- **Manifests are tracked.** `analysis/symbols.json`, `analysis/blocks.json` and
  `baserom.sym` are the record of what you learned. Generated-and-ignored things must be
  regenerable from tracked ones. (The GBA project lost a manifest to `make tidy` because it
  lived under `build/`.)
- **Renames go through the tool.** A plain text replace corrupts strings, comments and
  local labels.
- **A tool that deletes things needs a dry run.** Same lesson as `prune_drafts.py --apply`
  wiping a user's drafts: `redisasm.py` therefore refuses with uncommitted edits in `src/`.
- **Report `make` explicitly**, commit only when asked, never with a failing compare.
- **Ping when done:** `tools/notify_done.sh "<game> decomp" "<summary>"` as the last step.

## GB specific

- Fix data-as-code *first*. Every later analysis (call graph, RAM refs) is polluted by
  instructions that are really tables.
- Use an emulator trace if you can get one: executed addresses are ground truth for `.code`,
  and everything never executed that mgbdis called code is a candidate for `.data`.
- Name the bank switcher, VBlank handler, joypad reader, memcpy/memset, and the text printer
  before anything else; they appear in nearly every function's callee list.
- Freeze early. Once suspects are mostly noise, `redisasm.py --freeze` and hand-edit; stage 1
  re-disassembly is destructive by design.
- Keep per-bank `make compare` green at every step; a failing compare after a `carve` is
  rolled back for you, a failing compare after a hand edit is yours to bisect.
