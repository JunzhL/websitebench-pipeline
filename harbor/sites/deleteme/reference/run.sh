#!/usr/bin/env bash
# Run the reference outside Docker, straight from the clone.
#
# The reference is the frozen offline clone, so this delegates to it rather
# than holding a second copy. Honours the runtime ABI the site contract
# declares: HOST, PORT, DATA_DIR, SEED, TZ, foreground, clean SIGTERM.
set -Eeuo pipefail

here=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
repo=$(CDPATH= cd -- "$here/../../../.." && pwd)
clone="$repo/materials/deleteme/clone"

if [ ! -f "$clone/app.py" ]; then
  echo "reference source missing: $clone/app.py" >&2
  exit 1
fi

export HOST="${HOST:-0.0.0.0}"
export PORT="${PORT:-8080}"
export DATA_DIR="${DATA_DIR:-${TMPDIR:-/tmp}/wb-deleteme-reference}"
export SEED="${SEED:-1}"
export TZ="${TZ:-Etc/UTC}"
mkdir -p "$DATA_DIR"

cd "$clone"
exec python app.py
