---
description: PR의 CI/리뷰 상태를 백그라운드로 polling하여 이벤트 발생 시 분기 처리합니다.
argument-hint: "<pr-number>"
user-invocable: false
---

# Monitor PR — PR 상태 모니터링 서브스킬

PR 번호를 받아 백그라운드에서 CI/리뷰 상태를 polling하고, 이벤트 발생 시 적절한 처리를 수행한다.

## 설계 원칙

1. **Multi-event 수집**: 매 polling 반복에서 모든 이벤트를 동시에 감지한다. 첫 번째 이벤트에서 break하지 않는다.
2. **State snapshot**: polling 출력에 현재 상태값을 포함하여, 재시작 시 정확한 baseline을 보장한다.
3. **Mandatory catch-up**: 이벤트 처리 후 polling 재시작 전에 반드시 3채널 미처리 코멘트를 sweep한다.
4. **PR 수명 확인**: 매 iteration마다 PR이 OPEN 상태인지 확인하여 무한 루프를 방지한다.

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

## 미처리 코멘트 확인 (Catch-up Sweep)

**초기 시작 전과 매 polling 재시작 전** 반드시 실행한다. 건너뛰기 절대 금지.

3채널(인라인 스레드, 일반 코멘트, 리뷰 본문)에서 미처리 코멘트를 수집한다.

- 미처리 코멘트가 있으면 → 즉시 트리아지를 실행한 후 polling을 시작한다.
- 미처리 코멘트가 없으면 → 바로 polling을 시작한다.

수집 방법은 "리뷰 코멘트 감지 시 > 코멘트 수집" 절차를 참조한다.

> **왜 매번 sweep하는가?** polling이 break된 후 에이전트가 이벤트를 처리하는 동안 새 코멘트가 도착할 수 있다. 타이밍 gap으로 인한 코멘트 누락을 방지하려면 polling 재시작 직전에 반드시 3채널을 한 번 더 확인해야 한다.

## Polling 스크립트

**백그라운드**로 실행 (`isBackground: true`, 5초 간격):

> **`--jq` 필수**: `gh pr view --json ... | jq` 파이프는 PR body에 제어 문자(줄바꿈)가 포함되면 jq 파싱이 실패한다. 반드시 `gh` 내장 `--jq` 플래그를 사용하여 필드별로 개별 호출한다.
> **`GH_PAGER=cat` 필수**: `gh` 명령이 pager를 열면 백그라운드에서 hang된다.

### Baseline 초기화

polling 스크립트 시작 시 **현재 상태를 baseline으로 캡처**한다. 재시작 시에는 이전 polling 출력의 `STATE:` 값을 사용한다.

```bash
REPO_FULL=$(GH_PAGER=cat gh repo view --json nameWithOwner --jq '.nameWithOwner')
OWNER=$(echo $REPO_FULL | cut -d/ -f1)
REPO=$(echo $REPO_FULL | cut -d/ -f2)
PR_NUMBER={PR_NUMBER}
THREAD_QUERY="{ repository(owner: \"$OWNER\", name: \"$REPO\") { pullRequest(number: $PR_NUMBER) { reviewThreads(first: 100) { nodes { isResolved comments(first: 50) { totalCount } } } } } }"
```

**최초 실행 시** baseline을 API에서 캡처:

```bash
B_COMMENTS=$(GH_PAGER=cat gh pr view $PR_NUMBER --repo $REPO_FULL --json comments --jq '.comments | length' 2>/dev/null || echo 0)
B_REVIEWS=$(GH_PAGER=cat gh api repos/$OWNER/$REPO/pulls/$PR_NUMBER/reviews --jq 'length' 2>/dev/null || echo 0)
B_THREADS=$(GH_PAGER=cat gh api graphql -f query="$THREAD_QUERY" --jq '.data.repository.pullRequest.reviewThreads.nodes | length' 2>/dev/null || echo 0)
B_REPLIES=$(GH_PAGER=cat gh api graphql -f query="$THREAD_QUERY" --jq '[.data.repository.pullRequest.reviewThreads.nodes[].comments.totalCount] | add // 0' 2>/dev/null || echo 0)
B_REVIEW_DECISION=$(GH_PAGER=cat gh pr view $PR_NUMBER --repo $REPO_FULL --json reviewDecision --jq '.reviewDecision' 2>/dev/null || echo "")
```

