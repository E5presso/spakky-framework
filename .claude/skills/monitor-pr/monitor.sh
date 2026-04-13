#!/usr/bin/env bash
# PR 병합 허들 모니터. 스냅샷 기반, 60초 간격.
# Usage: monitor.sh <pr-number>
# 출력: 각 tick에 SNAPSHOT: 1줄 + 허들/대기 EVENT: N줄. 종료 이벤트가 감지되면 루프 종료.
#
# 상태 추적: 처리 완료한 코멘트/리뷰 ID를 `.claude/monitor-pr-seen/<pr>.json`에 기록.
# 새로 추가된 항목만 허들로 간주한다. bot 자동 코멘트(codecov 등)는 허들에서 제외.

set -u
PR_NUMBER="${1:?pr-number required}"
REPO_FULL=$(GH_PAGER=cat gh repo view --json nameWithOwner --jq '.nameWithOwner')
OWNER=$(echo "$REPO_FULL" | cut -d/ -f1)
REPO=$(echo "$REPO_FULL" | cut -d/ -f2)

STATE_DIR=".claude/monitor-pr-seen"
STATE_FILE="$STATE_DIR/$PR_NUMBER.json"
mkdir -p "$STATE_DIR"
[ -f "$STATE_FILE" ] || echo '{"comments":[],"reviews":[]}' > "$STATE_FILE"

THREAD_QUERY='{ repository(owner: "'"$OWNER"'", name: "'"$REPO"'") { pullRequest(number: '"$PR_NUMBER"') { reviewThreads(first: 100) { nodes { isResolved } } } } }'
REVIEW_REQUESTS_QUERY='{ repository(owner: "'"$OWNER"'", name: "'"$REPO"'") { pullRequest(number: '"$PR_NUMBER"') { reviewRequests(first: 20) { nodes { requestedReviewer { __typename ... on Bot { login } ... on User { login } } } } } } }'

# bot 코멘트 허들 제외 대상 (대문자 구분 없음, 부분 일치). review body는 copilot 등 봇도 실제 피드백이므로 포함.
BOT_COMMENT_PATTERN='codecov|github-actions|dependabot|renovate'

