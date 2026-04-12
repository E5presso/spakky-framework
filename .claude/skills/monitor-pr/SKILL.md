---
name: monitor-pr
description: PR의 CI/리뷰 상태를 백그라운드로 polling하여 이벤트 발생 시 분기 처리합니다.
argument-hint: "<pr-number>"
user-invocable: false
---

# Monitor PR

인자: PR 번호. 상위 스킬에서 호출.

## 초기화

```bash
REPO_FULL=$(GH_PAGER=cat gh repo view --json nameWithOwner --jq '.nameWithOwner')
OWNER=$(echo $REPO_FULL | cut -d/ -f1)
REPO=$(echo $REPO_FULL | cut -d/ -f2)
MY_LOGIN=$(GH_PAGER=cat gh api user --jq '.login')
```

## Catch-up Sweep

**polling 시작 전과 재시작 전** 반드시 실행. 건너뛰기 금지.

3채널(인라인 스레드, 일반 코멘트, 리뷰 본문)에서 미처리 코멘트를 수집한다. 수집 방법은 "코멘트 수집" 절 참조.

- 미처리 있으면 → 트리아지 후 polling 시작
- 없으면 → 바로 polling 시작

## Polling 스크립트

`isBackground: true`, 5초 간격. `GH_PAGER=cat` 필수(pager hang 방지). `gh --jq` 필수(PR body 제어 문자 대응).

**최초 실행**: baseline을 API에서 캡처. **재시작**: 이전 출력의 `STATE:` 값을 `B_*` 변수에 대입.

```bash
REPO_FULL=$(GH_PAGER=cat gh repo view --json nameWithOwner --jq '.nameWithOwner')
OWNER=$(echo $REPO_FULL | cut -d/ -f1)
REPO=$(echo $REPO_FULL | cut -d/ -f2)
PR_NUMBER={PR_NUMBER}
THREAD_QUERY="{ repository(owner: \"$OWNER\", name: \"$REPO\") { pullRequest(number: $PR_NUMBER) { reviewThreads(first: 100) { nodes { isResolved comments(first: 50) { totalCount } } } } } }"
# 최초: API 캡처 / 재시작: 이전 STATE: 값 대입
B_COMMENTS=$(GH_PAGER=cat gh pr view $PR_NUMBER --repo $REPO_FULL --json comments --jq '.comments | length' 2>/dev/null || echo 0)
B_REVIEWS=$(GH_PAGER=cat gh api repos/$OWNER/$REPO/pulls/$PR_NUMBER/reviews --jq 'length' 2>/dev/null || echo 0)
B_THREADS=$(GH_PAGER=cat gh api graphql -f query="$THREAD_QUERY" --jq '.data.repository.pullRequest.reviewThreads.nodes | length' 2>/dev/null || echo 0)
B_REPLIES=$(GH_PAGER=cat gh api graphql -f query="$THREAD_QUERY" --jq '[.data.repository.pullRequest.reviewThreads.nodes[].comments.totalCount] | add // 0' 2>/dev/null || echo 0)
B_REVIEW_DECISION=$(GH_PAGER=cat gh pr view $PR_NUMBER --repo $REPO_FULL --json reviewDecision --jq '.reviewDecision' 2>/dev/null || echo "")
POLL_START=$(date -u +%Y-%m-%dT%H:%M:%SZ)
while true; do
  pr_state=$(GH_PAGER=cat gh pr view $PR_NUMBER --repo $REPO_FULL --json state --jq '.state' 2>/dev/null || echo "")
  if [ "$pr_state" = "CLOSED" ] || [ "$pr_state" = "MERGED" ]; then
    echo "EVENT:PR_CLOSED state=$pr_state"; echo "STATE:POLL_START=$POLL_START"; break; fi
  comments=$(GH_PAGER=cat gh pr view $PR_NUMBER --repo $REPO_FULL --json comments --jq '.comments | length' 2>/dev/null || echo 0)
  reviews=$(GH_PAGER=cat gh api repos/$OWNER/$REPO/pulls/$PR_NUMBER/reviews --jq 'length' 2>/dev/null || echo 0)
  threads=$(GH_PAGER=cat gh api graphql -f query="$THREAD_QUERY" --jq '.data.repository.pullRequest.reviewThreads.nodes | length' 2>/dev/null || echo 0)
  replies=$(GH_PAGER=cat gh api graphql -f query="$THREAD_QUERY" --jq '[.data.repository.pullRequest.reviewThreads.nodes[].comments.totalCount] | add // 0' 2>/dev/null || echo 0)
  mergeState=$(GH_PAGER=cat gh pr view $PR_NUMBER --repo $REPO_FULL --json mergeStateStatus --jq '.mergeStateStatus' 2>/dev/null || echo "")
  reviewDecision=$(GH_PAGER=cat gh pr view $PR_NUMBER --repo $REPO_FULL --json reviewDecision --jq '.reviewDecision' 2>/dev/null || echo "")
  failedCount=$(GH_PAGER=cat gh pr view $PR_NUMBER --repo $REPO_FULL --json statusCheckRollup --jq '[(.statusCheckRollup // [])[] | select(.conclusion == "FAILURE" or .state == "FAILURE" or .conclusion == "ERROR" or .state == "ERROR")] | length' 2>/dev/null || echo 0)
  found=0
  if [ "$comments" -gt "$B_COMMENTS" ] || [ "$reviews" -gt "$B_REVIEWS" ]; then
    echo "EVENT:NEW_COMMENT comments=$comments(was:$B_COMMENTS) reviews=$reviews(was:$B_REVIEWS)"; found=1; fi
  if [ "$threads" -gt "$B_THREADS" ] || [ "$replies" -gt "$B_REPLIES" ]; then
    echo "EVENT:NEW_REVIEW_COMMENT threads=$threads(was:$B_THREADS) replies=$replies(was:$B_REPLIES)"; found=1; fi
  if [ "$failedCount" -gt 0 ]; then
    failedNames=$(GH_PAGER=cat gh pr view $PR_NUMBER --repo $REPO_FULL --json statusCheckRollup --jq '[(.statusCheckRollup // [])[] | select(.conclusion == "FAILURE" or .state == "FAILURE" or .conclusion == "ERROR" or .state == "ERROR") | .name] | join(",")' 2>/dev/null || echo "unknown")
    echo "EVENT:CI_FAILURE count=$failedCount names=$failedNames"; found=1; fi
  if [ "$mergeState" = "DIRTY" ]; then echo "EVENT:CONFLICT"; found=1; fi
  if [ "$reviewDecision" != "$B_REVIEW_DECISION" ] && [ -n "$B_REVIEW_DECISION" ]; then
    echo "EVENT:REVIEW_STATE_CHANGED from=$B_REVIEW_DECISION to=$reviewDecision"; found=1; fi
  B_REVIEW_DECISION=$reviewDecision
  if [ "$mergeState" = "CLEAN" ] || [ "$mergeState" = "UNSTABLE" ]; then
    echo "EVENT:MERGEABLE mergeState=$mergeState reviewDecision=$reviewDecision"; found=1; fi
  if [ "$found" -eq 1 ]; then
    echo "STATE:COMMENT_COUNT=$comments"; echo "STATE:REVIEW_COUNT=$reviews"
    echo "STATE:THREAD_COUNT=$threads"; echo "STATE:THREAD_REPLY_COUNT=$replies"
    echo "STATE:REVIEW_DECISION=$reviewDecision"; echo "STATE:MERGE_STATE=$mergeState"
    echo "STATE:POLL_START=$POLL_START"; break; fi
  sleep 5
done
```

