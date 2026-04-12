---
name: monitor-pr
description: PR의 CI/리뷰 상태를 백그라운드로 polling하여 이벤트 발생 시 분기 처리합니다.
argument-hint: "<pr-number>"
user-invocable: false
---

# Monitor PR

인자: PR 번호. 상위 스킬에서 호출.

## 원칙

- **스냅샷 기반**: 매 tick마다 PR의 전체 상태를 평가. 이전 대비 diff 추적 없음 (타이밍 이슈로 놓치기 쉬움).
- **60초 간격**: rate limit 회피, 단순성.
- **모든 허들 식별**: 병합 가로막는 요소를 누락 없이 감지.
- **모든 코멘트 감지**: bot/사람 구분 없이 모든 코멘트·리뷰를 허들로 간주.

## 실행

스크립트는 `monitor.sh`에 정의되어 있다. `Monitor` 도구로 백그라운드 실행:

```
bash .claude/skills/monitor-pr/monitor.sh <PR_NUMBER>
```

`persistent: true`로 실행하되, 스크립트는 병합 허들이나 `MERGEABLE`을 감지하면 스스로 루프를 종료한다. 이벤트 처리 후 `Monitor`를 재호출하여 재시작한다.

## 감지 항목

| 허들 | 감지 조건 | 이벤트 |
|------|----------|--------|
| PR 종료 | `state in {CLOSED, MERGED}` | `PR_CLOSED` |
| Conflict | `mergeStateStatus == DIRTY` | `CONFLICT` |
| Base 뒤처짐 | `mergeStateStatus == BEHIND` | `BEHIND` |
| CI 실패 | 체크 `conclusion in {FAILURE, ERROR, TIMED_OUT, CANCELLED}` | `CI_FAILURE` |
| CI 진행 중 | 체크 `status in {IN_PROGRESS, QUEUED, PENDING, WAITING}` | `CI_PENDING` (대기) |
| 미해결 review thread | `reviewThreads` 중 `isResolved == false` 존재 | `UNRESOLVED_THREAD` |
| 코멘트 존재 | issues API `length > 0` (bot 포함 전부) | `OPEN_COMMENT` |
| 리뷰 본문 존재 | reviews API `body != ""` (bot 포함 전부) | `OPEN_REVIEW` |
| 리뷰 미승인 | `reviewDecision != "APPROVED"` (공란 제외) | `REVIEW_PENDING` (대기) |
| 병합 가능 | `mergeStateStatus in {CLEAN, UNSTABLE}` + `reviewDecision in {APPROVED, ""}` | `MERGEABLE` |

`CI_PENDING` / `REVIEW_PENDING`은 대기 상태 알림(루프 계속). 나머지 이벤트는 루프를 종료한다.

## 이벤트 처리 우선순위

monitor 종료 후 stdout의 `EVENT:` 라인을 전부 읽고 아래 순으로 모두 처리:

| 우선순위 | 이벤트 | 처리 |
|---------|--------|------|
| 0 | `PR_CLOSED` | 사용자 알림 후 모니터링 종료 |
| 1 | `CONFLICT` | conflict 해결 → push → 재시작 |
| 2 | `BEHIND` | develop merge → push → 재시작 |
| 3 | `CI_FAILURE` | 로컬 재현 → 수정 → push → 재시작 |
| 4 | `OPEN_COMMENT` / `OPEN_REVIEW` / `UNRESOLVED_THREAD` | 코멘트 수집 → `/review-pr` → 재리뷰 요청 → 재시작 |
| 5 | `MERGEABLE` | Phase 7 전환 |

## 코멘트 수집 (`/review-pr`용)

```bash
# 미해결 인라인 스레드
GH_PAGER=cat gh api graphql -f query='{ repository(owner: "'"$OWNER"'", name: "'"$REPO"'") { pullRequest(number: '"$PR_NUMBER"') { reviewThreads(first: 100) { nodes { id isResolved comments(first: 10) { nodes { body author { login } path originalLine createdAt } } } } } } }' --jq '[.data.repository.pullRequest.reviewThreads.nodes[] | select(.isResolved == false)]'

# PR 코멘트 (전부)
GH_PAGER=cat gh api "repos/$OWNER/$REPO/issues/$PR_NUMBER/comments" --jq '[.[] | {id, author: .user.login, body, created: .created_at}]'

# 리뷰 본문 (전부)
GH_PAGER=cat gh api "repos/$OWNER/$REPO/pulls/$PR_NUMBER/reviews" --jq '[.[] | select(.body != "") | {id, author: .user.login, body, submitted: .submitted_at}]'
```

## CLEANUP

- 이벤트 처리 후 재시작하지 않을 경우 `TaskStop`으로 monitor 터미널 종료.
- `PR_CLOSED` 또는 `MERGEABLE` 처리 완료 시 재시작하지 않는다.

$ARGUMENTS