while true; do
  snap=$(GH_PAGER=cat gh pr view "$PR_NUMBER" --repo "$REPO_FULL" \
    --json state,mergeStateStatus,reviewDecision,statusCheckRollup 2>/dev/null || echo '{}')
  state=$(echo "$snap" | jq -r '.state // "UNKNOWN"')
  mergeState=$(echo "$snap" | jq -r '.mergeStateStatus // "UNKNOWN"')
  reviewDecision=$(echo "$snap" | jq -r '.reviewDecision // ""')
  ciFailed=$(echo "$snap" | jq '[(.statusCheckRollup // [])[] | select((.conclusion // .state // "") | IN("FAILURE","ERROR","TIMED_OUT","CANCELLED"))] | length')
  ciPending=$(echo "$snap" | jq '[(.statusCheckRollup // [])[] | select((.status // .state // "") | IN("IN_PROGRESS","QUEUED","PENDING","WAITING"))] | length')
  unresolvedThreads=$(GH_PAGER=cat gh api graphql -f query="$THREAD_QUERY" \
    --jq '[.data.repository.pullRequest.reviewThreads.nodes[] | select(.isResolved == false)] | length' 2>/dev/null || echo 0)

  # pending 자동화 봇 리뷰어만 카운트 (사람 리뷰어는 Phase 7 수동 판단에 맡김).
  pendingBotReviewers=$(GH_PAGER=cat gh api graphql -f query="$REVIEW_REQUESTS_QUERY" \
    --jq '[.data.repository.pullRequest.reviewRequests.nodes[].requestedReviewer | select(.__typename == "Bot")] | length' 2>/dev/null || echo 0)

  # 새로 도착한 사람 코멘트만 카운트 (bot 제외 + 이전 tick에 본 적 없는 것만).
  allComments=$(GH_PAGER=cat gh api "repos/$OWNER/$REPO/issues/$PR_NUMBER/comments" 2>/dev/null || echo '[]')
  newComments=$(echo "$allComments" | jq --arg pat "$BOT_COMMENT_PATTERN" --slurpfile state "$STATE_FILE" \
    '[.[] | select((.user.login | test($pat; "i")) | not) | select(.id as $i | ($state[0].comments | index($i)) | not)]')
  newCommentCount=$(echo "$newComments" | jq 'length')

  # 새로 도착한 리뷰 본문만 카운트 (bot 포함, 이전 tick에 본 적 없는 것만).
  allReviews=$(GH_PAGER=cat gh api "repos/$OWNER/$REPO/pulls/$PR_NUMBER/reviews" 2>/dev/null || echo '[]')
  newReviews=$(echo "$allReviews" | jq --slurpfile state "$STATE_FILE" \
    '[.[] | select(.body != "") | select(.id as $i | ($state[0].reviews | index($i)) | not)]')
  newReviewCount=$(echo "$newReviews" | jq 'length')

  echo "SNAPSHOT state=$state mergeState=$mergeState reviewDecision=$reviewDecision ciFailed=$ciFailed ciPending=$ciPending unresolvedThreads=$unresolvedThreads pendingBotReviewers=$pendingBotReviewers newComments=$newCommentCount newReviews=$newReviewCount"

  stop=0
  if [ "$state" = "CLOSED" ] || [ "$state" = "MERGED" ]; then echo "EVENT:PR_CLOSED state=$state"; stop=1; fi
  if [ "$mergeState" = "DIRTY" ]; then echo "EVENT:CONFLICT"; stop=1; fi
  if [ "$mergeState" = "BEHIND" ]; then echo "EVENT:BEHIND"; stop=1; fi
  if [ "$ciFailed" -gt 0 ]; then
    names=$(echo "$snap" | jq -r '[(.statusCheckRollup // [])[] | select((.conclusion // .state // "") | IN("FAILURE","ERROR","TIMED_OUT","CANCELLED")) | .name] | join(",")')
    echo "EVENT:CI_FAILURE count=$ciFailed names=$names"; stop=1
  fi
  if [ "$unresolvedThreads" -gt 0 ]; then echo "EVENT:UNRESOLVED_THREAD count=$unresolvedThreads"; stop=1; fi
  if [ "$newCommentCount" -gt 0 ]; then echo "EVENT:OPEN_COMMENT count=$newCommentCount"; stop=1; fi
  if [ "$newReviewCount" -gt 0 ]; then echo "EVENT:OPEN_REVIEW count=$newReviewCount"; stop=1; fi

  # MERGEABLE: CI 미진행 + 실패 없음 + mergeState CLEAN/UNSTABLE + 리뷰 통과(APPROVED 또는 승인 요구 없음) + pending 자동화 봇 리뷰어 없음.
  if [ "$stop" -eq 0 ]; then
    if [ "$ciPending" -eq 0 ] && [ "$ciFailed" -eq 0 ] \
       && { [ "$mergeState" = "CLEAN" ] || [ "$mergeState" = "UNSTABLE" ]; } \
       && { [ "$reviewDecision" = "APPROVED" ] || [ -z "$reviewDecision" ]; } \
       && [ "$pendingBotReviewers" -eq 0 ]; then
      echo "EVENT:MERGEABLE mergeState=$mergeState reviewDecision=$reviewDecision"
      stop=1
    fi
  fi

  if [ "$stop" -eq 1 ]; then
    # 이번 tick까지 관찰한 코멘트/리뷰 ID를 state에 병합 저장 — 재시작 시 같은 이벤트 재발 방지.
    mergedComments=$(echo "$allComments" | jq --arg pat "$BOT_COMMENT_PATTERN" --slurpfile state "$STATE_FILE" \
      '[.[] | select((.user.login | test($pat; "i")) | not) | .id] + $state[0].comments | unique')
    mergedReviews=$(echo "$allReviews" | jq --slurpfile state "$STATE_FILE" \
      '[.[] | select(.body != "") | .id] + $state[0].reviews | unique')
    jq -n --argjson c "$mergedComments" --argjson r "$mergedReviews" '{comments: $c, reviews: $r}' > "$STATE_FILE"
    break
  fi

  [ "$ciPending" -gt 0 ] && echo "EVENT:CI_PENDING count=$ciPending"
  [ -n "$reviewDecision" ] && [ "$reviewDecision" != "APPROVED" ] && echo "EVENT:REVIEW_PENDING decision=$reviewDecision"
  [ "$pendingBotReviewers" -gt 0 ] && echo "EVENT:REVIEW_PENDING pendingBotReviewers=$pendingBotReviewers"

  sleep 60
done
