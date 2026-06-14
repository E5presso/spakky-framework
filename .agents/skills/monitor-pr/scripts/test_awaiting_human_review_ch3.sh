#!/usr/bin/env bash
# Regression test for watch.sh awaiting-human-review terminal DONE branch — CH3 path.
#
# 시나리오: claude bot 이 HEAD 를 평가했고 의도적으로 승인하지 않은 상태인데,
# CH2 issue comment 가 부재하고 CH3 reviews API 로 state=COMMENTED 리뷰만 제출한 패턴
# (awaiting-human-review 회귀). watch.sh 가 무한 heartbeat 루프에 빠지지 않고
# `DONE reason=awaiting-human-review` 를 emit 하는지 검증한다.
#
# Fixture 조건:
#   pending_checks = 0, failed_checks = 0
#   mergeStateStatus = BLOCKED, reviewDecision = REVIEW_REQUIRED
#   CH2 issue comments = [] (bot CH2 미사용)
#   CH3 reviews: claude[bot] 1건, commit_id == HEAD oid, state = COMMENTED
#   → bot_evaluated_head=1 (CH3 OR-path)
set -euo pipefail

SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
WATCH_SH="$SCRIPT_DIR/watch.sh"

if [ ! -f "$WATCH_SH" ]; then
  echo "FATAL: watch.sh not found at $WATCH_SH" >&2
  exit 1
fi

TMPDIR=$(mktemp -d)
trap 'rm -rf "$TMPDIR"' EXIT

HEAD_OID="abc123def456"
HEAD_COMMIT_DATE="2026-01-01T00:00:00Z"
BOT_REVIEW_SUBMITTED_AT="2026-01-01T01:00:00Z"

mkdir -p "$TMPDIR/bin"
cat > "$TMPDIR/bin/gh" <<EOF_GH
#!/usr/bin/env bash
# Mock gh — minimal dispatch by argument pattern.
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
  "headRefOid": "$HEAD_OID"
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
    *"/pulls/"*"/comments")
      echo "[]"
      ;;
    *"/issues/"*"/comments")
      # CH2 부재 — bot 이 CH2 미사용
      echo "[]"
      ;;
    *"/pulls/"*"/reviews")
      cat <<'EOJSON'
[
  {"id": 101, "user": {"login": "claude[bot]"}, "submitted_at": "$BOT_REVIEW_SUBMITTED_AT", "commit_id": "$HEAD_OID", "state": "COMMENTED", "body": "휴먼 리뷰 필요"}
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

# Pre-populate baseline so watch.sh skips the baseline-init cycle.
# CH3 cache must contain id=101 with the same submitted_at to avoid comments-changed EVENT firing.
# reviewDecision baseline must match the live snapshot to avoid a false review-decision-changed EVENT.
cat > "$TMPDIR/prev_state.json" <<EOF_STATE
{
  "ch1": {},
  "ch2": {},
  "ch3": {"101": "$BOT_REVIEW_SUBMITTED_AT"},
  "reviewDecision": "REVIEW_REQUIRED"
}
EOF_STATE

cat > "$TMPDIR/bin/sleep" <<'EOF_SLEEP'
#!/usr/bin/env bash
exit 0
EOF_SLEEP
chmod +x "$TMPDIR/bin/sleep"

TEST_WATCH_SH="$TMPDIR/watch_under_test.sh"
grep -v '^export PATH="/opt/homebrew/bin' "$WATCH_SH" > "$TEST_WATCH_SH"

PATH="$TMPDIR/bin:/usr/bin:/bin" \
  REPO=E5presso/spakky-framework \
  PR_NUMBER=99999 \
  PREV_STATE_FILE="$TMPDIR/prev_state.json" \
  bash "$TEST_WATCH_SH" > "$TMPDIR/stdout.log" 2> "$TMPDIR/stderr.log" || true

fail=0

if ! grep -q "^DONE$" "$TMPDIR/stdout.log"; then
  echo "FAIL: expected 'DONE' marker on first line of stdout" >&2
  fail=1
fi

if ! grep -q "^reason=awaiting-human-review$" "$TMPDIR/stdout.log"; then
  echo "FAIL: expected 'reason=awaiting-human-review' in stdout" >&2
  fail=1
fi

if grep -q "^reason=heartbeat$" "$TMPDIR/stdout.log"; then
  echo "FAIL: heartbeat must NOT fire — awaiting-human-review precedes heartbeat" >&2
  fail=1
fi

if grep -q "^reason=bot-stuck$" "$TMPDIR/stdout.log"; then
  echo "FAIL: bot-stuck must NOT fire — bot evaluated HEAD via CH3 COMMENTED" >&2
  fail=1
fi

if [ "$fail" -ne 0 ]; then
  echo "--- stdout ---" >&2
  cat "$TMPDIR/stdout.log" >&2
  echo "--- stderr ---" >&2
  cat "$TMPDIR/stderr.log" >&2
  exit 1
fi

echo "OK: awaiting-human-review terminal DONE emitted via CH3 OR-path"
