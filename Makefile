# Game Boy / Game Boy Color matching-disassembly build (RGBDS).
include project.mk

export PATH := $(CURDIR)/tools/rgbds:$(PATH)

ROM   := $(FILE_NAME).$(EXT)
SYM   := $(FILE_NAME).sym
MAP   := $(FILE_NAME).map
OBJ   := build/game.o
SOURCES := $(shell find src -name '*.asm' -o -name '*.inc' 2>/dev/null)

SHA1 := $(shell { command -v sha1sum || command -v shasum; } 2>/dev/null)

.PHONY: all compare tidy disasm analyze symbols status document tier selftest check-baserom
.DEFAULT_GOAL := all

all: $(ROM)

$(OBJ): $(SOURCES) project.mk
	@mkdir -p build
	rgbasm $(ASM_FLAGS) -I src/ -o $@ src/game.asm

$(ROM): $(OBJ)
	rgblink -n $(SYM) -m $(MAP) -o $@ $<
ifneq ($(strip $(FIX_FLAGS)),)
	rgbfix $(FIX_FLAGS) $@
endif

# Rebuilds from scratch and checks the ROM against rom.sha1.
compare:
	@rm -f $(ROM) $(SYM) $(MAP) $(OBJ)
	@$(MAKE) --no-print-directory all
	@$(SHA1) -c rom.sha1

check-baserom:
	@ls baserom.gb baserom.gbc >/dev/null 2>&1 || { echo "error: put the clean dump at ./baserom.gb or ./baserom.gbc"; exit 1; }

# Regenerate src/ from baserom + baserom.sym (refuses once src/.frozen exists).
disasm: check-baserom
	python3 tools/decomp/redisasm.py

analyze: $(ROM)
	python3 tools/decomp/analyze.py

symbols:
	python3 tools/decomp/symbols.py generate

tier:
	python3 tools/decomp/tier.py

document:
	python3 tools/decomp/document.py

status:
	python3 tools/decomp/report_status.py

selftest:
	bash tests/selftest.sh

tidy:
	rm -rf build $(ROM) $(SYM) $(MAP)
