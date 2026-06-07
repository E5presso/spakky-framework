#!/usr/bin/env bash
# Verifies that Python edit hook dispatches checks from package roots.

set -u

HOOK="$(cd "$(dirname "$0")" && pwd)/check-python-edit.sh"
if [ ! -x "$HOOK" ]; then
  echo "FAIL: hook not executable at $HOOK" >&2
  exit 1
fi

raw_dir="$(mktemp -d -t spakky-python-hook-test-XXXXXX)"
trap 'rm -rf "$raw_dir"' EXIT
raw_dir="$(cd "$raw_dir" && pwd -P)"
repo="$raw_dir/repo"
mkdir -p "$repo/core/spakky/src/spakky" "$repo/plugins/spakky-fastapi/src/spakky/plugins/fastapi"
(
  cd "$repo"
  git init -q -b develop
  git config user.email test@example.com
  git config user.name test
  touch pyproject.toml
  touch core/spakky/pyproject.toml
  touch plugins/spakky-fastapi/pyproject.toml
  touch core/spakky/src/spakky/__init__.py
  touch plugins/spakky-fastapi/src/spakky/plugins/fastapi/__init__.py
  git add .
  git commit -q -m "seed"
)

bin_dir="$raw_dir/bin"
log_file="$raw_dir/calls.log"
mkdir -p "$bin_dir"
cat > "$bin_dir/uv" <<'SH'
#!/usr/bin/env bash
printf '%s|%s\n' "$PWD" "$*" >> "$UV_HOOK_LOG"
exit 0
SH
chmod +x "$bin_dir/uv"

payload="$(jq -n \
  --arg f1 "$repo/core/spakky/src/spakky/__init__.py" \
  --arg f2 "$repo/plugins/spakky-fastapi/src/spakky/plugins/fastapi/__init__.py" \
  '{tool_name:"Edit", tool_input:{file_path:$f1}, tool_response:{filePath:$f2}}')"

status=0
PATH="$bin_dir:$PATH" UV_HOOK_LOG="$log_file" \
  bash -c "cd '$repo' && printf '%s' '$payload' | '$HOOK'" || status=$?

if [ "$status" -ne 0 ]; then
  echo "FAIL: hook exited with $status" >&2
  exit 1
fi

grep -Fxq "$repo/core/spakky|run ruff format $repo/core/spakky/src/spakky/__init__.py" "$log_file" \
  || { echo "FAIL: missing core package ruff format dispatch" >&2; exit 1; }
grep -Fxq "$repo/core/spakky|run pyrefly check $repo/core/spakky/src/spakky/__init__.py" "$log_file" \
  || { echo "FAIL: missing core package pyrefly dispatch" >&2; exit 1; }
grep -Fxq "$repo/plugins/spakky-fastapi|run ruff format $repo/plugins/spakky-fastapi/src/spakky/plugins/fastapi/__init__.py" "$log_file" \
  || { echo "FAIL: missing plugin package ruff format dispatch" >&2; exit 1; }
grep -Fxq "$repo/plugins/spakky-fastapi|run pyrefly check $repo/plugins/spakky-fastapi/src/spakky/plugins/fastapi/__init__.py" "$log_file" \
  || { echo "FAIL: missing plugin package pyrefly dispatch" >&2; exit 1; }

if grep -Fq "$repo|run ruff" "$log_file"; then
  echo "FAIL: hook dispatched from repo root" >&2
  exit 1
fi

echo "PASS: Python edit hook dispatches from package roots"
