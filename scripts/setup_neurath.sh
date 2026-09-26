#!/bin/sh
set -eu

NEURATH_SETUP_REPOSITORY="https://github.com/E5presso/neurath.git"
NEURATH_SETUP_COMMIT="dd05ed0009b4618a19affcf5803d2177674379e9"
NEURATH_SETUP_ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd -P)
NEURATH_SETUP_TMP=$(mktemp -d "${TMPDIR:-/tmp}/spakky-neurath-setup.XXXXXX")

cleanup() {
  rm -rf -- "$NEURATH_SETUP_TMP"
}
trap cleanup EXIT HUP INT TERM

git clone --quiet --no-checkout --filter=blob:none \
  "$NEURATH_SETUP_REPOSITORY" "$NEURATH_SETUP_TMP/source"
git -C "$NEURATH_SETUP_TMP/source" checkout --quiet --detach "$NEURATH_SETUP_COMMIT"

resolved_commit=$(git -C "$NEURATH_SETUP_TMP/source" rev-parse HEAD)
if [ "$resolved_commit" != "$NEURATH_SETUP_COMMIT" ]; then
  printf 'Neurath commit mismatch: expected %s, got %s\n' \
    "$NEURATH_SETUP_COMMIT" "$resolved_commit" >&2
  exit 1
fi

# Preserve existing local settings. Seed only missing files from project defaults.
for config in .codex/config.toml .codex/hooks.json .claude/settings.json; do
  if [ ! -e "$NEURATH_SETUP_ROOT/$config" ] && [ ! -L "$NEURATH_SETUP_ROOT/$config" ]; then
    cp "$NEURATH_SETUP_ROOT/${config%.*}.example.${config##*.}" "$NEURATH_SETUP_ROOT/$config"
  fi
done

"$NEURATH_SETUP_TMP/source/setup" \
  "$NEURATH_SETUP_ROOT" \
  --skill-prefix neurath- \
  "$@"
