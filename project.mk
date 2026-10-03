# Single source of truth for per-game settings. Read by the Makefile and by
# tools/decomp/common.py (simple `NAME := value` lines only, no expansion).
# `./init_project.sh` overwrites this from the baserom header.

# Output name: <FILE_NAME>.<EXT>, symbol file <FILE_NAME>.sym
FILE_NAME  := mygame
GAME_NAME  := My Game
# gb or gbc (init_project.sh sets it from the CGB flag at 0x143)
EXT        := gb
# rgbfix flags. mgbdis disassembles the header bytes verbatim, so this only has
# to pad to the ROM size; clear it if the original has a deliberately bad checksum.
FIX_FLAGS  := -v -p 255
ASM_FLAGS  :=
