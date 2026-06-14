#!/usr/bin/env bash
# Regression test for watch.sh failed_checks — StatusContext.state in {ERROR, FAILURE} catch.
#
# 시나리오: statusCheckRollup 에 CheckRun 과 StatusContext 두 형태가 섞여 있다.
# external CI infra ERROR 같은 external status 는 StatusContext (`state` 필드) 로 보고되므로
# CheckRun (`conclusion` 필드) 만 보는 select 절은 false negative 를 만든다.
#
# Case A: StatusContext.state=ERROR 단독 → failedChecks=1, EVENT reason=ci-failed.
# Case B: StatusContext.state=FAILURE 단독 → failedChecks=1, EVENT reason=ci-failed.
# Case C: CheckRun.conclusion=FAILURE + StatusContext.state=ERROR 혼합 → failedChecks=2.
# Case D: StatusContext.state=SUCCESS (green) → failedChecks=0, EVENT 미송신.
set -euo pipefail

SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
WATCH_SH="$SCRIPT_DIR/watch.sh"

if [ ! -f "$WATCH_SH" ]; then
  echo "FATAL: watch.sh not found at $WATCH_SH" >&2
  exit 1
fi

run_case() {
  local case_name="$1" rollup_json="$2" expected_failed="$3" expected_event="$4"
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
  "mergeStateStatus": "BLOCKED",
  "reviewDecision": "REVIEW_REQUIRED",
  "statusCheckRollup": $rollup_json,
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
    *"/pulls/"*"/reviews") echo "[]" ;;
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

  # reviewDecision baseline must match the live snapshot to avoid a false review-decision-changed EVENT.
  echo '{"ch1":{},"ch2":{},"ch3":{},"reviewDecision":"REVIEW_REQUIRED"}' > "$TMPDIR/prev_state.json"

  cat > "$TMPDIR/bin/sleep" <<'EOF_SLEEP'
#!/usr/bin/env bash
exit 0
EOF_SLEEP
  chmod +x "$TMPDIR/bin/sleep"

  local TEST_WATCH_SH="$TMPDIR/watch_under_test.sh"
  grep -v '^export PATH="/opt/homebrew/bin' "$WATCH_SH" > "$TEST_WATCH_SH"

  PATH="$TMPDIR/bin:/usr/bin:/bin" \
    REPO=E5presso/spakky-framework \
    PR_NUMBER=99999 \
    PREV_STATE_FILE="$TMPDIR/prev_state.json" \
    bash "$TEST_WATCH_SH" > "$TMPDIR/stdout.log" 2> "$TMPDIR/stderr.log" || true

  local actual_failed
  actual_failed=$(grep "^failedChecks=" "$TMPDIR/stdout.log" | tail -1 | sed 's/^failedChecks=//')
  if [ "$actual_failed" != "$expected_failed" ]; then
    echo "FAIL [$case_name]: failedChecks expected=$expected_failed actual=$actual_failed" >&2
    echo "--- stdout ---" >&2; cat "$TMPDIR/stdout.log" >&2
    echo "--- stderr ---" >&2; cat "$TMPDIR/stderr.log" >&2
    return 1
  fi

  if [ -n "$expected_event" ]; then
    if ! grep -q "^reason=$expected_event$" "$TMPDIR/stdout.log"; then
      echo "FAIL [$case_name]: expected reason=$expected_event not found" >&2
      echo "--- stdout ---" >&2; cat "$TMPDIR/stdout.log" >&2
      return 1
    fi
  else
    if grep -q "^reason=ci-failed$" "$TMPDIR/stdout.log"; then
      echo "FAIL [$case_name]: ci-failed must NOT fire when all checks green" >&2
      echo "--- stdout ---" >&2; cat "$TMPDIR/stdout.log" >&2
      return 1
    fi
  fi

  echo "OK [$case_name]: failedChecks=$actual_failed reason=${expected_event:-no-ci-failed}"
}

fail=0
run_case "status-context-error-only" \
  '[{"__typename":"StatusContext","context":"legacy-ci","state":"ERROR"}]' \
  "1" "ci-failed" || fail=1

run_case "status-context-failure-only" \
  '[{"__typename":"StatusContext","context":"legacy-ci","state":"FAILURE"}]' \
  "1" "ci-failed" || fail=1

run_case "mixed-checkrun-and-status-context" \
  '[{"__typename":"CheckRun","name":"unit","status":"COMPLETED","conclusion":"FAILURE","workflowName":"ci"},{"__typename":"StatusContext","context":"legacy-ci","state":"ERROR"}]' \
  "2" "ci-failed" || fail=1

run_case "status-context-success-only" \
  '[{"__typename":"StatusContext","context":"legacy-ci","state":"SUCCESS"}]' \
  "0" "" || fail=1

if [ "$fail" -ne 0 ]; then
  echo "test_status_context_failed_checks.sh: FAIL" >&2
  exit 1
fi

echo "test_status_context_failed_checks.sh: OK"