## 이벤트 처리

출력에서 `EVENT:` 라인을 모두 추출, `STATE:` 라인에서 baseline을 기록한 후, 아래 우선순위로 순차 처리한다.

| 우선순위 | 이벤트 | 처리 |
|---------|--------|------|
| 0 | `PR_CLOSED` | 사용자에 알림 후 모니터링 종료 |
| 1 | `CONFLICT` | `git fetch` → conflict 해결 → push |
| 2 | `CI_FAILURE` | 로컬 재현(`ruff`/`pyrefly`/`pytest`) → 통과 시 사용자 보고, 실패 시 수정 & push |
| 3 | `NEW_COMMENT` / `NEW_REVIEW_COMMENT` | 코멘트 수집 → `/review-pr` → 재리뷰 요청 |
| 4 | `REVIEW_STATE_CHANGED` | 사용자에 알림 |
| 5 | `MERGEABLE` | **단독일 때만** Phase 7 전환 (다른 이벤트 동시 시 무시, 재평가) |

## 코멘트 수집

`$SINCE_TS`는 `STATE:POLL_START` 값. `gh --jq`는 `--arg` 미지원 → `| jq --arg me "$MY_LOGIN"` 파이프 사용.

**채널 1: 인라인 스레드** — 미해결 + SINCE 이후 활동

```bash
GH_PAGER=cat gh api graphql -f query='{ repository(owner: "'"$OWNER"'", name: "'"$REPO"'") { pullRequest(number: '"$PR_NUMBER"') { reviewThreads(first: 100) { nodes { id isResolved comments(first: 10) { nodes { body author { login } path originalLine createdAt } } } } } } }' \
  --jq "[.data.repository.pullRequest.reviewThreads.nodes[] | select(.isResolved == false) | select(.comments.nodes[-1].createdAt > \"$SINCE_TS\")]"
```

**채널 2: 일반 PR 코멘트** — Bot·자신 제외, 자신 응답 없는 것

```bash
GH_PAGER=cat gh api repos/$OWNER/$REPO/issues/$PR_NUMBER/comments | jq --arg me "$MY_LOGIN" '
  [.[] | select(.user.type != "Bot")] as $all |
  [.[] | select(.user.type != "Bot" and .user.login != $me)] as $others |
  [$others[] | . as $c |
    ($all | to_entries | map(select(.value.id == $c.id)) | .[0].key) as $idx |
    if ($idx + 1) < ($all | length)
    then ([$all[($idx+1):][].user.login] | any(. == $me))
    else false end |
    if . then empty else $c end
  ] | [.[] | {id: .id, author: .user.login, body: .body, created: .created_at}]'
```

**채널 3: 리뷰 본문** — body 비어있지 않은 리뷰 (처리 완료 = 해당 시각 이후 `$MY_LOGIN` 코멘트 존재)

```bash
GH_PAGER=cat gh api repos/$OWNER/$REPO/pulls/$PR_NUMBER/reviews \
  --jq '[.[] | select(.body != "" and .user.type != "Bot") | {id: .id, author: .user.login, body: .body, submitted: .submitted_at}]'
```

3채널 합산 > 0이면 `/review-pr` 실행 후 `gh pr edit --add-reviewer {REVIEWER_LOGIN}`.

## Polling 재시작

1. **Catch-up sweep** (건너뛰기 금지) → 미처리 있으면 트리아지 후 반복
2. 이전 출력 `STATE:` 값으로 `B_*` baseline 복원 (에이전트가 코멘트/리뷰를 추가했으면 API 재캡처)
3. polling 루프 재시작

**종료**: `MERGEABLE` 단독 → Phase 7 / `PR_CLOSED` → 종료 / 사용자 요청 시 종료

$ARGUMENTS
