---
description: PR의 CI/리뷰 상태를 백그라운드로 polling하여 이벤트 발생 시 분기 처리합니다.
argument-hint: "<pr-number>"
user-invocable: false
---

# Monitor PR — PR 상태 모니터링 서브스킬

PR 번호를 받아 백그라운드에서 CI/리뷰 상태를 polling하고, 이벤트 발생 시 적절한 처리를 수행한다.

## 사용법

상위 스킬에서 호출:

```
/doc:monitor-pr 105
```

인자: PR 번호

## 초기화

```bash
REPO_FULL=$(GH_PAGER=cat gh repo view --json nameWithOwner --jq '.nameWithOwner')
OWNER=$(echo $REPO_FULL | cut -d/ -f1)
REPO=$(echo $REPO_FULL | cut -d/ -f2)
MY_LOGIN=$(GH_PAGER=cat gh api user --jq '.login')
```

## 미처리 코멘트 확인

**초기 시작 전과 매 polling 재시작 전** 모두 실행한다.

3채널(인라인 스레드, 일반 코멘트, 리뷰 본문)에서 미처리 코멘트를 수집한다.

- 미처리 코멘트가 있으면 → 즉시 트리아지를 실행한 후 polling을 시작한다.
- 미처리 코멘트가 없으면 → 바로 polling을 시작한다.

수집 방법은 "리뷰 코멘트 감지 시 > 코멘트 수집" 절차를 참조한다.

## Polling 스크립트

**백그라운드 Bash**로 실행 (`isBackground: true`, 5초 간격):

> **`--jq` 필수**: `gh pr view --json ... | jq` 파이프는 PR body에 제어 문자(줄바꿈)가 포함되면 jq 파싱이 실패한다. 반드시 `gh` 내장 `--jq` 플래그를 사용하여 필드별로 개별 호출한다.
> **`GH_PAGER=cat` 필수**: `gh` 명령이 pager를 열면 백그라운드에서 hang된다.

