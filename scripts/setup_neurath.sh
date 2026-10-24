#!/bin/sh
set -eu

NEURATH_SETUP_VERSION="0.4.0"
NEURATH_SETUP_WHEEL="neurath-${NEURATH_SETUP_VERSION}-py3-none-any.whl"
NEURATH_SETUP_SHA256="c9bfc1b1bb4b976a6d9d518fcff4042c6a67558e1de4b8ed9e613ea8e8ec483e"
NEURATH_SETUP_COMMIT="d5025a6f7de1da8a0df9b5bf19b1e161e877f419"
NEURATH_SETUP_ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd -P)
NEURATH_SETUP_ENV="$NEURATH_SETUP_ROOT/.neurath/local/bootstrap/$NEURATH_SETUP_SHA256"

[ "$#" -eq 0 ] || { printf '%s\n' 'Usage: scripts/setup_neurath.sh' >&2; exit 2; }

# Verify the same public artifact through each current host command; never use old run/MCP.
if uv run --no-project python - "$NEURATH_SETUP_ROOT" "$NEURATH_SETUP_SHA256" "$NEURATH_SETUP_VERSION" "$NEURATH_SETUP_COMMIT" <<'PY'
import json
import subprocess
import sys
from pathlib import Path
root = Path(sys.argv[1])
for host in (".codex", ".claude"):
    command = root / host / "neurath/neurath"
    receipt = command.with_name("distribution.json")
    if not command.is_file() or not receipt.is_file():
        sys.exit(1)
    state = json.loads(receipt.read_text())
    if state.get("wheel_sha256") != sys.argv[2] or state.get("version") != sys.argv[3]:
        sys.exit(1)
    observed = subprocess.run([str(command), "distribution", "verify"], capture_output=True, text=True)
    if observed.returncode:
        sys.exit(1)
    report = json.loads(observed.stdout)
    if not report.get("guide_matches") or report.get("package_sha256") != state.get("package_sha256") or report.get("provenance", {}).get("source_commit") != sys.argv[4]:
        sys.exit(1)
    preview = subprocess.run([str(command), "maintenance", "install", "--provider", host[1:], "--directory", str(root), "--preview"], capture_output=True, text=True)
    if preview.returncode or json.loads(preview.stdout)["changed_files"]:
        sys.exit(1)
PY
then
    printf 'Verified Neurath %s CLI and guide; native activation remains unverified.\n' "$NEURATH_SETUP_VERSION"
    exit 0
fi

# Preserve current user records; source conversion is an explicit official migration operation.
for original in neurath.sqlite3 runtime.sqlite3; do
  if [ -f "$NEURATH_SETUP_ROOT/.neurath/local/$original" ]; then
    printf '%s\n' 'Preserve and transition originals with official migration prepare/read/fence before applying.' >&2
    exit 1
  fi
done

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

if [ ! -x "$NEURATH_SETUP_ENV/bin/python" ]; then
  uv venv --python 3.14 "$NEURATH_SETUP_ENV"
  uv pip install --python "$NEURATH_SETUP_ENV/bin/python" "$NEURATH_SETUP_TMP/$NEURATH_SETUP_WHEEL"
fi

# Let the official installer preserve host settings; do not seed native permissions or trust.
uv run --no-project --python "$NEURATH_SETUP_ENV/bin/python" python -I - \
  "$NEURATH_SETUP_ROOT" "$NEURATH_SETUP_TMP/$NEURATH_SETUP_WHEEL" "$NEURATH_SETUP_COMMIT" <<'PY'
import json
import os
import subprocess
import sys
from pathlib import Path
root, wheel, commit = sys.argv[1:]
home = Path(os.environ.get("XDG_DATA_HOME", str(Path.home() / ".local/share"))).expanduser().resolve()
bootstrap = Path(sys.executable).with_name("neurath")
def call(command, arguments):
    result = subprocess.run([str(command), *arguments], capture_output=True, text=True, check=True)
    return json.loads(result.stdout)
candidate = call(bootstrap, ["distribution", "prepare", "--wheel", wheel, "--store", str(home / "neurath/distributions"), "--source-commit", commit])
command = Path(candidate["python"]).with_name("neurath")
if not (home / "neurath/core.sqlite3").exists():
    call(command, ["maintenance", "initialize"])
for host in ("codex", "claude"):
    arguments = ["--candidate", candidate["candidate"], "--provider", host, "--directory", root, "--data-home", str(home)]
    plan = call(command, ["distribution", "plan", *arguments])
    if plan["database_transition"]["required"]:
        raise RuntimeError("Continue the official preserving migration: " + json.dumps(plan["continuation"]))
    result = call(command, ["distribution", "apply", *arguments])
    print(json.dumps({"provider": host, "command": result["command"], "cli_invoked": result["cli_invoked"], "native_activation": result["native_activation"]}))
PY