**재시작 시**는 이전 polling 출력의 `STATE:` 라인에서 baseline을 복원한다:

```bash
B_COMMENTS={이전 출력의 STATE:COMMENT_COUNT 값}
B_REVIEWS={이전 출력의 STATE:REVIEW_COUNT 값}
B_THREADS={이전 출력의 STATE:THREAD_COUNT 값}
B_REPLIES={이전 출력의 STATE:THREAD_REPLY_COUNT 값}
B_REVIEW_DECISION="{이전 출력의 STATE:REVIEW_DECISION 값}"
```

### Multi-event Polling Loop

```bash
POLL_START=$(date -u +%Y-%m-%dT%H:%M:%SZ)
while true; do
  # 0. PR 수명 확인 — CLOSED/MERGED면 즉시 종료
  pr_state=$(GH_PAGER=cat gh pr view $PR_NUMBER --repo $REPO_FULL --json state --jq '.state' 2>/dev/null || echo "")
  if [ "$pr_state" = "CLOSED" ] || [ "$pr_state" = "MERGED" ]; then
    echo "EVENT:PR_CLOSED state=$pr_state"
    echo "STATE:POLL_START=$POLL_START"
    break
  fi

  # 현재 상태 수집
  comments=$(GH_PAGER=cat gh pr view $PR_NUMBER --repo $REPO_FULL --json comments --jq '.comments | length' 2>/dev/null || echo 0)
  reviews=$(GH_PAGER=cat gh api repos/$OWNER/$REPO/pulls/$PR_NUMBER/reviews --jq 'length' 2>/dev/null || echo 0)
  threads=$(GH_PAGER=cat gh api graphql -f query="$THREAD_QUERY" --jq '.data.repository.pullRequest.reviewThreads.nodes | length' 2>/dev/null || echo 0)
  replies=$(GH_PAGER=cat gh api graphql -f query="$THREAD_QUERY" --jq '[.data.repository.pullRequest.reviewThreads.nodes[].comments.totalCount] | add // 0' 2>/dev/null || echo 0)
  mergeState=$(GH_PAGER=cat gh pr view $PR_NUMBER --repo $REPO_FULL --json mergeStateStatus --jq '.mergeStateStatus' 2>/dev/null || echo "")
  reviewDecision=$(GH_PAGER=cat gh pr view $PR_NUMBER --repo $REPO_FULL --json reviewDecision --jq '.reviewDecision' 2>/dev/null || echo "")
  failedCount=$(GH_PAGER=cat gh pr view $PR_NUMBER --repo $REPO_FULL --json statusCheckRollup --jq '[(.statusCheckRollup // [])[] | select(.conclusion == "FAILURE" or .state == "FAILURE" or .conclusion == "ERROR" or .state == "ERROR")] | length' 2>/dev/null || echo 0)

  # 모든 이벤트를 수집 — 하나라도 감지되면 found=1
  found=0

  # 1. 새 일반 코멘트 또는 새 리뷰 본문
  if [ "$comments" -gt "$B_COMMENTS" ] || [ "$reviews" -gt "$B_REVIEWS" ]; then
    echo "EVENT:NEW_COMMENT comments=$comments(was:$B_COMMENTS) reviews=$reviews(was:$B_REVIEWS)"
    found=1
  fi

  # 2. 인라인 리뷰 스레드 변화 — 새 스레드 추가 또는 기존 스레드에 새 답글
  if [ "$threads" -gt "$B_THREADS" ] || [ "$replies" -gt "$B_REPLIES" ]; then
    echo "EVENT:NEW_REVIEW_COMMENT threads=$threads(was:$B_THREADS) replies=$replies(was:$B_REPLIES)"
    found=1
  fi

  # 3. CI 실패 또는 에러
  if [ "$failedCount" -gt 0 ]; then
    failedNames=$(GH_PAGER=cat gh pr view $PR_NUMBER --repo $REPO_FULL --json statusCheckRollup --jq '[(.statusCheckRollup // [])[] | select(.conclusion == "FAILURE" or .state == "FAILURE" or .conclusion == "ERROR" or .state == "ERROR") | .name] | join(",")' 2>/dev/null || echo "unknown")
    echo "EVENT:CI_FAILURE count=$failedCount names=$failedNames"
    found=1
  fi

  # 4. Merge conflict
  if [ "$mergeState" = "DIRTY" ]; then
    echo "EVENT:CONFLICT"
    found=1
  fi

  # 5. 리뷰 상태 변경 (APPROVED, CHANGES_REQUESTED 등)
  if [ "$reviewDecision" != "$B_REVIEW_DECISION" ] && [ -n "$B_REVIEW_DECISION" ]; then
    echo "EVENT:REVIEW_STATE_CHANGED from=$B_REVIEW_DECISION to=$reviewDecision"
    found=1
  fi
  B_REVIEW_DECISION=$reviewDecision

  # 6. Merge 가능 (checks pass + review approved)
  if [ "$mergeState" = "CLEAN" ] || [ "$mergeState" = "UNSTABLE" ]; then
    echo "EVENT:MERGEABLE mergeState=$mergeState reviewDecision=$reviewDecision"
    found=1
  fi

  # 하나라도 감지되면 state snapshot 출력 후 break
  if [ "$found" -eq 1 ]; then
    echo "STATE:COMMENT_COUNT=$comments"
    echo "STATE:REVIEW_COUNT=$reviews"
    echo "STATE:THREAD_COUNT=$threads"
    echo "STATE:THREAD_REPLY_COUNT=$replies"
    echo "STATE:REVIEW_DECISION=$reviewDecision"
    echo "STATE:MERGE_STATE=$mergeState"
    echo "STATE:POLL_START=$POLL_START"
    break
  fi

  sleep 5
done
```

