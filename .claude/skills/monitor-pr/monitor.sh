#!/usr/bin/env bash
# PR 병합 허들 모니터. 스냅샷 기반, 60초 간격.
# Usage: monitor.sh <pr-number>
# 출력: 각 tick에 SNAPSHOT: 1줄 + 허들/대기 EVENT: N줄. 종료 이벤트가 감지되면 루프 종료.

set -u
PR_NUMBER="${1:?pr-number required}"
REPO_FULL=$(GH_PAGER=cat gh repo view --json nameWithOwner --jq '.nameWithOwner')
OWNER=$(echo "$REPO_FULL" | cut -d/ -f1)
REPO=$(echo "$REPO_FULL" | cut -d/ -f2)
THREAD_QUERY='{ repository(owner: "'"$OWNER"'", name: "'"$REPO"'") { pullRequest(number: '"$PR_NUMBER"') { reviewThreads(first: 100) { nodes { isResolved } } } } }'

while true; do
  snap=$(GH_PAGER=cat gh pr view "$PR_NUMBER" --repo "$REPO_FULL" \
    --json state,mergeStateStatus,reviewDecision,statusCheckRollup 2>/dev/null || echo '{}')
  state=$(echo "$snap" | jq -r '.state // "UNKNOWN"')
  mergeState=$(echo "$snap" | jq -r '.mergeStateStatus // "UNKNOWN"')
  reviewDecision=$(echo "$snap" | jq -r '.reviewDecision // ""')
  ciFailed=$(echo "$snap" | jq '[(.statusCheckRollup // [])[] | select((.conclusion // "") | IN("FAILURE","ERROR","TIMED_OUT","CANCELLED"))] | length')
  ciPending=$(echo "$snap" | jq '[(.statusCheckRollup // [])[] | select((.status // "") | IN("IN_PROGRESS","QUEUED","PENDING","WAITING"))] | length')
  unresolvedThreads=$(GH_PAGER=cat gh api graphql -f query="$THREAD_QUERY" \
    --jq '[.data.repository.pullRequest.reviewThreads.nodes[] | select(.isResolved == false)] | length' 2>/dev/null || echo 0)
  commentCount=$(GH_PAGER=cat gh api "repos/$OWNER/$REPO/issues/$PR_NUMBER/comments" --jq 'length' 2>/dev/null || echo 0)
  reviewCount=$(GH_PAGER=cat gh api "repos/$OWNER/$REPO/pulls/$PR_NUMBER/reviews" --jq '[.[] | select(.body != "")] | length' 2>/dev/null || echo 0)

  echo "SNAPSHOT state=$state mergeState=$mergeState reviewDecision=$reviewDecision ciFailed=$ciFailed ciPending=$ciPending unresolvedThreads=$unresolvedThreads comments=$commentCount reviews=$reviewCount"

  stop=0
  if [ "$state" = "CLOSED" ] || [ "$state" = "MERGED" ]; then echo "EVENT:PR_CLOSED state=$state"; stop=1; fi
  if [ "$mergeState" = "DIRTY" ]; then echo "EVENT:CONFLICT"; stop=1; fi
  if [ "$mergeState" = "BEHIND" ]; then echo "EVENT:BEHIND"; stop=1; fi
  if [ "$ciFailed" -gt 0 ]; then
    names=$(echo "$snap" | jq -r '[(.statusCheckRollup // [])[] | select((.conclusion // "") | IN("FAILURE","ERROR","TIMED_OUT","CANCELLED")) | .name] | join(",")')
    echo "EVENT:CI_FAILURE count=$ciFailed names=$names"; stop=1
  fi
  if [ "$unresolvedThreads" -gt 0 ]; then echo "EVENT:UNRESOLVED_THREAD count=$unresolvedThreads"; stop=1; fi
  if [ "$commentCount" -gt 0 ]; then echo "EVENT:OPEN_COMMENT count=$commentCount"; stop=1; fi
  if [ "$reviewCount" -gt 0 ]; then echo "EVENT:OPEN_REVIEW count=$reviewCount"; stop=1; fi

  if [ "$stop" -eq 0 ]; then
    if { [ "$mergeState" = "CLEAN" ] || [ "$mergeState" = "UNSTABLE" ]; } && { [ "$reviewDecision" = "APPROVED" ] || [ -z "$reviewDecision" ]; }; then
      echo "EVENT:MERGEABLE mergeState=$mergeState reviewDecision=$reviewDecision"
      stop=1
    fi
  fi

  if [ "$stop" -eq 1 ]; then break; fi

  [ "$ciPending" -gt 0 ] && echo "EVENT:CI_PENDING count=$ciPending"
  [ -n "$reviewDecision" ] && [ "$reviewDecision" != "APPROVED" ] && echo "EVENT:REVIEW_PENDING decision=$reviewDecision"

  sleep 60
done
