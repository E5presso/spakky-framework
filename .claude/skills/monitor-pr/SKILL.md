---
name: monitor-pr
description: PR의 CI/리뷰 상태를 백그라운드로 polling하여 이벤트 발생 시 분기 처리합니다.
argument-hint: "<pr-number>"
user-invocable: false
---

# Monitor PR — PR 상태 모니터링 서브스킬

PR 번호를 받아 백그라운드에서 CI/리뷰 상태를 polling하고, 이벤트 발생 시 적절한 처리를 수행한다.

## 사용법

서브에이전트 또는 상위 스킬에서 호출:

```
/monitor-pr 53
```

인자: PR 번호

## Polling 스크립트

**백그라운드 Bash**로 실행 (`run_in_background: true`, 10초 간격):

```bash
OWNER_REPO=$(gh repo view --json nameWithOwner --jq '.nameWithOwner')
OWNER=$(echo $OWNER_REPO | cut -d/ -f1)
REPO=$(echo $OWNER_REPO | cut -d/ -f2)
PR_NUMBER={PR_NUMBER}
LAST_COMMENT_COUNT=$(gh pr view $PR_NUMBER --json comments --jq '.comments | length' 2>/dev/null || echo 0)
LAST_UNRESOLVED_COUNT=$(gh api graphql -f query="{ repository(owner: \"$OWNER\", name: \"$REPO\") { pullRequest(number: $PR_NUMBER) { reviewThreads(first: 100) { nodes { isResolved } } } } }" --jq '[.data.repository.pullRequest.reviewThreads.nodes[] | select(.isResolved == false)] | length' 2>/dev/null || echo 0)
LAST_REVIEW_DECISION=$(gh pr view $PR_NUMBER --json reviewDecision --jq '.reviewDecision' 2>/dev/null || echo "")
while true; do
   mergeState=$(gh pr view $PR_NUMBER --json mergeStateStatus --jq '.mergeStateStatus' 2>/dev/null || echo "")
   reviewDecision=$(gh pr view $PR_NUMBER --json reviewDecision --jq '.reviewDecision' 2>/dev/null || echo "")
   commentCount=$(gh pr view $PR_NUMBER --json comments --jq '.comments | length' 2>/dev/null || echo 0)
   unresolvedCount=$(gh api graphql -f query="{ repository(owner: \"$OWNER\", name: \"$REPO\") { pullRequest(number: $PR_NUMBER) { reviewThreads(first: 100) { nodes { isResolved } } } } }" --jq '[.data.repository.pullRequest.reviewThreads.nodes[] | select(.isResolved == false)] | length' 2>/dev/null || echo 0)
   failedChecks=$(gh pr view $PR_NUMBER --json statusCheckRollup --jq '[.statusCheckRollup[] | select(.conclusion == "FAILURE" or .state == "FAILURE")] | length' 2>/dev/null || echo 0)

   # 1. 새 일반 코멘트 (코멘트가 merge 상태보다 우선)
   if [ "$commentCount" -gt "$LAST_COMMENT_COUNT" ]; then
      echo "NEW_COMMENT_DETECTED count=$commentCount"
      LAST_COMMENT_COUNT=$commentCount
      break
   fi

   # 2. 미해결 인라인 리뷰 스레드 (resolved 제외)
   if [ "$unresolvedCount" -gt "$LAST_UNRESOLVED_COUNT" ]; then
      echo "NEW_REVIEW_COMMENT_DETECTED count=$unresolvedCount"
      LAST_UNRESOLVED_COUNT=$unresolvedCount
      break
   fi

   # 3. CI 실패
   if [ "$failedChecks" -gt "0" ]; then
      echo "CI_FAILURE_DETECTED"
      gh pr view $PR_NUMBER --json statusCheckRollup --jq '[.statusCheckRollup[] | select(.conclusion == "FAILURE" or .state == "FAILURE")]'
      break
   fi

   # 4. 리뷰 상태 변경
   if [ "$reviewDecision" != "$LAST_REVIEW_DECISION" ] && [ -n "$LAST_REVIEW_DECISION" ]; then
      echo "REVIEW_STATE_CHANGED from=$LAST_REVIEW_DECISION to=$reviewDecision"
      break
   fi
   LAST_REVIEW_DECISION=$reviewDecision

   # 5. Merge 가능 (후순위)
   if [ "$mergeState" = "CLEAN" ] || [ "$mergeState" = "UNSTABLE" ]; then
      echo "MERGEABLE_DETECTED mergeState=$mergeState reviewDecision=$reviewDecision"
      break
   fi

   sleep 10
done
```

## 이벤트 분기 처리

백그라운드 완료 알림을 받으면 출력을 읽고 이벤트 타입에 따라 분기한다:

| 이벤트 | 처리 |
|--------|------|
| `NEW_COMMENT_DETECTED` | 리뷰 코멘트 감지 절차 실행 후 polling 재시작 |
| `NEW_REVIEW_COMMENT_DETECTED` | 리뷰 코멘트 감지 절차 실행 후 polling 재시작 |
| `CI_FAILURE_DETECTED` | CI 실패 감지 절차 실행 후 polling 재시작 |
| `REVIEW_STATE_CHANGED` | 사용자에게 알리고 상태에 따라 Phase 7 또는 polling 재시작 |
| `MERGEABLE_DETECTED` | Phase 7로 전환 |

### CI 실패 감지 시

1. 로컬에서 해당 패키지의 검증을 재현한다:
   ```bash
   cd <package-dir>
   uv run ruff check .
   uv run pyrefly check
   uv run pytest
   ```
2. 로컬 통과 → "로컬 검증 통과, CI 인프라 문제 가능성" 보고 + 사용자 판단 요청.
3. 로컬 실패 → 원인 수정 + 커밋 & push 후 polling 재시작.

### 리뷰 코멘트 감지 시

1. 사용자에게 새 리뷰 코멘트가 달렸음을 알린다.
2. `/review-pr` 스킬을 실행한다.
3. 트리아지 완료 후 리뷰어에게 재리뷰를 요청한다:
   ```bash
   gh pr edit {PR_NUMBER} --add-reviewer {REVIEWER_LOGIN}
   ```

### Polling 재시작

이벤트 처리 후 다시 동일한 polling 루프를 백그라운드로 실행한다.
`LAST_COMMENT_COUNT`, `LAST_UNRESOLVED_COUNT`, `LAST_REVIEW_DECISION`은 현재 값으로 초기화하여 중복 감지를 방지한다.

$ARGUMENTS