## 이벤트 분기 처리

백그라운드 완료 알림을 받으면 출력을 읽고 **모든 `EVENT:` 라인을 파싱**한다. 복수의 이벤트가 동시에 존재할 수 있다.

### 출력 파싱 프로토콜

1. 출력에서 `EVENT:` 접두사가 있는 라인을 **모두** 추출한다.
2. `STATE:` 접두사가 있는 라인에서 다음 polling의 baseline 값을 추출 & 기록한다.
3. 아래 **우선순위 순서**대로 이벤트를 처리한다.

### 처리 우선순위

여러 이벤트가 동시에 감지되면 아래 우선순위에 따라 **순차적으로** 처리한다:

| 우선순위 | 이벤트 | 처리 |
|---------|--------|------|
| 0 | `PR_CLOSED` | PR이 외부에서 닫힘/병합됨. 사용자에게 알리고 모니터링 종료 |
| 1 | `CONFLICT` | merge conflict 해결 → push → 다음 이벤트로 |
| 2 | `CI_FAILURE` | CI 실패 감지 절차 실행 → 다음 이벤트로 |
| 3 | `NEW_COMMENT` 또는 `NEW_REVIEW_COMMENT` | 코멘트 감지 절차 실행 → 다음 이벤트로 |
| 4 | `REVIEW_STATE_CHANGED` | 사용자에게 상태 변경 알림 → 다음 이벤트로 |
| 5 | `MERGEABLE` | 다른 이벤트가 **없을 때만** Phase 7로 전환 |

> **MERGEABLE 주의**: MERGEABLE과 다른 이벤트(예: NEW_COMMENT + MERGEABLE)가 동시에 감지되면, 코멘트를 먼저 처리한 후 재평가한다. 코멘트 처리 후 상태가 변할 수 있으므로 MERGEABLE 단독일 때만 Phase 7로 전환한다.

### 이벤트 개별 처리

#### PR_CLOSED

PR이 외부에서 닫히거나 병합된 경우. 모니터링을 즉시 종료하고 사용자에게 알린다.

#### CONFLICT

1. `git fetch origin`으로 최신화한다.
2. merge conflict를 해결한다.
3. 커밋 & push 후 다음 이벤트 처리를 계속한다.

#### CI_FAILURE

