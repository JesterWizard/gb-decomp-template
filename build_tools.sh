#!/usr/bin/env bash
# Fetch the two external tools: RGBDS (assembler/linker) and mgbdis (disassembler).
# Both land in git-ignored tools/ subdirectories. Uses a system RGBDS (>= 0.8) if present.
set -euo pipefail
cd "$(dirname "$0")"

RGBDS_VERSION="${RGBDS_VERSION:-v0.9.4}"

need() { command -v "$1" >/dev/null 2>&1 || { echo "error: missing $1" >&2; exit 1; }; }
need git
need python3

echo "==> GB/GBC decomp tool bootstrap"

if command -v rgbasm >/dev/null 2>&1 && [ ! -x tools/rgbds/rgbasm ]; then
  echo "==> Using system $(rgbasm --version)"
elif [ ! -x tools/rgbds/rgbasm ]; then
  need curl
  need tar
  case "$(uname -s)-$(uname -m)" in
    Linux-x86_64) asset="rgbds-linux-x86_64.tar.xz" ;;
    *) echo "error: no prebuilt RGBDS for $(uname -sm); install RGBDS >= 0.8 (https://rgbds.gbdev.io)" >&2; exit 1 ;;
  esac
  echo "==> Downloading RGBDS $RGBDS_VERSION"
  mkdir -p tools/rgbds
  curl -fsSL "https://github.com/gbdev/rgbds/releases/download/$RGBDS_VERSION/$asset" | tar -xJ -C tools/rgbds
fi

if [ ! -f tools/mgbdis/mgbdis.py ]; then
  echo "==> Cloning mgbdis"
  git clone --depth 1 https://github.com/mattcurrie/mgbdis tools/mgbdis
fi

echo "==> Done. Next: put the dump at ./baserom.gb (or .gbc), then ./init_project.sh"
