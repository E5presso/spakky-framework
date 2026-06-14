#!/usr/bin/env bash
# PR 상태 스냅샷을 30초 주기 polling으로 수집한다.
# 이벤트 분류/비교는 수행하지 않는다 — raw 상태만 출력하고, 판단은 호출자(에이전트)가 한다.
#
# 사용법: REPO=E5presso/spakky-framework PR_NUMBER=23504 bash poll.sh
# 동작:
#   1. 30초 sleep
#   2. gh pr view --json ... 으로 상태 스냅샷 획득
#   3. POLL_RESULT 블록을 stdout으로 출력하고 종료
# 재기동은 호출자가 반복 호출한다 (백그라운드 금지, ScheduleWakeup 금지, exponent backoff 금지).
set -euo pipefail

# Claude Code Bash tool spawns non-login shells that miss /opt/homebrew/bin.
export PATH="/opt/homebrew/bin:$PATH"

if ! command -v gh >/dev/null 2>&1; then
  echo "FATAL: gh CLI not found in PATH ($PATH)" >&2
  exit 1
fi

: "${REPO:?REPO env required}"
: "${PR_NUMBER:?PR_NUMBER env required}"

sleep 30

snapshot=$(gh pr view "$PR_NUMBER" --repo "$REPO" \
  --json mergeStateStatus,reviewDecision,statusCheckRollup,comments)
reviewCommentCount=$(gh api "repos/$REPO/pulls/$PR_NUMBER/comments" --jq 'length')

echo "POLL_RESULT"
echo "mergeState=$(echo "$snapshot" | jq -r '.mergeStateStatus // ""')"
echo "reviewDecision=$(echo "$snapshot" | jq -r '.reviewDecision // ""')"
echo "commentCount=$(echo "$snapshot" | jq '.comments | length')"
echo "reviewCommentCount=$reviewCommentCount"
echo "failedChecks=$(echo "$snapshot" | jq '[.statusCheckRollup // [] | group_by(.name // .context) | .[] | sort_by(.startedAt // .completedAt // "") | last | select(((.conclusion == "FAILURE" or .conclusion == "ERROR") or (.state == "FAILURE" or .state == "ERROR")) and (.workflowName != "Auto PR Code Review"))] | length')"
