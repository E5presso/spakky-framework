#!/bin/sh
set -eu

NEURATH_SETUP_VERSION="0.3.1"
NEURATH_SETUP_WHEEL="neurath-${NEURATH_SETUP_VERSION}-py3-none-any.whl"
NEURATH_SETUP_SHA256="d54534ecee84daf396bb215452ca949799dbb50167ca6fb6cd8d9c33f92ffcd9"
NEURATH_SETUP_ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd -P)
NEURATH_SETUP_ENV="$NEURATH_SETUP_ROOT/.neurath/local/environments/$NEURATH_SETUP_SHA256"

[ "$#" -eq 0 ] || { printf '%s\n' 'Usage: scripts/setup_neurath.sh' >&2; exit 2; }

# An identical official installation needs no writes or renewed hook trust.
if [ -x "$NEURATH_SETUP_ENV/bin/python" ] && [ -f "$NEURATH_SETUP_ROOT/.neurath/install.json" ]; then
  if uv run --no-project --python "$NEURATH_SETUP_ENV/bin/python" python -c '
import json, sys
from pathlib import Path
from neurath import __version__
receipt = json.loads((Path(sys.argv[1]) / ".neurath/install.json").read_text())
sys.exit(0 if receipt.get("wheel_sha256") == sys.argv[2] and receipt.get("version") == __version__ == sys.argv[3] else 1)
' "$NEURATH_SETUP_ROOT" "$NEURATH_SETUP_SHA256" "$NEURATH_SETUP_VERSION"; then
    printf 'Neurath %s already installed from verified wheel %s\n' "$NEURATH_SETUP_VERSION" "$NEURATH_SETUP_SHA256"
    exit 0
  fi
fi

# Legacy import is explicit: do not silently configure a new empty task database.
if [ -f "$NEURATH_SETUP_ROOT/.neurath/local/runtime.sqlite3" ] && [ ! -f "$NEURATH_SETUP_ROOT/.neurath/local/neurath.sqlite3" ]; then
  printf '%s\n' 'Preserve the legacy database and complete neurath.migration.import_legacy/verify_archive before installing.' >&2
  exit 1
fi

NEURATH_SETUP_TMP=$(mktemp -d "${TMPDIR:-/tmp}/spakky-neurath-setup.XXXXXX")

cleanup() {
  rm -f -- "$NEURATH_SETUP_TMP/$NEURATH_SETUP_WHEEL"
  rmdir -- "$NEURATH_SETUP_TMP"
}
trap cleanup EXIT HUP INT TERM

curl --fail --location --proto '=https' --tlsv1.2 \
  "https://github.com/E5presso/neurath/releases/download/v${NEURATH_SETUP_VERSION}/${NEURATH_SETUP_WHEEL}" \
  --output "$NEURATH_SETUP_TMP/$NEURATH_SETUP_WHEEL"
NEURATH_SETUP_ACTUAL=$(shasum -a 256 "$NEURATH_SETUP_TMP/$NEURATH_SETUP_WHEEL" | cut -d ' ' -f 1)
[ "$NEURATH_SETUP_ACTUAL" = "$NEURATH_SETUP_SHA256" ] || { printf '%s\n' 'Neurath wheel checksum mismatch' >&2; exit 1; }

uv venv --python 3.14 "$NEURATH_SETUP_ENV"
uv pip install --python "$NEURATH_SETUP_ENV/bin/python" "$NEURATH_SETUP_TMP/$NEURATH_SETUP_WHEEL"

# Preserve existing local settings. Seed only missing files from project defaults.
for config in .codex/config.toml .codex/hooks.json .claude/settings.json; do
  if [ ! -e "$NEURATH_SETUP_ROOT/$config" ] && [ ! -L "$NEURATH_SETUP_ROOT/$config" ]; then
    mkdir -p "$NEURATH_SETUP_ROOT/$(dirname "$config")"
    cp "$NEURATH_SETUP_ROOT/${config%.*}.example.${config##*.}" "$NEURATH_SETUP_ROOT/$config"
  fi
done

uv run --no-project --python "$NEURATH_SETUP_ENV/bin/python" python -c '
import json, sys
from neurath.install import configure
print(json.dumps(configure(sys.argv[1], sys.argv[2], sys.argv[3]), indent=2))
' "$NEURATH_SETUP_ROOT" "$NEURATH_SETUP_ENV/bin/python" "$NEURATH_SETUP_SHA256"
