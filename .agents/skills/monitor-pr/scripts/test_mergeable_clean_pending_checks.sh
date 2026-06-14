#!/usr/bin/env bash
# Regression test for mergeable-clean gating:
# CLEAN/UNSTABLE PRs must wait until pending_checks=0, and Codex/Copilot COMMENTED
# reviews should satisfy the review-bot HEAD evaluation gate without requiring APPROVED.
set -euo pipefail

SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
WATCH_SH="$SCRIPT_DIR/watch.sh"

run_case() {
  local case_name="$1" check_status="$2" expected_reason="$3"
  local TMPDIR
  TMPDIR=$(mktemp -d)
  # shellcheck disable=SC2064
  trap "rm -rf '$TMPDIR'" RETURN

  local HEAD_OID="abc123def456"
  local HEAD_COMMIT_DATE="2026-01-01T00:00:00Z"

  mkdir -p "$TMPDIR/bin"
  cat > "$TMPDIR/bin/gh" <<EOF_GH
#!/usr/bin/env bash
set -e

cmd="\$1"
shift || true

if [ "\$cmd" = "pr" ] && [ "\${1:-}" = "view" ]; then
  cat <<'EOJSON'
{
  "mergeStateStatus": "CLEAN",
  "reviewDecision": "REVIEW_REQUIRED",
  "statusCheckRollup": [
    {
      "__typename": "CheckRun",
      "name": "unit",
      "status": "$check_status",
      "conclusion": "SUCCESS",
      "workflowName": "ci",
      "startedAt": "2026-01-01T00:01:00Z"
    }
  ],
  "comments": [],
  "state": "OPEN",
  "headRefOid": "$HEAD_OID",
  "labels": []
}
EOJSON
  exit 0
fi

if [ "\$cmd" = "api" ]; then
  endpoint="\$1"
  shift
  jq_filter=""
  while [ \$# -gt 0 ]; do
    case "\$1" in
      --jq) jq_filter="\$2"; shift 2;;
      *) shift;;
    esac
  done

  case "\$endpoint" in
    *"/pulls/"*"/comments") echo "[]" ;;
    *"/issues/"*"/comments") echo "[]" ;;
    *"/pulls/"*"/reviews")
      cat <<EOJSON
[
  {
    "id": 301,
    "user": {"login": "claude[bot]"},
    "state": "COMMENTED",
    "body": "reviewed",
    "commit_id": "$HEAD_OID",
    "submitted_at": "2026-01-01T00:02:00Z"
  }
]
EOJSON
      ;;
    *"/commits/"*)
      if [ -n "\$jq_filter" ]; then
        echo "$HEAD_COMMIT_DATE"
      else
        printf '{"commit":{"committer":{"date":"%s"}}}\n' "$HEAD_COMMIT_DATE"
      fi
      ;;
    *)
      echo "MOCK gh api: unhandled endpoint \$endpoint" >&2
      exit 1
      ;;
  esac
  exit 0
fi

echo "MOCK gh: unhandled command \$cmd \$*" >&2
exit 1
EOF_GH
  chmod +x "$TMPDIR/bin/gh"

  cat > "$TMPDIR/bin/sleep" <<'EOF_SLEEP'
#!/usr/bin/env bash
exit 0
EOF_SLEEP
  chmod +x "$TMPDIR/bin/sleep"

  echo '{"ch1":{},"ch2":{},"ch3":{"301":"2026-01-01T00:02:00Z"},"reviewDecision":"REVIEW_REQUIRED"}' > "$TMPDIR/prev_state.json"

  local TEST_WATCH_SH="$TMPDIR/watch_under_test.sh"
  grep -v '^export PATH="/opt/homebrew/bin' "$WATCH_SH" > "$TEST_WATCH_SH"

  PATH="$TMPDIR/bin:/usr/bin:/bin" \
    REPO=E5presso/spakky-framework \
    PR_NUMBER=99999 \
    PREV_STATE_FILE="$TMPDIR/prev_state.json" \
    bash "$TEST_WATCH_SH" > "$TMPDIR/stdout.log" 2> "$TMPDIR/stderr.log" || true

  if ! grep -q "^reason=$expected_reason$" "$TMPDIR/stdout.log"; then
    echo "FAIL [$case_name]: expected reason=$expected_reason" >&2
    echo "--- stdout ---" >&2; cat "$TMPDIR/stdout.log" >&2
    echo "--- stderr ---" >&2; cat "$TMPDIR/stderr.log" >&2
    return 1
  fi
  echo "OK [$case_name]: reason=$expected_reason"
}

run_case "completed-checks" "COMPLETED" "mergeable-clean"
run_case "pending-checks" "IN_PROGRESS" "heartbeat"

echo "test_mergeable_clean_pending_checks.sh: OK"
