#!/usr/bin/env bash
# Regression test for watch.sh bot-stuck (f) gate — auto-approvable label.
#
# 시나리오: claude bot 이 HEAD 를 평가하지 않은 정체 상태 (a~e 5-조건 모두 만족)에서
# `auto-approvable` 태그 유무에 따라 bot-stuck EVENT 가 분기되는지 검증한다.
#
# Case A: 태그 부재 → bot-stuck EVENT 미송신 (휴먼 리뷰 대기가 정상 경로 — 빈 커밋 재트리거 회피).
# Case B: 태그 존재 → bot-stuck EVENT 송신 (자동 승인 가능 PR 의 일시적 봇 오동작 → 재트리거 유효).
#
# Fixture 공통 조건 (a~e):
#   pending_checks = 0, failed_checks = 0
#   mergeStateStatus = BLOCKED, reviewDecision = REVIEW_REQUIRED
#   CH2 issue comments = [] (bot CH2 미사용)
#   CH3 reviews = [] (claude[bot] formal review 부재 → latest_bot_review_oid 빈 문자열)
#   → bot_evaluated_head=0
#   → (a) CI all COMPLETED, (b) BLOCKED != CLEAN, (c) REVIEW_REQUIRED != APPROVED,
#     (d) latest_bot_review_oid("") != HEAD_OID, (e) bot_evaluated_head=0
set -euo pipefail

SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
WATCH_SH="$SCRIPT_DIR/watch.sh"

if [ ! -f "$WATCH_SH" ]; then
  echo "FATAL: watch.sh not found at $WATCH_SH" >&2
  exit 1
fi

run_case() {
  local case_name="$1" labels_json="$2"
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
  "statusCheckRollup": [
    {"name": "ci", "status": "COMPLETED", "conclusion": "SUCCESS", "workflowName": "ci"}
  ],
  "comments": [],
  "state": "OPEN",
  "headRefOid": "$HEAD_OID",
  "labels": $labels_json
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

  # Baseline pre-populated (empty CH1/CH2/CH3) so first real cycle evaluates branches.
  # reviewDecision baseline must match the live snapshot to avoid a false review-decision-changed EVENT.
  echo '{"ch1":{},"ch2":{},"ch3":{},"reviewDecision":"REVIEW_REQUIRED"}' > "$TMPDIR/prev_state.json"

  cat > "$TMPDIR/bin/sleep" <<'EOF_SLEEP'
#!/usr/bin/env bash
exit 0
EOF_SLEEP
  chmod +x "$TMPDIR/bin/sleep"

  local TEST_WATCH_SH="$TMPDIR/watch_under_test.sh"
  grep -v '^export PATH="/opt/homebrew/bin' "$WATCH_SH" > "$TEST_WATCH_SH"

  # watch.sh 무한 루프이므로 timeout 으로 강제 종료. heartbeat threshold=6 cycle 도달 시
  # EVENT reason=heartbeat emit → exit 0. 태그 부재 case 에서 bot-stuck 미송신을 검증할 때
  # heartbeat 가 정상 경로가 된다.
  PATH="$TMPDIR/bin:/usr/bin:/bin" \
    REPO=E5presso/spakky-framework \
    PR_NUMBER=99999 \
    PREV_STATE_FILE="$TMPDIR/prev_state.json" \
    bash "$TEST_WATCH_SH" > "$TMPDIR/stdout.log" 2> "$TMPDIR/stderr.log" || true

  if [ "$case_name" = "no-tag" ]; then
    # 기대: bot-stuck EVENT 미송신. heartbeat 까지 진행했어야 함 (변화 없음 path).
    if grep -q "^reason=bot-stuck$" "$TMPDIR/stdout.log"; then
      echo "FAIL [no-tag]: bot-stuck must NOT fire when auto-approvable label is absent" >&2
      echo "--- stdout ---" >&2; cat "$TMPDIR/stdout.log" >&2
      return 1
    fi
    if ! grep -q "^reason=heartbeat$" "$TMPDIR/stdout.log"; then
      echo "FAIL [no-tag]: expected heartbeat fallback (no EVENT path matched)" >&2
      echo "--- stdout ---" >&2; cat "$TMPDIR/stdout.log" >&2
      echo "--- stderr ---" >&2; cat "$TMPDIR/stderr.log" >&2
      return 1
    fi
    echo "OK [no-tag]: bot-stuck suppressed without auto-approvable label"
  else
    # 기대: bot-stuck EVENT 송신.
    if ! grep -q "^reason=bot-stuck$" "$TMPDIR/stdout.log"; then
      echo "FAIL [with-tag]: bot-stuck must fire when auto-approvable label is present" >&2
      echo "--- stdout ---" >&2; cat "$TMPDIR/stdout.log" >&2
      echo "--- stderr ---" >&2; cat "$TMPDIR/stderr.log" >&2
      return 1
    fi
    echo "OK [with-tag]: bot-stuck fires with auto-approvable label"
  fi
}

fail=0
run_case "no-tag"   '[{"name":"Development"},{"name":"Back-end"}]' || fail=1
run_case "with-tag" '[{"name":"Development"},{"name":"auto-approvable"}]' || fail=1

if [ "$fail" -ne 0 ]; then
  echo "test_bot_stuck_auto_approvable_gate.sh: FAIL" >&2
  exit 1
fi

echo "test_bot_stuck_auto_approvable_gate.sh: OK"
