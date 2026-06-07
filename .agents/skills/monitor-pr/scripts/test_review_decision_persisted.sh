#!/usr/bin/env bash
# Verifies watch.sh reads reviewDecision from PREV_STATE_FILE.

set -euo pipefail

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
tmp_dir="$(mktemp -d)"
trap 'rm -rf "$tmp_dir"' EXIT

mkdir -p "$tmp_dir/bin"
cat > "$tmp_dir/bin/sleep" <<'SH'
#!/usr/bin/env bash
exit 0
SH
cat > "$tmp_dir/bin/gh" <<'SH'
#!/usr/bin/env bash
set -euo pipefail

case "${1:-}:${2:-}" in
  pr:view)
    cat <<'JSON'
{
  "mergeStateStatus": "UNKNOWN",
  "reviewDecision": "CHANGES_REQUESTED",
  "statusCheckRollup": [
    {"status": "IN_PROGRESS", "conclusion": null, "workflowName": "ci"}
  ],
  "comments": [],
  "state": "OPEN",
  "headRefOid": "abc123"
}
JSON
    ;;
  api:repos/*/commits/*)
    echo '{"commit":{"committer":{"date":"2026-01-01T00:00:00Z"}}}'
    ;;
  api:repos/*/pulls/*/comments|api:repos/*/issues/*/comments|api:repos/*/pulls/*/reviews)
    echo '[]'
    ;;
  *)
    echo "unsupported gh invocation: $*" >&2
    exit 1
    ;;
esac
SH
chmod +x "$tmp_dir/bin/"*

state_file="$tmp_dir/state.json"
printf '%s' '{"ch1":{},"ch2":{},"ch3":{},"reviewDecision":"REVIEW_REQUIRED"}' > "$state_file"

out="$(PATH="$tmp_dir/bin:$PATH" REPO=E5presso/spakky-framework PR_NUMBER=1 PREV_STATE_FILE="$state_file" bash "$script_dir/watch.sh")"

grep -q '^EVENT$' <<<"$out"
grep -q '^reason=review-decision-changed$' <<<"$out"
grep -q '"reviewDecision": "CHANGES_REQUESTED"' "$state_file"

echo "monitor-pr reviewDecision persistence check passed"