```bash
REPO_FULL=$(GH_PAGER=cat gh repo view --json nameWithOwner --jq '.nameWithOwner')
OWNER=$(echo $REPO_FULL | cut -d/ -f1)
REPO=$(echo $REPO_FULL | cut -d/ -f2)
PR_NUMBER={PR_NUMBER}
THREAD_QUERY="{ repository(owner: \"$OWNER\", name: \"$REPO\") { pullRequest(number: $PR_NUMBER) { reviewThreads(first: 100) { nodes { isResolved comments(first: 50) { totalCount } } } } } }"
LAST_COMMENT_COUNT=$(GH_PAGER=cat gh pr view $PR_NUMBER --repo $REPO_FULL --json comments --jq '.comments | length' 2>/dev/null || echo 0)
LAST_REVIEW_COUNT=$(GH_PAGER=cat gh api repos/$OWNER/$REPO/pulls/$PR_NUMBER/reviews --jq 'length' 2>/dev/null || echo 0)
LAST_TOTAL_THREAD_COUNT=$(GH_PAGER=cat gh api graphql -f query="$THREAD_QUERY" --jq '.data.repository.pullRequest.reviewThreads.nodes | length' 2>/dev/null || echo 0)
LAST_TOTAL_THREAD_REPLY_COUNT=$(GH_PAGER=cat gh api graphql -f query="$THREAD_QUERY" --jq '[.data.repository.pullRequest.reviewThreads.nodes[].comments.totalCount] | add // 0' 2>/dev/null || echo 0)
LAST_REVIEW_DECISION=$(GH_PAGER=cat gh pr view $PR_NUMBER --repo $REPO_FULL --json reviewDecision --jq '.reviewDecision' 2>/dev/null || echo "")
POLL_START_TS=$(date -u +%Y-%m-%dT%H:%M:%SZ)
while true; do
  mergeState=$(GH_PAGER=cat gh pr view $PR_NUMBER --repo $REPO_FULL --json mergeStateStatus --jq '.mergeStateStatus' 2>/dev/null || echo "")
  reviewDecision=$(GH_PAGER=cat gh pr view $PR_NUMBER --repo $REPO_FULL --json reviewDecision --jq '.reviewDecision' 2>/dev/null || echo "")
  commentCount=$(GH_PAGER=cat gh pr view $PR_NUMBER --repo $REPO_FULL --json comments --jq '.comments | length' 2>/dev/null || echo 0)
  reviewCount=$(GH_PAGER=cat gh api repos/$OWNER/$REPO/pulls/$PR_NUMBER/reviews --jq 'length' 2>/dev/null || echo 0)
  totalThreadCount=$(GH_PAGER=cat gh api graphql -f query="$THREAD_QUERY" --jq '.data.repository.pullRequest.reviewThreads.nodes | length' 2>/dev/null || echo 0)
  totalThreadReplyCount=$(GH_PAGER=cat gh api graphql -f query="$THREAD_QUERY" --jq '[.data.repository.pullRequest.reviewThreads.nodes[].comments.totalCount] | add // 0' 2>/dev/null || echo 0)
  failedChecks=$(GH_PAGER=cat gh pr view $PR_NUMBER --repo $REPO_FULL --json statusCheckRollup --jq '[.statusCheckRollup[] | select(.conclusion == "FAILURE" or .state == "FAILURE" or .conclusion == "ERROR" or .state == "ERROR")] | length' 2>/dev/null || echo 0)

  # 1. 새 일반 코멘트 또는 새 리뷰 본문 (코멘트가 merge 상태보다 우선)
  if [ "$commentCount" -gt "$LAST_COMMENT_COUNT" ] || [ "$reviewCount" -gt "$LAST_REVIEW_COUNT" ]; then
    echo "NEW_COMMENT_DETECTED comments=$commentCount reviews=$reviewCount since=$POLL_START_TS"
    LAST_COMMENT_COUNT=$commentCount
    LAST_REVIEW_COUNT=$reviewCount
    break
  fi

  # 2. 인라인 리뷰 스레드 변화 — 새 스레드 추가 또는 기존 스레드에 새 답글
  if [ "$totalThreadCount" -gt "$LAST_TOTAL_THREAD_COUNT" ] || [ "$totalThreadReplyCount" -gt "$LAST_TOTAL_THREAD_REPLY_COUNT" ]; then
    echo "NEW_REVIEW_COMMENT_DETECTED threads=$totalThreadCount replies=$totalThreadReplyCount since=$POLL_START_TS"
    LAST_TOTAL_THREAD_COUNT=$totalThreadCount
    LAST_TOTAL_THREAD_REPLY_COUNT=$totalThreadReplyCount
    break
  fi

  # 3. CI 실패 또는 에러
  if [ "$failedChecks" -gt "0" ]; then
    echo "CI_FAILURE_DETECTED"
    GH_PAGER=cat gh pr view $PR_NUMBER --repo $REPO_FULL --json statusCheckRollup --jq '[.statusCheckRollup[] | select(.conclusion == "FAILURE" or .state == "FAILURE" or .conclusion == "ERROR" or .state == "ERROR")]'
    break
  fi

  # 4. Merge conflict
  if [ "$mergeState" = "DIRTY" ]; then
    echo "CONFLICT_DETECTED mergeState=$mergeState"
    break
  fi

  # 5. 리뷰 상태 변경
  if [ "$reviewDecision" != "$LAST_REVIEW_DECISION" ] && [ -n "$LAST_REVIEW_DECISION" ]; then
    echo "REVIEW_STATE_CHANGED from=$LAST_REVIEW_DECISION to=$reviewDecision"
    break
  fi
  LAST_REVIEW_DECISION=$reviewDecision

  # 6. Merge 가능
  if [ "$mergeState" = "CLEAN" ] || [ "$mergeState" = "UNSTABLE" ]; then
    echo "MERGEABLE_DETECTED mergeState=$mergeState reviewDecision=$reviewDecision"
    break
  fi

  sleep 5
done
```

## 이벤트 분기 처리

백그라운드 완료 알림을 받으면 출력을 읽고 이벤트 타입에 따라 분기한다:

