#!/usr/bin/env bash
# Regression checks for monitor-pr comment filtering. This script stubs gh so it
# can run without mutating GitHub state.
set -euo pipefail

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
tmp_dir="$(mktemp -d)"
trap 'rm -rf "$tmp_dir"' EXIT

mkdir -p "$tmp_dir/bin"
cat > "$tmp_dir/bin/gh" <<'SH'
#!/usr/bin/env bash
set -euo pipefail

if [ "${1:-}" != "api" ]; then
  echo "unsupported gh invocation: $*" >&2
  exit 1
fi

path="${2:-}"
case "$path" in
  repos/*/pulls/*/comments)
    if [ "${FAKE_CASE:-codecov-only}" = "actionable" ]; then
      cat <<'JSON'
[
  {
    "id": 201,
    "user": {"login": "chatgpt-codex-connector[bot]"},
    "body": "**P1** actionable review feedback",
    "path": "file.py",
    "original_line": 7,
    "created_at": "2026-05-03T12:10:00Z",
    "updated_at": "2026-05-03T12:10:00Z"
  }
]
JSON
    else
      printf '[]\n'
    fi
    ;;
  repos/*/issues/*/comments)
    cat <<'JSON'
[
  {
    "id": 100,
    "user": {"login": "codecov[bot]"},
    "body": "## [Codecov](https://app.codecov.io/example)\n\nAll modified lines are covered.",
    "created_at": "2026-05-03T12:00:00Z",
    "updated_at": "2026-05-03T12:05:00Z"
  },
  {
    "id": 101,
    "user": {"login": "E5presso"},
    "body": "Codecov checked.\n\n<!-- claude-agent-reply to=100 -->",
    "created_at": "2026-05-03T12:01:00Z",
    "updated_at": "2026-05-03T12:01:00Z"
  },
  {
    "id": 102,
    "user": {"login": "E5presso"},
    "body": "Codecov checked again.\n\n<!-- claude-agent-reply to=100 -->",
    "created_at": "2026-05-03T12:02:00Z",
    "updated_at": "2026-05-03T12:02:00Z"
  }
]
JSON
    ;;
  repos/*/pulls/*/reviews)
    printf '[]\n'
    ;;
  *)
    echo "unsupported gh api path: $path" >&2
    exit 1
    ;;
esac
SH
chmod +x "$tmp_dir/bin/gh"

run_collect() {
  PATH="$tmp_dir/bin:$PATH" REPO=E5presso/spakky-framework PR_NUMBER=1 \
    bash "$script_dir/collect_comments.sh"
}

codecov_only="$(run_collect)"
grep -q '^TOTAL=0$' <<<"$codecov_only"

stale_codecov="$(PATH="$tmp_dir/bin:$PATH" REPO=E5presso/spakky-framework PR_NUMBER=1 \
  STALE_HANDLED_IDS=100 bash "$script_dir/collect_comments.sh")"
grep -q '^TOTAL=0$' <<<"$stale_codecov"

actionable="$(FAKE_CASE=actionable run_collect)"
grep -q '^TOTAL=1$' <<<"$actionable"
grep -q 'chatgpt-codex-connector\[bot\]' <<<"$actionable"

echo "monitor-pr filter checks passed"
