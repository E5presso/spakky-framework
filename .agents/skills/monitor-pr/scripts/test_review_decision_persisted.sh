#!/usr/bin/env bash
# Regression test for watch.sh reviewDecision baseline persistence (issue regression).
#
# 결함: reviewDecision 은 PREV_REVIEW_DECISION 환경변수로만 전달되어 PREV_STATE_FILE JSON 에
# 영속되지 않았다. PREV_STATE_FILE 이 비어있지 않으면 baseline-init 블록이 skip 되므로,
# 호출자가 환경변수를 누락하면 prev_review_decision="" 로 고정되어 변화 없는 PR 에 매 cycle
# review-decision-changed EVENT 가 무한 발생했다.
#
# 수정: reviewDecision 을 코멘트 3채널과 동일하게 PREV_STATE_FILE JSON 에 영속한다.
# 본 테스트는 PREV_REVIEW_DECISION 환경변수를 일절 전달하지 않고 watch.sh 를 실행한다.
#
# Case A (persisted, no change): prev_state.json 의 reviewDecision 이 live snapshot 과 일치
#   → review-decision-changed 미송신, 변화 없음 path 의 heartbeat 까지 진행.
#   (수정 전: env var 누락 → prev_review_decision="" → 매 cycle false EVENT)
# Case B (real change): prev_state.json 의 reviewDecision 과 live snapshot 이 불일치
#   → review-decision-changed 송신. 영속 baseline 이 실제 변화 감지를 막지 않음을 검증.
set -euo pipefail

SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
WATCH_SH="$SCRIPT_DIR/watch.sh"

if [ ! -f "$WATCH_SH" ]; then
  echo "FATAL: watch.sh not found at $WATCH_SH" >&2
  exit 1
fi

run_case() {
  local case_name="$1" live_review_decision="$2" baseline_review_decision="$3"
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
  "reviewDecision": "$live_review_decision",
  "statusCheckRollup": [
    {"name": "ci", "status": "COMPLETED", "conclusion": "SUCCESS", "workflowName": "ci"}
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

  # Baseline pre-populated with reviewDecision persisted in the state file (the fixed contract).
  # baseline_done=1 forces watch.sh to evaluate branches on the first real cycle.
  echo "{\"ch1\":{},\"ch2\":{},\"ch3\":{},\"reviewDecision\":\"$baseline_review_decision\"}" \
    > "$TMPDIR/prev_state.json"

  cat > "$TMPDIR/bin/sleep" <<'EOF_SLEEP'
#!/usr/bin/env bash
exit 0
EOF_SLEEP
  chmod +x "$TMPDIR/bin/sleep"

  local TEST_WATCH_SH="$TMPDIR/watch_under_test.sh"
  grep -v '^export PATH="/opt/homebrew/bin' "$WATCH_SH" > "$TEST_WATCH_SH"

  # PREV_REVIEW_DECISION 을 전달하지 않는다 — reviewDecision baseline 은 PREV_STATE_FILE 에서만 로드됨을 검증.
  PATH="$TMPDIR/bin:/usr/bin:/bin" \
    REPO=E5presso/spakky-framework \
    PR_NUMBER=99999 \
    PREV_STATE_FILE="$TMPDIR/prev_state.json" \
    bash "$TEST_WATCH_SH" > "$TMPDIR/stdout.log" 2> "$TMPDIR/stderr.log" || true

  if [ "$case_name" = "persisted-no-change" ]; then
    # 기대: review-decision-changed 미송신. 변화 없음 path 의 heartbeat 까지 진행.
    if grep -q "^reason=review-decision-changed$" "$TMPDIR/stdout.log"; then
      echo "FAIL [persisted-no-change]: review-decision-changed must NOT fire when baseline matches" >&2
      echo "--- stdout ---" >&2; cat "$TMPDIR/stdout.log" >&2
      return 1
    fi
    if ! grep -q "^reason=heartbeat$" "$TMPDIR/stdout.log"; then
      echo "FAIL [persisted-no-change]: expected heartbeat (no-change path)" >&2
      echo "--- stdout ---" >&2; cat "$TMPDIR/stdout.log" >&2
      echo "--- stderr ---" >&2; cat "$TMPDIR/stderr.log" >&2
      return 1
    fi
    echo "OK [persisted-no-change]: reviewDecision loaded from state file, no false EVENT"
  else
    # 기대: review-decision-changed 송신 (영속 baseline 과 live snapshot 불일치).
    if ! grep -q "^reason=review-decision-changed$" "$TMPDIR/stdout.log"; then
      echo "FAIL [real-change]: review-decision-changed must fire when baseline differs" >&2
      echo "--- stdout ---" >&2; cat "$TMPDIR/stdout.log" >&2
      echo "--- stderr ---" >&2; cat "$TMPDIR/stderr.log" >&2
      return 1
    fi
    echo "OK [real-change]: review-decision-changed fires on genuine decision change"
  fi
}

fail=0
run_case "persisted-no-change" "REVIEW_REQUIRED" "REVIEW_REQUIRED" || fail=1
run_case "real-change"         "APPROVED"        "REVIEW_REQUIRED" || fail=1

if [ "$fail" -ne 0 ]; then
  echo "test_review_decision_persisted.sh: FAIL" >&2
  exit 1
fi

echo "test_review_decision_persisted.sh: OK"