| 이벤트 | 처리 |
|--------|------|
| `NEW_COMMENT_DETECTED` | 리뷰 코멘트 감지 절차 실행 후 polling 재시작 |
| `NEW_REVIEW_COMMENT_DETECTED` | 리뷰 코멘트 감지 절차 실행 후 polling 재시작 |
| `CI_FAILURE_DETECTED` | CI 실패 감지 절차 실행 후 polling 재시작 |
| `CONFLICT_DETECTED` | merge conflict 해결 후 push, polling 재시작 |
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

1. **코멘트 수집** — 아래 3가지 채널을 **모두** 조회하여 미처리 코멘트를 수집한다.

   `gh --jq`는 `--arg`를 지원하지 않으므로, `| jq --arg me "$MY_LOGIN"` 파이프를 사용한다.

   **채널 1: 인라인 리뷰 스레드** — 미해결 + 최근 활동 있음
   ```bash
   GH_PAGER=cat gh api graphql -f query='{ repository(owner: "'"$OWNER"'", name: "'"$REPO"'") { pullRequest(number: '"$PR_NUMBER"') { reviewThreads(first: 100) { nodes { id isResolved comments(first: 10) { nodes { body author { login } path line: originalLine createdAt } } } } } } }' \
     --jq "[.data.repository.pullRequest.reviewThreads.nodes[] | select(.isResolved == false) | select(.comments.nodes[-1].createdAt > \"$SINCE_TS\")]"
   ```
   `$SINCE_TS`는 polling 출력의 `since=` 값. 마지막 코멘트가 polling 시작 이후에 작성된 미해결 스레드만 반환한다.

   **채널 2: 일반 PR 코멘트** — Bot과 `$MY_LOGIN` 제외, `$MY_LOGIN` 응답이 뒤따르지 않는 것
   ```bash
   GH_PAGER=cat gh api repos/$OWNER/$REPO/issues/$PR_NUMBER/comments | jq --arg me "$MY_LOGIN" '
     [.[] | select(.user.type != "Bot")] as $all |
     [.[] | select(.user.type != "Bot" and .user.login != $me)] as $others |
     [$others[] |
       . as $c |
       ($all | to_entries | map(select(.value.id == $c.id)) | .[0].key) as $idx |
       if ($idx + 1) < ($all | length)
       then ([$all[($idx+1):][].user.login] | any(. == $me))
       else false end |
       if . then empty else $c end
     ] | [.[] | {id: .id, author: .user.login, body: .body, created: .created_at}]'
   ```

   **채널 3: 리뷰 본문** — body가 비어있지 않은 리뷰
   ```bash
   GH_PAGER=cat gh api repos/$OWNER/$REPO/pulls/$PR_NUMBER/reviews \
     --jq '[.[] | select(.body != "" and .user.type != "Bot") | {id: .id, author: .user.login, body: .body, submitted: .submitted_at}]'
   ```
   처리 완료 여부는 해당 리뷰 시각 이후에 `$MY_LOGIN`의 PR 코멘트가 존재하는지로 판정.

2. 미처리 코멘트가 있으면 `/review-pr` 스킬을 실행한다.

3. 트리아지 완료 후 코멘트를 남긴 리뷰어에게 재리뷰를 요청한다:
   ```bash
   GH_PAGER=cat gh pr edit $PR_NUMBER --repo $REPO_FULL --add-reviewer {REVIEWER_LOGIN}
   ```

### Polling 재시작

이벤트 처리 후 **"미처리 코멘트 확인" 절차를 실행**한 뒤, 동일한 polling 루프를 백그라운드로 재시작한다.

`LAST_COMMENT_COUNT`, `LAST_REVIEW_COUNT`, `LAST_TOTAL_THREAD_COUNT`, `LAST_TOTAL_THREAD_REPLY_COUNT`, `LAST_REVIEW_DECISION`, `POLL_START_TS`는 현재 값으로 초기화하여 중복 감지를 방지한다.

**종료 조건**: PR의 merge button이 활성화된 상태 (mergeable + checks pass + review approved)

$ARGUMENTS