1. `EVENT:CI_FAILURE count=N names=check1,check2` 라인에서 실패한 check 이름을 파악한다.
2. 로컬에서 해당 패키지의 검증을 재현한다:
   ```bash
   cd <package-dir>
   uv run ruff check .
   uv run pyrefly check
   uv run pytest
   ```
3. 로컬 통과 → "로컬 검증 통과, CI 인프라 문제 가능성" 보고 + 사용자 판단 요청.
4. 로컬 실패 → 원인 수정 + 커밋 & push 후 다음 이벤트 처리를 계속한다.

#### NEW_COMMENT / NEW_REVIEW_COMMENT

이 두 이벤트는 동일한 코멘트 감지 절차로 처리한다. 둘 다 감지된 경우 한 번만 실행한다.

1. **코멘트 수집** — 아래 3가지 채널을 **모두** 조회하여 미처리 코멘트를 수집한다.

   `$SINCE_TS`는 polling 출력의 `STATE:POLL_START` 값을 사용한다.

   `gh --jq`는 `--arg`를 지원하지 않으므로, `| jq --arg me "$MY_LOGIN"` 파이프를 사용한다.

   **채널 1: 인라인 리뷰 스레드** — 미해결 + SINCE 이후 활동
   ```bash
   GH_PAGER=cat gh api graphql -f query='{ repository(owner: "'"$OWNER"'", name: "'"$REPO"'") { pullRequest(number: '"$PR_NUMBER"') { reviewThreads(first: 100) { nodes { id isResolved comments(first: 10) { nodes { body author { login } path originalLine createdAt } } } } } } }' \
     --jq "[.data.repository.pullRequest.reviewThreads.nodes[] | select(.isResolved == false) | select(.comments.nodes[-1].createdAt > \"$SINCE_TS\")]"
   ```
   마지막 코멘트가 polling 시작 이후에 작성된 미해결 스레드만 반환한다.

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

2. **3채널 합산**: 채널 1·2·3의 미처리 코멘트 합산이 0보다 크면 `/review-pr` 스킬을 실행한다.

3. 트리아지 완료 후 코멘트를 남긴 리뷰어에게 재리뷰를 요청한다:
   ```bash
   GH_PAGER=cat gh pr edit $PR_NUMBER --repo $REPO_FULL --add-reviewer {REVIEWER_LOGIN}
   ```

#### REVIEW_STATE_CHANGED

사용자에게 리뷰 상태 변경을 알린다 (`from=X to=Y`). `APPROVED`로 변경된 경우 다른 이벤트가 없으면 Phase 7 고려.

#### MERGEABLE

**다른 이벤트가 동시에 없을 때만** Phase 7(PR 병합)로 전환한다.

## Polling 재시작 프로토콜

모든 이벤트 처리가 완료된 후 다음 순서로 재시작한다:

1. **Catch-up sweep 실행** — "미처리 코멘트 확인" 절차를 실행한다 (절대 건너뛰지 않는다).
2. **미처리 코멘트가 있으면** → 트리아지 실행 후 3번으로 돌아간다.
3. **미처리 코멘트가 없으면** → polling을 재시작한다.

### Baseline 복원

polling 스크립트의 baseline 변수를 **이전 polling 출력의 `STATE:` 값**으로 설정한다:

```
STATE:COMMENT_COUNT=6    → B_COMMENTS=6
STATE:REVIEW_COUNT=3     → B_REVIEWS=3
STATE:THREAD_COUNT=8     → B_THREADS=8
STATE:THREAD_REPLY_COUNT=15 → B_REPLIES=15
STATE:REVIEW_DECISION=CHANGES_REQUESTED → B_REVIEW_DECISION="CHANGES_REQUESTED"
```

> **주의**: catch-up sweep과 이벤트 처리 과정에서 코멘트/리뷰를 추가했다면 baseline 카운트가 변했을 수 있다. 의심스러우면 **API에서 재캡처**한다 (최초 실행과 동일).

### 종료 조건

아래 중 하나를 만족하면 polling을 종료한다:

- `EVENT:MERGEABLE`이 **단독으로** 감지된 경우 → Phase 7로 전환
- `EVENT:PR_CLOSED` 감지 → 모니터링 종료
- 사용자가 명시적으로 종료를 요청한 경우

$ARGUMENTS
